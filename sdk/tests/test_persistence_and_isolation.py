"""Tests for local account persistence, project persistence, database consistency,
multi-installation isolation, and safe database migration.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agentreliability.config import (
    generate_instance_id,
    resolve_database_path,
    resolve_instance_id,
    save_config,
)
from agentreliability.db_migrator import import_database, run_import_db
from agentreliability.ports import probe_backend, resolve_service_ports


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_user_persistence_and_authentication_across_restart(temp_workspace):
    """Restarting AgentReliability or reopening the DB preserves accounts and passwords."""
    db_file = temp_workspace / "backend" / "test_persist.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)

    with patch.dict(os.environ, {"AGENTRELIABILITY_DB": str(db_file)}):
        from app.database import init_db
        from app import auth_store, security

        init_db()

        # 1. Register a new user with scrypt password hash
        email = "developer@example.com"
        raw_password = "SecurePassword123!"
        name = "Persistence Tester"
        pw_hash = security.hash_password(raw_password)

        user = auth_store.create_user(email=email, password_hash=pw_hash, name=name)
        assert user is not None
        user_id = user["id"]
        assert user["email"] == email

        # 2. Authenticate
        user_record = auth_store.get_user_by_email_with_hash(email)
        assert user_record is not None
        assert security.verify_password(raw_password, user_record["password_hash"]) is True
        assert security.verify_password("WrongPassword!", user_record["password_hash"]) is False

        # 3. Simulate backend restart: new connection to same database
        user_after_restart = auth_store.get_user_by_email_with_hash(email)
        assert user_after_restart is not None
        assert user_after_restart["id"] == user_id
        assert user_after_restart["email"] == email
        assert security.verify_password(raw_password, user_after_restart["password_hash"]) is True


def test_project_persistence_across_sessions(temp_workspace):
    """Projects and generated API keys persist in the same database."""
    db_file = temp_workspace / "backend" / "projects_test.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)

    with patch.dict(os.environ, {"AGENTRELIABILITY_DB": str(db_file)}):
        from app.database import init_db
        from app import auth_store, project_store, security

        init_db()

        user = auth_store.create_user(
            email="owner@company.com",
            password_hash=security.hash_password("Password123!"),
            name="Project Owner",
        )
        user_id = user["id"]

        # Create multiple projects
        p1, p1_key = project_store.create_project(name="Production Bot", owner_id=user_id)
        p2, p2_key = project_store.create_project(name="Staging Bot", owner_id=user_id)

        assert p1["id"] is not None
        assert p2["id"] is not None

        # Re-fetch from database (simulating page reload or restart)
        user_projects = project_store.list_user_projects(user_id)
        # Default project on user create + 2 explicit projects
        assert len(user_projects) >= 2
        names = {p["name"] for p in user_projects}
        assert "Production Bot" in names
        assert "Staging Bot" in names

        # API keys persisted
        keys_p1 = project_store.list_project_keys(p1["id"])
        assert len(keys_p1) >= 1
        assert keys_p1[0]["project_id"] == p1["id"]


def test_port_change_retains_same_database(temp_workspace):
    """Changing ports does NOT change the database used by the installation."""
    custom_db = temp_workspace / "data" / "persistent_agentreliability.db"
    custom_db.parent.mkdir(parents=True, exist_ok=True)

    # Save configuration with custom database path and initial port 8001
    save_config(
        {
            "database_path": str(custom_db.resolve()),
            "backend_port": 8001,
            "frontend_port": 5174,
        },
        target_dir=temp_workspace,
    )

    # Resolve database path with port 8001
    resolved_db_1 = resolve_database_path(start_dir=temp_workspace)
    assert resolved_db_1.resolve() == custom_db.resolve()

    # Now change port in config to 8002
    save_config(
        {
            "database_path": str(custom_db.resolve()),
            "backend_port": 8002,
            "frontend_port": 5175,
        },
        target_dir=temp_workspace,
    )

    resolved_db_2 = resolve_database_path(start_dir=temp_workspace)
    assert resolved_db_2.resolve() == custom_db.resolve()
    assert resolved_db_1.resolve() == resolved_db_2.resolve()


def test_installation_isolation_and_instance_ids(temp_workspace):
    """Separate installation directories have distinct instance IDs and isolated data."""
    workspace_a = temp_workspace / "installation_a"
    workspace_b = temp_workspace / "installation_b"
    workspace_a.mkdir()
    workspace_b.mkdir()

    id_a = resolve_instance_id(workspace_a)
    id_b = resolve_instance_id(workspace_b)

    assert id_a.startswith("ar_inst_")
    assert id_b.startswith("ar_inst_")
    assert id_a != id_b, "Two distinct directory installations must have different instance IDs"

    # Initialize isolated databases in both
    db_a = workspace_a / "agentreliability.db"
    db_b = workspace_b / "agentreliability.db"

    with patch.dict(os.environ, {"AGENTRELIABILITY_DB": str(db_a)}):
        from app.database import init_db
        from app import auth_store, security

        init_db()
        auth_store.create_user("user_a@example.com", security.hash_password("PasswordA123!"), "User A")

    with patch.dict(os.environ, {"AGENTRELIABILITY_DB": str(db_b)}):
        from app.database import init_db
        from app import auth_store, security

        init_db()
        # Verify user_a does not exist in workspace B
        assert auth_store.get_user_by_email_with_hash("user_a@example.com") is None
        # User in workspace B
        auth_store.create_user("user_b@example.com", security.hash_password("PasswordB123!"), "User B")
        assert auth_store.get_user_by_email_with_hash("user_b@example.com") is not None


def test_backend_reuse_rejected_for_foreign_installation():
    """resolve_service_ports must refuse backend reuse when the active backend belongs to another installation."""
    with patch("agentreliability.ports.probe_backend") as mock_probe_backend, \
         patch("agentreliability.ports.probe_frontend") as mock_probe_frontend, \
         patch("agentreliability.ports.find_available_port") as mock_find_port:

        # Scenario 1: Port 8001 is running an AgentReliability instance from a DIFFERENT installation
        mock_probe_backend.return_value = {
            "occupied": True,
            "is_agentreliability": True,
            "compatible": False,  # Flagged incompatible because instance_id or db_path differed
            "same_installation": False,
            "details": "Separate AgentReliability instance active (ID: foreign_inst, DB: /tmp/foreign.db)",
        }
        mock_probe_frontend.return_value = {
            "occupied": False,
            "is_agentreliability": False,
        }
        mock_find_port.return_value = 8002

        b_port, reuse_b, f_port, reuse_f = resolve_service_ports(
            preferred_backend_port=8001,
            preferred_frontend_port=5174,
            expected_instance_id="my_inst_123",
            expected_db_path="/my/workspace/db.db",
        )

        assert b_port == 8002
        assert reuse_b is False, "Must NOT reuse foreign installation's backend"

        # Scenario 2: Port 8001 is running the SAME installation
        mock_probe_backend.return_value = {
            "occupied": True,
            "is_agentreliability": True,
            "compatible": True,
            "same_installation": True,
            "details": "Compatible AgentReliability backend running",
        }

        b_port, reuse_b, f_port, reuse_f = resolve_service_ports(
            preferred_backend_port=8001,
            preferred_frontend_port=5174,
            expected_instance_id="my_inst_123",
            expected_db_path="/my/workspace/db.db",
        )

        assert b_port == 8001
        assert reuse_b is True, "Should reuse backend from the same installation"


def test_database_import_and_migration(temp_workspace):
    """`agentreliability import-db` safely imports records from source to target database."""
    source_db = temp_workspace / "source.db"
    target_db = temp_workspace / "target.db"

    # 1. Populate source database
    with patch.dict(os.environ, {"AGENTRELIABILITY_DB": str(source_db)}):
        from app.database import init_db, save_execution
        from app import auth_store, baseline_store, project_store, security, test_store, trace_store

        init_db()
        test_store.init_tables()
        trace_store.init_tables()

        u = auth_store.create_user("migrated@example.com", security.hash_password("MigratedPass123!"), "Migrated Dev")
        p, p_key = project_store.create_project("Migrated Project", owner_id=u["id"])

        save_execution(
            log={"agent_name": "SupportBot", "steps": [{"step": 1}]},
            analysis={"status": "success", "findings": []},
            project_id=p["id"],
        )

        baseline_store.create_baseline(
            project_id=p["id"],
            agent_name="SupportBot",
            name="Production Golden Baseline",
            description="Golden baseline for support",
            source_type="trace",
            source_id="tr_migrated_001",
            status="success",
            duration_ms=120.0,
            input_val={"issue": "login issue"},
            output_val={"resolution": "reset password"},
            tools=[],
            expected={},
        )

    # 2. Test Dry Run on empty target
    success_dry, msg_dry, counts_dry = import_database(
        source_path=source_db,
        target_path=target_db,
        dry_run=True,
    )
    assert success_dry is True
    assert "Dry-run" in msg_dry
    assert counts_dry.get("users", 0) >= 1
    assert counts_dry.get("projects", 0) >= 1
    assert counts_dry.get("baselines", 0) >= 1

    # Verify target has 0 users committed after dry-run
    with patch.dict(os.environ, {"AGENTRELIABILITY_DB": str(target_db)}):
        assert auth_store.get_user_by_email_with_hash("migrated@example.com") is None

    # 3. Test Full Import
    success, msg, counts = import_database(
        source_path=source_db,
        target_path=target_db,
        dry_run=False,
    )
    assert success is True
    assert counts.get("users", 0) >= 1
    assert counts.get("projects", 0) >= 1
    assert counts.get("baselines", 0) >= 1
    assert counts.get("executions", 0) >= 1

    # 4. Verify target database now contains the migrated user and project
    with patch.dict(os.environ, {"AGENTRELIABILITY_DB": str(target_db)}):
        migrated_user = auth_store.get_user_by_email_with_hash("migrated@example.com")
        assert migrated_user is not None
        assert migrated_user["name"] == "Migrated Dev"

        # User can authenticate with original password
        assert security.verify_password("MigratedPass123!", migrated_user["password_hash"]) is True

        # Projects exist
        projects = project_store.list_user_projects(migrated_user["id"])
        assert len(projects) >= 1
        assert any(proj["name"] == "Migrated Project" for proj in projects)

        # Baseline exists
        baselines = baseline_store.list_baselines(project_id=projects[0]["id"])
        assert len(baselines) >= 1

    # 5. Idempotent re-import (should not duplicate or fail)
    success_re, _, counts_re = import_database(
        source_path=source_db,
        target_path=target_db,
        dry_run=False,
    )
    assert success_re is True
    assert counts_re.get("users", 0) == 0, "No duplicate users should be added on re-import"


def test_cli_import_db_action(temp_workspace, capsys):
    """Test `run_import_db` function outputs friendly summary."""
    source_db = temp_workspace / "source_cli.db"
    target_db = temp_workspace / "target_cli.db"

    with patch.dict(os.environ, {"AGENTRELIABILITY_DB": str(source_db)}):
        from app.database import init_db
        from app import auth_store, security

        init_db()
        auth_store.create_user("cli_user@test.com", security.hash_password("Pass12345!"), "CLI User")

    code = run_import_db(source=str(source_db), target=str(target_db))
    assert code == 0

    captured = capsys.readouterr()
    assert "Database Import & Migration" in captured.out
    assert "Imported Records Summary:" in captured.out
    assert "Users" in captured.out
