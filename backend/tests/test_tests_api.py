import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

SAMPLES = Path(__file__).resolve().parents[2] / "sample_logs"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTRELIABILITY_DB", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


def upload(client, sample):
    r = client.post("/api/executions", files={"file": (sample, (SAMPLES / sample).read_text(), "application/json")})
    assert r.status_code == 201
    return r.json()["id"]


def make_test(client, sample):
    exec_id = upload(client, sample)
    r = client.post(f"/api/tests/from-execution/{exec_id}")
    assert r.status_code == 201, r.text
    return r.json()


def test_generate_test_from_success_and_failed_logs(client):
    ok = make_test(client, "success_log.json")
    assert ok["expected"]["status"] == "success"
    assert ok["expected"]["tool_sequence"] == ["lookup_order"]
    assert ok["source_execution_id"] is not None
    bad = make_test(client, "failed_tool_log.json")
    assert bad["expected"]["status"] == "failed"
    assert bad["expected"]["error_conditions"][0]["category"] == "failed_tool_call"


def test_from_missing_execution_404(client):
    assert client.post("/api/tests/from-execution/999").status_code == 404


def test_run_generated_tests_pass(client):
    t = make_test(client, "failed_tool_log.json")
    r = client.post(f"/api/tests/{t['id']}/run")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "passed" and body["mode"] == "deterministic_simulation"
    assert body["disclaimer"]


def test_editing_expected_makes_test_fail_with_explanation(client):
    t = make_test(client, "success_log.json")
    t["expected"]["tool_sequence"] = ["wrong_tool"]
    t["expected"]["final_output"] = "something else"
    r = client.put(f"/api/tests/{t['id']}", json=t)
    assert r.status_code == 200
    run = client.post(f"/api/tests/{t['id']}/run").json()
    assert run["status"] == "failed"
    kinds = {m["kind"] for m in run["mismatches"]}
    assert {"sequence_mismatch", "output_mismatch"} <= kinds


def test_create_manual_test_and_validation_errors(client):
    payload = {
        "name": "manual", "agent_name": "a",
        "steps": [{"type": "tool_call", "name": "t", "output": "ok"}],
        "expected": {"status": "success", "tool_sequence": ["t"], "final_output": "ok"},
    }
    r = client.post("/api/tests", json=payload)
    assert r.status_code == 201 and r.json()["name"] == "manual"
    bad = client.post("/api/tests", json={**payload, "steps": [], "name": ""})
    assert bad.status_code == 422
    assert bad.json()["detail"]["problems"]
    bad_cat = {**payload, "expected": {"error_conditions": [{"step_index": 0, "category": "nope"}]}}
    assert client.post("/api/tests", json=bad_cat).status_code == 422


def test_delete_test_keeps_history(client):
    t = make_test(client, "success_log.json")
    client.post(f"/api/tests/{t['id']}/run")
    assert client.delete(f"/api/tests/{t['id']}").status_code == 204
    assert client.get(f"/api/tests/{t['id']}").status_code == 404
    assert client.delete(f"/api/tests/{t['id']}").status_code == 404
    runs = client.get("/api/test-runs").json()
    assert len(runs) == 1 and runs[0]["test_name"] == t["name"]


def test_run_all_and_history(client):
    make_test(client, "success_log.json")
    bad = make_test(client, "timeout_log.json")
    # break one test so we get a mix of results
    bad["expected"]["status"] = "success"
    bad["expected"]["error_conditions"] = []
    client.put(f"/api/tests/{bad['id']}", json=bad)
    res = client.post("/api/tests/run-all").json()
    assert (res["total"], res["passed"], res["failed"]) == (2, 1, 1)
    hist = client.get("/api/test-runs").json()
    assert len(hist) == 2
    only = client.get(f"/api/test-runs?test_id={bad['id']}").json()
    assert len(only) == 1 and only[0]["status"] == "failed"
    detail = client.get(f"/api/test-runs/{only[0]['id']}").json()
    assert detail["mismatches"] and detail["observed"]["steps"]
    assert client.get("/api/test-runs/9999").status_code == 404


def test_overview_and_failure_analysis_come_from_database(client):
    empty = client.get("/api/overview").json()
    assert empty["tests"]["total"] == 0 and empty["executions"]["total"] == 0
    good = make_test(client, "success_log.json")
    bad = make_test(client, "failed_tool_log.json")
    bad["expected"]["error_conditions"] = []
    bad["expected"]["status"] = "success"
    client.put(f"/api/tests/{bad['id']}", json=bad)
    ov = client.get("/api/overview").json()
    assert ov["tests"] == {"total": 2, "passed": 0, "failed": 0, "not_run": 2}
    client.post("/api/tests/run-all")
    ov = client.get("/api/overview").json()
    assert ov["tests"] == {"total": 2, "passed": 1, "failed": 1, "not_run": 0}
    fa = client.get("/api/failure-analysis").json()
    assert fa["execution_findings"]["failed_tool_call"] == 1
    assert fa["replay_mismatches"]["failed_tool_call"] == 1
    assert len(fa["failing_runs"]) == 1


def test_malformed_log_never_creates_test_or_crashes(client):
    r = client.post("/api/executions", files={"file": ("x.json", b"\xff\xfe not json", "application/json")})
    assert r.status_code == 400
    r = client.post("/api/executions", files={"file": ("x.json", json.dumps([1, 2, 3]), "application/json")})
    assert r.status_code == 422
    assert client.get("/api/tests").json() == []


def test_uploaded_code_is_only_data(client):
    # Strings that look like code must be stored and replayed as plain text.
    payload = {"agent_name": "evil", "steps": [
        {"type": "tool_call", "name": "__import__('os').system('echo hacked')", "output": "$(whoami)"}]}
    r = client.post("/api/executions", files={"file": ("e.json", json.dumps(payload), "application/json")})
    t = client.post(f"/api/tests/from-execution/{r.json()['id']}").json()
    run = client.post(f"/api/tests/{t['id']}/run").json()
    assert run["status"] == "passed"
    assert run["observed"]["final_output"] == "$(whoami)"

