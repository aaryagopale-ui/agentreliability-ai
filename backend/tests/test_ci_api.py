import pytest
from fastapi.testclient import TestClient

from app import database, project_store
from app.main import app
from app.migrations.runner import run_migrations
from app.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", db_file)
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "test")
    with database.connect() as conn:
        run_migrations(conn)

    with TestClient(app) as c:
        res = c.post("/api/auth/register", json={"email": "alice@example.com", "password": "Password123!", "name": "Alice"})
        user = res.json()
        csrf = res.cookies[CSRF_COOKIE_NAME]
        c.headers[CSRF_HEADER_NAME] = csrf
        projs = project_store.list_user_projects(user["id"])
        c.user_id = user["id"]
        c.project_id = projs[0]["id"]
        yield c

@pytest.fixture()
def project_key(client):
    _, raw_key = project_store.create_api_key(client.project_id, "CI Key")
    return raw_key

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

