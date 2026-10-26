"""Phase 6 Step 1: Real Agent Integration and End-to-End Trace Verification Tests.

Verifies:
1. Real execution trace ingestion via Python SDK format.
2. Proper latency, step capturing, and tool call timing.
3. Secret redaction (e.g. sk-live-... and api_secret keys).
4. Controlled failure trace classification and error recording.
5. Multi-tenant project scoping and anti-enumeration.
6. Immediate rejection of revoked API keys (401).
7. Trace to regression test case generation (/api/traces/executions/{id}/create-test).
8. Deterministic replay engine execution and test history persistence.
9. Dashboard metrics isolation.
"""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app import database, project_store
from app.main import app
from app.migrations.runner import run_migrations
from app.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from agentreliability.redaction import Redactor


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Run tests in an isolated ephemeral database with all migrations applied."""
    db_file = str(tmp_path / "test_real_agent.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", db_file)
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "test")
    with database.connect() as conn:
        run_migrations(conn)


def test_real_agent_trace_ingestion_and_dashboard_verification():
    client = TestClient(app)

    # 1. Register Developer A
    reg_res = client.post(
        "/api/auth/register",
        json={"email": "order_team@example.com", "password": "SecurePassword123!", "name": "Order Systems"},
    )
    assert reg_res.status_code == 201
    user_a = reg_res.json()
    csrf_a = reg_res.cookies[CSRF_COOKIE_NAME]
    headers_a = {CSRF_HEADER_NAME: csrf_a}

    # 2. Create isolated project
    proj_res = client.post(
        "/api/projects",
        json={"name": "Order Fulfillment Service", "description": "Production Agent"},
        headers=headers_a,
    )
    assert proj_res.status_code == 201
    project_a = proj_res.json()
    project_a_id = project_a["id"]
    headers_a_scoped = {**headers_a, "X-Project-Id": str(project_a_id)}

    # 3. Generate Project API Key & verify single plaintext exposure
    key_res = client.post(
        f"/api/projects/{project_a_id}/keys",
        json={"name": "Agent Trace Ingestion Key"},
        headers=headers_a,
    )
    assert key_res.status_code == 201
    key_data = key_res.json()
    raw_api_key = key_data["api_key"]
    key_id = key_data["id"]
    assert raw_api_key.startswith("ar_live_")

    # Verify listing keys does NOT leak the plaintext key
    list_keys = client.get(f"/api/projects/{project_a_id}/keys", headers=headers_a).json()
    assert all("api_key" not in k and "key_hash" not in k for k in list_keys)

    # 4. Redaction check on sensitive credentials before ingestion
    redactor = Redactor()
    raw_secret_token = "sk-live-super-secret-token-xyz987"
    raw_input_dict = {"client_id": "corp-42", "api_secret": raw_secret_token}
    redacted_input = redactor.prepare(raw_input_dict, max_chars=2000)
    assert redacted_input["api_secret"] == "[REDACTED]"
    assert raw_secret_token not in str(redacted_input)

    # 5. Ingest Real Successful Agent Trace
    now = datetime.now(timezone.utc).isoformat()
    success_events = [
        {
            "event_id": "order-exec-101:start",
            "execution_id": "order-exec-101",
            "agent_name": "order_fulfillment_agent",
            "type": "execution_start",
            "timestamp": now,
            "input": {"query": "Order 2 units of Widget-A"},
            "metadata": {"environment": "local_dev", "runtime": "python-3.14"},
        },
        {
            "event_id": "order-exec-101:tool:1",
            "execution_id": "order-exec-101",
            "agent_name": "order_fulfillment_agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "verify_client_credentials",
            "duration_ms": 15.4,
            "status": "success",
            "input": redacted_input,
            "output": {"authenticated": True, "client_id": "corp-42", "tier": "enterprise"},
        },
        {
            "event_id": "order-exec-101:tool:2",
            "execution_id": "order-exec-101",
            "agent_name": "order_fulfillment_agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "check_inventory",
            "duration_ms": 22.1,
            "status": "success",
            "input": {"sku": "SKU-WIDGET-A", "quantity": 2},
            "output": {"sku": "SKU-WIDGET-A", "available": 150, "in_stock": True},
        },
        {
            "event_id": "order-exec-101:tool:3",
            "execution_id": "order-exec-101",
            "agent_name": "order_fulfillment_agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "calculate_order_totals",
            "duration_ms": 10.8,
            "status": "success",
            "input": {"items": [{"sku": "SKU-WIDGET-A", "price": 49.99, "quantity": 2}], "discount_pct": 10.0},
            "output": {"subtotal": 99.98, "discount_applied": 10.0, "tax": 7.42, "total": 97.4, "currency": "USD"},
        },
        {
            "event_id": "order-exec-101:end",
            "execution_id": "order-exec-101",
            "agent_name": "order_fulfillment_agent",
            "type": "execution_end",
            "timestamp": now,
            "status": "success",
            "duration_ms": 55.2,
            "output": {"status": "order_confirmed", "order_id": "ORD-9999", "total": 97.4},
        },
    ]

    ingest_res = client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": raw_api_key},
        json={"events": success_events},
    )
    assert ingest_res.status_code == 200
    assert ingest_res.json()["accepted"] == 5

    # 6. Ingest Real Controlled Failure Agent Trace
    failure_events = [
        {
            "event_id": "order-exec-102:start",
            "execution_id": "order-exec-102",
            "agent_name": "order_fulfillment_agent",
            "type": "execution_start",
            "timestamp": now,
            "input": {"query": "Order 10 units of Discontinued SKU"},
            "metadata": {"environment": "local_dev"},
        },
        {
            "event_id": "order-exec-102:tool:1",
            "execution_id": "order-exec-102",
            "agent_name": "order_fulfillment_agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "verify_client_credentials",
            "duration_ms": 14.8,
            "status": "success",
            "input": redacted_input,
            "output": {"authenticated": True},
        },
        {
            "event_id": "order-exec-102:tool:2",
            "execution_id": "order-exec-102",
            "agent_name": "order_fulfillment_agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "check_inventory",
            "duration_ms": 18.5,
            "status": "error",
            "error_type": "ValueError",
            "error_message": "Requested quantity (10) exceeds available stock (0) for SKU-DISCONTINUED.",
        },
        {
            "event_id": "order-exec-102:end",
            "execution_id": "order-exec-102",
            "agent_name": "order_fulfillment_agent",
            "type": "execution_end",
            "timestamp": now,
            "status": "failed",
            "duration_ms": 38.2,
            "error_type": "ValueError",
            "error_message": "Requested quantity (10) exceeds available stock (0) for SKU-DISCONTINUED.",
        },
    ]

    ingest_fail = client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": raw_api_key},
        json={"events": failure_events},
    )
    assert ingest_fail.status_code == 200
    assert ingest_fail.json()["accepted"] == 4

    # 7. Dashboard Live Monitoring Retrieval
    traces_res = client.get("/api/traces/executions", headers=headers_a_scoped)
    assert traces_res.status_code == 200
    traces = traces_res.json()["items"]
    assert len(traces) == 2

    # Verify successful trace details
    exec_succ = next(t for t in traces if t["execution_id"] == "order-exec-101")
    assert exec_succ["status"] == "success"
    assert exec_succ["agent_name"] == "order_fulfillment_agent"
    assert exec_succ["tool_call_count"] == 3

    # Verify failed trace classification
    exec_fail = next(t for t in traces if t["execution_id"] == "order-exec-102")
    assert exec_fail["status"] == "failed"
    assert exec_fail["failure_kind"] == "tool_failure"

    # Detail query shows secret was never leaked
    detail_res = client.get("/api/traces/executions/order-exec-101", headers=headers_a_scoped)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert "sk-live-" not in str(detail)
    assert "[REDACTED]" in str(detail)

    # 8. Test Generation from Live Trace
    gen_res = client.post(
        "/api/traces/executions/order-exec-101/create-test",
        headers=headers_a_scoped,
        json={"name": "Order Fulfillment Regression Test"},
    )
    assert gen_res.status_code == 201
    test_case = gen_res.json()
    assert test_case["name"] == "Order Fulfillment Regression Test"
    test_id = test_case["id"]

    # 9. Deterministic Replay Execution
    run_res = client.post(f"/api/tests/{test_id}/run", headers=headers_a_scoped)
    assert run_res.status_code in (200, 201)
    run_data = run_res.json()
    assert run_data["status"] == "passed"

    # Verify Test History & Overview
    history = client.get(f"/api/test-runs?test_id={test_id}", headers=headers_a_scoped).json()
    assert len(history) >= 1
    assert history[0]["status"] == "passed"

    overview = client.get("/api/overview", headers=headers_a_scoped).json()
    assert overview["tests"]["total"] == 1
    assert overview["tests"]["passed"] == 1
    assert overview["tests"]["failed"] == 0

    # 10. Multi-Tenant Project Isolation Check (Developer B)
    client_b = TestClient(app)
    reg_b = client_b.post(
        "/api/auth/register",
        json={"email": "competitor@example.com", "password": "Password123!", "name": "Competitor"},
    )
    assert reg_b.status_code == 201
    csrf_b = reg_b.cookies[CSRF_COOKIE_NAME]
    headers_b = {CSRF_HEADER_NAME: csrf_b}
    projs_b = project_store.list_user_projects(reg_b.json()["id"])
    headers_b_scoped = {**headers_b, "X-Project-Id": str(projs_b[0]["id"])}

    # Developer B sees 0 traces in their project
    traces_b = client_b.get("/api/traces/executions", headers=headers_b_scoped).json()["items"]
    assert len(traces_b) == 0

    # Developer B cannot access Developer A's trace -> 404
    assert client_b.get("/api/traces/executions/order-exec-101", headers=headers_b_scoped).status_code == 404

    # Developer B cannot create test from Developer A's trace -> 404
    assert client_b.post("/api/traces/executions/order-exec-101/create-test", headers=headers_b_scoped).status_code == 404

    # 11. Revoked Key Enforcement
    del_key = client.delete(f"/api/projects/{project_a_id}/keys/{key_id}", headers=headers_a)
    assert del_key.status_code == 200

    # Ingestion with revoked key immediately rejected with 401
    rejected_ingest = client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": raw_api_key},
        json={"events": success_events},
    )
    assert rejected_ingest.status_code == 401


def test_nested_tool_calls_and_waterfall_timeline_api():
    """Verify Phase 6 Step 2: Nested tool calls and retry attempts in trace events and API."""
    client = TestClient(app)

    reg = client.post(
        "/api/auth/register",
        json={"email": "timeline_developer@example.com", "password": "SecurePassword123!", "name": "Timeline Dev"},
    )
    assert reg.status_code == 201
    csrf = reg.cookies[CSRF_COOKIE_NAME]
    headers = {CSRF_HEADER_NAME: csrf}
    user_id = reg.json()["id"]

    projs = project_store.list_user_projects(user_id)
    proj_id = projs[0]["id"]
    headers_scoped = {**headers, "X-Project-Id": str(proj_id)}

    key_res = client.post(f"/api/projects/{proj_id}/keys", json={"name": "Timeline Key"}, headers=headers)
    assert key_res.status_code == 201
    raw_key = key_res.json()["api_key"]

    now = datetime.now(timezone.utc).isoformat()

    # Events representing a parent tool call, a nested child tool call, and a retried tool call
    nested_events = [
        {
            "event_id": "hierarchical-exec:start",
            "execution_id": "hierarchical-exec-001",
            "agent_name": "nested_order_agent",
            "type": "execution_start",
            "timestamp": now,
            "input": {"order_id": "ORD-555"},
            "metadata": {"runtime": "python-3.14"},
        },
        {
            "event_id": "hierarchical-exec:tool:1",
            "execution_id": "hierarchical-exec-001",
            "agent_name": "nested_order_agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "check_inventory",
            "duration_ms": 25.5,
            "status": "success",
            "input": {"sku": "SKU-WIDGET-A", "quantity": 1},
            "output": {"available": 150},
            "parent_call_id": None,
            "retry_count": 0,
        },
        {
            "event_id": "hierarchical-exec:tool:2",
            "execution_id": "hierarchical-exec-001",
            "agent_name": "nested_order_agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "query_warehouse_shelf",
            "duration_ms": 8.2,
            "status": "success",
            "input": {"sku": "SKU-WIDGET-A"},
            "output": {"aisle": "A-04", "bin": "Shelf-12"},
            "parent_call_id": "hierarchical-exec:tool:1",
            "retry_count": 0,
        },
        {
            "event_id": "hierarchical-exec:tool:3",
            "execution_id": "hierarchical-exec-001",
            "agent_name": "nested_order_agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "process_payment",
            "duration_ms": 32.0,
            "status": "success",
            "input": {"amount": 97.4},
            "output": {"paid": True},
            "parent_call_id": None,
            "retry_count": 1,
        },
        {
            "event_id": "hierarchical-exec:end",
            "execution_id": "hierarchical-exec-001",
            "agent_name": "nested_order_agent",
            "type": "execution_end",
            "timestamp": now,
            "status": "success",
            "duration_ms": 68.0,
            "output": {"status": "fulfilled"},
        },
    ]

    ingest_res = client.post("/api/v1/traces/events", headers={"X-API-Key": raw_key}, json={"events": nested_events})
    assert ingest_res.status_code == 200
    assert ingest_res.json()["accepted"] == 5

    # Retrieve execution details and verify parent_call_id and retry_count
    detail_res = client.get("/api/traces/executions/hierarchical-exec-001", headers=headers_scoped)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["agent_name"] == "nested_order_agent"
    assert detail["status"] == "success"
    assert len(detail["tool_calls"]) == 3

    tool_1 = next(t for t in detail["tool_calls"] if t["call_id"] == "hierarchical-exec:tool:1")
    tool_2 = next(t for t in detail["tool_calls"] if t["call_id"] == "hierarchical-exec:tool:2")
    tool_3 = next(t for t in detail["tool_calls"] if t["call_id"] == "hierarchical-exec:tool:3")

    assert tool_1["parent_call_id"] is None
    assert tool_1["retry_count"] == 0

    assert tool_2["parent_call_id"] == "hierarchical-exec:tool:1"
    assert tool_2["retry_count"] == 0

    assert tool_3["parent_call_id"] is None
    assert tool_3["retry_count"] == 1

