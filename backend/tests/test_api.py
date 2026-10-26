import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

SAMPLES = Path(__file__).resolve().parents[2] / "sample_logs"


from app import database, project_store
from app.migrations.runner import run_migrations
from app.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Each test gets its own empty database file with migrations applied.
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
        if projs:
            project_store.archive_project(projs[0]["id"], user["id"])
        project_store.claim_legacy_project(1, user["id"])
        yield c


def upload(client, content, name="log.json"):
    if not isinstance(content, (bytes, str)):
        content = json.dumps(content)
    return client.post("/api/executions", files={"file": (name, content, "application/json")})


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_upload_success_sample(client):
    r = upload(client, (SAMPLES / "success_log.json").read_text())
    assert r.status_code == 201
    assert r.json()["status"] == "success"


def test_upload_failed_sample_has_findings(client):
    r = upload(client, (SAMPLES / "failed_tool_log.json").read_text())
    body = r.json()
    assert body["status"] == "failed"
    cats = [f["category"] for f in body["findings"]]
    assert cats == ["failed_tool_call", "explicit_error"]


def test_upload_timeout_sample(client):
    body = upload(client, (SAMPLES / "timeout_log.json").read_text()).json()
    assert [f["category"] for f in body["findings"]] == ["timeout", "timeout"]


def test_invalid_json_rejected(client):
    assert upload(client, "{not json").status_code == 400


def test_invalid_format_rejected_with_problems(client):
    r = upload(client, {"agent_name": "a", "steps": []})
    assert r.status_code == 422
    assert r.json()["detail"]["problems"]


def test_list_and_get_persisted(client):
    upload(client, (SAMPLES / "success_log.json").read_text())
    upload(client, (SAMPLES / "failed_tool_log.json").read_text())
    rows = client.get("/api/executions").json()
    assert len(rows) == 2 and rows[0]["agent_name"] == "research-agent"
    detail = client.get(f"/api/executions/{rows[0]['id']}").json()
    assert len(detail["steps"]) == 4


def test_get_missing_404(client):
    assert client.get("/api/executions/999").status_code == 404


def test_seed(client):
    from app.seed import seed
    assert seed() == 3
    assert len(client.get("/api/executions").json()) == 3

