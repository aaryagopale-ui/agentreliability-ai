"""Transactional migration runner for SQLite.

Features:
- Versioned schema tracking in `schema_migrations` table
- Atomic transactions per migration
- Safe to run on fresh databases or existing Phase 1-4 databases
- PRAGMA foreign_keys = ON enforced
- Rollback support for recovery and testing
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Callable, List, Tuple

logger = logging.getLogger("agentreliability.migrations")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )"""
    )


def get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    init_migrations_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r[0] for r in rows}


def record_migration(conn: sqlite3.Connection, version: int, name: str) -> None:
    conn.execute(
        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
        (version, name, _now()),
    )


# -----------------------------------------------------------------------------
# Migration 001: Multi-tenant Security Schema & Project Ownership
# -----------------------------------------------------------------------------

def migration_001_up(conn: sqlite3.Connection) -> None:
    """Creates users, sessions, api_keys, password_resets, and adds project_id references."""
    # 1. Users table
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)")

    # 2. Projects table: ensure projects exists with clean owner_id schema
    old_projects = []
    proj_exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'").fetchone()
    if not proj_exists:
        conn.execute(
            """CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL
            )"""
        )
    else:
        proj_cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
        if "key_hash" in proj_cols:
            old_projects = conn.execute("SELECT id, name, key_hash, key_prefix, created_at FROM projects").fetchall()
            # Disable FK during table rebuild so references aren't prematurely dropped
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute(
                """CREATE TABLE projects_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL
                )"""
            )
            has_owner = "owner_id" in proj_cols
            if has_owner:
                conn.execute("INSERT INTO projects_v2 (id, name, owner_id, created_at) SELECT id, name, owner_id, created_at FROM projects")
            else:
                conn.execute("INSERT INTO projects_v2 (id, name, owner_id, created_at) SELECT id, name, NULL, created_at FROM projects")
            conn.execute("DROP TABLE projects")
            conn.execute("ALTER TABLE projects_v2 RENAME TO projects")
            conn.execute("PRAGMA foreign_keys = ON")
        elif "owner_id" not in proj_cols:
            conn.execute("ALTER TABLE projects ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects (owner_id)")

    # Ensure project id=1 exists as an unassigned container for historical/default records
    conn.execute(
        """INSERT OR IGNORE INTO projects (id, name, owner_id, created_at)
           VALUES (1, 'Default Project', NULL, ?)""",
        (_now(),)
    )

    # 3. Dedicated API Keys table
    conn.execute(
        """CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            key_prefix TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            revoked_at TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys (key_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_project ON api_keys (project_id)")

    # Migrate any historical project keys into api_keys
    for row in old_projects:
        pid, pname, khash, kprefix, pcreated = row[0], row[1], row[2], row[3], row[4]
        if khash:
            existing = conn.execute("SELECT id FROM api_keys WHERE key_hash = ?", (khash,)).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO api_keys (project_id, name, key_prefix, key_hash, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (pid, f"{pname} Default Key", kprefix or "ar_", khash, pcreated),
                )

    # 4. Sessions table (server-backed cryptographic sessions)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            user_agent TEXT,
            ip_address TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions (token_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions (expires_at)")

    # 5. Password Resets table
    conn.execute(
        """CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_password_resets_token ON password_resets (token_hash)")

    # 6. Executions table (Phase 1): add project_id column
    conn.execute(
        """CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            run_id TEXT,
            status TEXT NOT NULL,
            step_count INTEGER NOT NULL,
            failure_count INTEGER NOT NULL,
            steps_json TEXT NOT NULL,
            findings_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    exec_cols = {r[1] for r in conn.execute("PRAGMA table_info(executions)").fetchall()}
    if "project_id" not in exec_cols:
        conn.execute("ALTER TABLE executions ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE")
        conn.execute("UPDATE executions SET project_id = 1 WHERE project_id IS NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_executions_project ON executions (project_id)")

    # 7. Test cases & test runs (Phase 2): add project_id column
    conn.execute(
        """CREATE TABLE IF NOT EXISTS test_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            agent_name TEXT NOT NULL,
            source_execution_id INTEGER,
            input_json TEXT NOT NULL,
            steps_json TEXT NOT NULL,
            expected_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'uploaded_log',
            source_trace_id TEXT
        )"""
    )
    tc_cols = {r[1] for r in conn.execute("PRAGMA table_info(test_cases)").fetchall()}
    if "project_id" not in tc_cols:
        conn.execute("ALTER TABLE test_cases ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE")
        conn.execute("UPDATE test_cases SET project_id = 1 WHERE project_id IS NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_test_cases_project ON test_cases (project_id)")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS test_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_case_id INTEGER NOT NULL,
            test_name TEXT NOT NULL,
            status TEXT NOT NULL,
            mode TEXT NOT NULL,
            mismatches_json TEXT NOT NULL,
            observed_json TEXT NOT NULL,
            duration_ms REAL NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    tr_cols = {r[1] for r in conn.execute("PRAGMA table_info(test_runs)").fetchall()}
    if "project_id" not in tr_cols:
        conn.execute("ALTER TABLE test_runs ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE")
        conn.execute("UPDATE test_runs SET project_id = 1 WHERE project_id IS NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_project ON test_runs (project_id)")

    # 8. CI runs (Phase 4)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ci_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            commit_sha TEXT NOT NULL,
            branch TEXT NOT NULL,
            actor TEXT NOT NULL,
            status TEXT NOT NULL,
            total INTEGER NOT NULL,
            passed INTEGER NOT NULL,
            failed INTEGER NOT NULL,
            duration_ms REAL NOT NULL,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ci_project ON ci_runs (project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ci_created ON ci_runs (created_at)")


def migration_001_down(conn: sqlite3.Connection) -> None:
    """Rollback migration 001 for test and rollback verification."""
    conn.execute("DROP TABLE IF EXISTS password_resets")
    conn.execute("DROP TABLE IF EXISTS sessions")
    conn.execute("DROP TABLE IF EXISTS api_keys")
    conn.execute("DROP TABLE IF EXISTS users")
    conn.execute("DELETE FROM schema_migrations WHERE version = 1")


def migration_002_up(conn: sqlite3.Connection) -> None:
    """Adds archived_at and updated_at to projects for safe soft-deletion, and ensures trace tables exist."""
    proj_cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if "archived_at" not in proj_cols:
        conn.execute("ALTER TABLE projects ADD COLUMN archived_at TEXT")
    if "updated_at" not in proj_cols:
        conn.execute("ALTER TABLE projects ADD COLUMN updated_at TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_archived ON projects (archived_at)")

    # Ensure trace storage tables exist
    conn.execute(
        """CREATE TABLE IF NOT EXISTS trace_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            event_id TEXT NOT NULL,
            execution_id TEXT NOT NULL,
            type TEXT NOT NULL,
            received_at TEXT NOT NULL,
            UNIQUE (project_id, event_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS trace_executions (
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            execution_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL,
            failure_kind TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_ms REAL,
            input_json TEXT,
            output_json TEXT,
            error_type TEXT,
            error_message TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (project_id, execution_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS trace_tool_calls (
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            call_id TEXT NOT NULL,
            execution_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            duration_ms REAL,
            status TEXT NOT NULL,
            input_json TEXT,
            output_json TEXT,
            error_type TEXT,
            error_message TEXT,
            PRIMARY KEY (project_id, call_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_exec_started ON trace_executions (started_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_exec_agent ON trace_executions (agent_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_tool_exec ON trace_tool_calls (execution_id)")


def migration_002_down(conn: sqlite3.Connection) -> None:
    """Rollback migration 002."""
    conn.execute("DROP INDEX IF EXISTS idx_projects_archived")
    conn.execute("DELETE FROM schema_migrations WHERE version = 2")


# -----------------------------------------------------------------------------
# Migration 003: Trace Tool Calls Nesting and Retries Support
# -----------------------------------------------------------------------------

def migration_003_up(conn: sqlite3.Connection) -> None:
    """Adds parent_call_id and retry_count to trace_tool_calls for visual timeline and waterfall."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(trace_tool_calls)").fetchall()}
    if "parent_call_id" not in cols:
        conn.execute("ALTER TABLE trace_tool_calls ADD COLUMN parent_call_id TEXT")
    if "retry_count" not in cols:
        conn.execute("ALTER TABLE trace_tool_calls ADD COLUMN retry_count INTEGER DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_tool_parent ON trace_tool_calls (parent_call_id)")


def migration_003_down(conn: sqlite3.Connection) -> None:
    """Rollback migration 003."""
    conn.execute("DROP INDEX IF EXISTS idx_trace_tool_parent")
    conn.execute("DELETE FROM schema_migrations WHERE version = 3")


# -----------------------------------------------------------------------------
# Migration 004: Regression Baselines and Versioning
# -----------------------------------------------------------------------------

def migration_004_up(conn: sqlite3.Connection) -> None:
    """Creates baselines and baseline_versions tables for regression testing."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS baselines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            agent_name TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            current_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS baseline_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            baseline_id INTEGER NOT NULL REFERENCES baselines(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            status TEXT NOT NULL,
            duration_ms REAL,
            input_json TEXT,
            output_json TEXT,
            tools_json TEXT NOT NULL,
            expected_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            UNIQUE(baseline_id, version)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_baselines_project ON baselines (project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_baseline_versions_baseline ON baseline_versions (baseline_id)")


def migration_004_down(conn: sqlite3.Connection) -> None:
    """Rollback migration 004."""
    conn.execute("DROP TABLE IF EXISTS baseline_versions")
    conn.execute("DROP TABLE IF EXISTS baselines")
    conn.execute("DELETE FROM schema_migrations WHERE version = 4")


# List of registered migrations: (version, name, up_fn, down_fn)
MIGRATIONS: List[Tuple[int, str, Callable[[sqlite3.Connection], None], Callable[[sqlite3.Connection], None]]] = [
    (1, "001_security_schema", migration_001_up, migration_001_down),
    (2, "002_project_archival", migration_002_up, migration_002_down),
    (3, "003_trace_tool_calls_nesting_and_retries", migration_003_up, migration_003_down),
    (4, "004_regression_baselines", migration_004_up, migration_004_down),
]


def run_migrations(conn: sqlite3.Connection) -> List[int]:
    """Execute all pending migrations transactionally. Returns list of applied version numbers."""
    conn.execute("PRAGMA foreign_keys = ON")
    applied = get_applied_versions(conn)
    newly_applied = []

    for version, name, up_fn, _ in MIGRATIONS:
        if version not in applied:
            logger.info("Applying migration %03d: %s...", version, name)
            with conn:
                up_fn(conn)
                record_migration(conn, version, name)
            newly_applied.append(version)
            logger.info("Migration %03d applied successfully.", version)

    return newly_applied


def rollback_migration(conn: sqlite3.Connection, target_version: int) -> bool:
    """Rollback a specific migration version."""
    conn.execute("PRAGMA foreign_keys = ON")
    for version, name, _, down_fn in reversed(MIGRATIONS):
        if version == target_version:
            logger.info("Rolling back migration %03d: %s...", version, name)
            with conn:
                down_fn(conn)
            logger.info("Migration %03d rolled back successfully.", version)
            return True
    return False
