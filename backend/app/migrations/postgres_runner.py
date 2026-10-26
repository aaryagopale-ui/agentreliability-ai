"""PostgreSQL Transactional Migration Runner for AgentReliability AI.

Provides version-tracked schema migrations on PostgreSQL (e.g. Neon Free Tier).
Maintains strict schema parity with SQLite migrations.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Set

logger = logging.getLogger("agentreliability.migrations.postgres")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_postgres_migrations_table(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL
        )"""
    )


def get_applied_postgres_versions(conn) -> Set[int]:
    init_postgres_migrations_table(conn)
    cur = conn.execute("SELECT version FROM schema_migrations")
    rows = cur.fetchall()
    return {r[0] for r in rows}


def record_postgres_migration(conn, version: int, name: str) -> None:
    conn.execute(
        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (%s, %s, %s)",
        (version, name, _now()),
    )


# -----------------------------------------------------------------------------
# Migration 001: Multi-tenant Security Schema & Project Ownership
# -----------------------------------------------------------------------------

def migration_001_up(conn) -> None:
    """Creates users, projects, api_keys, sessions, password_resets, executions, test_cases, test_runs."""
    # 1. Users
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")

    # 2. Projects
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL,
            archived_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_id)")

    # 3. API Keys
    conn.execute(
        """CREATE TABLE IF NOT EXISTS api_keys (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            key_prefix VARCHAR(32) NOT NULL,
            key_hash VARCHAR(64) UNIQUE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            last_used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_project ON api_keys(project_id)")

    # 4. Sessions
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) UNIQUE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            user_agent TEXT,
            ip_address VARCHAR(45)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")

    # 5. Password Resets
    conn.execute(
        """CREATE TABLE IF NOT EXISTS password_resets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) UNIQUE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            ip_address VARCHAR(45)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_password_resets_hash ON password_resets(token_hash)")

    # 6. Executions
    conn.execute(
        """CREATE TABLE IF NOT EXISTS executions (
            id SERIAL PRIMARY KEY,
            agent_name VARCHAR(255) NOT NULL,
            run_id VARCHAR(255),
            status VARCHAR(64) NOT NULL,
            step_count INTEGER NOT NULL,
            failure_count INTEGER NOT NULL,
            steps_json TEXT NOT NULL,
            findings_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_executions_project ON executions(project_id)")

    # 7. Test Cases
    conn.execute(
        """CREATE TABLE IF NOT EXISTS test_cases (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            agent_name VARCHAR(255) NOT NULL,
            source_execution_id INTEGER REFERENCES executions(id) ON DELETE SET NULL,
            input_json TEXT NOT NULL,
            steps_json TEXT NOT NULL,
            expected_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            source_type VARCHAR(64) NOT NULL,
            source_trace_id VARCHAR(255),
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_test_cases_project ON test_cases(project_id)")

    # 8. Test Runs
    conn.execute(
        """CREATE TABLE IF NOT EXISTS test_runs (
            id SERIAL PRIMARY KEY,
            test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
            test_name VARCHAR(255) NOT NULL,
            status VARCHAR(64) NOT NULL,
            mode VARCHAR(64) NOT NULL,
            mismatches_json TEXT NOT NULL,
            observed_json TEXT NOT NULL,
            duration_ms DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_case ON test_runs(test_case_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_project ON test_runs(project_id)")


# -----------------------------------------------------------------------------
# Migration 002: Golden Baselines & Baseline Versions
# -----------------------------------------------------------------------------

def migration_002_up(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS baselines (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            agent_name VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            current_version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_baselines_project ON baselines(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_baselines_agent ON baselines(project_id, agent_name)")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS baseline_versions (
            id SERIAL PRIMARY KEY,
            baseline_id INTEGER NOT NULL REFERENCES baselines(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            source_type VARCHAR(64) NOT NULL,
            source_id VARCHAR(255) NOT NULL,
            status VARCHAR(64) NOT NULL,
            duration_ms DOUBLE PRECISION,
            input_json TEXT,
            output_json TEXT,
            tools_json TEXT NOT NULL,
            expected_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT uq_baseline_version UNIQUE (baseline_id, version)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_baseline_versions_baseline ON baseline_versions(baseline_id)")


# -----------------------------------------------------------------------------
# Migration 003: CI Runs
# -----------------------------------------------------------------------------

def migration_003_up(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ci_runs (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            commit_sha VARCHAR(64) NOT NULL,
            branch VARCHAR(255) NOT NULL,
            actor VARCHAR(255) NOT NULL,
            status VARCHAR(64) NOT NULL,
            total INTEGER NOT NULL,
            passed INTEGER NOT NULL,
            failed INTEGER NOT NULL,
            duration_ms DOUBLE PRECISION NOT NULL,
            report_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ci_runs_project ON ci_runs(project_id)")


# -----------------------------------------------------------------------------
# Migration 004: Trace Events & Executions
# -----------------------------------------------------------------------------

def migration_004_up(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS trace_events (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            event_id VARCHAR(255) NOT NULL,
            execution_id VARCHAR(255) NOT NULL,
            type VARCHAR(64) NOT NULL,
            received_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_trace_project_event UNIQUE (project_id, event_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_events_exec ON trace_events(project_id, execution_id)")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS trace_executions (
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            execution_id VARCHAR(255) NOT NULL,
            agent_name VARCHAR(255) NOT NULL,
            status VARCHAR(64) NOT NULL,
            failure_kind VARCHAR(64),
            started_at TIMESTAMPTZ NOT NULL,
            ended_at TIMESTAMPTZ,
            duration_ms DOUBLE PRECISION,
            input_json TEXT,
            output_json TEXT,
            error_type VARCHAR(255),
            error_message TEXT,
            metadata_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (project_id, execution_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_exec_started ON trace_executions(started_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_exec_agent ON trace_executions(agent_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_exec_proj_started ON trace_executions(project_id, started_at)")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS trace_tool_calls (
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            call_id VARCHAR(255) NOT NULL,
            execution_id VARCHAR(255) NOT NULL,
            tool_name VARCHAR(255) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            duration_ms DOUBLE PRECISION,
            status VARCHAR(64) NOT NULL,
            input_json TEXT,
            output_json TEXT,
            error_type VARCHAR(255),
            error_message TEXT,
            parent_call_id VARCHAR(255),
            retry_count INTEGER DEFAULT 0,
            PRIMARY KEY (project_id, call_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_tool_exec ON trace_tool_calls(execution_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_tool_proj_exec ON trace_tool_calls(project_id, execution_id)")


POSTGRES_MIGRATIONS = [
    (1, "001_multi_tenant_schema", migration_001_up),
    (2, "002_baselines_schema", migration_002_up),
    (3, "003_ci_runs_schema", migration_003_up),
    (4, "004_traces_schema", migration_004_up),
]


def run_postgres_migrations(conn) -> int:
    """Run all pending PostgreSQL migrations sequentially in topological order. Returns count applied."""
    applied = get_applied_postgres_versions(conn)
    applied_count = 0
    for version, name, func in POSTGRES_MIGRATIONS:
        if version not in applied:
            logger.info("Applying PostgreSQL migration %03d: %s", version, name)
            func(conn)
            record_postgres_migration(conn, version, name)
            applied_count += 1
    return applied_count

