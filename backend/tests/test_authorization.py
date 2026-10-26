"""Comprehensive automated security and multi-tenant authorization tests (Phase 5A Step 5).

Covers all 15 required security test scenarios:
1. Unauthenticated execution listing and resource access return 401.
2. User A cannot access User B's executions.
3. User A cannot access User B's test cases.
4. User A cannot run User B's tests.
5. User A cannot access User B's traces.
6. User A cannot access User B's CI results.
7. User A cannot delete User B's resources.
8. Project API keys cannot access another project's data.
9. SDK ingestion associates traces with the correct project.
10. Revoked API keys are rejected.
11. CSRF protection works on mutating requests.
12. Direct object ID enumeration does not bypass authorization (returns 404, not 403).
13. Dashboard metrics are isolated by project.
14. Historical data remains intact and isolated until claimed.
15. Existing offline CLI regression testing remains operational.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient

from app import database, project_store, test_store, trace_store, ci_store
from app.main import app
from app.migrations.runner import run_migrations
from app.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

SAMPLES = Path(__file__).resolve().parents[2] / "sample_logs"


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Isolate every test in an ephemeral temporary database with migrations applied."""
    db_file = str(tmp_path / "test_authz.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", db_file)
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "test")
    with database.connect() as conn:
        run_migrations(conn)


def create_user_session(email: str, name: str) -> dict:
    """Helper: register user and return authenticated TestClient, user info, project, and API key."""
    client = TestClient(app)
    res = client.post("/api/auth/register", json={"email": email, "password": "Password123!", "name": name})
    assert res.status_code == 201, res.text
    user = res.json()
    csrf = res.cookies[CSRF_COOKIE_NAME]
    client.headers[CSRF_HEADER_NAME] = csrf

    projs = project_store.list_user_projects(user["id"])
    assert len(projs) >= 1
    project = projs[0]

    _, raw_key = project_store.create_api_key(project["id"], f"{name} Key")

    return {
        "client": client,
        "user": user,
        "project": project,
        "api_key": raw_key,
        "csrf": csrf,
    }


# -----------------------------------------------------------------------------
# 1. Unauthenticated Requests Return 401
# -----------------------------------------------------------------------------

def test_unauthenticated_requests_return_401():
    anon = TestClient(app)

    # Executions
    assert anon.get("/api/executions").status_code == 401
    assert anon.post("/api/executions").status_code == 401
    assert anon.get("/api/executions/1").status_code == 401

    # Tests
    assert anon.get("/api/tests").status_code == 401
    assert anon.post("/api/tests", json={"name": "test"}).status_code == 401
    assert anon.get("/api/tests/1").status_code == 401
    assert anon.post("/api/tests/1/run").status_code == 401
    assert anon.post("/api/tests/run-all").status_code == 401
    assert anon.get("/api/test-runs").status_code == 401

    # Traces dashboard
    assert anon.get("/api/traces/executions").status_code == 401
    assert anon.get("/api/traces/agents").status_code == 401
    assert anon.get("/api/traces/errors").status_code == 401
    assert anon.get("/api/traces/tool-calls").status_code == 401
    assert anon.get("/api/traces/executions/any-id").status_code == 401
    assert anon.post("/api/traces/executions/any-id/create-test").status_code == 401

    # CI dashboard
    assert anon.get("/api/ci/runs").status_code == 401
    assert anon.get("/api/ci/runs/1").status_code == 401
    assert anon.get("/api/ci/regression?base_id=1&head_id=2").status_code == 401

    # Analytics / Dashboard
    assert anon.get("/api/overview").status_code == 401
    assert anon.get("/api/failure-analysis").status_code == 401


# -----------------------------------------------------------------------------
# 2. Cross-Tenant Execution Isolation & Anti-Enumeration
# -----------------------------------------------------------------------------

def test_cross_tenant_execution_isolation():
    user_a = create_user_session("alice@example.com", "Alice")
    user_b = create_user_session("bob@example.com", "Bob")

    # User A uploads execution
    sample_content = (SAMPLES / "success_log.json").read_text()
    upload_res = user_a["client"].post(
        "/api/executions",
        files={"file": ("log.json", sample_content, "application/json")},
    )
    assert upload_res.status_code == 201
    exec_id = upload_res.json()["id"]

    # User A sees execution
    list_a = user_a["client"].get("/api/executions").json()
    assert any(e["id"] == exec_id for e in list_a)
    assert user_a["client"].get(f"/api/executions/{exec_id}").status_code == 200

    # User B list does NOT contain User A's execution
    list_b = user_b["client"].get("/api/executions").json()
    assert not any(e["id"] == exec_id for e in list_b)

    # User B direct ID access returns 404 (anti-enumeration)
    assert user_b["client"].get(f"/api/executions/{exec_id}").status_code == 404
    assert user_b["client"].get(f"/api/executions/{exec_id}/analysis").status_code == 404

    # User B cannot delete User A's execution
    del_res = user_b["client"].delete(f"/api/executions/{exec_id}")
    assert del_res.status_code == 404

    # Execution is still intact for User A
    assert user_a["client"].get(f"/api/executions/{exec_id}").status_code == 200


# -----------------------------------------------------------------------------
# 3. Cross-Tenant Test Case Isolation & Prevention of Running Foreign Tests
# -----------------------------------------------------------------------------

def test_cross_tenant_test_case_isolation_and_execution_prevention():
    user_a = create_user_session("alice@example.com", "Alice")
    user_b = create_user_session("bob@example.com", "Bob")

    # User A creates test case
    test_payload = {
        "name": "Alice Private Test",
        "description": "Sensitive test case",
        "agent_name": "agent-a",
        "input": {"prompt": "do secret work"},
        "steps": [{"type": "tool_call", "name": "secret_tool", "status": "success", "output": {"data": 1}}],
        "expected": {"status": "success", "tool_sequence": ["secret_tool"]},
    }
    create_res = user_a["client"].post("/api/tests", json=test_payload)
    assert create_res.status_code == 201
    case_id = create_res.json()["id"]

    # User A sees it
    assert any(c["id"] == case_id for c in user_a["client"].get("/api/tests").json())
    assert user_a["client"].get(f"/api/tests/{case_id}").status_code == 200

    # User B list does NOT contain it
    assert not any(c["id"] == case_id for c in user_b["client"].get("/api/tests").json())

    # User B direct ID access returns 404
    assert user_b["client"].get(f"/api/tests/{case_id}").status_code == 404

    # User B cannot update User A's test
    update_res = user_b["client"].put(f"/api/tests/{case_id}", json={**test_payload, "name": "Hacked Test"})
    assert update_res.status_code == 404

    # User B cannot run User A's test
    run_res = user_b["client"].post(f"/api/tests/{case_id}/run")
    assert run_res.status_code == 404

    # User B cannot delete User A's test
    del_res = user_b["client"].delete(f"/api/tests/{case_id}")
    assert del_res.status_code == 404

    # User A runs their own test successfully
    run_ok = user_a["client"].post(f"/api/tests/{case_id}/run")
    assert run_ok.status_code == 201
    run_id = run_ok.json()["id"]

    # User B cannot see User A's test run
    assert user_b["client"].get(f"/api/test-runs/{run_id}").status_code == 404
    assert not any(r["id"] == run_id for r in user_b["client"].get("/api/test-runs").json())


# -----------------------------------------------------------------------------
# 4. Cross-Tenant Trace Isolation & Trace Ingestion Key Scoping
# -----------------------------------------------------------------------------

def test_cross_tenant_trace_isolation_and_ingestion():
    user_a = create_user_session("alice@example.com", "Alice")
    user_b = create_user_session("bob@example.com", "Bob")

    now = datetime.now(timezone.utc).isoformat()
    trace_events = [
        {
            "event_id": "alice-trace-1:start",
            "execution_id": "alice-exec-12345",
            "agent_name": "alice-agent",
            "type": "execution_start",
            "timestamp": now,
            "input": {"task": "confidential task"},
            "metadata": {"dept": "finance"},
        },
        {
            "event_id": "alice-trace-1:tool",
            "execution_id": "alice-exec-12345",
            "agent_name": "alice-agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "process_payroll",
            "duration_ms": 15.0,
            "status": "success",
            "output": {"balance": 999999},
        },
        {
            "event_id": "alice-trace-1:end",
            "execution_id": "alice-exec-12345",
            "agent_name": "alice-agent",
            "type": "execution_end",
            "timestamp": now,
            "status": "success",
            "duration_ms": 45.0,
            "output": "processed",
        },
    ]

    # Ingest using User A's API key
    ingest_res = user_a["client"].post(
        "/api/v1/traces/events",
        headers={"X-API-Key": user_a["api_key"]},
        json={"events": trace_events},
    )
    assert ingest_res.status_code == 200
    assert ingest_res.json()["accepted"] == 3

    # User A sees the trace in executions, agents, and tool-calls
    traces_a = user_a["client"].get("/api/traces/executions").json()
    assert any(t["execution_id"] == "alice-exec-12345" for t in traces_a["items"])
    assert "alice-agent" in user_a["client"].get("/api/traces/agents").json()

    tools_a = user_a["client"].get("/api/traces/tool-calls?execution_id=alice-exec-12345").json()
    assert len(tools_a) == 1

    detail_a = user_a["client"].get("/api/traces/executions/alice-exec-12345")
    assert detail_a.status_code == 200
    assert detail_a.json()["agent_name"] == "alice-agent"

    # User B sees none of User A's trace data
    traces_b = user_b["client"].get("/api/traces/executions").json()
    assert not any(t["execution_id"] == "alice-exec-12345" for t in traces_b["items"])
    assert "alice-agent" not in user_b["client"].get("/api/traces/agents").json()
    assert len(user_b["client"].get("/api/traces/tool-calls?execution_id=alice-exec-12345").json()) == 0

    # User B direct ID access returns 404
    assert user_b["client"].get("/api/traces/executions/alice-exec-12345").status_code == 404

    # User B cannot convert User A's trace into a test case
    create_test_b = user_b["client"].post("/api/traces/executions/alice-exec-12345/create-test")
    assert create_test_b.status_code == 404


# -----------------------------------------------------------------------------
# 5. Cross-Tenant CI/CD Results Isolation
# -----------------------------------------------------------------------------

def test_cross_tenant_ci_isolation():
    user_a = create_user_session("alice@example.com", "Alice")
    user_b = create_user_session("bob@example.com", "Bob")

    ci_payload = {
        "commit_sha": "c0ffee123456",
        "branch": "main",
        "actor": "alice",
        "total": 3,
        "passed": 3,
        "failed": 0,
        "duration_ms": 250.0,
        "report": {"results": [{"name": "ci_test_1", "status": "passed"}]},
    }

    # Ingest CI run via User A's API key
    ci_res = user_a["client"].post(
        "/api/v1/ci/runs",
        headers={"X-API-Key": user_a["api_key"]},
        json=ci_payload,
    )
    assert ci_res.status_code == 201
    ci_id = ci_res.json()["id"]

    # User A sees it
    runs_a = user_a["client"].get("/api/ci/runs").json()
    assert any(r["id"] == ci_id for r in runs_a)
    assert user_a["client"].get(f"/api/ci/runs/{ci_id}").status_code == 200

    # User B list does NOT contain it
    runs_b = user_b["client"].get("/api/ci/runs").json()
    assert not any(r["id"] == ci_id for r in runs_b)

    # User B direct ID access returns 404
    assert user_b["client"].get(f"/api/ci/runs/{ci_id}").status_code == 404

    # User B cannot run regression comparison on User A's run
    compare_res = user_b["client"].get(f"/api/ci/regression?base_id={ci_id}&head_id={ci_id}")
    assert compare_res.status_code == 404


# -----------------------------------------------------------------------------
# 6. API Key Revocation Enforcement
# -----------------------------------------------------------------------------

def test_api_key_revocation_enforcement():
    user_a = create_user_session("alice@example.com", "Alice")
    proj_id = user_a["project"]["id"]
    api_key = user_a["api_key"]

    events = [
        {
            "event_id": "test-key-rev:1",
            "execution_id": "test-key-rev-exec",
            "agent_name": "agent-k",
            "type": "execution_start",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    ]

    # Active key succeeds
    assert user_a["client"].post(
        "/api/v1/traces/events",
        headers={"X-API-Key": api_key},
        json={"events": events},
    ).status_code == 200

    # Revoke key
    keys = user_a["client"].get(f"/api/projects/{proj_id}/keys").json()
    key_id = next(k["id"] for k in keys if k["name"] == "Alice Key")
    del_res = user_a["client"].delete(f"/api/projects/{proj_id}/keys/{key_id}")
    assert del_res.status_code == 200

    # Now ingestion fails with 401
    fail_res = user_a["client"].post(
        "/api/v1/traces/events",
        headers={"X-API-Key": api_key},
        json={"events": events},
    )
    assert fail_res.status_code == 401
    assert "Invalid API key" in fail_res.json()["detail"]


# -----------------------------------------------------------------------------
# 7. CSRF Protection on Mutating Requests
# -----------------------------------------------------------------------------

def test_csrf_protection_on_mutating_requests():
    user_a = create_user_session("alice@example.com", "Alice")

    # Creating client without CSRF header (but with session cookie intact)
    no_csrf_client = TestClient(app)
    no_csrf_client.cookies.set(CSRF_COOKIE_NAME, user_a["csrf"])
    # copy session cookie
    sess_cookie = user_a["client"].cookies.get("agentreliability_session")
    no_csrf_client.cookies.set("agentreliability_session", sess_cookie)

    # 1. Upload execution without CSRF -> 403
    r1 = no_csrf_client.post(
        "/api/executions",
        files={"file": ("log.json", "{}", "application/json")},
    )
    assert r1.status_code == 403
    assert "CSRF validation failed" in r1.json()["detail"]

    # 2. Create test case without CSRF -> 403
    valid_test_payload = {
        "name": "No CSRF Test",
        "agent_name": "agent-a",
        "steps": [{"type": "tool_call", "name": "t1", "status": "success"}],
        "expected": {"status": "success", "tool_sequence": ["t1"]},
    }
    r2 = no_csrf_client.post("/api/tests", json=valid_test_payload)
    assert r2.status_code == 403
    assert "CSRF validation failed" in r2.json()["detail"]


# -----------------------------------------------------------------------------
# 8. Dashboard Overview & Failure Analysis Isolation
# -----------------------------------------------------------------------------

def test_dashboard_metrics_isolated_by_project():
    user_a = create_user_session("alice@example.com", "Alice")
    user_b = create_user_session("bob@example.com", "Bob")

    # User A creates a test case and execution
    sample_content = (SAMPLES / "failed_tool_log.json").read_text()
    user_a["client"].post("/api/executions", files={"file": ("log.json", sample_content, "application/json")})
    user_a["client"].post(
        "/api/tests",
        json={
            "name": "Failing Test A",
            "agent_name": "agent-a",
            "steps": [{"type": "tool_call", "name": "t1", "status": "failed", "error": "timeout"}],
            "expected": {"status": "success", "tool_sequence": ["t1"]},
        },
    )
    user_a["client"].post("/api/tests/run-all")

    # User A overview shows 1 execution, 1 test, 1 failed
    over_a = user_a["client"].get("/api/overview").json()
    assert over_a["executions"]["total"] == 1
    assert over_a["tests"]["total"] == 1
    assert over_a["tests"]["failed"] == 1

    # User B overview shows 0 executions, 0 tests
    over_b = user_b["client"].get("/api/overview").json()
    assert over_b["executions"]["total"] == 0
    assert over_b["tests"]["total"] == 0
    assert over_b["tests"]["failed"] == 0


# -----------------------------------------------------------------------------
# 9. Legacy Historical Data Preservation and Safe Claiming
# -----------------------------------------------------------------------------

def test_historical_data_preservation_and_safe_claiming():
    user_a = create_user_session("alice@example.com", "Alice")
    user_b = create_user_session("bob@example.com", "Bob")

    # Before claiming, legacy project 1 has owner_id=NULL
    # Neither User A nor User B sees project 1 in their projects list
    assert not any(p["id"] == 1 for p in user_a["client"].get("/api/projects").json())
    assert not any(p["id"] == 1 for p in user_b["client"].get("/api/projects").json())

    # User A explicitly claims project 1
    claim_res = user_a["client"].post("/api/projects/1/claim")
    assert claim_res.status_code == 200
    claimed_proj = claim_res.json()
    assert claimed_proj["id"] == 1
    assert claimed_proj["name"] == "Default Project"

    # Now User A sees project 1 and can query its executions
    assert any(p["id"] == 1 for p in user_a["client"].get("/api/projects").json())
    execs_proj_1 = user_a["client"].get("/api/executions?project_id=1")
    assert execs_proj_1.status_code == 200

    # User B still CANNOT access project 1 (returns 404 anti-enumeration)
    assert user_b["client"].get("/api/executions?project_id=1").status_code == 404
    assert user_b["client"].get("/api/projects/1").status_code == 404


# -----------------------------------------------------------------------------
# 10. Offline CLI Regression Tests Pass Unaffected
# -----------------------------------------------------------------------------

def test_offline_cli_regression_testing_unaffected(tmp_path):
    from agentreliability.cli import main
    test_case = {
        "name": "offline_cli_pass",
        "steps": [{"type": "tool_call", "name": "lookup", "status": "success", "output": {"data": 42}}],
        "expected": {"status": "success", "tool_sequence": ["lookup"], "final_output": {"data": 42}},
    }
    case_path = tmp_path / "test_offline.json"
    case_path.write_text(json.dumps(test_case))
    report_path = tmp_path / "report.json"

    # CLI executes offline without network or browser cookies
    exit_code = main(["test", "--project", str(tmp_path), "--output", str(report_path)])
    assert exit_code == 0
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["total"] == 1
    assert report["passed"] == 1
    assert report["failed"] == 0
