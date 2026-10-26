"""End-to-End User Journey and Multi-Tenant Security Verification (Phase 5A Step 7).

Tests the full 16-step developer lifecycle from registration through CI regression testing,
key revocation, and logout, followed by strict multi-tenant isolation verification.
"""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app import database, project_store
from app.main import app
from app.migrations.runner import run_migrations
from app.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from agentreliability.regression import compare_runs


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Run tests in an isolated ephemeral database with all migrations applied."""
    db_file = str(tmp_path / "test_e2e_journey.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", db_file)
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "test")
    with database.connect() as conn:
        run_migrations(conn)


def test_complete_16_step_user_journey_and_multi_tenant_isolation():
    client = TestClient(app)

    # =========================================================================
    # STEP 1: A new developer can register
    # =========================================================================
    reg_payload = {
        "email": "dev1@example.com",
        "password": "SecurePassword123!",
        "name": "Alice Developer",
    }
    reg_res = client.post("/api/auth/register", json=reg_payload)
    assert reg_res.status_code == 201, reg_res.text
    user_data = reg_res.json()
    assert user_data["email"] == "dev1@example.com"
    assert user_data["name"] == "Alice Developer"
    assert "id" in user_data
    assert "password" not in user_data
    assert "password_hash" not in user_data

    # Verify session cookie and CSRF token were issued
    assert CSRF_COOKIE_NAME in reg_res.cookies
    assert SESSION_COOKIE_NAME in reg_res.cookies
    csrf_token = reg_res.cookies[CSRF_COOKIE_NAME]
    auth_headers = {CSRF_HEADER_NAME: csrf_token}

    # =========================================================================
    # STEP 2: The developer can log in (tested with second fresh client)
    # =========================================================================
    login_client = TestClient(app)
    login_res = login_client.post(
        "/api/auth/login",
        json={"email": "dev1@example.com", "password": "SecurePassword123!"},
    )
    assert login_res.status_code == 200, login_res.text
    assert login_res.json()["email"] == "dev1@example.com"
    assert SESSION_COOKIE_NAME in login_res.cookies
    assert CSRF_COOKIE_NAME in login_res.cookies

    # =========================================================================
    # STEP 3: Authentication sessions work correctly
    # =========================================================================
    me_res = login_client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "dev1@example.com"
    assert me_res.json()["id"] == user_data["id"]

    # Use login_client with proper CSRF headers for subsequent requests
    client = login_client
    csrf_token = login_res.cookies[CSRF_COOKIE_NAME]
    auth_headers = {CSRF_HEADER_NAME: csrf_token}

    # =========================================================================
    # STEP 4: The developer can create a project
    # =========================================================================
    proj_res = client.post(
        "/api/projects",
        json={"name": "Customer Support Agent", "description": "Production LLM triage bot"},
        headers=auth_headers,
    )
    assert proj_res.status_code == 201, proj_res.text
    project_a = proj_res.json()
    assert project_a["name"] == "Customer Support Agent"
    assert project_a["id"] > 0
    project_a_id = project_a["id"]

    # Create a second project to test switching
    proj_res2 = client.post(
        "/api/projects",
        json={"name": "Code Review Agent", "description": "PR assistant"},
        headers=auth_headers,
    )
    assert proj_res2.status_code == 201
    project_b = proj_res2.json()
    project_b_id = project_b["id"]

    # =========================================================================
    # STEP 5: The developer can switch between projects
    # =========================================================================
    headers_proj_a = {**auth_headers, "X-Project-Id": str(project_a_id)}
    headers_proj_b = {**auth_headers, "X-Project-Id": str(project_b_id)}

    list_a = client.get("/api/executions", headers=headers_proj_a)
    assert list_a.status_code == 200
    assert list_a.json() == []

    list_b = client.get("/api/executions", headers=headers_proj_b)
    assert list_b.status_code == 200
    assert list_b.json() == []

    # =========================================================================
    # STEP 6: Developer generates API key & verifies plaintext is shown ONCE
    # =========================================================================
    key_res = client.post(
        f"/api/projects/{project_a_id}/keys",
        json={"name": "Prod Ingestion Key"},
        headers=auth_headers,
    )
    assert key_res.status_code == 201, key_res.text
    key_data = key_res.json()
    assert "api_key" in key_data
    assert key_data["api_key"].startswith("ar_live_") or key_data["api_key"].startswith("ag_")
    plaintext_key = key_data["api_key"]
    key_id = key_data["id"]

    # Subsequent GET must NOT show the plaintext key
    list_keys_res = client.get(f"/api/projects/{project_a_id}/keys", headers=auth_headers)
    assert list_keys_res.status_code == 200
    keys_list = list_keys_res.json()
    assert len(keys_list) >= 1
    found_key = next(k for k in keys_list if k["id"] == key_id)
    assert "api_key" not in found_key
    assert "plaintext_key" not in found_key
    assert "key_hash" not in found_key
    assert "key_prefix" in found_key

    # =========================================================================
    # STEP 7: AI Agent uses Python SDK to send execution traces via API key
    # =========================================================================
    sdk_client = TestClient(app)
    now = datetime.now(timezone.utc).isoformat()
    trace_events = [
        {
            "event_id": "journey-exec-1:start",
            "execution_id": "journey-exec-1",
            "agent_name": "support-agent",
            "type": "execution_start",
            "timestamp": now,
            "input": {"ticket_id": "TICK-101"},
            "metadata": {"environment": "production"},
        },
        {
            "event_id": "journey-exec-1:tool:1",
            "execution_id": "journey-exec-1",
            "agent_name": "support-agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "fetch_user_account",
            "duration_ms": 120.0,
            "status": "success",
            "output": {"status": "active", "tier": "enterprise"},
        },
        {
            "event_id": "journey-exec-1:end",
            "execution_id": "journey-exec-1",
            "agent_name": "support-agent",
            "type": "execution_end",
            "timestamp": now,
            "status": "success",
            "duration_ms": 450.0,
            "output": "Ticket resolved.",
        },
    ]

    trace_res = sdk_client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": plaintext_key},
        json={"events": trace_events},
    )
    assert trace_res.status_code == 200, trace_res.text
    assert trace_res.json()["accepted"] == 3

    # =========================================================================
    # STEP 8: Traces appear under the correct project in AgentReliability
    # =========================================================================
    traces_a_res = client.get("/api/traces/executions", headers=headers_proj_a)
    assert traces_a_res.status_code == 200
    traces_a = traces_a_res.json()["items"]
    assert len(traces_a) == 1
    assert traces_a[0]["execution_id"] == "journey-exec-1"

    # In Project B, traces must be empty
    traces_b_res = client.get("/api/traces/executions", headers=headers_proj_b)
    assert traces_b_res.status_code == 200
    assert len(traces_b_res.json()["items"]) == 0

    # =========================================================================
    # STEP 9: Turn an execution trace into a regression test case
    # =========================================================================
    gen_res = client.post(
        "/api/traces/executions/journey-exec-1/create-test",
        headers=headers_proj_a,
        json={"name": "Support Agent Resolution Test"},
    )
    assert gen_res.status_code == 201, gen_res.text
    test_case = gen_res.json()
    assert test_case["id"] > 0
    assert test_case["name"] == "Support Agent Resolution Test"
    assert test_case["agent_name"] == "support-agent"
    test_id = test_case["id"]

    # Verify test is listed in Project A but NOT in Project B
    tests_a = client.get("/api/tests", headers=headers_proj_a).json()
    assert any(t["id"] == test_id for t in tests_a)
    tests_b = client.get("/api/tests", headers=headers_proj_b).json()
    assert len(tests_b) == 0

    # =========================================================================
    # STEP 10: Test case can be replayed and evaluated
    # =========================================================================
    run_res = client.post(f"/api/tests/{test_id}/run", headers=headers_proj_a)
    assert run_res.status_code in (200, 201), run_res.text
    run_data = run_res.json()
    assert run_data["status"] == "passed"
    run_id = run_data["id"]

    # Test history reflects this run
    history_res = client.get(f"/api/test-runs?test_id={test_id}", headers=headers_proj_a)
    assert history_res.status_code == 200
    runs = history_res.json()
    assert len(runs) >= 1
    assert runs[0]["id"] == run_id
    assert runs[0]["status"] == "passed"

    # =========================================================================
    # STEP 11: Failure analysis correctly summarizes results
    # =========================================================================
    fa_res = client.get("/api/failure-analysis", headers=headers_proj_a)
    assert fa_res.status_code == 200
    fa_data = fa_res.json()
    assert "execution_findings" in fa_data
    assert "replay_mismatches" in fa_data
    assert len(fa_data["replay_mismatches"]) == 0

    # =========================================================================
    # STEP 12: Simulated CI run uploads test results under the project
    # =========================================================================
    ci_payload = {
        "commit_sha": "abc1234def5678",
        "branch": "main",
        "actor": "alice",
        "total": 1,
        "passed": 1,
        "failed": 0,
        "duration_ms": 115.0,
        "report": {
            "results": [
                {
                    "test_id": test_id,
                    "name": test_case["name"],
                    "status": "passed",
                }
            ]
        },
    }
    ci_res = client.post(
        "/api/v1/ci/runs",
        json=ci_payload,
        headers={"X-API-Key": plaintext_key},
    )
    assert ci_res.status_code == 201, ci_res.text
    ci_data = ci_res.json()
    ci_run_id = ci_data["id"]

    # Verify CI run shows in project A
    ci_list_a = client.get("/api/ci/runs", headers=headers_proj_a).json()
    assert any(c["id"] == ci_run_id for c in ci_list_a)

    # =========================================================================
    # STEP 13: CI regression comparison detects regressions vs baseline
    # =========================================================================
    baseline_runs = [
        {"name": test_case["name"], "status": "passed"}
    ]
    regressed_runs = [
        {
            "name": test_case["name"],
            "status": "failed",
            "error": "Unexpected tool call sequence",
        }
    ]
    diff = compare_runs(regressed_runs, baseline_runs)
    assert diff["has_baseline"] is True
    assert diff["counts"]["new_failures"] == 1
    assert diff["counts"]["fixed_failures"] == 0
    assert len(diff["summary"]["new_failures"]) == 1
    assert diff["summary"]["new_failures"][0]["name"] == test_case["name"]

    # =========================================================================
    # STEP 14: API key can be revoked and immediately stops accepting traces
    # =========================================================================
    revoke_res = client.delete(
        f"/api/projects/{project_a_id}/keys/{key_id}",
        headers=auth_headers,
    )
    assert revoke_res.status_code == 200, revoke_res.text
    assert "revoked successfully" in revoke_res.json()["message"]

    # Ingestion attempt with revoked key must immediately fail with HTTP 401
    bad_ingest = client.post(
        "/api/v1/traces/events",
        json={"events": trace_events},
        headers={"X-API-Key": plaintext_key},
    )
    assert bad_ingest.status_code == 401
    assert "revoked" in bad_ingest.json()["detail"].lower() or "invalid" in bad_ingest.json()["detail"].lower()

    # =========================================================================
    # STEP 15: Developer can log out safely
    # =========================================================================
    logout_res = client.post("/api/auth/logout", headers=auth_headers)
    assert logout_res.status_code == 200, logout_res.text
    assert "Logged out successfully" in logout_res.json()["message"]

    # Session cookie must be cleared/expired in response
    assert client.cookies.get(SESSION_COOKIE_NAME) is None or logout_res.headers.get("set-cookie", "")

    # =========================================================================
    # STEP 16: Unauthenticated requests are rejected
    # =========================================================================
    post_logout_me = client.get("/api/auth/me")
    assert post_logout_me.status_code == 401

    post_logout_exec = client.get("/api/executions")
    assert post_logout_exec.status_code == 401

    post_logout_tests = client.get("/api/tests")
    assert post_logout_tests.status_code == 401


def test_cross_tenant_isolation_and_anti_enumeration():
    """Verify strict multi-tenant boundary between User A and User B."""
    now = datetime.now(timezone.utc).isoformat()

    # Setup User A
    client_a = TestClient(app)
    res_a = client_a.post(
        "/api/auth/register",
        json={"email": "alpha@example.com", "password": "Password123!", "name": "Alpha Corp"},
    )
    assert res_a.status_code == 201
    csrf_a = res_a.cookies[CSRF_COOKIE_NAME]
    headers_a = {CSRF_HEADER_NAME: csrf_a}

    user_a = res_a.json()
    proj_a_list = project_store.list_user_projects(user_a["id"])
    proj_a_id = proj_a_list[0]["id"]
    headers_a_scoped = {**headers_a, "X-Project-Id": str(proj_a_id)}

    # User A creates an API key, trace, test case, and test run
    _, raw_key_a = project_store.create_api_key(proj_a_id, "Alpha Key")
    trace_events_a = [
        {
            "event_id": "alpha-exec-1:start",
            "execution_id": "alpha-exec-1",
            "agent_name": "alpha_agent",
            "type": "execution_start",
            "timestamp": now,
        },
        {
            "event_id": "alpha-exec-1:end",
            "execution_id": "alpha-exec-1",
            "agent_name": "alpha_agent",
            "type": "execution_end",
            "timestamp": now,
            "status": "success",
            "output": "done",
        },
    ]
    trace_res = client_a.post(
        "/api/v1/traces/events",
        json={"events": trace_events_a},
        headers={"X-API-Key": raw_key_a},
    )
    assert trace_res.status_code == 200

    test_res = client_a.post(
        "/api/traces/executions/alpha-exec-1/create-test",
        headers=headers_a_scoped,
        json={"name": "Alpha Test"},
    )
    assert test_res.status_code == 201
    test_a_id = test_res.json()["id"]

    run_res = client_a.post(f"/api/tests/{test_a_id}/run", headers=headers_a_scoped)
    assert run_res.status_code in (200, 201)
    run_a_id = run_res.json()["id"]

    # Setup User B
    client_b = TestClient(app)
    res_b = client_b.post(
        "/api/auth/register",
        json={"email": "beta@example.com", "password": "Password123!", "name": "Beta LLC"},
    )
    assert res_b.status_code == 201
    csrf_b = res_b.cookies[CSRF_COOKIE_NAME]
    headers_b = {CSRF_HEADER_NAME: csrf_b}

    user_b = res_b.json()
    proj_b_list = project_store.list_user_projects(user_b["id"])
    proj_b_id = proj_b_list[0]["id"]
    headers_b_scoped = {**headers_b, "X-Project-Id": str(proj_b_id)}

    # User B generates their own API key
    _, raw_key_b = project_store.create_api_key(proj_b_id, "Beta Key")

    # -------------------------------------------------------------------------
    # Verification: User B attempts to access User A's resources
    # -------------------------------------------------------------------------

    # 1. Access User A's project details directly -> 404 (Anti-enumeration)
    assert client_b.get(f"/api/projects/{proj_a_id}", headers=headers_b).status_code == 404

    # 2. Scope requests to User A's project using X-Project-Id header -> 404
    cross_scope_header = {**headers_b, "X-Project-Id": str(proj_a_id)}
    assert client_b.get("/api/tests", headers=cross_scope_header).status_code == 404
    assert client_b.get("/api/traces/executions", headers=cross_scope_header).status_code == 404
    assert client_b.get("/api/ci/runs", headers=cross_scope_header).status_code == 404

    # 3. Access User A's test case by ID -> 404
    assert client_b.get(f"/api/tests/{test_a_id}", headers=headers_b_scoped).status_code == 404

    # 4. Modify User A's test case -> 404
    assert client_b.put(
        f"/api/tests/{test_a_id}",
        json={"name": "Hacked Test"},
        headers=headers_b_scoped,
    ).status_code == 404

    # 5. Delete User A's test case -> 404
    assert client_b.delete(f"/api/tests/{test_a_id}", headers=headers_b_scoped).status_code == 404

    # 6. Execute replay on User A's test case -> 404
    assert client_b.post(f"/api/tests/{test_a_id}/run", headers=headers_b_scoped).status_code == 404

    # 7. View replay run details for User A's run -> 404
    assert client_b.get(f"/api/test-runs/{run_a_id}", headers=headers_b_scoped).status_code == 404

    # 8. Create test case from User A's trace -> 404
    assert client_b.post(
        "/api/traces/executions/alpha-exec-1/create-test",
        headers=headers_b_scoped,
        json={"name": "Steal Trace Test"},
    ).status_code == 404

    # 9. Ingest trace using User B's API key: verify it lands in Project B, not Project A
    trace_events_b = [
        {
            "event_id": "beta-exec-1:start",
            "execution_id": "beta-exec-1",
            "agent_name": "beta_agent",
            "type": "execution_start",
            "timestamp": now,
        },
        {
            "event_id": "beta-exec-1:end",
            "execution_id": "beta-exec-1",
            "agent_name": "beta_agent",
            "type": "execution_end",
            "timestamp": now,
            "status": "success",
            "output": "done",
        },
    ]
    trace_b = client_b.post(
        "/api/v1/traces/events",
        json={"events": trace_events_b},
        headers={"X-API-Key": raw_key_b},
    )
    assert trace_b.status_code == 200

    # User A sees only User A's traces
    traces_a = client_a.get("/api/traces/executions", headers=headers_a_scoped).json()["items"]
    assert any(t["execution_id"] == "alpha-exec-1" for t in traces_a)
    assert not any(t["execution_id"] == "beta-exec-1" for t in traces_a)

    # User B sees only User B's traces
    traces_b = client_b.get("/api/traces/executions", headers=headers_b_scoped).json()["items"]
    assert any(t["execution_id"] == "beta-exec-1" for t in traces_b)
    assert not any(t["execution_id"] == "alpha-exec-1" for t in traces_b)

    # 10. CSRF rejection on state-changing requests
    no_csrf_post = client_b.post("/api/projects", json={"name": "No CSRF"})
    assert no_csrf_post.status_code == 403
    bad_csrf_post = client_b.post(
        "/api/projects",
        json={"name": "Bad CSRF"},
        headers={CSRF_HEADER_NAME: "invalid-token-value"},
    )
    assert bad_csrf_post.status_code == 403
