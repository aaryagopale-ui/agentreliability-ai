import json
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import trace_store

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTRELIABILITY_DB", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c

@pytest.fixture()
def project_key(client):
    from app.create_key import create_key
    return create_key("test-project")

def test_trace_auth_required(client):
    r = client.post("/api/v1/traces/events", json={"events": []})
    assert r.status_code == 401
    assert "Missing API key" in r.json()["detail"]

def test_trace_auth_invalid_key(client):
    r = client.post("/api/v1/traces/events", headers={"X-API-Key": "ar_invalid_key"}, json={"events": []})
    assert r.status_code == 401
    assert "Invalid API key" in r.json()["detail"]

def test_trace_ingest_and_query(client, project_key):
    now = datetime.now(timezone.utc).isoformat()
    events = [
        {
            "event_id": "test-exec-1:start",
            "execution_id": "test-exec-1",
            "agent_name": "support-agent",
            "type": "execution_start",
            "timestamp": now,
            "input": {"query": "hello"},
            "metadata": {"env": "prod"}
        },
        {
            "event_id": "test-exec-1:tool:1",
            "execution_id": "test-exec-1",
            "agent_name": "support-agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "lookup_user",
            "duration_ms": 12.5,
            "status": "success",
            "output": {"id": 123}
        },
        {
            "event_id": "test-exec-1:end",
            "execution_id": "test-exec-1",
            "agent_name": "support-agent",
            "type": "execution_end",
            "timestamp": now,
            "status": "success",
            "duration_ms": 50.0,
            "output": "Welcome!"
        }
    ]
    r = client.post("/api/v1/traces/events", headers={"X-API-Key": project_key}, json={"events": events})
    assert r.status_code == 200
    assert r.json() == {"accepted": 3, "duplicates": 0}

    # Test idempotence / duplicate rejection
    r_dup = client.post("/api/v1/traces/events", headers={"X-API-Key": project_key}, json={"events": events})
    assert r_dup.status_code == 200
    assert r_dup.json() == {"accepted": 0, "duplicates": 3}

    # Query executions list
    r_list = client.get("/api/traces/executions?agent=support-agent")
    assert r_list.status_code == 200
    items = r_list.json()["items"]
    assert len(items) == 1
    assert items[0]["execution_id"] == "test-exec-1"
    assert items[0]["tool_call_count"] == 1
    assert items[0]["status"] == "success"

    # Query single execution details
    r_detail = client.get("/api/traces/executions/test-exec-1")
    assert r_detail.status_code == 200
    det = r_detail.json()
    assert det["agent_name"] == "support-agent"
    assert det["tool_calls"][0]["tool_name"] == "lookup_user"

    # Query tool calls endpoint
    r_tools = client.get("/api/traces/tool-calls?execution_id=test-exec-1")
    assert r_tools.status_code == 200
    assert len(r_tools.json()) == 1

def test_trace_failure_classification(client, project_key):
    now = datetime.now(timezone.utc).isoformat()
    # Tool failure
    events = [
        {
            "event_id": "test-fail-1:start",
            "execution_id": "test-fail-1",
            "agent_name": "worker",
            "type": "execution_start",
            "timestamp": now
        },
        {
            "event_id": "test-fail-1:tool:1",
            "execution_id": "test-fail-1",
            "agent_name": "worker",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "api_fetch",
            "status": "error",
            "error_type": "HTTPError",
            "error_message": "500 Internal Error"
        },
        {
            "event_id": "test-fail-1:end",
            "execution_id": "test-fail-1",
            "agent_name": "worker",
            "type": "execution_end",
            "timestamp": now,
            "status": "failed",
            "error_type": "HTTPError",
            "error_message": "500 Internal Error"
        }
    ]
    r = client.post("/api/v1/traces/events", headers={"X-API-Key": project_key}, json={"events": events})
    assert r.status_code == 200
    det = client.get("/api/traces/executions/test-fail-1").json()
    assert det["status"] == "failed"
    assert det["failure_kind"] == "tool_failure"

def test_create_test_from_trace(client, project_key):
    now = datetime.now(timezone.utc).isoformat()
    events = [
        {
            "event_id": "trace-test-1:start",
            "execution_id": "trace-test-1",
            "agent_name": "pipeline-agent",
            "type": "execution_start",
            "timestamp": now,
            "input": {"prompt": "calculate"}
        },
        {
            "event_id": "trace-test-1:tool:1",
            "execution_id": "trace-test-1",
            "agent_name": "pipeline-agent",
            "type": "tool_call",
            "timestamp": now,
            "tool_name": "compute",
            "status": "success",
            "output": 42
        },
        {
            "event_id": "trace-test-1:end",
            "execution_id": "trace-test-1",
            "agent_name": "pipeline-agent",
            "type": "execution_end",
            "timestamp": now,
            "status": "success",
            "output": "42"
        }
    ]
    client.post("/api/v1/traces/events", headers={"X-API-Key": project_key}, json={"events": events})
    
    # Create test case from trace
    r = client.post("/api/traces/executions/trace-test-1/create-test", json={"name": "Pipeline Test Case"})
    assert r.status_code == 201
    test_case = r.json()
    assert test_case["name"] == "Pipeline Test Case"
    assert test_case["agent_name"] == "pipeline-agent"
    assert test_case["source_type"] == "recorded_real_execution"
    assert test_case["source_trace_id"] == "trace-test-1"

    # Replay it using Phase 2 engine
    r_run = client.post(f"/api/tests/{test_case['id']}/run")
    assert r_run.status_code == 201
    assert r_run.json()["status"] == "passed"

