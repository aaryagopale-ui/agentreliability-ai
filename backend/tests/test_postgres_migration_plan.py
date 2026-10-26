"""Unit tests for the SQLite to PostgreSQL migration plan and dry-run utility."""
import sqlite3
import pytest
from app import database
from app.migrations.runner import run_migrations
from scripts.migrate_sqlite_to_postgres import (
    run_migration_audit,
    verify_sqlite_referential_integrity,
    export_sqlite_to_postgres_sql,
)


@pytest.fixture
def mock_migrated_db(tmp_path):
    """Create a temporary SQLite database with historical records and foreign keys."""
    db_file = str(tmp_path / "mock_historical.db")
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)

    # Insert mock user
    conn.execute(
        """INSERT INTO users (id, email, password_hash, name, created_at, updated_at)
           VALUES (1, 'founder@agentreliability.com', 'scrypt$dummy_hash_123', 'Founder', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"""
    )
    # Insert mock project (id=2 since id=1 is Default Project)
    conn.execute(
        """INSERT INTO projects (id, name, owner_id, created_at, updated_at)
           VALUES (2, 'Core Platform', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"""
    )
    # Insert mock API key
    conn.execute(
        """INSERT INTO api_keys (id, project_id, name, key_prefix, key_hash, created_at)
           VALUES (1, 2, 'Default Key', 'ar_live_1234', 'hash_sha256_mock_abc', '2026-01-01T00:00:00Z')"""
    )
    # Insert mock execution
    conn.execute(
        """INSERT INTO executions (id, agent_name, status, step_count, failure_count, steps_json, findings_json, created_at, project_id)
           VALUES (1, 'triage_agent', 'success', 2, 0, '[]', '[]', '2026-01-01T00:00:00Z', 2)"""
    )
    conn.commit()
    conn.close()
    return db_file


def test_migration_audit_succeeds_on_valid_data(mock_migrated_db):
    audit = run_migration_audit(mock_migrated_db)
    assert audit["referential_integrity_ok"] is True
    assert len(audit["violations"]) == 0
    assert audit["table_record_counts"]["users"] == 1
    assert audit["table_record_counts"]["projects"] >= 1
    assert audit["table_record_counts"]["api_keys"] == 1
    assert audit["table_record_counts"]["executions"] == 1

    sql = audit["sql_dump"]
    assert "CREATE TABLE IF NOT EXISTS users" in sql
    assert "CREATE TABLE IF NOT EXISTS projects" in sql
    assert "founder@agentreliability.com" in sql
    assert "scrypt$dummy_hash_123" in sql
    assert "hash_sha256_mock_abc" in sql
    assert "SELECT setval(pg_get_serial_sequence('users', 'id')" in sql


def test_referential_integrity_catches_orphaned_records(tmp_path):
    db_file = str(tmp_path / "broken_fk.db")
    conn = sqlite3.connect(db_file)
    run_migrations(conn)

    # Disable FK after migrations to simulate corrupt legacy database state
    conn.execute("PRAGMA foreign_keys = OFF")

    # Insert project with nonexistent owner_id
    conn.execute(
        """INSERT INTO projects (id, name, owner_id, created_at, updated_at)
           VALUES (99, 'Orphaned Project', 9999, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"""
    )
    conn.commit()

    violations = verify_sqlite_referential_integrity(conn)
    conn.close()

    assert len(violations) > 0
    assert "projects" in violations[0]
