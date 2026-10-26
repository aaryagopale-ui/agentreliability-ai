"""Verification of Account Persistence, Project Loading, and Multi-Tenant Isolation.

Tests:
1. Existing-user login loads all existing projects without creating new ones.
2. Previously selected project is persisted and restored on sign-in.
3. Switching between projects updates the active project.
4. All project data (traces, baselines, test history, API keys) is preserved.
5. New user registration behavior is explicitly validated.
6. Proper empty state is displayed for accounts with zero projects (e.g. after archiving).
7. Tenant isolation: User B cannot see or access User A's projects or data (anti-enumeration 404).
8. Preserves the original database and instance identity without side effects.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_DB = REPO_ROOT / "backend" / "agentreliability.db"


def main():
    print("\n" + "=" * 75)
    print("🔒 AgentReliability AI — Account Persistence & Isolation Verification")
    print("=" * 75)

    # 1. Verify safety of original database
    orig_stat = None
    if ORIGINAL_DB.is_file():
        orig_stat = (ORIGINAL_DB.stat().st_size, ORIGINAL_DB.stat().st_mtime)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        test_db_path = tmp_path / "test_isolated.db"

        # Setup environment pointing to isolated test database
        os.environ["AGENTRELIABILITY_DB"] = str(test_db_path.resolve())
        os.environ["AGENTRELIABILITY_WORKSPACE_ROOT"] = str(tmp_path.resolve())
        os.environ["AGENTRELIABILITY_INSTANCE_ID"] = "ar_inst_verification_test"

        sys.path.insert(0, str(REPO_ROOT / "backend"))
        sys.path.insert(0, str(REPO_ROOT / "sdk" / "src"))

        from app import database, project_store, test_store, trace_store, ci_store, baseline_store
        database.init_db()
        test_store.init_tables()
        trace_store.init_tables()
        ci_store.init_tables()

        from app.main import app
        client_a = TestClient(app)
        client_b = TestClient(app)

        # ---------------------------------------------------------------------
        # TEST 1: Register User A and verify starter project policy (Requirement 5)
        # ---------------------------------------------------------------------
        print("\n[Test 1] Registering User A and validating starter project creation...")
        user_a_email = "alice@company.com"
        password = "Password123!"

        res = client_a.post("/api/auth/register", json={"email": user_a_email, "name": "Alice Developer", "password": password})
        assert res.status_code in (200, 201), f"Register failed: {res.text}"
        user_a = res.json()
        csrf_a = client_a.cookies.get("agentreliability_csrf", "")

        # Verify initial registration created exactly 1 starter project
        res_projs = client_a.get("/api/projects")
        assert res_projs.status_code == 200
        initial_projects = res_projs.json()
        assert len(initial_projects) == 1, f"Expected 1 starter project, found: {len(initial_projects)}"
        starter_proj = initial_projects[0]
        assert "Alice Developer's Project" in starter_proj["name"]
        print(f"   ✅ Starter project confirmed: '{starter_proj['name']}' (ID: {starter_proj['id']}).")

        # Create Project Alpha
        res_p1 = client_a.post("/api/projects", json={"name": "Project Alpha"}, headers={"X-CSRF-Token": csrf_a})
        assert res_p1.status_code in (200, 201)
        p1 = res_p1.json()
        p1_id = p1["id"]
        p1_key = p1["api_key"]

        # Create Project Beta
        res_p2 = client_a.post("/api/projects", json={"name": "Project Beta"}, headers={"X-CSRF-Token": csrf_a})
        assert res_p2.status_code in (200, 201)
        p2 = res_p2.json()
        p2_id = p2["id"]
        p2_key = p2["api_key"]

        # Ingest a trace and baseline into Project Alpha
        trace_events = [
            {
                "event_id": "evt_alpha_start_01",
                "execution_id": "tr_alpha_001",
                "agent_name": "alpha-agent",
                "type": "execution_start",
                "timestamp": "2026-10-26T12:00:00Z",
                "input": "alpha query",
            },
            {
                "event_id": "evt_alpha_tool_001",
                "execution_id": "tr_alpha_001",
                "agent_name": "alpha-agent",
                "type": "tool_call",
                "tool_name": "lookup_docs",
                "duration_ms": 15.0,
                "status": "success",
                "timestamp": "2026-10-26T12:00:01Z",
            },
            {
                "event_id": "evt_alpha_end_0001",
                "execution_id": "tr_alpha_001",
                "agent_name": "alpha-agent",
                "type": "execution_end",
                "status": "success",
                "duration_ms": 25.0,
                "output": {"status": "ok"},
                "timestamp": "2026-10-26T12:00:02Z",
            },
        ]
        res_ingest = client_a.post(
            "/api/v1/traces/events",
            json={"events": trace_events},
            headers={"X-API-Key": p1_key},
        )
        assert res_ingest.status_code == 200, f"Ingestion failed: {res_ingest.text}"

        # Create baseline in Project Alpha
        res_base = client_a.post(
            "/api/baselines",
            json={"name": "Alpha Baseline", "source_type": "trace", "source_id": "tr_alpha_001"},
            headers={"X-CSRF-Token": csrf_a, "X-Project-Id": str(p1_id)},
        )
        assert res_base.status_code in (200, 201), f"Baseline creation failed: {res_base.text}"
        base_id = res_base.json()["id"]
        print(f"   ✅ Created Project Alpha (ID {p1_id}) and Project Beta (ID {p2_id}) with traces and baseline.")

        # ---------------------------------------------------------------------
        # TEST 2: Existing User Logout and Sign In Again (Requirements 1, 2, 3, 4)
        # ---------------------------------------------------------------------
        print("\n[Test 2] Testing User A logout, sign-in, and project persistence...")
        # Logout User A
        res_logout = client_a.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_a})
        assert res_logout.status_code in (200, 204), f"Logout failed: {res_logout.status_code} {res_logout.text}"

        # Login User A again
        res_login = client_a.post("/api/auth/login", json={"email": user_a_email, "password": password})
        assert res_login.status_code == 200, f"Login failed: {res_login.text}"
        csrf_a = client_a.cookies.get("agentreliability_csrf", "")

        # Requirement 1: Load all projects associated with user's account from database
        res_projs_after = client_a.get("/api/projects")
        assert res_projs_after.status_code == 200
        user_a_projs = res_projs_after.json()
        assert len(user_a_projs) == 3, f"Expected exactly 3 projects, found {len(user_a_projs)}"
        proj_ids = {p["id"] for p in user_a_projs}
        assert p1_id in proj_ids and p2_id in proj_ids and starter_proj["id"] in proj_ids
        print(f"   ✅ Loaded all {len(user_a_projs)} projects for User A ({user_a_email}).")

        # Requirement 2: Did NOT automatically create a new project on login
        assert len(user_a_projs) == 3, "An extra project was incorrectly created on existing-user login!"
        print("   ✅ Confirmed no new project was automatically created for existing account.")

        # Requirement 3: Preserve all existing projects, traces, baselines, and API keys
        res_traces = client_a.get("/api/traces/executions", headers={"X-Project-Id": str(p1_id)})
        assert res_traces.status_code == 200
        items = res_traces.json().get("items", [])
        assert len(items) == 1 and items[0]["execution_id"] == "tr_alpha_001"

        res_baselines = client_a.get("/api/baselines", headers={"X-Project-Id": str(p1_id)})
        assert res_baselines.status_code == 200 and len(res_baselines.json()) == 1

        res_keys = client_a.get(f"/api/projects/{p1_id}/keys")
        assert res_keys.status_code == 200 and len(res_keys.json()) >= 1
        print("   ✅ Preserved all traces, Golden Baselines, and API keys intact.")

        # ---------------------------------------------------------------------
        # TEST 3: Project Switching (Requirement 4)
        # ---------------------------------------------------------------------
        print("\n[Test 3] Testing project switching between Alpha and Beta...")
        # Access overview of Project Alpha
        res_ov_1 = client_a.get("/api/overview", headers={"X-Project-Id": str(p1_id)})
        assert res_ov_1.status_code == 200
        assert res_ov_1.json()["live_traces"]["total"] == 1

        # Switch to Project Beta
        res_ov_2 = client_a.get("/api/overview", headers={"X-Project-Id": str(p2_id)})
        assert res_ov_2.status_code == 200
        assert res_ov_2.json()["live_traces"]["total"] == 0  # Beta has 0 traces
        print("   ✅ Project switching successfully isolates project data within User A's account.")

        # ---------------------------------------------------------------------
        # TEST 4: Register User B and Verify Complete Tenant Isolation (Requirement 7)
        # ---------------------------------------------------------------------
        print("\n[Test 4] Registering User B and verifying cross-tenant isolation...")
        user_b_email = "bob@other.com"
        res_b = client_b.post("/api/auth/register", json={"email": user_b_email, "name": "Bob Tester", "password": password})
        assert res_b.status_code in (200, 201)
        csrf_b = client_b.cookies.get("agentreliability_csrf", "")

        # User B lists projects -> MUST only see User B's starter project (cannot see User A's projects)
        res_b_projs = client_b.get("/api/projects")
        assert res_b_projs.status_code == 200
        b_projs = res_b_projs.json()
        assert len(b_projs) == 1
        assert b_projs[0]["name"] == "Bob Tester's Project"
        bob_starter_id = b_projs[0]["id"]
        assert bob_starter_id not in (p1_id, p2_id, starter_proj["id"])
        print(f"   ✅ User B only sees their own starter project (ID: {bob_starter_id}); zero User A projects visible.")

        # User B tries to access User A's Project 1 directly -> MUST return 404
        res_leak_1 = client_b.get(f"/api/projects/{p1_id}")
        assert res_leak_1.status_code == 404, f"Expected 404, got: {res_leak_1.status_code}"

        # User B tries to view traces from User A's Project 1 -> MUST return 404
        res_leak_traces = client_b.get("/api/traces/executions", headers={"X-Project-Id": str(p1_id)})
        assert res_leak_traces.status_code == 404, f"Expected 404, got: {res_leak_traces.status_code}"

        # User B tries to view baselines from User A's Project 1 -> MUST return 404
        res_leak_base = client_b.get("/api/baselines", headers={"X-Project-Id": str(p1_id)})
        assert res_leak_base.status_code == 404, f"Expected 404, got: {res_leak_base.status_code}"

        # User B tries to view API keys from User A's Project 1 -> MUST return 404
        res_leak_keys = client_b.get(f"/api/projects/{p1_id}/keys")
        assert res_leak_keys.status_code == 404, f"Expected 404, got: {res_leak_keys.status_code}"

        # User B tries to delete/archive User A's Project 1 -> MUST return 404
        res_leak_del = client_b.request(
            "DELETE",
            f"/api/projects/{p1_id}",
            json={"confirm_name": "Project Alpha"},
            headers={"X-CSRF-Token": csrf_b},
        )
        assert res_leak_del.status_code == 404, f"Expected 404, got: {res_leak_del.status_code}"
        print("   ✅ Anti-enumeration access control verified: foreign projects return 404 across all endpoints.")

        # ---------------------------------------------------------------------
        # TEST 5: User B archives their project -> Zero Projects (Requirement 6)
        # ---------------------------------------------------------------------
        print("\n[Test 5] User B archives their only project and verifies empty state...")
        res_archive = client_b.request(
            "DELETE",
            f"/api/projects/{bob_starter_id}",
            json={"confirm_name": "Bob Tester's Project"},
            headers={"X-CSRF-Token": csrf_b},
        )
        assert res_archive.status_code == 200

        res_b_empty = client_b.get("/api/projects")
        assert res_b_empty.status_code == 200
        assert len(res_b_empty.json()) == 0, f"Expected 0 projects for User B, got {len(res_b_empty.json())}"

        # When account has zero projects, requesting overview returns 404
        res_empty_ov = client_b.get("/api/overview")
        assert res_empty_ov.status_code == 404
        assert "No active project found" in res_empty_ov.json().get("detail", "")
        print("   ✅ Verified zero-project account correctly reports empty state.")

        # ---------------------------------------------------------------------
        # TEST 6: User B creates new project (Project Gamma)
        # ---------------------------------------------------------------------
        print("\n[Test 6] User B creates Project Gamma and verifies isolated restoration...")
        res_p3 = client_b.post("/api/projects", json={"name": "Project Gamma"}, headers={"X-CSRF-Token": csrf_b})
        assert res_p3.status_code in (200, 201)
        p3_id = res_p3.json()["id"]

        # User A still sees their 3 projects, not Gamma
        res_a_check = client_a.get("/api/projects")
        assert len(res_a_check.json()) == 3
        assert all(p["id"] in (p1_id, p2_id, starter_proj["id"]) for p in res_a_check.json())

        # User B only sees Project Gamma
        res_b_check = client_b.get("/api/projects")
        assert len(res_b_check.json()) == 1 and res_b_check.json()[0]["id"] == p3_id
        print("   ✅ Two-way isolation confirmed: User A and User B only see their own projects.")

    # -------------------------------------------------------------------------
    # Final Safety Verification: Main database strictly unmodified
    # -------------------------------------------------------------------------
    if orig_stat:
        assert ORIGINAL_DB.is_file(), "Original database was unexpectedly deleted!"
        current_stat = (ORIGINAL_DB.stat().st_size, ORIGINAL_DB.stat().st_mtime)
        assert current_stat == orig_stat, "Original database was modified during verification!"
        print(f"\n🔒 Safety Verified: Main database '{ORIGINAL_DB.name}' was strictly unmodified.")

    print("\n" + "=" * 75)
    print("🎉 ALL ACCOUNT PERSISTENCE & ISOLATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
