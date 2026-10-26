"""Automated tests for database migrations, schema evolution, and foreign keys."""
import sqlite3
import pytest
from app.migrations.runner import run_migrations, rollback_migration, get_applied_versions


@pytest.fixture
def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_migrations_create_expected_tables(memory_db):
    applied = run_migrations(memory_db)
    assert applied == [1, 2, 3, 4]

    tables = {r[0] for r in memory_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    expected = {
        "schema_migrations", "users", "projects", "api_keys", "sessions",
        "password_resets", "executions", "test_cases", "test_runs", "ci_runs",
        "trace_events", "trace_executions", "trace_tool_calls",
        "baselines", "baseline_versions"
    }
    assert expected.issubset(tables)

    # Check applied versions
    versions = get_applied_versions(memory_db)
    assert 1 in versions and 2 in versions and 3 in versions and 4 in versions

    # Verify migration 003 added columns
    tool_cols = {r[1] for r in memory_db.execute("PRAGMA table_info(trace_tool_calls)").fetchall()}
    assert "parent_call_id" in tool_cols
    assert "retry_count" in tool_cols


def test_migrations_are_idempotent(memory_db):
    first_run = run_migrations(memory_db)
    assert first_run == [1, 2, 3, 4]

    second_run = run_migrations(memory_db)
    assert second_run == []


def test_foreign_key_constraints_enforced(memory_db):
    run_migrations(memory_db)
    memory_db.execute("PRAGMA foreign_keys = ON")

    # Invalid project_id on executions must raise IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(
            """INSERT INTO executions
               (agent_name, status, step_count, failure_count, steps_json, findings_json, created_at, project_id)
               VALUES ('test', 'success', 0, 0, '[]', '[]', '2026-01-01', 99999)"""
        )

    # Invalid owner_id on projects must raise IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(
            "INSERT INTO projects (name, owner_id, created_at) VALUES ('Orphan', 99999, '2026-01-01')"
        )


def test_cascade_delete_removes_child_resources(memory_db):
    run_migrations(memory_db)
    memory_db.execute("PRAGMA foreign_keys = ON")

    # Insert user -> project -> api_key
    memory_db.execute(
        "INSERT INTO users (email, password_hash, name, created_at, updated_at) VALUES ('test@example.com', 'h', 'Test', '2026-01-01', '2026-01-01')"
    )
    user_id = memory_db.execute("SELECT id FROM users WHERE email='test@example.com'").fetchone()[0]

    memory_db.execute(
        "INSERT INTO projects (name, owner_id, created_at) VALUES ('User Project', ?, '2026-01-01')",
        (user_id,)
    )
    proj_id = memory_db.execute("SELECT id FROM projects WHERE name='User Project'").fetchone()[0]

    memory_db.execute(
        "INSERT INTO api_keys (project_id, name, key_prefix, key_hash, created_at) VALUES (?, 'Key', 'ar_', 'hash1', '2026-01-01')",
        (proj_id,)
    )
    memory_db.execute(
        "INSERT INTO sessions (user_id, token_hash, created_at, expires_at) VALUES (?, 'sess1', '2026-01-01', '2026-01-02')",
        (user_id,)
    )

    # Deleting the user must cascade delete the project, API key, and session
    memory_db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    assert memory_db.execute("SELECT count(*) FROM projects WHERE id = ?", (proj_id,)).fetchone()[0] == 0
    assert memory_db.execute("SELECT count(*) FROM api_keys WHERE project_id = ?", (proj_id,)).fetchone()[0] == 0
    assert memory_db.execute("SELECT count(*) FROM sessions WHERE user_id = ?", (user_id,)).fetchone()[0] == 0


def test_migration_rollback_and_recovery(memory_db):
    run_migrations(memory_db)
    assert 1 in get_applied_versions(memory_db)
    assert 2 in get_applied_versions(memory_db)
    assert 3 in get_applied_versions(memory_db)
    assert 4 in get_applied_versions(memory_db)

    # Rollback migration 4
    rolled_back_4 = rollback_migration(memory_db, 4)
    assert rolled_back_4 is True
    assert 4 not in get_applied_versions(memory_db)

    # Rollback migration 3
    rolled_back_3 = rollback_migration(memory_db, 3)
    assert rolled_back_3 is True
    assert 3 not in get_applied_versions(memory_db)

    # Rollback migration 2
    rolled_back_2 = rollback_migration(memory_db, 2)
    assert rolled_back_2 is True

    # Rollback migration 1
    rolled_back_1 = rollback_migration(memory_db, 1)
    assert rolled_back_1 is True

    tables = {r[0] for r in memory_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "users" not in tables
    assert "sessions" not in tables
    assert "baselines" not in tables

    # Re-apply
    reapplied = run_migrations(memory_db)
    assert reapplied == [1, 2, 3, 4]
    tables_after = {r[0] for r in memory_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "users" in tables_after
    assert "projects" in tables_after
    assert "baselines" in tables_after
