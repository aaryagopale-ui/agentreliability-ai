import pytest
from fastapi.testclient import TestClient

from app.main import app

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTRELIABILITY_DB", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c

@pytest.fixture()
def project_key(client):
    from app.create_key import create_key
    return create_key("ci-project")

def test_ci_ingest_auth_required(client):
    r = client.post("/api/v1/ci/runs", json={})
    assert r.status_code == 401

def test_ci_ingest_and_query(client, project_key):
    payload = {
        "commit_sha": "a1b2c3d4e5f6",
        "branch": "feature/agent-tools",
        "actor": "octocat",
        "total": 5,
        "passed": 4,
        "failed": 1,
        "duration_ms": 142.5,
        "report": {
            "results": [
                {"name": "test_pass", "status": "passed"},
                {"name": "test_fail", "status": "failed", "mismatches": [{"kind": "timeout", "message": "Timed out"}]}
            ]
        }
    }
    r = client.post("/api/v1/ci/runs", headers={"X-API-Key": project_key}, json=payload)
    assert r.status_code == 201
    run_id = r.json()["id"]
    assert run_id > 0

    # Query list
    r_list = client.get("/api/ci/runs")
    assert r_list.status_code == 200
    items = r_list.json()
    assert len(items) == 1
    assert items[0]["commit_sha"] == "a1b2c3d4e5f6"
    assert items[0]["status"] == "failed"

    # Query detail
    r_detail = client.get(f"/api/ci/runs/{run_id}")
    assert r_detail.status_code == 200
    det = r_detail.json()
    assert det["actor"] == "octocat"
    assert det["report"]["results"][1]["name"] == "test_fail"

