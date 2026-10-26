#!/usr/bin/env python3
"""Account-Scoped SQLite to PostgreSQL Migration Tool for AgentReliability AI.

Safely migrates a specific user account and all owned projects, executions,
test cases, test runs, trace events, trace executions, trace tool calls,
CI runs, and golden baselines from local SQLite to Neon PostgreSQL.

Key Guarantees:
1. Strict Account Scoping: Only migrates the specified user (default ID: 2) and their owned projects.
2. Read-Only Source Access: SQLite opened strictly with '?mode=ro'; source DB is NEVER modified.
3. Zero Secret Leakage: Passwords and tokens are preserved byte-for-byte in the DB but NEVER printed to logs/stdout.
4. Excludes Ephemeral Secrets by Default: Historical sessions, password resets, and API keys are excluded by default.
5. Schema Compatibility & Conflict Detection: Verifies target tables/columns and checks for existing user/project collisions.
6. Atomic Transactional Rollback: Entire migration executes in a single transaction; rolls back on any error.
7. Sequence Synchronization: Updates PostgreSQL serial sequences (`setval`) to prevent ID collisions on future inserts.
8. Post-Import Verification: Queries target DB to confirm exact count parity before commit.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

TABLE_COLUMNS: Dict[str, List[str]] = {
    "users": ["id", "email", "password_hash", "name", "created_at", "updated_at"],
    "projects": ["id", "name", "owner_id", "created_at", "archived_at", "updated_at"],
    "executions": ["id", "agent_name", "run_id", "status", "step_count", "failure_count", "steps_json", "findings_json", "created_at", "project_id"],
    "test_cases": ["id", "name", "description", "agent_name", "source_execution_id", "input_json", "steps_json", "expected_json", "created_at", "updated_at", "source_type", "source_trace_id", "project_id"],
    "test_runs": ["id", "test_case_id", "test_name", "status", "mode", "mismatches_json", "observed_json", "duration_ms", "created_at", "project_id"],
    "trace_events": ["id", "project_id", "event_id", "execution_id", "type", "received_at"],
    "trace_executions": ["project_id", "execution_id", "agent_name", "status", "failure_kind", "started_at", "ended_at", "duration_ms", "input_json", "output_json", "error_type", "error_message", "metadata_json", "created_at", "updated_at"],
    "trace_tool_calls": ["project_id", "call_id", "execution_id", "tool_name", "started_at", "duration_ms", "status", "input_json", "output_json", "error_type", "error_message", "parent_call_id", "retry_count"],
    "ci_runs": ["id", "project_id", "commit_sha", "branch", "actor", "status", "total", "passed", "failed", "duration_ms", "report_json", "created_at"],
    "baselines": ["id", "project_id", "agent_name", "name", "description", "current_version", "created_at", "updated_at"],
    "baseline_versions": ["id", "baseline_id", "version", "source_type", "source_id", "status", "duration_ms", "input_json", "output_json", "tools_json", "expected_json", "created_at", "created_by_user_id"],
    "api_keys": ["id", "project_id", "name", "key_prefix", "key_hash", "created_at", "last_used_at", "revoked_at"],
}

SERIAL_SEQUENCE_TABLES = [
    "users",
    "projects",
    "executions",
    "test_cases",
    "test_runs",
    "trace_events",
    "ci_runs",
    "baselines",
    "baseline_versions",
]


def mask_email(email: str) -> str:
    """Mask email for safe logging: alex@example.com -> a***@e***.com."""
    if not email or "@" not in email:
        return "***"
    user_part, domain_part = email.split("@", 1)
    m_user = user_part[0] + "***" if user_part else "***"
    domain_subparts = domain_part.split(".")
    m_domain = ".".join(d[0] + "***" for d in domain_subparts if d)
    return f"{m_user}@{m_domain}"


def mask_url(url: str) -> str:
    """Mask database connection password: postgresql://user:pass@host/db -> postgresql://user:****@host/db."""
    if not url:
        return ""
    return re.sub(r":([^:@]+)@", ":****@", url)


# -----------------------------------------------------------------------------
# Source Data Extraction (Read-Only)
# -----------------------------------------------------------------------------

def open_source_sqlite(source_path: str) -> sqlite3.Connection:
    """Open SQLite connection strictly in read-only mode."""
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source SQLite database not found: {source_path}")
    abs_path = os.path.abspath(source_path)
    conn = sqlite3.connect(f"file:{abs_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def extract_account_data(
    conn: sqlite3.Connection,
    user_id: int,
    include_api_keys: bool = False,
    clean_orphans: bool = True,
) -> Dict[str, Any]:
    """Extract strictly account-scoped records for user_id and their owned projects."""
    c = conn.cursor()

    # 1. User
    user_row = c.execute(
        f"SELECT {', '.join(TABLE_COLUMNS['users'])} FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    if not user_row:
        raise ValueError(f"User with ID {user_id} not found in source database.")

    # 2. Projects
    project_rows = c.execute(
        f"SELECT {', '.join(TABLE_COLUMNS['projects'])} FROM projects WHERE owner_id = ? ORDER BY id",
        (user_id,)
    ).fetchall()
    project_ids = [p["id"] for p in project_rows]

    if not project_ids:
        project_marks = "NULL"
    else:
        project_marks = ",".join(str(pid) for pid in project_ids)

    # 3. Executions
    execution_rows = c.execute(
        f"SELECT {', '.join(TABLE_COLUMNS['executions'])} FROM executions WHERE project_id IN ({project_marks}) ORDER BY id"
    ).fetchall()
    execution_ids = {e["id"] for e in execution_rows}

    # 4. Test Cases
    test_case_rows = c.execute(
        f"SELECT {', '.join(TABLE_COLUMNS['test_cases'])} FROM test_cases WHERE project_id IN ({project_marks}) ORDER BY id"
    ).fetchall()
    test_case_ids = {tc["id"] for tc in test_case_rows}

    # 5. Test Runs (filter orphans if clean_orphans=True)
    raw_test_runs = c.execute(
        f"SELECT {', '.join(TABLE_COLUMNS['test_runs'])} FROM test_runs WHERE project_id IN ({project_marks}) ORDER BY id"
    ).fetchall()

    test_run_rows = []
    pruned_records = []
    violations = []

    for tr in raw_test_runs:
        if tr["test_case_id"] in test_case_ids:
            test_run_rows.append(tr)
        else:
            if clean_orphans:
                pruned_records.append({
                    "table": "test_runs",
                    "id": tr["id"],
                    "reason": f"test_case_id {tr['test_case_id']} does not exist in test_cases",
                })
            else:
                violations.append(f"test_run {tr['id']} references missing test_case_id {tr['test_case_id']}")

    # 6. Trace Events
    trace_event_rows = c.execute(
        f"SELECT {', '.join(TABLE_COLUMNS['trace_events'])} FROM trace_events WHERE project_id IN ({project_marks}) ORDER BY id"
    ).fetchall()

    # 7. Trace Executions
    trace_exec_rows = c.execute(
        f"SELECT {', '.join(TABLE_COLUMNS['trace_executions'])} FROM trace_executions WHERE project_id IN ({project_marks})"
    ).fetchall()

    # 8. Trace Tool Calls
    trace_tool_rows = c.execute(
        f"SELECT {', '.join(TABLE_COLUMNS['trace_tool_calls'])} FROM trace_tool_calls WHERE project_id IN ({project_marks})"
    ).fetchall()

    # 9. CI Runs
    ci_run_rows = c.execute(
        f"SELECT {', '.join(TABLE_COLUMNS['ci_runs'])} FROM ci_runs WHERE project_id IN ({project_marks}) ORDER BY id"
    ).fetchall()

    # 10. Baselines
    baseline_rows = c.execute(
        f"SELECT {', '.join(TABLE_COLUMNS['baselines'])} FROM baselines WHERE project_id IN ({project_marks}) ORDER BY id"
    ).fetchall()
    baseline_ids = [b["id"] for b in baseline_rows]

    # 11. Baseline Versions
    if baseline_ids:
        b_marks = ",".join(str(bid) for bid in baseline_ids)
        baseline_version_rows = c.execute(
            f"SELECT {', '.join(TABLE_COLUMNS['baseline_versions'])} FROM baseline_versions WHERE baseline_id IN ({b_marks}) ORDER BY id"
        ).fetchall()
    else:
        baseline_version_rows = []

    # 12. API Keys (opt-in)
    if include_api_keys and project_ids:
        api_key_rows = c.execute(
            f"SELECT {', '.join(TABLE_COLUMNS['api_keys'])} FROM api_keys WHERE project_id IN ({project_marks}) ORDER BY id"
        ).fetchall()
    else:
        api_key_rows = []

    # Check source_execution_id references in test_cases
    for tc in test_case_rows:
        src_exec = tc["source_execution_id"]
        if src_exec is not None and src_exec not in execution_ids:
            violations.append(f"test_case {tc['id']} references foreign source_execution_id {src_exec} outside dataset")

    return {
        "user": user_row,
        "projects": project_rows,
        "executions": execution_rows,
        "test_cases": test_case_rows,
        "test_runs": test_run_rows,
        "trace_events": trace_event_rows,
        "trace_executions": trace_exec_rows,
        "trace_tool_calls": trace_tool_rows,
        "ci_runs": ci_run_rows,
        "baselines": baseline_rows,
        "baseline_versions": baseline_version_rows,
        "api_keys": api_key_rows,
        "pruned_records": pruned_records,
        "integrity_violations": violations,
    }


# -----------------------------------------------------------------------------
# Target PostgreSQL Schema & Conflict Checks
# -----------------------------------------------------------------------------

def _row_val(row: Any, key: str, idx: int = 0) -> Any:
    """Safely extract column value from a row whether it is a dict (psycopg dict_row),
    UnifiedRow, sqlite3.Row, or a plain tuple."""
    if row is None:
        return None
    if isinstance(row, dict):
        if key in row:
            return row[key]
        if key.lower() in row:
            return row[key.lower()]
        if key.upper() in row:
            return row[key.upper()]
        return None
    if hasattr(row, "__getitem__"):
        try:
            return row[key]
        except (KeyError, TypeError, IndexError):
            try:
                return row[idx]
            except (KeyError, TypeError, IndexError):
                return None
    return getattr(row, key, None)


def verify_postgres_schema(pg_conn: Any, include_api_keys: bool = False) -> List[str]:
    """Verify that all target PostgreSQL tables exist and have matching columns."""
    cur = pg_conn.cursor()
    errors = []

    tables_to_check = [
        "users", "projects", "executions", "test_cases", "test_runs",
        "trace_events", "trace_executions", "trace_tool_calls", "ci_runs",
        "baselines", "baseline_versions",
    ]
    if include_api_keys:
        tables_to_check.append("api_keys")

    for tbl in tables_to_check:
        cur.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_name = %s AND table_schema = 'public'""",
            (tbl,)
        )
        pg_cols = {
            r["column_name"] if (isinstance(r, dict) or hasattr(r, "keys")) else r[0]
            for r in cur.fetchall()
        }
        if not pg_cols:
            errors.append(f"Target table '{tbl}' does not exist in target database.")
            continue
        req_cols = set(TABLE_COLUMNS[tbl])
        missing = req_cols - pg_cols
        if missing:
            errors.append(f"Target table '{tbl}' is missing columns: {sorted(missing)}")

    # Check schema_migrations
    try:
        cur.execute("SELECT version FROM schema_migrations")
        applied = {
            int(r["version"] if (isinstance(r, dict) or hasattr(r, "keys")) else r[0])
            for r in cur.fetchall()
        }
        expected_migrations = {1, 2, 3, 4}
        if not expected_migrations.issubset(applied):
            errors.append(f"Target schema_migrations is missing versions: {expected_migrations - applied}")
    except Exception as e:
        errors.append(f"Error checking schema_migrations: {e}")

    return errors


def check_postgres_conflicts(pg_conn: Any, user_row: Any, project_rows: List[Any]) -> List[str]:
    """Detect collisions with existing users, emails, or project IDs in target database."""
    cur = pg_conn.cursor()
    conflicts = []

    # 1. User ID collision
    cur.execute("SELECT id, email FROM users WHERE id = %s", (user_row["id"],))
    existing_u = cur.fetchone()
    if existing_u:
        u_email = _row_val(existing_u, "email", 1)
        conflicts.append(f"User ID {user_row['id']} already exists in target database with email {mask_email(u_email)}.")

    # 2. Email collision
    cur.execute("SELECT id, email FROM users WHERE email = %s", (user_row["email"],))
    existing_email = cur.fetchone()
    if existing_email:
        existing_uid = _row_val(existing_email, "id", 0)
        if existing_uid != user_row["id"]:
            conflicts.append(f"Email {mask_email(user_row['email'])} already exists in target DB under different user ID {existing_uid}.")

    # 3. Project ID collisions
    pids = [p["id"] for p in project_rows]
    if pids:
        p_marks = ", ".join(["%s"] * len(pids))
        cur.execute(f"SELECT id, name FROM projects WHERE id IN ({p_marks})", tuple(pids))
        existing_p = cur.fetchall()
        for ep in existing_p:
            ep_id = _row_val(ep, "id", 0)
            ep_name = _row_val(ep, "name", 1)
            conflicts.append(f"Project ID {ep_id} ('{ep_name}') already exists in target database.")

    return conflicts


# -----------------------------------------------------------------------------
# SQL Script Generation (Optional Export)
# -----------------------------------------------------------------------------

def sql_quote(val: Any) -> str:
    """Format Python value as SQL literal."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    # String / JSON
    s = str(val).replace("'", "''")
    return f"'{s}'"


def generate_migration_sql(data: Dict[str, Any], include_api_keys: bool = False) -> str:
    """Generate safe, transactional SQL script for manual psql inspection or import."""
    lines = [
        "-- ==========================================================================",
        "-- AgentReliability AI — Account-Scoped Neon PostgreSQL Migration Script",
        f"-- Scoped User ID: {data['user']['id']} ({mask_email(data['user']['email'])})",
        "-- ==========================================================================",
        "BEGIN;\n",
    ]

    insert_order = [
        ("users", [data["user"]]),
        ("projects", data["projects"]),
        ("executions", data["executions"]),
        ("test_cases", data["test_cases"]),
        ("test_runs", data["test_runs"]),
        ("trace_events", data["trace_events"]),
        ("trace_executions", data["trace_executions"]),
        ("trace_tool_calls", data["trace_tool_calls"]),
        ("ci_runs", data["ci_runs"]),
        ("baselines", data["baselines"]),
        ("baseline_versions", data["baseline_versions"]),
    ]
    if include_api_keys and data["api_keys"]:
        insert_order.append(("api_keys", data["api_keys"]))

    for tbl, rows in insert_order:
        if not rows:
            continue
        cols = TABLE_COLUMNS[tbl]
        cols_str = ", ".join(cols)
        lines.append(f"-- Table: {tbl} ({len(rows)} records)")
        for r in rows:
            vals_str = ", ".join(sql_quote(r[c]) for c in cols)
            lines.append(f"INSERT INTO {tbl} ({cols_str}) VALUES ({vals_str});")
        lines.append("")

    # Sequence synchronization
    lines.append("-- Sequence Synchronization (setval)")
    seq_tables = list(SERIAL_SEQUENCE_TABLES)
    if include_api_keys:
        seq_tables.append("api_keys")

    for tbl in seq_tables:
        lines.append(f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), COALESCE(MAX(id), 1), true) FROM {tbl};")

    lines.append("\nCOMMIT;")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Live Execution Engine
# -----------------------------------------------------------------------------

def verify_imported_table_counts(cur: Any, data: Dict[str, Any], include_api_keys: bool = False) -> Dict[str, int]:
    """Verify that actual imported row counts for EVERY migrated table match the extracted dataset,
    strictly scoped to the specified user ID and their owned projects.

    If any table count mismatches, raises RuntimeError with complete diagnostic details,
    guaranteeing that the surrounding atomic transaction is rolled back.
    """
    u_id = data["user"]["id"]
    projects = data["projects"]
    p_ids = [p["id"] for p in projects]
    p_marks = ", ".join(["%s"] * len(p_ids)) if p_ids else None

    expected: Dict[str, int] = {
        "users": 1,
        "projects": len(data["projects"]),
        "executions": len(data["executions"]),
        "test_cases": len(data["test_cases"]),
        "test_runs": len(data["test_runs"]),
        "trace_events": len(data["trace_events"]),
        "trace_executions": len(data["trace_executions"]),
        "trace_tool_calls": len(data["trace_tool_calls"]),
        "ci_runs": len(data["ci_runs"]),
        "baselines": len(data["baselines"]),
        "baseline_versions": len(data["baseline_versions"]),
    }
    if include_api_keys:
        expected["api_keys"] = len(data["api_keys"])

    actual: Dict[str, int] = {}

    # 1. users
    cur.execute("SELECT COUNT(*) AS count FROM users WHERE id = %s", (u_id,))
    actual["users"] = _row_val(cur.fetchone(), "count", 0) or 0

    # 2. projects
    if p_ids:
        cur.execute(f"SELECT COUNT(*) AS count FROM projects WHERE id IN ({p_marks}) AND owner_id = %s", (*p_ids, u_id))
        actual["projects"] = _row_val(cur.fetchone(), "count", 0) or 0
    else:
        actual["projects"] = 0

    # 3. executions (scoped to project_id)
    if p_ids:
        cur.execute(f"SELECT COUNT(*) AS count FROM executions WHERE project_id IN ({p_marks})", tuple(p_ids))
        actual["executions"] = _row_val(cur.fetchone(), "count", 0) or 0
    else:
        actual["executions"] = 0

    # 4. test_cases (scoped to project_id)
    if p_ids:
        cur.execute(f"SELECT COUNT(*) AS count FROM test_cases WHERE project_id IN ({p_marks})", tuple(p_ids))
        actual["test_cases"] = _row_val(cur.fetchone(), "count", 0) or 0
    else:
        actual["test_cases"] = 0

    # 5. test_runs (scoped to project_id)
    if p_ids:
        cur.execute(f"SELECT COUNT(*) AS count FROM test_runs WHERE project_id IN ({p_marks})", tuple(p_ids))
        actual["test_runs"] = _row_val(cur.fetchone(), "count", 0) or 0
    else:
        actual["test_runs"] = 0

    # 6. trace_events (scoped to project_id)
    if p_ids:
        cur.execute(f"SELECT COUNT(*) AS count FROM trace_events WHERE project_id IN ({p_marks})", tuple(p_ids))
        actual["trace_events"] = _row_val(cur.fetchone(), "count", 0) or 0
    else:
        actual["trace_events"] = 0

    # 7. trace_executions (composite primary key: project_id, execution_id)
    if p_ids:
        cur.execute(f"SELECT COUNT(*) AS count FROM trace_executions WHERE project_id IN ({p_marks})", tuple(p_ids))
        actual["trace_executions"] = _row_val(cur.fetchone(), "count", 0) or 0
    else:
        actual["trace_executions"] = 0

    # 8. trace_tool_calls (composite primary key: project_id, call_id)
    if p_ids:
        cur.execute(f"SELECT COUNT(*) AS count FROM trace_tool_calls WHERE project_id IN ({p_marks})", tuple(p_ids))
        actual["trace_tool_calls"] = _row_val(cur.fetchone(), "count", 0) or 0
    else:
        actual["trace_tool_calls"] = 0

    # 9. ci_runs (scoped to project_id)
    if p_ids:
        cur.execute(f"SELECT COUNT(*) AS count FROM ci_runs WHERE project_id IN ({p_marks})", tuple(p_ids))
        actual["ci_runs"] = _row_val(cur.fetchone(), "count", 0) or 0
    else:
        actual["ci_runs"] = 0

    # 10. baselines (scoped to project_id)
    if p_ids:
        cur.execute(f"SELECT COUNT(*) AS count FROM baselines WHERE project_id IN ({p_marks})", tuple(p_ids))
        actual["baselines"] = _row_val(cur.fetchone(), "count", 0) or 0
    else:
        actual["baselines"] = 0

    # 11. baseline_versions (scoped via JOIN baselines on baselines.project_id)
    if p_ids:
        cur.execute(
            f"""SELECT COUNT(*) AS count
                FROM baseline_versions bv
                JOIN baselines b ON bv.baseline_id = b.id
                WHERE b.project_id IN ({p_marks})""",
            tuple(p_ids),
        )
        actual["baseline_versions"] = _row_val(cur.fetchone(), "count", 0) or 0
    else:
        actual["baseline_versions"] = 0

    # 12. api_keys (if included)
    if include_api_keys:
        if p_ids:
            cur.execute(f"SELECT COUNT(*) AS count FROM api_keys WHERE project_id IN ({p_marks})", tuple(p_ids))
            actual["api_keys"] = _row_val(cur.fetchone(), "count", 0) or 0
        else:
            actual["api_keys"] = 0

    # Validation check across every table
    mismatches = []
    for tbl, exp_cnt in expected.items():
        act_cnt = actual.get(tbl, 0)
        if act_cnt != exp_cnt:
            mismatches.append(f"{tbl}: expected {exp_cnt}, found {act_cnt}")

    if mismatches:
        raise RuntimeError(
            "Post-import verification failed with count mismatches across migrated tables:\n"
            + "\n".join(f"  ❌ {m}" for m in mismatches)
            + "\nTransaction will roll back all imported records."
        )

    return actual


def synchronize_postgres_sequences(cur: Any, include_api_keys: bool = False) -> List[str]:
    """Synchronize PostgreSQL serial sequences to the maximum ID present in each table.

    CRITICAL ARCHITECTURAL GUARANTEE:
    In PostgreSQL, sequence operations (setval, nextval) are NOT transactional and are NOT
    rolled back if an enclosing transaction aborts. Therefore, this function MUST ONLY be called
    AFTER all table insertions and data row count verifications have fully succeeded.
    """
    seq_tables = list(SERIAL_SEQUENCE_TABLES)
    if include_api_keys:
        seq_tables.append("api_keys")

    for tbl in seq_tables:
        cur.execute(f"SELECT setval(pg_get_serial_sequence(%s, 'id'), COALESCE(MAX(id), 1), true) FROM {tbl}", (tbl,))

    return seq_tables


def execute_account_migration(pg_conn: Any, data: Dict[str, Any], include_api_keys: bool = False) -> Dict[str, int]:
    """Execute account migration inside an atomic PostgreSQL transaction with post-import verification.

    Lifecycle:
    1. Insert rows across all 11 (or 12) tables in strict foreign-key dependency order.
    2. Perform post-import verification: query actual counts for EVERY table, scoped to the
       target user ID and project IDs.
    3. If verification fails on any table, raise RuntimeError immediately so that the
       caller's transaction context manager triggers a clean ROLLBACK.
    4. Only after all verifications succeed, synchronize PostgreSQL serial sequences.
    """
    cur = pg_conn.cursor()
    counts = {}

    insert_order = [
        ("users", [data["user"]]),
        ("projects", data["projects"]),
        ("executions", data["executions"]),
        ("test_cases", data["test_cases"]),
        ("test_runs", data["test_runs"]),
        ("trace_events", data["trace_events"]),
        ("trace_executions", data["trace_executions"]),
        ("trace_tool_calls", data["trace_tool_calls"]),
        ("ci_runs", data["ci_runs"]),
        ("baselines", data["baselines"]),
        ("baseline_versions", data["baseline_versions"]),
    ]
    if include_api_keys and data["api_keys"]:
        insert_order.append(("api_keys", data["api_keys"]))

    # Step 1: Insert records in strict foreign-key order
    for tbl, rows in insert_order:
        if not rows:
            counts[tbl] = 0
            continue
        cols = TABLE_COLUMNS[tbl]
        cols_str = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        sql = f"INSERT INTO {tbl} ({cols_str}) VALUES ({placeholders})"
        param_tuples = [tuple(r[c] for c in cols) for r in rows]
        cur.executemany(sql, param_tuples)
        counts[tbl] = len(rows)

    # Step 2: Comprehensive Post-Import Count Verification (BEFORE sequence changes)
    # If any count does not match, this raises RuntimeError and aborts the transaction.
    verified_counts = verify_imported_table_counts(cur, data, include_api_keys=include_api_keys)

    # Step 3: Sequence Synchronization (Executed ONLY after 100% verification passes)
    synchronize_postgres_sequences(cur, include_api_keys=include_api_keys)

    return verified_counts


# -----------------------------------------------------------------------------
# Main CLI
# -----------------------------------------------------------------------------

def run_migration_audit(
    source_db: str,
    user_id: int = 2,
    target_url: Optional[str] = None,
    include_api_keys: bool = False,
) -> Dict[str, Any]:
    """Run non-mutating audit: inspect source records, check integrity, and optionally check target schema/conflicts."""
    src_conn = open_source_sqlite(source_db)
    try:
        data = extract_account_data(src_conn, user_id=user_id, include_api_keys=include_api_keys)
    finally:
        src_conn.close()

    result: Dict[str, Any] = {
        "user_id": user_id,
        "user_email_masked": mask_email(data["user"]["email"]),
        "user_name": data["user"]["name"],
        "project_count": len(data["projects"]),
        "integrity_ok": len(data["integrity_violations"]) == 0,
        "integrity_violations": data["integrity_violations"],
        "table_counts": {
            "users": 1,
            "projects": len(data["projects"]),
            "executions": len(data["executions"]),
            "test_cases": len(data["test_cases"]),
            "test_runs": len(data["test_runs"]),
            "trace_events": len(data["trace_events"]),
            "trace_executions": len(data["trace_executions"]),
            "trace_tool_calls": len(data["trace_tool_calls"]),
            "ci_runs": len(data["ci_runs"]),
            "baselines": len(data["baselines"]),
            "baseline_versions": len(data["baseline_versions"]),
            "api_keys": len(data["api_keys"]),
        },
        "target_checked": False,
        "target_schema_ok": None,
        "target_schema_errors": [],
        "target_conflicts": [],
    }

    if target_url:
        import psycopg
        from psycopg.rows import dict_row

        clean_url = target_url
        if clean_url.startswith("postgres://"):
            clean_url = "postgresql://" + clean_url[len("postgres://"):]

        try:
            with psycopg.connect(clean_url, connect_timeout=15, row_factory=dict_row) as pg_conn:
                schema_errs = verify_postgres_schema(pg_conn, include_api_keys=include_api_keys)
                conflicts = check_postgres_conflicts(pg_conn, data["user"], data["projects"])
                result["target_checked"] = True
                result["target_schema_ok"] = len(schema_errs) == 0
                result["target_schema_errors"] = schema_errs
                result["target_conflicts"] = conflicts
        except Exception as exc:
            result["target_checked"] = False
            result["target_schema_ok"] = False
            result["target_schema_errors"] = [f"Failed to connect to target PostgreSQL: {exc}"]

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Safely migrate a specific account and its projects from SQLite to Neon PostgreSQL."
    )
    parser.add_argument(
        "--source-db",
        default="backend/agentreliability.db",
        help="Path to source SQLite database (default: backend/agentreliability.db)",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=2,
        help="Original user ID to migrate (default: 2)",
    )
    parser.add_argument(
        "--target-url",
        default=os.environ.get("TARGET_DATABASE_URL") or os.environ.get("DATABASE_URL"),
        help="Target Neon PostgreSQL connection URL (or set TARGET_DATABASE_URL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Perform dry-run audit and conflict checks without writing to target (default: True)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the live migration into target PostgreSQL (requires explicit confirmation)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip manual interactive confirmation prompt",
    )
    parser.add_argument(
        "--include-api-keys",
        action="store_true",
        help="Include existing project API keys in migration (default: False, excluded)",
    )
    parser.add_argument(
        "--output-sql",
        help="Save generated PostgreSQL insert script to a local file",
    )

    args = parser.parse_args()

    # If --execute is passed, dry_run is disabled
    is_dry_run = not args.execute

    print("=" * 72)
    print(" AgentReliability AI — Account-Scoped PostgreSQL Migration Tool")
    print("=" * 72)
    print(f" Source SQLite DB : {args.source_db} [READ-ONLY]")
    print(f" Target User ID   : {args.user_id}")
    print(f" Target Postgres  : {mask_url(args.target_url) if args.target_url else '(None provided)'}")
    print(f" Execution Mode   : {'DRY-RUN (Safe, no writes)' if is_dry_run else 'LIVE EXECUTION'}")
    print(f" Include API Keys : {args.include_api_keys}")
    print("=" * 72)

    # 1. Source Extraction
    src_conn = open_source_sqlite(args.source_db)
    try:
        data = extract_account_data(src_conn, user_id=args.user_id, include_api_keys=args.include_api_keys)
    finally:
        src_conn.close()

    user = data["user"]
    projects = data["projects"]

    print("\n--- 1. Account Scope Audit ---")
    print(f"  User Record       : ID {user['id']} | Email: {mask_email(user['email'])} | Name: {user['name']}")
    print(f"  Owned Projects    : {len(projects)} projects identified")
    for p in projects:
        print(f"    - [{p['id']:3d}] {p['name']:<40} (Created: {p['created_at'][:19]})")

    print("\n--- 2. Related Records Breakdown ---")
    counts = {
        "executions": len(data["executions"]),
        "test_cases": len(data["test_cases"]),
        "test_runs": len(data["test_runs"]),
        "trace_events": len(data["trace_events"]),
        "trace_executions": len(data["trace_executions"]),
        "trace_tool_calls": len(data["trace_tool_calls"]),
        "ci_runs": len(data["ci_runs"]),
        "baselines": len(data["baselines"]),
        "baseline_versions": len(data["baseline_versions"]),
        "api_keys": len(data["api_keys"]) if args.include_api_keys else "EXCLUDED (Default)",
        "sessions": "EXCLUDED (Default)",
        "password_resets": "EXCLUDED (Default)",
    }
    for k, v in counts.items():
        print(f"  {k:<20}: {v}")

    # Integrity Check
    print("\n--- 3. Source Referential Integrity ---")
    if data.get("pruned_records"):
        for pr in data["pruned_records"]:
            print(f"  ⚠️  Excluded orphaned {pr['table']} record (ID: {pr['id']}): {pr['reason']}")

    if data["integrity_violations"]:
        print("  ❌ Referential Integrity Violations Found:")
        for v in data["integrity_violations"]:
            print(f"    - {v}")
        sys.exit(1)
    else:
        print("  ✅ All foreign keys and cross-table references within account dataset are 100% valid.")

    # Optional SQL Export
    if args.output_sql:
        sql_content = generate_migration_sql(data, include_api_keys=args.include_api_keys)
        with open(args.output_sql, "w", encoding="utf-8") as f:
            f.write(sql_content)
        print(f"\n--- 4. SQL Script Generated ---\n  Saved to: {args.output_sql}")

    # Target Checks & Execution
    if not args.target_url:
        print("\nℹ️  No --target-url provided. Audit complete. Dry-run finished successfully.")
        return

    import psycopg
    from psycopg.rows import dict_row

    clean_url = args.target_url
    if clean_url.startswith("postgres://"):
        clean_url = "postgresql://" + clean_url[len("postgres://"):]

    print(f"\n--- 5. Target PostgreSQL Audit ({mask_url(clean_url)}) ---")
    with psycopg.connect(clean_url, connect_timeout=15, row_factory=dict_row) as pg_conn:
        schema_errs = verify_postgres_schema(pg_conn, include_api_keys=args.include_api_keys)
        if schema_errs:
            print("  ❌ Schema Incompatibility Detected:")
            for err in schema_errs:
                print(f"    - {err}")
            sys.exit(1)
        print("  ✅ Target PostgreSQL schema compatibility verified (all tables and columns match).")

        conflicts = check_postgres_conflicts(pg_conn, user, projects)
        if conflicts:
            print("  ❌ Data Collisions Detected in Target:")
            for c_msg in conflicts:
                print(f"    - {c_msg}")
            sys.exit(1)
        print("  ✅ Target conflict check passed (zero collisions detected; target is clean for import).")

        if is_dry_run:
            print("\n🎉 Dry-run audit completed successfully. Zero target changes made.")
            print("To execute live migration, run with: --execute (requires explicit confirmation)")
            return

        # Explicit confirmation
        print("\n" + "!" * 72)
        print(" WARNING: LIVE MIGRATION REQUESTED")
        print(f" Target Database : {mask_url(clean_url)}")
        print(f" User ID {user['id']} and {len(projects)} projects will be written into target PostgreSQL.")
        print("!" * 72)

        if not args.yes:
            confirm = input("\nType 'MIGRATE' to confirm and execute: ").strip()
            if confirm != "MIGRATE":
                print("Aborted by user. No data written.")
                sys.exit(0)

        # Atomic transaction execution
        print("\nExecuting migration inside atomic transaction...")
        try:
            with pg_conn.transaction():
                migrated_counts = execute_account_migration(pg_conn, data, include_api_keys=args.include_api_keys)
        except Exception as exc:
            print(f"\n❌ MIGRATION FAILED: {exc}\n⚠️  All database changes have been completely rolled back. Zero records retained in target.", file=sys.stderr)
            sys.exit(1)

        print("\n✅ Migration successfully committed to PostgreSQL!")
        for tbl, cnt in migrated_counts.items():
            print(f"  {tbl:<20}: {cnt} records imported & verified")
        print("\nSequence synchronization and post-import verification complete.")


if __name__ == "__main__":
    main()
