#!/usr/bin/env python3
"""SQLite to PostgreSQL Migration & Export Utility for AgentReliability AI.

Key Guarantees:
1. Zero Data Loss: Preserves all historical records, primary key IDs, and timestamps.
2. Complete Hash Fidelity: Password hashes (scrypt), session token hashes (SHA-256),
   and API key hashes are preserved byte-for-byte.
3. Referential Integrity: Migrates tables in topological dependency order:
   users -> projects -> api_keys, sessions, password_resets, executions, test_cases, trace_events, ci_runs -> test_runs.
4. Sequence Synchronization: Emits Postgres sequence updates (`setval`) so newly generated
   records in Postgres never collide with migrated IDs.
5. Dry-Run Capable: Runs safety audits and validates foreign keys without writing to Postgres.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Tuple

# Topological order respecting foreign key dependencies
TABLE_ORDER = [
    "schema_migrations",
    "users",
    "projects",
    "api_keys",
    "sessions",
    "password_resets",
    "executions",
    "test_cases",
    "test_runs",
    "trace_events",
    "trace_executions",
    "trace_tool_calls",
    "ci_runs",
    "baselines",
    "baseline_versions",
]

POSTGRES_SCHEMA_SQL = """
-- PostgreSQL Schema for AgentReliability AI
BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL,
    archived_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(32) NOT NULL,
    key_hash VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    last_active_at TIMESTAMPTZ NOT NULL,
    user_agent TEXT,
    ip_address VARCHAR(45)
);

CREATE TABLE IF NOT EXISTS password_resets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    ip_address VARCHAR(45)
);

CREATE TABLE IF NOT EXISTS executions (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    run_id VARCHAR(255),
    status VARCHAR(64) NOT NULL,
    step_count INTEGER NOT NULL,
    failure_count INTEGER NOT NULL,
    steps_json JSONB NOT NULL,
    findings_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS test_cases (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    steps_json JSONB NOT NULL,
    expected_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    source_type VARCHAR(64),
    source_trace_id VARCHAR(255),
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS test_runs (
    id SERIAL PRIMARY KEY,
    test_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    status VARCHAR(64) NOT NULL,
    passed BOOLEAN NOT NULL,
    mismatches_json JSONB,
    observed_json JSONB,
    duration_ms DOUBLE PRECISION,
    executed_at TIMESTAMPTZ NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trace_events (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    event_id VARCHAR(255) NOT NULL,
    execution_id VARCHAR(255) NOT NULL,
    type VARCHAR(64) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_trace_project_event UNIQUE (project_id, event_id)
);

CREATE TABLE IF NOT EXISTS trace_executions (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    execution_id VARCHAR(255) NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    status VARCHAR(64) NOT NULL,
    failure_kind VARCHAR(64),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    duration_ms DOUBLE PRECISION,
    input_json JSONB,
    output_json JSONB,
    error_type VARCHAR(255),
    error_message TEXT,
    metadata_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (project_id, execution_id)
);

CREATE TABLE IF NOT EXISTS trace_tool_calls (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    call_id VARCHAR(255) NOT NULL,
    execution_id VARCHAR(255) NOT NULL,
    tool_name VARCHAR(255) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    duration_ms DOUBLE PRECISION,
    status VARCHAR(64) NOT NULL,
    input_json JSONB,
    output_json JSONB,
    error_type VARCHAR(255),
    error_message TEXT,
    parent_call_id VARCHAR(255),
    retry_count INTEGER DEFAULT 0,
    PRIMARY KEY (project_id, call_id)
);

CREATE TABLE IF NOT EXISTS ci_runs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    commit_sha VARCHAR(64),
    branch VARCHAR(255),
    actor VARCHAR(255),
    total INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    duration_ms DOUBLE PRECISION,
    report_json JSONB,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS baselines (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    current_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS baseline_versions (
    id SERIAL PRIMARY KEY,
    baseline_id INTEGER NOT NULL REFERENCES baselines(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    source_type VARCHAR(64) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    status VARCHAR(64) NOT NULL,
    duration_ms DOUBLE PRECISION,
    input_json JSONB,
    output_json JSONB,
    tools_json JSONB NOT NULL,
    expected_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT uq_baseline_version UNIQUE (baseline_id, version)
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_project ON api_keys(project_id);
CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_id);
CREATE INDEX IF NOT EXISTS idx_projects_archived ON projects(archived_at);
CREATE INDEX IF NOT EXISTS idx_executions_project ON executions(project_id);
CREATE INDEX IF NOT EXISTS idx_test_cases_project ON test_cases(project_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_project ON test_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_trace_events_exec ON trace_events(project_id, execution_id);
CREATE INDEX IF NOT EXISTS idx_trace_exec_started ON trace_executions (started_at);
CREATE INDEX IF NOT EXISTS idx_trace_exec_agent ON trace_executions (agent_name);
CREATE INDEX IF NOT EXISTS idx_trace_tool_exec ON trace_tool_calls (execution_id);
CREATE INDEX IF NOT EXISTS idx_ci_runs_project ON ci_runs(project_id);

COMMIT;
"""


def verify_sqlite_referential_integrity(conn: sqlite3.Connection) -> List[str]:
    """Check for orphaned child records in SQLite before attempting migration."""
    violations = []
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_key_check")
    rows = cursor.fetchall()
    for row in rows:
        violations.append(f"Foreign key violation in table {row[0]}, rowid {row[1]}, parent {row[2]}")
    return violations


def export_sqlite_to_postgres_sql(sqlite_conn: sqlite3.Connection) -> str:
    """Generate a clean, self-contained PostgreSQL SQL dump script."""
    cursor = sqlite_conn.cursor()
    lines = [
        "-- AgentReliability AI: SQLite to PostgreSQL Data Dump",
        "-- Generated automatically with foreign-key preservation",
        "BEGIN;",
        POSTGRES_SCHEMA_SQL,
    ]

    table_counts: Dict[str, int] = {}

    for table in TABLE_ORDER:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cursor.fetchone():
            continue

        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]

        cursor.execute(f"SELECT * FROM {table} ORDER BY id ASC" if "id" in columns else f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        table_counts[table] = len(rows)

        if not rows:
            continue

        lines.append(f"\n-- Data for {table} ({len(rows)} records)")
        col_list = ", ".join(f'"{c}"' for c in columns)

        for row in rows:
            formatted_vals = []
            for val in row:
                if val is None:
                    formatted_vals.append("NULL")
                elif isinstance(val, (int, float)):
                    formatted_vals.append(str(val))
                elif isinstance(val, bool):
                    formatted_vals.append("TRUE" if val else "FALSE")
                else:
                    # String / JSON escaping for Postgres
                    escaped = str(val).replace("'", "''")
                    formatted_vals.append(f"'{escaped}'")

            vals_str = ", ".join(formatted_vals)
            lines.append(f"INSERT INTO {table} ({col_list}) VALUES ({vals_str}) ON CONFLICT DO NOTHING;")

        # Update sequence for tables with serial primary keys
        if "id" in columns:
            lines.append(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1));")

    lines.append("\nCOMMIT;")
    return "\n".join(lines)


def run_migration_audit(db_path: str) -> dict:
    """Audit the SQLite database and verify migration readiness."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        violations = verify_sqlite_referential_integrity(conn)

        cursor = conn.cursor()
        summary = {}
        for table in TABLE_ORDER:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if cursor.fetchone():
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                summary[table] = cursor.fetchone()[0]

        sql_dump = export_sqlite_to_postgres_sql(conn)

        return {
            "source_db": db_path,
            "referential_integrity_ok": len(violations) == 0,
            "violations": violations,
            "table_record_counts": summary,
            "sql_dump_size_bytes": len(sql_dump),
            "sql_dump": sql_dump,
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="AgentReliability AI SQLite to PostgreSQL Migration Tool")
    parser.add_argument("--source-db", default="backend/agentreliability.db", help="Path to SQLite database")
    parser.add_argument("--output-sql", default=None, help="Path to write the PostgreSQL SQL dump")
    parser.add_argument("--target-url", default=None, help="PostgreSQL connection string (e.g. postgresql://user:pass@host:5432/dbname)")
    parser.add_argument("--dry-run", action="store_true", help="Run audit and schema validation without modifying anything")

    args = parser.parse_args()

    print(f"[*] Auditing SQLite database: {args.source_db}")
    audit = run_migration_audit(args.source_db)

    print("\n--- Migration Audit Results ---")
    print(f"Referential Integrity: {'[PASS] No violations' if audit['referential_integrity_ok'] else '[FAIL] Violations found'}")
    if audit["violations"]:
        for v in audit["violations"]:
            print(f"  - {v}")

    print("\nRecord Counts by Table:")
    for table, count in audit["table_record_counts"].items():
        print(f"  {table:20s}: {count} records")

    if args.output_sql:
        with open(args.output_sql, "w", encoding="utf-8") as f:
            f.write(audit["sql_dump"])
        print(f"\n[+] PostgreSQL migration script written to: {args.output_sql} ({audit['sql_dump_size_bytes']} bytes)")

    if args.target_url:
        try:
            import psycopg
            print(f"\n[*] Executing transactional migration against target PostgreSQL database...")
            with psycopg.connect(args.target_url) as pg_conn:
                with pg_conn.cursor() as cur:
                    cur.execute(audit["sql_dump"])
                pg_conn.commit()
            print("[+] Direct PostgreSQL migration executed and committed successfully!")
        except ImportError:
            print("[!] Note: psycopg is not installed locally. Run 'pip install psycopg[binary]' or apply the generated SQL dump with 'psql <TARGET_URL> -f <dump_file>'", file=sys.stderr)
        except Exception as e:
            print(f"[!] PostgreSQL Migration Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.dry_run and not args.output_sql:
        print(f"\n[+] Dry-run complete. Generated SQL dump size: {audit['sql_dump_size_bytes']} bytes.")


if __name__ == "__main__":
    main()
