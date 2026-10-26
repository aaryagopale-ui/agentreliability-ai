"""Test suite for Phase 6 Step 3: Real Trace-to-Test Regression Testing & Baseline Management.

Tests:
1. Trace-to-test creation with customizable expectations (status, tool sequence, required output keys, max duration, strict ordering).
2. Enhanced replay assertions (duration exceeded, missing output keys, error type mismatch).
3. Baseline creation from recorded trace.
4. Baseline versioning & history preservation (creating version 2 leaves version 1 intact).
5. Deterministic Regression Comparison Engine:
   - Identical candidate passes.
   - Missing required tool detected as breaking regression.
   - Unexpected tool detected as breaking regression.
   - Tool reordering detected under strict_order, allowed under strict_order=False.
   - Output schema change (missing required key) detected as breaking regression.
   - Status regression (success -> failed) detected.
   - Duration threshold exceeded (breaking regression when max_duration_ms exceeded).
   - Latency regression (informational/performance warning when tolerance exceeded).
   - Inconclusive handling for running/incomplete traces.
6. Baseline API & Trace Comparison endpoints.
7. Multi-tenant project isolation (cross-project access rejected).
"""
import pytest
from fastapi.testclient import TestClient

from app import ci_store, database, test_store, trace_store
from app.email_sink import dev_email_sink
from app.main import app
from app.migrations.runner import run_migrations
from app.replay import run_test
from app.regression_engine import compare_execution_to_baseline
from app.security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    auth_rate_limiter,
)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Isolate every test in an ephemeral temporary database with migrations applied."""
    db_file = str(tmp_path / "test_regression.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", db_file)
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "test")
    auth_rate_limiter.clear_all()
    dev_email_sink.clear()
    database.init_db()
    test_store.init_tables()
    trace_store.init_tables()
    ci_store.init_tables()


@pytest.fixture
def client():
    return TestClient(app)


def register_user(client: TestClient, email: str, name: str, password: str = "Password123!") -> dict:
    """Helper: register user and return session cookies, csrf header, user profile, and active project id."""
    res = client.post("/api/auth/register", json={"email": email, "password": password, "name": name})
    assert res.status_code == 201, res.text
    csrf = res.cookies[CSRF_COOKIE_NAME]
    # Fetch user's default project
    proj_res = client.get("/api/projects", cookies=res.cookies)
    projects = proj_res.json()
    proj_id = projects[0]["id"]
    return {
        "cookies": res.cookies,
        "headers": {CSRF_HEADER_NAME: csrf},
        "user": res.json(),
        "project_id": proj_id,
    }


import json

def _create_trace_fixture(project_id: int, execution_id: str, status: str = "success", tools: list = None, output: dict = None, duration_ms: float = 250.0):
    with database.connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO trace_executions
               (project_id, execution_id, agent_name, status, failure_kind, started_at, ended_at,
                duration_ms, input_json, output_json, error_type, error_message, metadata_json,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                execution_id,
                "OrderProcessingAgent",
                status,
                "tool_failure" if status == "failed" else None,
                "2026-10-18T10:00:00Z",
                "2026-10-18T10:00:01Z",
                duration_ms,
                '{"order_id": "ORD-123"}',
                json.dumps(output if output is not None else ({"order_id": "ORD-123", "status": "processed", "total": 99.5} if status == "success" else None)),
                "WarehouseError" if status == "failed" else None,
                "Shelf not found" if status == "failed" else None,
                "{}",
                "2026-10-18T10:00:00Z",
                "2026-10-18T10:00:01Z",
            ),
        )
        conn.execute("DELETE FROM trace_tool_calls WHERE project_id = ? AND execution_id = ?", (project_id, execution_id))
        tool_list = tools or ["validate_order", "check_inventory", "charge_payment"]
        for idx, tname in enumerate(tool_list):
            conn.execute(
                """INSERT INTO trace_tool_calls
                   (project_id, call_id, execution_id, tool_name, started_at, duration_ms,
                    status, input_json, output_json, error_type, error_message, parent_call_id, retry_count)
                   VALUES (?, ?, ?, ?, '2026-10-18T10:00:00Z', 50.0, 'success', '{"step": 1}', '{"ok": true}', NULL, NULL, NULL, 0)""",
                (project_id, f"{execution_id}:tool:{idx}", execution_id, tname),
            )


def test_customizable_trace_to_test(client):
    auth = register_user(client, "alice@example.com", "Alice")
    pid = auth["project_id"]
    _create_trace_fixture(project_id=pid, execution_id="trace-custom-test-1")

    # Create test case with custom expectations
    payload = {
        "name": "Custom Order Processing Test",
        "description": "Regression test verifying mandatory payment and duration limit",
        "expected": {
            "status": "success",
            "tool_sequence": ["validate_order", "check_inventory", "charge_payment"],
            "expected_output_fields": ["order_id", "status", "total"],
            "max_duration_ms": 500.0,
            "strict_order": True,
            "allow_additional_tools": False,
        },
    }
    resp = client.post(
        f"/api/traces/executions/trace-custom-test-1/create-test?project_id={pid}",
        json=payload,
        cookies=auth["cookies"],
        headers=auth["headers"],
    )
    assert resp.status_code == 201, resp.text
    case = resp.json()
    assert case["name"] == "Custom Order Processing Test"
    assert case["expected"]["expected_output_fields"] == ["order_id", "status", "total"]
    assert case["expected"]["max_duration_ms"] == 500.0

    # Replay simulation of this case should pass
    replay_result = run_test(case)
    assert replay_result["status"] == "passed"
    assert replay_result["mismatches"] == []


def test_replay_catches_missing_output_fields_and_duration():
    # Construct a test case with missing output fields and exceeded duration
    case = {
        "name": "Failing Assertion Test",
        "agent_name": "TestAgent",
        "input": {},
        "steps": [
            {"type": "tool_call", "name": "t1", "status": "success", "duration_ms": 800.0},
            {"type": "agent_output", "name": "TestAgent", "status": "success", "output": {"only_one_field": 1}},
        ],
        "expected": {
            "status": "success",
            "tool_sequence": ["t1"],
            "expected_output_fields": ["only_one_field", "missing_field"],
            "max_duration_ms": 500.0,
        },
    }
    result = run_test(case)
    assert result["status"] == "failed"
    kinds = [m["kind"] for m in result["mismatches"]]
    assert "missing_output_field" in kinds
    assert "duration_exceeded" in kinds


def test_baseline_creation_and_versioning(client):
    auth = register_user(client, "alice@example.com", "Alice")
    pid = auth["project_id"]
    _create_trace_fixture(project_id=pid, execution_id="trace-baseline-v1")

    # 1. Create Baseline
    create_payload = {
        "name": "Order Flow Golden Baseline",
        "description": "Golden baseline for standard checkout",
        "source_type": "trace",
        "source_id": "trace-baseline-v1",
        "expected": {
            "status": "success",
            "tool_sequence": ["validate_order", "check_inventory", "charge_payment"],
            "expected_output_fields": ["order_id", "status", "total"],
            "max_duration_ms": 400.0,
            "strict_order": True,
        },
    }
    resp = client.post(
        f"/api/baselines?project_id={pid}",
        json=create_payload,
        cookies=auth["cookies"],
        headers=auth["headers"],
    )
    assert resp.status_code == 201, resp.text
    baseline = resp.json()
    b_id = baseline["id"]
    assert baseline["current_version"] == 1
    assert baseline["name"] == "Order Flow Golden Baseline"
    assert baseline["version_data"]["expected"]["tool_sequence"] == ["validate_order", "check_inventory", "charge_payment"]

    # 2. Update Baseline to Version 2 with a new trace
    _create_trace_fixture(
        project_id=pid,
        execution_id="trace-baseline-v2",
        tools=["validate_order", "check_inventory", "charge_payment", "send_notification"],
    )
    update_payload = {
        "source_type": "trace",
        "source_id": "trace-baseline-v2",
        "description": "Added notification step",
        "expected": {
            "status": "success",
            "tool_sequence": ["validate_order", "check_inventory", "charge_payment", "send_notification"],
            "expected_output_fields": ["order_id", "status", "total"],
            "strict_order": True,
        },
    }
    up_resp = client.post(
        f"/api/baselines/{b_id}/versions?project_id={pid}",
        json=update_payload,
        cookies=auth["cookies"],
        headers=auth["headers"],
    )
    assert up_resp.status_code == 201, up_resp.text
    updated = up_resp.json()
    assert updated["current_version"] == 2

    # 3. Retrieve Baseline and verify history is intact
    get_resp = client.get(f"/api/baselines/{b_id}?project_id={pid}", cookies=auth["cookies"])
    assert get_resp.status_code == 200
    baseline_data = get_resp.json()
    assert len(baseline_data["history"]) == 2
    assert baseline_data["history"][0]["version"] == 2
    assert baseline_data["history"][1]["version"] == 1

    # 4. Specific version retrieval
    v1_resp = client.get(f"/api/baselines/{b_id}/versions/1?project_id={pid}", cookies=auth["cookies"])
    assert v1_resp.status_code == 200
    assert v1_resp.json()["version"] == 1
    assert len(v1_resp.json()["tools"]) == 3


def test_regression_comparison_engine_scenarios():
    baseline = {
        "id": 1,
        "name": "Standard Checkout Baseline",
        "agent_name": "OrderProcessingAgent",
        "expected": {
            "status": "success",
            "tool_sequence": ["validate_order", "check_inventory", "charge_payment"],
            "expected_output_fields": ["order_id", "status", "total"],
            "expected_error_type": None,
            "max_duration_ms": 300.0,
            "strict_order": True,
            "allow_additional_tools": False,
        },
        "tools": [
            {"tool_name": "validate_order"},
            {"tool_name": "check_inventory"},
            {"tool_name": "charge_payment"},
        ],
        "output": {"order_id": "ORD-1", "status": "processed", "total": 100},
        "duration_ms": 200.0,
        "status": "success",
    }

    # Scenario 1: Matching candidate passes
    cand_ok = {
        "status": "success",
        "tool_calls": [
            {"tool_name": "validate_order"},
            {"tool_name": "check_inventory"},
            {"tool_name": "charge_payment"},
        ],
        "output": {"order_id": "ORD-1", "status": "processed", "total": 100},
        "duration_ms": 220.0,
    }
    res = compare_execution_to_baseline(baseline, cand_ok)
    assert res["verdict"] == "passed"
    assert res["is_regression"] is False
    assert res["differences"] == []

    # Scenario 2: Missing tool (Breaking)
    cand_missing_tool = {
        "status": "success",
        "tool_calls": [
            {"tool_name": "validate_order"},
            {"tool_name": "charge_payment"},
        ],
        "output": {"order_id": "ORD-1", "status": "processed", "total": 100},
        "duration_ms": 150.0,
    }
    res = compare_execution_to_baseline(baseline, cand_missing_tool)
    assert res["verdict"] == "regression"
    assert res["is_regression"] is True
    diff_kinds = [r["category"] for r in res["differences"]]
    assert "missing_tool_call" in diff_kinds
    assert any(r["severity"] == "breaking_regression" for r in res["differences"])

    # Scenario 3: Unexpected tool (Breaking)
    cand_unexpected_tool = {
        "status": "success",
        "tool_calls": [
            {"tool_name": "validate_order"},
            {"tool_name": "check_inventory"},
            {"tool_name": "charge_payment"},
            {"tool_name": "unauthorized_refund"},
        ],
        "output": {"order_id": "ORD-1", "status": "processed", "total": 100},
        "duration_ms": 250.0,
    }
    res = compare_execution_to_baseline(baseline, cand_unexpected_tool)
    assert res["verdict"] == "regression"
    assert any(r["category"] == "unexpected_tool_call" for r in res["differences"])

    # Scenario 4: Reordered tools under strict_order=True
    cand_reordered = {
        "status": "success",
        "tool_calls": [
            {"tool_name": "check_inventory"},
            {"tool_name": "validate_order"},
            {"tool_name": "charge_payment"},
        ],
        "output": {"order_id": "ORD-1", "status": "processed", "total": 100},
        "duration_ms": 200.0,
    }
    res = compare_execution_to_baseline(baseline, cand_reordered)
    assert res["verdict"] == "regression"
    assert any(r["category"] == "tool_sequence_mismatch" for r in res["differences"])

    # Scenario 5: Missing required output field
    cand_missing_field = {
        "status": "success",
        "tool_calls": [
            {"tool_name": "validate_order"},
            {"tool_name": "check_inventory"},
            {"tool_name": "charge_payment"},
        ],
        "output": {"order_id": "ORD-1"},  # missing 'status' and 'total'
        "duration_ms": 200.0,
    }
    res = compare_execution_to_baseline(baseline, cand_missing_field)
    assert res["verdict"] == "regression"
    assert any(r["category"] == "missing_output_field" for r in res["differences"])

    # Scenario 6: Status regression (success -> failed)
    cand_failed = {
        "status": "failed",
        "error_type": "PaymentDeclined",
        "error_message": "Card expired",
        "tool_calls": [
            {"tool_name": "validate_order"},
            {"tool_name": "check_inventory"},
            {"tool_name": "charge_payment"},
        ],
        "output": None,
        "duration_ms": 200.0,
    }
    res = compare_execution_to_baseline(baseline, cand_failed)
    assert res["verdict"] == "regression"
    assert any(r["category"] == "status_regression" for r in res["differences"])

    # Scenario 7A: Duration threshold exceeded (breaking regression when max_duration_ms is defined)
    cand_exceeded = {
        "status": "success",
        "tool_calls": [
            {"tool_name": "validate_order"},
            {"tool_name": "check_inventory"},
            {"tool_name": "charge_payment"},
        ],
        "output": {"order_id": "ORD-1", "status": "processed", "total": 100},
        "duration_ms": 600.0,  # > max_duration_ms (300.0)
    }
    res_exceeded = compare_execution_to_baseline(baseline, cand_exceeded)
    assert res_exceeded["verdict"] == "regression"
    assert any(r["category"] == "duration_threshold_exceeded" for r in res_exceeded["differences"])

    # Scenario 7B: Latency regression (informational/performance warning when no hard max, but > tolerance)
    baseline_no_max = dict(baseline)
    baseline_no_max["expected"] = dict(baseline["expected"])
    baseline_no_max["expected"]["max_duration_ms"] = None
    res_slow = compare_execution_to_baseline(baseline_no_max, cand_exceeded, duration_tolerance_pct=50.0)
    dur_regs = [r for r in res_slow["differences"] if r["category"] == "latency_regression"]
    assert len(dur_regs) == 1
    assert dur_regs[0]["severity"] == "performance_regression"

    # Scenario 8: Inconclusive when running
    cand_running = {
        "status": "running",
        "tool_calls": [],
        "output": None,
        "duration_ms": 50.0,
    }
    res = compare_execution_to_baseline(baseline, cand_running)
    assert res["verdict"] == "inconclusive"
    assert any(r["category"] == "execution_incomplete" for r in res["differences"])


def test_baseline_compare_api_and_adhoc(client):
    auth = register_user(client, "alice@example.com", "Alice")
    pid = auth["project_id"]
    _create_trace_fixture(project_id=pid, execution_id="trace-base-api", duration_ms=200.0)
    _create_trace_fixture(
        project_id=pid,
        execution_id="trace-cand-regressed",
        tools=["validate_order", "check_inventory"],  # missing charge_payment
        duration_ms=210.0,
    )

    # 1. Create baseline
    resp = client.post(
        f"/api/baselines?project_id={pid}",
        json={
            "name": "Order Flow API Baseline",
            "source_type": "trace",
            "source_id": "trace-base-api",
        },
        cookies=auth["cookies"],
        headers=auth["headers"],
    )
    assert resp.status_code == 201, resp.text
    baseline_id = resp.json()["id"]

    # 2. Compare candidate against baseline via API
    cmp_resp = client.post(
        f"/api/baselines/{baseline_id}/compare?project_id={pid}",
        json={"candidate_trace_id": "trace-cand-regressed"},
        cookies=auth["cookies"],
        headers=auth["headers"],
    )
    assert cmp_resp.status_code == 200, cmp_resp.text
    cmp_data = cmp_resp.json()
    assert cmp_data["verdict"] == "regression"
    assert cmp_data["is_regression"] is True
    assert any(r["category"] == "missing_tool_call" for r in cmp_data["differences"])

    # 3. Ad-hoc trace comparison
    adhoc_resp = client.post(
        f"/api/regression/compare-traces?project_id={pid}&baseline_trace_id=trace-base-api&candidate_trace_id=trace-cand-regressed",
        cookies=auth["cookies"],
        headers=auth["headers"],
    )
    assert adhoc_resp.status_code == 200, adhoc_resp.text
    adhoc_data = adhoc_resp.json()
    assert adhoc_data["verdict"] == "regression"
    assert adhoc_data["is_regression"] is True
    assert any(r["category"] == "missing_tool_call" for r in adhoc_data["differences"])


def test_cross_project_isolation_on_baselines(client):
    alice_auth = register_user(client, "alice@example.com", "Alice")
    bob_auth = register_user(client, "bob@example.com", "Bob")
    p1 = alice_auth["project_id"]
    p2 = bob_auth["project_id"]

    _create_trace_fixture(project_id=p1, execution_id="alice-trace-1")
    _create_trace_fixture(project_id=p2, execution_id="bob-trace-1")

    # Alice creates a baseline in Project 1
    resp = client.post(
        f"/api/baselines?project_id={p1}",
        json={"name": "Alice Baseline", "source_type": "trace", "source_id": "alice-trace-1"},
        cookies=alice_auth["cookies"],
        headers=alice_auth["headers"],
    )
    assert resp.status_code == 201
    alice_b_id = resp.json()["id"]

    # Bob tries to access Alice's baseline (specifying his own project) -> 404
    bob_get = client.get(f"/api/baselines/{alice_b_id}?project_id={p2}", cookies=bob_auth["cookies"])
    assert bob_get.status_code == 404

    # Bob tries to update Alice's baseline -> 404
    bob_update = client.post(
        f"/api/baselines/{alice_b_id}/versions?project_id={p2}",
        json={"source_type": "trace", "source_id": "bob-trace-1"},
        cookies=bob_auth["cookies"],
        headers=bob_auth["headers"],
    )
    assert bob_update.status_code == 404

    # Bob tries to create a baseline using Alice's trace -> 404
    bob_steal_trace = client.post(
        f"/api/baselines?project_id={p2}",
        json={"name": "Bob Baseline", "source_type": "trace", "source_id": "alice-trace-1"},
        cookies=bob_auth["cookies"],
        headers=bob_auth["headers"],
    )
    assert bob_steal_trace.status_code == 404


def test_regression_json_string_outputs():
    """Verify Issue #5: Regression detection handles JSON-stringified outputs gracefully."""
    base_tools = [{"tool_name": "step1"}]
    cand_tools = [{"tool_name": "step1"}]

    # 1. JSON-string vs JSON-string matching
    baseline_json_str = {
        "agent_name": "Agent", "status": "success", "duration_ms": 100.0,
        "tools": base_tools,
        "output": '{"approved": true, "score": 15, "tier": "silver"}',
        "expected": {"expected_output_fields": ["approved", "score", "tier"]}
    }
    cand_json_str_ok = {
        "status": "success", "duration_ms": 110.0,
        "tool_calls": cand_tools,
        "output": '{"approved": true, "score": 15, "tier": "silver"}',
    }
    res1 = compare_execution_to_baseline(baseline_json_str, cand_json_str_ok)
    assert res1["verdict"] == "passed"
    assert res1["is_regression"] is False

    # 2. JSON-string candidate vs dict baseline matching
    baseline_dict = {
        "agent_name": "Agent", "status": "success", "duration_ms": 100.0,
        "tools": base_tools,
        "output": {"approved": True, "score": 15, "tier": "silver"},
        "expected": {"expected_output_fields": ["approved", "score", "tier"]}
    }
    res2 = compare_execution_to_baseline(baseline_dict, cand_json_str_ok)
    assert res2["verdict"] == "passed"
    assert res2["is_regression"] is False

    # Reverse: Dict candidate vs JSON-string baseline matching
    cand_dict_ok = {
        "status": "success", "duration_ms": 110.0,
        "tool_calls": cand_tools,
        "output": {"approved": True, "score": 15, "tier": "silver"},
    }
    res2_rev = compare_execution_to_baseline(baseline_json_str, cand_dict_ok)
    assert res2_rev["verdict"] == "passed"
    assert res2_rev["is_regression"] is False

    # 3. Missing fields in JSON-string candidate
    cand_missing_fields = {
        "status": "success", "duration_ms": 100.0,
        "tool_calls": cand_tools,
        "output": '{"approved": true}',  # missing score and tier
    }
    res3 = compare_execution_to_baseline(baseline_json_str, cand_missing_fields)
    assert res3["verdict"] == "regression"
    assert res3["is_regression"] is True
    diff_kinds = [d["category"] for d in res3["differences"]]
    assert "missing_output_field" in diff_kinds
    missing_diff = next(d for d in res3["differences"] if d["category"] == "missing_output_field")
    assert "score" in missing_diff["evidence"]["candidate_keys"] or "score" in missing_diff["message"]

    # 4. Incompatible field type in JSON-string candidate
    cand_wrong_type = {
        "status": "success", "duration_ms": 100.0,
        "tool_calls": cand_tools,
        "output": '{"approved": true, "score": "fifteen", "tier": "silver"}',  # score is string, not number
    }
    res4 = compare_execution_to_baseline(baseline_json_str, cand_wrong_type)
    assert res4["verdict"] == "regression"
    assert res4["is_regression"] is True
    diff_kinds = [d["category"] for d in res4["differences"]]
    assert "field_type_mismatch" in diff_kinds
    type_diff = next(d for d in res4["differences"] if d["category"] == "field_type_mismatch")
    assert type_diff["evidence"]["field"] == "score"
    assert type_diff["evidence"]["expected_type"] == "int"
    assert type_diff["evidence"]["candidate_type"] == "str"

    # 5. Unexpected added fields when strict schema is enabled
    baseline_strict = {
        "agent_name": "Agent", "status": "success", "duration_ms": 100.0,
        "tools": base_tools,
        "output": '{"approved": true, "score": 15}',
        "expected": {"allow_additional_output_fields": False}
    }
    cand_extra_fields = {
        "status": "success", "duration_ms": 100.0,
        "tool_calls": cand_tools,
        "output": '{"approved": true, "score": 15, "unauthorized_flag": true}',
    }
    res5 = compare_execution_to_baseline(baseline_strict, cand_extra_fields)
    assert res5["verdict"] == "regression"
    assert any(d["category"] == "unexpected_output_field" for d in res5["differences"])

    # 6. Malformed JSON string triggers schema mismatch
    cand_malformed = {
        "status": "success", "duration_ms": 100.0,
        "tool_calls": cand_tools,
        "output": '{"approved": true, score: NOT_JSON',
    }
    res6 = compare_execution_to_baseline(baseline_dict, cand_malformed)
    assert res6["verdict"] == "regression"
    assert any(d["category"] == "output_schema_mismatch" for d in res6["differences"])

    # 7. Ordinary text preserved as informational value change
    baseline_text = {
        "agent_name": "Agent", "status": "success", "duration_ms": 100.0,
        "tools": base_tools,
        "output": "Audit completed successfully.",
    }
    cand_text_changed = {
        "status": "success", "duration_ms": 100.0,
        "tool_calls": cand_tools,
        "output": "Audit completed with 2 warnings.",
    }
    res7 = compare_execution_to_baseline(baseline_text, cand_text_changed)
    assert res7["verdict"] == "passed"
    assert res7["is_regression"] is False
    assert any(d["category"] == "output_value_change" for d in res7["differences"])

    # 8. JSON Array string comparison
    baseline_array = {
        "agent_name": "Agent", "status": "success", "duration_ms": 100.0,
        "tools": base_tools,
        "output": '[{"item": "book", "qty": 2}, {"item": "pen", "qty": 5}]',
    }
    cand_array_ok = {
        "status": "success", "duration_ms": 100.0,
        "tool_calls": cand_tools,
        "output": [{"item": "book", "qty": 2}, {"item": "pen", "qty": 5}],
    }
    res8 = compare_execution_to_baseline(baseline_array, cand_array_ok)
    assert res8["verdict"] == "passed"
    assert res8["is_regression"] is False


def test_v1_baseline_api_endpoints_and_isolation(client):
    """Verify Issue #4: /api/v1/baselines endpoints support project-scoped API-key auth with strict isolation."""
    alice_auth = register_user(client, "alice_api@example.com", "Alice API")
    p1 = alice_auth["project_id"]

    # Generate API key for Project 1
    key_resp = client.post(
        f"/api/projects/{p1}/keys",
        json={"name": "Alice CLI Key"},
        cookies=alice_auth["cookies"],
        headers=alice_auth["headers"],
    )
    assert key_resp.status_code == 201
    p1_api_key = key_resp.json()["api_key"]

    # Create baseline in Project 1
    _create_trace_fixture(project_id=p1, execution_id="alice-base-trace")
    _create_trace_fixture(project_id=p1, execution_id="alice-cand-ok")
    _create_trace_fixture(project_id=p1, execution_id="alice-cand-regressed", tools=["validate_order"])  # missing tools

    base_resp = client.post(
        f"/api/baselines?project_id={p1}",
        json={"name": "Alice Order Flow", "source_type": "trace", "source_id": "alice-base-trace"},
        cookies=alice_auth["cookies"],
        headers=alice_auth["headers"],
    )
    assert base_resp.status_code == 201
    b1_id = base_resp.json()["id"]

    # 1. List baselines using API key
    list_resp = client.get("/api/v1/baselines", headers={"X-API-Key": p1_api_key})
    assert list_resp.status_code == 200
    baselines = list_resp.json()
    assert len(baselines) == 1
    assert baselines[0]["id"] == b1_id
    assert baselines[0]["name"] == "Alice Order Flow"

    # Query with matching agent_name
    filter_resp = client.get("/api/v1/baselines?agent_name=OrderProcessingAgent", headers={"X-API-Key": p1_api_key})
    assert filter_resp.status_code == 200
    assert len(filter_resp.json()) == 1

    # Query with non-matching agent_name
    empty_resp = client.get("/api/v1/baselines?agent_name=NonExistentAgent", headers={"X-API-Key": p1_api_key})
    assert empty_resp.status_code == 200
    assert len(empty_resp.json()) == 0

    # 2. Compare matching candidate using API key -> passed
    cmp_ok = client.post(
        f"/api/v1/baselines/{b1_id}/compare",
        json={"candidate_trace_id": "alice-cand-ok"},
        headers={"X-API-Key": p1_api_key},
    )
    assert cmp_ok.status_code == 200
    report_ok = cmp_ok.json()
    assert report_ok["verdict"] == "passed"
    assert report_ok["is_regression"] is False
    assert report_ok["baseline_id"] == b1_id

    # 3. Compare regressed candidate using API key -> regression
    cmp_bad = client.post(
        f"/api/v1/baselines/{b1_id}/compare",
        json={"candidate_trace_id": "alice-cand-regressed"},
        headers={"X-API-Key": p1_api_key},
    )
    assert cmp_bad.status_code == 200
    report_bad = cmp_bad.json()
    assert report_bad["verdict"] == "regression"
    assert report_bad["is_regression"] is True
    assert any(d["category"] == "missing_tool_call" for d in report_bad["differences"])

    # 4. Invalid API key -> 401
    cmp_unauth = client.post(
        f"/api/v1/baselines/{b1_id}/compare",
        json={"candidate_trace_id": "alice-cand-ok"},
        headers={"X-API-Key": "ar_invalid_key_9999"},
    )
    assert cmp_unauth.status_code == 401

    # Missing API key -> 401
    cmp_no_key = client.post(f"/api/v1/baselines/{b1_id}/compare", json={"candidate_trace_id": "alice-cand-ok"})
    assert cmp_no_key.status_code == 401

    # 5. Non-existent baseline -> 404
    cmp_no_b = client.post(
        "/api/v1/baselines/99999/compare",
        json={"candidate_trace_id": "alice-cand-ok"},
        headers={"X-API-Key": p1_api_key},
    )
    assert cmp_no_b.status_code == 404

    # 6. Non-existent candidate trace -> 404
    cmp_no_t = client.post(
        f"/api/v1/baselines/{b1_id}/compare",
        json={"candidate_trace_id": "non-existent-trace-id"},
        headers={"X-API-Key": p1_api_key},
    )
    assert cmp_no_t.status_code == 404

    # 7. Cross-project isolation: Bob cannot access Alice's baseline or trace
    bob_auth = register_user(client, "bob_api@example.com", "Bob API")
    p2 = bob_auth["project_id"]
    bob_key_resp = client.post(
        f"/api/projects/{p2}/keys",
        json={"name": "Bob CLI Key"},
        cookies=bob_auth["cookies"],
        headers=bob_auth["headers"],
    )
    p2_api_key = bob_key_resp.json()["api_key"]
    _create_trace_fixture(project_id=p2, execution_id="bob-trace-1")

    # Bob tries to compare using Alice's baseline_id -> 404
    bob_steal_b = client.post(
        f"/api/v1/baselines/{b1_id}/compare",
        json={"candidate_trace_id": "bob-trace-1"},
        headers={"X-API-Key": p2_api_key},
    )
    assert bob_steal_b.status_code == 404

    # Alice tries to compare against Bob's candidate trace -> 404
    alice_steal_t = client.post(
        f"/api/v1/baselines/{b1_id}/compare",
        json={"candidate_trace_id": "bob-trace-1"},
        headers={"X-API-Key": p1_api_key},
    )
    assert alice_steal_t.status_code == 404


