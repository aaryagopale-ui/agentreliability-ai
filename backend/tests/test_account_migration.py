"""Automated Unit & Integration Tests for the Account-Scoped SQLite-to-PostgreSQL Migration Tool."""
from __future__ import annotations

import os
import sqlite3
import pytest

from scripts.migrate_account_to_postgres import (
    TABLE_COLUMNS,
    _row_val,
    extract_account_data,
    mask_email,
    mask_url,
    open_source_sqlite,
    generate_migration_sql,
    verify_postgres_schema,
    check_postgres_conflicts,
    verify_imported_table_counts,
    synchronize_postgres_sequences,
    execute_account_migration,
    run_migration_audit,
)
from tests.test_postgres_integration import PostgresHarnessConnection
from app.database import PostgresConnectionWrapper
from app.migrations.postgres_runner import run_postgres_migrations


SOURCE_DB = "backend/agentreliability.db"


def test_open_source_sqlite_read_only():
    """Verify that open_source_sqlite opens database in read-only mode and refuses writes."""
    conn = open_source_sqlite(SOURCE_DB)
    c = conn.cursor()
    # Attempting a write should fail because of mode=ro
    with pytest.raises(sqlite3.OperationalError):
        c.execute("CREATE TABLE _should_fail_ro (id INT)")
    conn.close()


def test_mask_email_and_mask_url():
    """Verify safe masking of emails and database connection URLs."""
    assert mask_email("2024.aarya.gopale@ves.ac.in") == "2***@v***.a***.i***"
    assert mask_email("alex@example.com") == "a***@e***.c***"
    assert mask_url("postgresql://user:SecretPass123@ep-cool-fog.neon.tech/neondb?sslmode=require") == \
           "postgresql://user:****@ep-cool-fog.neon.tech/neondb?sslmode=require"


def test_extract_account_data_scope():
    """Verify user ID 2 extraction yields exactly 1 user and their 14 projects, excluding other users."""
    conn = open_source_sqlite(SOURCE_DB)
    try:
        data = extract_account_data(conn, user_id=2, include_api_keys=False)
    finally:
        conn.close()

    # User validation
    user = data["user"]
    assert user["id"] == 2
    assert "aarya" in user["email"].lower()
    assert len(user["password_hash"]) > 20

    # Projects validation: exactly 14 projects owned by user 2
    projects = data["projects"]
    assert len(projects) == 14
    for p in projects:
        assert p["owner_id"] == 2

    # Related records validation
    assert len(data["executions"]) == 4
    assert len(data["test_cases"]) == 18
    # 72 valid test runs (1 orphaned run 469 cleanly excluded)
    assert len(data["test_runs"]) == 72
    assert len(data["trace_events"]) == 1393
    assert len(data["trace_executions"]) == 62
    assert len(data["trace_tool_calls"]) == 1269
    assert len(data["ci_runs"]) == 3
    assert len(data["baselines"]) == 21
    assert len(data["baseline_versions"]) == 25

    # Excluded by default
    assert len(data["api_keys"]) == 0

    # Pruned orphans
    assert len(data["pruned_records"]) == 1
    assert data["pruned_records"][0]["table"] == "test_runs"
    assert data["pruned_records"][0]["id"] == 469

    # Referential integrity violations
    assert len(data["integrity_violations"]) == 0


def test_extract_account_data_include_api_keys():
    """Verify opt-in --include-api-keys extracts the 49 project API keys."""
    conn = open_source_sqlite(SOURCE_DB)
    try:
        data = extract_account_data(conn, user_id=2, include_api_keys=True)
    finally:
        conn.close()

    assert len(data["api_keys"]) == 49
    for k in data["api_keys"]:
        assert k["project_id"] in [p["id"] for p in data["projects"]]


def test_generate_migration_sql():
    """Verify SQL script generation wraps in transaction, includes all tables and setval sequences."""
    conn = open_source_sqlite(SOURCE_DB)
    try:
        data = extract_account_data(conn, user_id=2, include_api_keys=False)
    finally:
        conn.close()

    sql = generate_migration_sql(data, include_api_keys=False)
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql
    assert "INSERT INTO users" in sql
    assert "INSERT INTO projects" in sql
    assert "INSERT INTO baselines" in sql
    assert "INSERT INTO trace_events" in sql
    assert "SELECT setval(pg_get_serial_sequence('users', 'id')" in sql
    assert "SELECT setval(pg_get_serial_sequence('projects', 'id')" in sql


def test_check_postgres_conflicts():
    """Verify conflict detector catches existing user IDs, email collisions, and project IDs."""
    from tests.test_postgres_integration import PostgresHarnessConnection

    # Create mock target database
    raw_target = sqlite3.connect(":memory:")
    harness = PostgresHarnessConnection(raw_target)
    conn = PostgresConnectionWrapper(harness)

    # Initialize schema
    run_postgres_migrations(conn)

    # Insert conflicting user with id=2
    conn.execute(
        "INSERT INTO users (id, email, password_hash, name, created_at, updated_at) "
        "VALUES (2, 'existing@target.com', 'dummy_hash', 'Existing', '2026-01-01', '2026-01-01')"
    )

    user_data = {"id": 2, "email": "founder@source.com"}
    project_data = [{"id": 3, "name": "Source Project"}]

    conflicts = check_postgres_conflicts(conn, user_data, project_data)
    assert len(conflicts) >= 1
    assert "User ID 2 already exists" in conflicts[0]

    # Insert conflicting project with id=3
    conn.execute(
        "INSERT INTO projects (id, name, owner_id, created_at) VALUES (3, 'Target Conflicting Proj', 2, '2026-01-01')"
    )
    conflicts_proj = check_postgres_conflicts(conn, {"id": 99, "email": "new@source.com"}, project_data)
    assert len(conflicts_proj) >= 1
    assert "Project ID 3" in conflicts_proj[0]


def test_execute_account_migration_and_verification(tmp_path):
    """Verify end-to-end execution of account migration against target PostgreSQL harness."""
    # 1. Extract source data
    src_conn = open_source_sqlite(SOURCE_DB)
    try:
        data = extract_account_data(src_conn, user_id=2, include_api_keys=False)
    finally:
        src_conn.close()

    # 2. Setup target PostgreSQL harness
    target_db_file = str(tmp_path / "mock_target_pg.db")
    raw_target = sqlite3.connect(target_db_file)
    harness = PostgresHarnessConnection(raw_target)
    pg_conn = PostgresConnectionWrapper(harness)

    # Initialize schema via migrations
    run_postgres_migrations(pg_conn)

    # 3. Execute migration
    counts = execute_account_migration(pg_conn, data, include_api_keys=False)

    assert counts["users"] == 1
    assert counts["projects"] == 14
    assert counts["executions"] == 4
    assert counts["test_cases"] == 18
    assert counts["test_runs"] == 72
    assert counts["trace_events"] == 1393
    assert counts["trace_executions"] == 62
    assert counts["trace_tool_calls"] == 1269
    assert counts["ci_runs"] == 3
    assert counts["baselines"] == 21
    assert counts["baseline_versions"] == 25

    # 4. Post-import query checks directly on target
    u_row = pg_conn.execute("SELECT id, email, name FROM users WHERE id = 2").fetchone()
    assert u_row is not None
    assert u_row["id"] == 2
    assert u_row["name"] == "Aarya Gopale"

    p_rows = pg_conn.execute("SELECT id, name FROM projects WHERE owner_id = 2").fetchall()
    assert len(p_rows) == 14

    b_rows = pg_conn.execute("SELECT id, name FROM baselines WHERE project_id = 307").fetchall()
    assert len(b_rows) >= 1


def test_run_migration_audit_dry_run():
    """Verify run_migration_audit runs in memory without modifying any database."""
    audit = run_migration_audit(SOURCE_DB, user_id=2, target_url=None, include_api_keys=False)
    assert audit["user_id"] == 2
    assert audit["project_count"] == 14
    assert audit["integrity_ok"] is True
    assert audit["table_counts"]["users"] == 1
    assert audit["table_counts"]["projects"] == 14
    assert audit["table_counts"]["executions"] == 4
    assert audit["table_counts"]["test_cases"] == 18
    assert audit["table_counts"]["test_runs"] == 72


# -----------------------------------------------------------------------------
# Regression Tests for psycopg dict_row Parity
# -----------------------------------------------------------------------------

def test_row_val_parity_with_dict_and_tuples():
    """Verify _row_val extracts columns from pure dicts (psycopg dict_row) without KeyError: 0,
    as well as from tuples, sqlite3.Row, and UnifiedRow."""
    # Pure dict (psycopg dict_row does NOT support integer index row[0])
    dict_row = {"column_name": "project_id", "version": 4, "count": 14}
    with pytest.raises(KeyError):
        _ = dict_row[0]  # Reproduces the real crash before fix

    assert _row_val(dict_row, "column_name", 0) == "project_id"
    assert _row_val(dict_row, "version", 1) == 4
    assert _row_val(dict_row, "count", 2) == 14
    assert _row_val(dict_row, "nonexistent", 0) is None

    # Tuple
    tuple_row = ("project_id", 4, 14)
    assert _row_val(tuple_row, "column_name", 0) == "project_id"
    assert _row_val(tuple_row, "version", 1) == 4
    assert _row_val(tuple_row, "count", 2) == 14


class MockDictRowCursor:
    """Simulates a psycopg cursor yielding pure Python dicts via psycopg.rows.dict_row."""
    def __init__(self, table_columns_map: dict[str, list[str]], applied_versions: list[int], counts_map: dict[str, int] | None = None):
        self.table_columns_map = table_columns_map
        self.applied_versions = applied_versions
        self.counts_map = counts_map or {}
        self._last_result = []

    def execute(self, sql: str, params: tuple = ()):
        s = sql.strip()
        if "COUNT(*)" in s:
            for tbl in ["baseline_versions", "trace_executions", "trace_tool_calls",
                        "trace_events", "test_cases", "test_runs", "executions",
                        "projects", "ci_runs", "baselines", "api_keys", "users"]:
                if tbl in s:
                    cnt = self.counts_map.get(tbl, 0)
                    self._last_result = [{"count": cnt}]
                    return self
            self._last_result = [{"count": 0}]
        elif "information_schema.columns" in s:
            tbl = params[0]
            cols = self.table_columns_map.get(tbl, [])
            self._last_result = [{"column_name": c} for c in cols]
        elif "schema_migrations" in s:
            self._last_result = [{"version": v} for v in self.applied_versions]
        elif "FROM users WHERE id =" in s:
            uid = params[0]
            if uid == 2:
                self._last_result = [{"id": 2, "email": "existing@neon.tech"}]
            else:
                self._last_result = []
        elif "FROM users WHERE email =" in s:
            self._last_result = []
        elif "FROM projects WHERE id IN" in s:
            self._last_result = [{"id": 3, "name": "Existing Proj 3"}]
        elif "setval(" in s:
            self._last_result = []
        else:
            self._last_result = []
        return self

    def executemany(self, sql: str, params_seq: list):
        return self

    def fetchone(self):
        if not self._last_result:
            return None
        return self._last_result[0]

    def fetchall(self):
        return list(self._last_result)


class MockDictRowConnection:
    """Simulates psycopg connection configured with row_factory=dict_row."""
    def __init__(self, table_columns_map: dict[str, list[str]], applied_versions: list[int], counts_map: dict[str, int] | None = None):
        self._cur = MockDictRowCursor(table_columns_map, applied_versions, counts_map=counts_map)

    def cursor(self):
        return self._cur


def test_verify_postgres_schema_with_dict_row():
    """Verify verify_postgres_schema succeeds against pure dict_row cursor without KeyError: 0."""
    # Complete schema
    conn = MockDictRowConnection(TABLE_COLUMNS, [1, 2, 3, 4])
    errors = verify_postgres_schema(conn, include_api_keys=False)
    assert errors == []

    # Incomplete migrations
    conn_missing_migration = MockDictRowConnection(TABLE_COLUMNS, [1, 2])
    errs = verify_postgres_schema(conn_missing_migration, include_api_keys=False)
    assert any("Target schema_migrations is missing versions" in e for e in errs)

    # Missing column in table
    bad_columns = dict(TABLE_COLUMNS)
    bad_columns["users"] = ["id", "email"]  # missing password_hash, name, created_at, updated_at
    conn_missing_cols = MockDictRowConnection(bad_columns, [1, 2, 3, 4])
    errs_col = verify_postgres_schema(conn_missing_cols, include_api_keys=False)
    assert any("Target table 'users' is missing columns" in e for e in errs_col)


def test_check_postgres_conflicts_with_dict_row():
    """Verify check_postgres_conflicts detects collisions with pure dict_row cursor without KeyError."""
    conn = MockDictRowConnection(TABLE_COLUMNS, [1, 2, 3, 4])
    user_row = {"id": 2, "email": "founder@test.com"}
    project_rows = [{"id": 3, "name": "Project 3"}]

    conflicts = check_postgres_conflicts(conn, user_row, project_rows)
    assert len(conflicts) == 2
    assert "User ID 2 already exists" in conflicts[0]
    assert "Project ID 3 ('Existing Proj 3') already exists" in conflicts[1]


def test_execute_account_migration_post_import_verification_with_dict_row():
    """Verify post-import verification in execute_account_migration handles dict_row without KeyError: 0."""
    src_conn = open_source_sqlite(SOURCE_DB)
    try:
        data = extract_account_data(src_conn, user_id=2, include_api_keys=False)
    finally:
        src_conn.close()

    expected_counts = {
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
    conn = MockDictRowConnection(TABLE_COLUMNS, [1, 2, 3, 4], counts_map=expected_counts)

    counts = execute_account_migration(conn, data, include_api_keys=False)
    assert counts["users"] == 1
    assert counts["projects"] == 14
    assert counts["trace_executions"] == 62
    assert counts["trace_tool_calls"] == 1269
    assert counts["baseline_versions"] == 25


def test_verify_imported_table_counts_detects_mismatch():
    """Verify verify_imported_table_counts raises RuntimeError listing mismatched tables."""
    src_conn = open_source_sqlite(SOURCE_DB)
    try:
        data = extract_account_data(src_conn, user_id=2, include_api_keys=False)
    finally:
        src_conn.close()

    # Create mock cursor returning incorrect count for executions (expected 4, returns 3)
    counts_map = {
        "users": 1,
        "projects": 14,
        "executions": 3,  # Mismatch!
        "test_cases": 18,
        "test_runs": 72,
        "trace_events": 1393,
        "trace_executions": 62,
        "trace_tool_calls": 1269,
        "ci_runs": 3,
        "baselines": 21,
        "baseline_versions": 25,
    }
    conn = MockDictRowConnection(TABLE_COLUMNS, [1, 2, 3, 4], counts_map=counts_map)

    with pytest.raises(RuntimeError) as exc_info:
        verify_imported_table_counts(conn.cursor(), data, include_api_keys=False)

    assert "Post-import verification failed with count mismatches" in str(exc_info.value)
    assert "executions: expected 4, found 3" in str(exc_info.value)


def test_verification_failure_raises_and_rolls_back(tmp_path, monkeypatch):
    """Verify that if any table count verification fails, an exception is raised
    and the surrounding transaction rolls back all inserted data."""
    # 1. Extract source data
    src_conn = open_source_sqlite(SOURCE_DB)
    try:
        data = extract_account_data(src_conn, user_id=2, include_api_keys=False)
    finally:
        src_conn.close()

    # 2. Setup target PostgreSQL harness
    target_db_file = str(tmp_path / "mock_target_rollback.db")
    raw_target = sqlite3.connect(target_db_file)
    harness = PostgresHarnessConnection(raw_target)
    pg_conn = PostgresConnectionWrapper(harness)

    # Initialize schema
    run_postgres_migrations(pg_conn)

    # 3. Simulate a verification failure triggered during migration
    import scripts.migrate_account_to_postgres as mig_module

    def mock_verify_fail(cur, d, include_api_keys=False):
        raise RuntimeError(
            "Post-import verification failed with count mismatches across migrated tables:\n"
            "  ❌ test_cases: expected 18, found 17\n"
            "Transaction will roll back all imported records."
        )

    monkeypatch.setattr(mig_module, "verify_imported_table_counts", mock_verify_fail)

    # Attempt migration inside atomic transaction
    with pytest.raises(RuntimeError) as exc_info:
        with pg_conn.transaction():
            execute_account_migration(pg_conn, data, include_api_keys=False)

    assert "Post-import verification failed with count mismatches" in str(exc_info.value)
    assert "test_cases" in str(exc_info.value)

    # 4. Verify complete rollback: target database must have 0 users and 0 projects!
    u_cnt = pg_conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    assert _row_val(u_cnt, "count", 0) == 0

    p_cnt = pg_conn.execute("SELECT COUNT(*) AS count FROM projects").fetchone()
    assert _row_val(p_cnt, "count", 0) == 0

    tr_cnt = pg_conn.execute("SELECT COUNT(*) AS count FROM test_runs").fetchone()
    assert _row_val(tr_cnt, "count", 0) == 0


def test_sequences_not_synchronized_when_verification_fails(tmp_path, monkeypatch):
    """Verify that PostgreSQL sequence synchronization (setval) is NEVER called
    if table count verification fails, preserving sequence integrity."""
    src_conn = open_source_sqlite(SOURCE_DB)
    try:
        data = extract_account_data(src_conn, user_id=2, include_api_keys=False)
    finally:
        src_conn.close()

    target_db_file = str(tmp_path / "mock_target_seq.db")
    raw_target = sqlite3.connect(target_db_file)
    harness = PostgresHarnessConnection(raw_target)
    pg_conn = PostgresConnectionWrapper(harness)
    run_postgres_migrations(pg_conn)

    seq_calls = []
    import scripts.migrate_account_to_postgres as mig_module
    orig_sync = mig_module.synchronize_postgres_sequences

    def spy_sync(*args, **kwargs):
        seq_calls.append(True)
        return orig_sync(*args, **kwargs)

    monkeypatch.setattr(mig_module, "synchronize_postgres_sequences", spy_sync)

    def mock_verify_fail(cur, d, include_api_keys=False):
        raise RuntimeError("Verification failed")

    monkeypatch.setattr(mig_module, "verify_imported_table_counts", mock_verify_fail)

    with pytest.raises(RuntimeError):
        with pg_conn.transaction():
            execute_account_migration(pg_conn, data, include_api_keys=False)

    # Sequence synchronization MUST NOT have been called
    assert len(seq_calls) == 0
