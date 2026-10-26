"""Automated end-to-end integration tests for Phase 5A Step 6 (React Auth UI & Project Switcher APIs).

Simulates the complete frontend client lifecycle:
1. Register new developer account and verify automatic project provisioning.
2. Sign in, receive HttpOnly session cookie and double-submit CSRF cookie.
3. Access protected user profile (`/api/auth/me`).
4. List user projects and verify initial project.
5. Create new project with auto-generated initial API key.
6. Switch active project via `X-Project-Id` and confirm isolated executions/test-cases.
7. Rename project and confirm updated name.
8. API Key lifecycle: generate key (verify plaintext returned once), list masked keys, rotate key, and revoke key.
9. Archive project with confirmation name validation.
10. Logout and verify immediate session revocation (subsequent requests return 401).
"""
import pytest
from fastapi.testclient import TestClient

from app import database, project_store
from app.main import app
from app.migrations.runner import run_migrations
from app.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Isolate every test in an ephemeral temporary database with migrations applied."""
    db_file = str(tmp_path / "test_frontend_integration.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", db_file)
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "test")
    with database.connect() as conn:
        run_migrations(conn)


def test_full_frontend_auth_and_project_lifecycle():
    client = TestClient(app)

    # 1. Unauthenticated client accessing dashboard endpoints receives 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/executions").status_code == 401

    # 2. Sign up: POST /api/auth/register
    reg_res = client.post(
        "/api/auth/register",
        json={"email": "developer@agentreliability.ai", "password": "SecurePassword123!", "name": "Dev User"},
    )
    assert reg_res.status_code == 201
    user_data = reg_res.json()
    assert user_data["email"] == "developer@agentreliability.ai"
    assert user_data["name"] == "Dev User"

    # Verify session and CSRF cookies were set
    assert SESSION_COOKIE_NAME in reg_res.cookies
    assert CSRF_COOKIE_NAME in reg_res.cookies
    csrf_token = reg_res.cookies[CSRF_COOKIE_NAME]
    auth_headers = {CSRF_HEADER_NAME: csrf_token}

    # 3. Access /api/auth/me
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "developer@agentreliability.ai"

    # 4. List projects: Verify initial auto-provisioned project
    projs_res = client.get("/api/projects")
    assert projs_res.status_code == 200
    initial_projects = projs_res.json()
    assert len(initial_projects) >= 1
    proj_1 = initial_projects[0]
    assert "Dev User's Project" in proj_1["name"]

    # 5. Create a second project: POST /api/projects
    create_proj_res = client.post(
        "/api/projects",
        json={"name": "Production Agents"},
        headers=auth_headers,
    )
    assert create_proj_res.status_code == 201
    proj_2 = create_proj_res.json()
    assert proj_2["name"] == "Production Agents"
    # Plaintext API key is returned exactly once
    assert "api_key" in proj_2
    assert proj_2["api_key"].startswith("ar_live_")

    # 6. Switch active project via X-Project-Id header
    # In Project 2, upload an execution
    proj_2_headers = {**auth_headers, "X-Project-Id": str(proj_2["id"])}
    sample_log = {
        "agent_name": "prod-customer-service",
        "run_id": "run-prod-001",
        "steps": [{"type": "tool_call", "name": "search_db", "status": "success", "output": {"found": True}}],
    }
    import json
    upload_res = client.post(
        "/api/executions",
        files={"file": ("log.json", json.dumps(sample_log), "application/json")},
        headers=proj_2_headers,
    )
    assert upload_res.status_code == 201
    exec_2_id = upload_res.json()["id"]

    # Verify Project 2 sees the execution
    list_p2 = client.get("/api/executions", headers=proj_2_headers).json()
    assert any(e["id"] == exec_2_id for e in list_p2)

    # Verify Project 1 does NOT see the execution (project switching isolation)
    proj_1_headers = {**auth_headers, "X-Project-Id": str(proj_1["id"])}
    list_p1 = client.get("/api/executions", headers=proj_1_headers).json()
    assert not any(e["id"] == exec_2_id for e in list_p1)

    # 7. Rename Project 2: PATCH /api/projects/{id}
    patch_res = client.patch(
        f"/api/projects/{proj_2['id']}",
        json={"name": "Production Agents V2"},
        headers=auth_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Production Agents V2"

    # 8. API Key Management in Project 2:
    # 8a. Generate additional key
    key_res = client.post(
        f"/api/projects/{proj_2['id']}/keys",
        json={"name": "CI Runner Key"},
        headers=auth_headers,
    )
    assert key_res.status_code == 201
    key_data = key_res.json()
    raw_ci_key = key_data["api_key"]
    ci_key_id = key_data["id"]

    # 8b. List keys: plaintext key is NEVER returned in listings
    keys_list = client.get(f"/api/projects/{proj_2['id']}/keys").json()
    assert len(keys_list) >= 2
    for k in keys_list:
        assert "api_key" not in k
        assert "key_hash" not in k
        assert "key_prefix" in k

    # 8c. Rotate the CI Runner Key
    rotate_res = client.post(
        f"/api/projects/{proj_2['id']}/keys/{ci_key_id}/rotate",
        headers=auth_headers,
    )
    assert rotate_res.status_code == 200
    new_rotated_key = rotate_res.json()["api_key"]
    assert new_rotated_key != raw_ci_key

    # 8d. Revoke the rotated key
    rotated_key_id = rotate_res.json()["id"]
    revoke_res = client.delete(
        f"/api/projects/{proj_2['id']}/keys/{rotated_key_id}",
        headers=auth_headers,
    )
    assert revoke_res.status_code == 200

    # 9. Archive Project 2 with confirmation name matching
    # Fails if confirmation name doesn't match
    bad_archive = client.request(
        "DELETE",
        f"/api/projects/{proj_2['id']}",
        json={"confirm_name": "Wrong Name"},
        headers=auth_headers,
    )
    assert bad_archive.status_code == 400

    # Succeeds with exact name match
    good_archive = client.request(
        "DELETE",
        f"/api/projects/{proj_2['id']}",
        json={"confirm_name": "Production Agents V2"},
        headers=auth_headers,
    )
    assert good_archive.status_code == 200

    # 10. Logout: POST /api/auth/logout
    logout_res = client.post("/api/auth/logout", headers=auth_headers)
    assert logout_res.status_code == 200

    # After logout, accessing protected endpoints immediately returns 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/projects").status_code == 401
