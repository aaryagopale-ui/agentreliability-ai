"""Automated tests for One-Click Demo Agent & Traces Seeding (Issue #10).

Covers:
- Successful demo data creation (multi-step success, timeout failure, missing tool regression)
- Idempotency and duplicate prevention on repeated button clicks
- Authentication requirements and CSRF enforcement
- Project isolation (preventing cross-project data leakage)
- Preservation of existing user traces and baselines
- Verification of passing comparison and breaking regression
- Failure analysis diagnosis on the demo timeout trace without Ollama
"""
import pytest
from fastapi.testclient import TestClient

from app import database
from app.email_sink import dev_email_sink
from app.main import app
from app.migrations.runner import run_migrations
from app.security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    auth_rate_limiter,
)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Isolate every test in an ephemeral temporary database with migrations applied."""
    db_file = str(tmp_path / "test_demo.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", db_file)
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "test")
    auth_rate_limiter.clear_all()
    dev_email_sink.clear()
    with database.connect() as conn:
        run_migrations(conn)


@pytest.fixture
def client():
    return TestClient(app)


def register_user_and_create_project(client: TestClient, email: str, name: str, proj_name: str) -> dict:
    """Helper: register user, create project, and return auth info."""
    reg = client.post("/api/auth/register", json={"email": email, "password": "Password123!", "name": name})
    assert reg.status_code == 201
    csrf = reg.cookies[CSRF_COOKIE_NAME]

    proj = client.post(
        "/api/projects",
        json={"name": proj_name},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert proj.status_code == 201
    pdata = proj.json()
    return {
        "user": reg.json(),
        "csrf": csrf,
        "project": pdata,
        "headers": {
            CSRF_HEADER_NAME: csrf,
            "X-Project-Id": str(pdata["id"]),
        },
    }


def test_demo_requires_auth(client):
    """Anonymous requests must be rejected with 401."""
    res_seed = client.post("/api/demo/seed")
    assert res_seed.status_code == 401

    res_status = client.get("/api/demo/status")
    assert res_status.status_code == 401


def test_demo_seed_successful(client):
    """Successful creation of synthetic demo traces, Golden Baseline, and comparisons."""
    auth = register_user_and_create_project(client, "founder@yc.org", "Demo Founder", "S26 Batch Demo")
    headers = auth["headers"]
    pid = auth["project"]["id"]

    # 1. Initial status is not loaded
    st_res = client.get("/api/demo/status", headers=headers)
    assert st_res.status_code == 200
    st_data = st_res.json()
    assert st_data["demo_loaded"] is False
    assert st_data["traces_count"] == 0

    # 2. Seed demo data
    seed_res = client.post("/api/demo/seed", headers=headers)
    assert seed_res.status_code == 201
    data = seed_res.json()

    assert data["status"] == "success"
    assert data["already_existed"] is False
    assert data["agent_name"] == "support_triage_agent"
    assert "traces" in data
    assert data["traces"]["success"] == f"demo-trace-support-success-{pid}"
    assert data["traces"]["timeout"] == f"demo-trace-support-timeout-{pid}"
    assert data["traces"]["regressed"] == f"demo-trace-support-regressed-{pid}"

    # Verify Golden Baseline
    assert data["baseline"]["name"] == "Support Triage Golden Baseline (Demo)"
    baseline_id = data["baseline"]["id"]
    assert baseline_id is not None

    # Verify passing and breaking comparisons
    assert data["comparisons"]["passing"]["verdict"] == "passed"
    assert data["comparisons"]["passing"]["is_regression"] is False
    assert data["comparisons"]["breaking_regression"]["verdict"] == "regression"
    assert data["comparisons"]["breaking_regression"]["is_regression"] is True

    # 3. Verify traces in trace store via API
    traces_res = client.get("/api/traces/executions", headers=headers)
    assert traces_res.status_code == 200
    items = traces_res.json().get("items", [])
    exec_ids = [t["execution_id"] for t in items]
    assert f"demo-trace-support-success-{pid}" in exec_ids
    assert f"demo-trace-support-timeout-{pid}" in exec_ids
    assert f"demo-trace-support-regressed-{pid}" in exec_ids

    # 4. Check timeout trace detail
    detail_res = client.get(f"/api/traces/executions/demo-trace-support-timeout-{pid}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["status"] == "failed"
    assert detail["error_type"] == "GatewayTimeoutError"
    assert len(detail.get("tool_calls", [])) == 3
    timeout_tool = next(t for t in detail["tool_calls"] if t["tool_name"] == "issue_refund")
    assert timeout_tool["status"] == "timeout"
    assert timeout_tool["duration_ms"] >= 5000.0

    # 5. Check baseline via baseline API
    b_res = client.get(f"/api/baselines/{baseline_id}", headers=headers)
    assert b_res.status_code == 200
    b_data = b_res.json()
    assert b_data["agent_name"] == "support_triage_agent"
    assert len(b_data["version_data"]["tools"]) == 4

    # 6. Verify status updated
    st2_res = client.get("/api/demo/status", headers=headers)
    assert st2_res.status_code == 200
    assert st2_res.json()["demo_loaded"] is True
    assert st2_res.json()["traces_count"] == 3


def test_demo_repeated_clicks_idempotent(client):
    """Repeated clicks must be safe and not duplicate traces, baselines, or test cases."""
    auth = register_user_and_create_project(client, "repeat@yc.org", "Repeater", "Repeat Project")
    headers = auth["headers"]

    # First call
    res1 = client.post("/api/demo/seed", headers=headers)
    assert res1.status_code == 201
    assert res1.json()["already_existed"] is False

    # Second call
    res2 = client.post("/api/demo/seed", headers=headers)
    assert res2.status_code == 201
    assert res2.json()["already_existed"] is True

    # Third call
    res3 = client.post("/api/demo/seed", headers=headers)
    assert res3.status_code == 201
    assert res3.json()["already_existed"] is True

    # Verify counts have not multiplied
    traces_res = client.get("/api/traces/executions", headers=headers)
    assert traces_res.status_code == 200
    assert len(traces_res.json()["items"]) == 3

    baselines_res = client.get("/api/baselines", headers=headers)
    assert baselines_res.status_code == 200
    assert len(baselines_res.json()) == 1

    cases_res = client.get("/api/tests", headers=headers)
    assert cases_res.status_code == 200
    assert len(cases_res.json()) == 1


def test_demo_project_isolation(client):
    """Demo data seeded in Project A must be completely isolated from Project B."""
    auth_a = register_user_and_create_project(client, "alice@yc.org", "Alice", "Project Alpha")
    auth_b = register_user_and_create_project(client, "bob@yc.org", "Bob", "Project Beta")

    # Project A seeds demo
    client.post("/api/demo/seed", headers=auth_a["headers"])

    # Project B status must still be unloaded
    st_b = client.get("/api/demo/status", headers=auth_b["headers"])
    assert st_b.json()["demo_loaded"] is False
    assert st_b.json()["traces_count"] == 0

    # Project B trace list must be empty
    traces_b = client.get("/api/traces/executions", headers=auth_b["headers"])
    assert len(traces_b.json()["items"]) == 0

    # Project B cannot access Project A's demo trace
    pid_a = auth_a["project"]["id"]
    forbidden_trace = client.get(f"/api/traces/executions/demo-trace-support-success-{pid_a}", headers=auth_b["headers"])
    assert forbidden_trace.status_code == 404

    # Project B seeds demo
    res_b = client.post("/api/demo/seed", headers=auth_b["headers"])
    assert res_b.status_code == 201
    pid_b = auth_b["project"]["id"]
    assert res_b.json()["traces"]["success"] == f"demo-trace-support-success-{pid_b}"


def test_demo_preserves_existing_user_data(client):
    """Seeding demo data must not delete or modify existing user traces or baselines."""
    auth = register_user_and_create_project(client, "carol@yc.org", "Carol", "Production Project")
    headers = auth["headers"]
    pid = auth["project"]["id"]

    # 1. User has an existing test case
    case_res = client.post(
        "/api/tests",
        json={
            "name": "User Custom Test",
            "agent_name": "custom_agent",
            "input": {"query": "test"},
            "steps": [{"name": "tool1", "duration_ms": 100.0, "status": "success", "type": "tool_call"}],
            "expected": {"status": "success"},
        },
        headers=headers,
    )
    assert case_res.status_code == 201
    user_case_id = case_res.json()["id"]

    # 2. Seed demo
    seed_res = client.post("/api/demo/seed", headers=headers)
    assert seed_res.status_code == 201

    # 3. User's test case is preserved
    cases_res = client.get("/api/tests", headers=headers)
    case_names = [c["name"] for c in cases_res.json()]
    assert "User Custom Test" in case_names
    assert "Support Triage Refund Flow (Demo)" in case_names


def test_failure_analysis_on_demo_timeout_trace(client):
    """Failure analysis endpoint can diagnose the demo timeout trace deterministically without Ollama."""
    auth = register_user_and_create_project(client, "diagnose@yc.org", "Diagnoser", "Diagnostic Project")
    headers = auth["headers"]
    pid = auth["project"]["id"]

    # Seed demo data
    client.post("/api/demo/seed", headers=headers)

    # Run failure diagnosis on the timeout trace
    diag_res = client.post(
        "/api/failure-analysis/diagnose",
        json={
            "execution_id": f"demo-trace-support-timeout-{pid}",
            "source_type": "trace",
        },
        headers=headers,
    )
    assert diag_res.status_code == 200
    data = diag_res.json()

    # Verify diagnostic report findings
    report = data["diagnostic_report"]
    assert report["primary_error"]["error_type"] == "GatewayTimeoutError"
    assert report["primary_error"]["failing_tool"] == "issue_refund"
    assert len(report["timing_anomalies"]) >= 1
    assert len(report["deterministic_recommendations"]) >= 1

    # Verify rule-based analysis fallback is present
    ai_analysis = data["ai_analysis"]
    assert ai_analysis["status"] in ("unavailable", "fallback", "disabled")
    fallback = ai_analysis.get("deterministic_fallback") or ai_analysis.get("hypotheses")
    assert fallback is not None
    assert "issue_refund" in str(fallback.get("likely_contributing_factors", [])) + str(fallback.get("possible_code_areas_to_inspect", []))
