"""Automated security and integration tests for Multi-Tenant Projects and API Key Management."""
import pytest
from fastapi.testclient import TestClient

from app import database
from app.email_sink import dev_email_sink
from app.main import app
from app.migrations.runner import run_migrations
from app.security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    auth_rate_limiter,
)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Isolate every test in an ephemeral temporary database with migrations applied."""
    db_file = str(tmp_path / "test_projects.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", db_file)
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "test")
    auth_rate_limiter.clear_all()
    dev_email_sink.clear()
    with database.connect() as conn:
        run_migrations(conn)


@pytest.fixture
def client():
    return TestClient(app)


def register_user(client: TestClient, email: str, name: str, password: str = "Password123!") -> dict:
    """Helper: register user and return safe user profile with csrf token."""
    res = client.post("/api/auth/register", json={"email": email, "password": password, "name": name})
    assert res.status_code == 201
    csrf = res.cookies[CSRF_COOKIE_NAME]
    return {"user": res.json(), "csrf": csrf}


# -----------------------------------------------------------------------------
# 1. Project Creation, Listing, and Renaming
# -----------------------------------------------------------------------------

def test_project_lifecycle(client):
    auth = register_user(client, "alice@example.com", "Alice")
    csrf = auth["csrf"]

    # 1. Create a project
    create_res = client.post(
        "/api/projects",
        json={"name": "Alpha Project"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert create_res.status_code == 201
    proj_data = create_res.json()
    assert proj_data["name"] == "Alpha Project"
    assert proj_data["api_key"].startswith("ar_live_")
    project_id = proj_data["id"]

    # 2. List projects (user has auto-provisioned project + Alpha Project)
    list_res = client.get("/api/projects")
    assert list_res.status_code == 200
    projects = list_res.json()
    assert len(projects) >= 2
    assert any(p["name"] == "Alpha Project" for p in projects)

    # 3. Rename project
    patch_res = client.patch(
        f"/api/projects/{project_id}",
        json={"name": "Alpha V2"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Alpha V2"

    # 4. Get individual project
    get_res = client.get(f"/api/projects/{project_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Alpha V2"


# -----------------------------------------------------------------------------
# 2. Project Archival (Soft Deletion with Confirmation)
# -----------------------------------------------------------------------------

def test_project_archival_with_confirmation(client):
    auth = register_user(client, "bob@example.com", "Bob")
    csrf = auth["csrf"]

    create_res = client.post(
        "/api/projects",
        json={"name": "Beta Project"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    project_id = create_res.json()["id"]

    # Deletion fails if confirm_name does not match
    fail_del = client.request(
        "DELETE",
        f"/api/projects/{project_id}",
        json={"confirm_name": "Wrong Name"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert fail_del.status_code == 400
    assert "does not match" in fail_del.json()["detail"]

    # Deletion succeeds with exact matching name
    del_res = client.request(
        "DELETE",
        f"/api/projects/{project_id}",
        json={"confirm_name": "Beta Project"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert del_res.status_code == 200
    assert "archived successfully" in del_res.json()["message"]

    # Archived project is omitted from list and returns 404
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    projs = client.get("/api/projects").json()
    assert not any(p["id"] == project_id for p in projs)


# -----------------------------------------------------------------------------
# 3. Cross-User Data Isolation (Tenant Security)
# -----------------------------------------------------------------------------

def test_cross_user_project_and_key_isolation():
    client_a = TestClient(app)
    auth_a = register_user(client_a, "user_a@example.com", "User A")
    csrf_a = auth_a["csrf"]

    # User A creates project
    res_a = client_a.post("/api/projects", json={"name": "Secret A"}, headers={CSRF_HEADER_NAME: csrf_a})
    proj_a_id = res_a.json()["id"]

    client_b = TestClient(app)
    auth_b = register_user(client_b, "user_b@example.com", "User B")
    csrf_b = auth_b["csrf"]

    # User B attempts to access User A's project -> Must return 404 (anti-enumeration)
    assert client_b.get(f"/api/projects/{proj_a_id}").status_code == 404

    # User B attempts to rename User A's project -> 404
    patch_b = client_b.patch(
        f"/api/projects/{proj_a_id}",
        json={"name": "Hacked"},
        headers={CSRF_HEADER_NAME: csrf_b},
    )
    assert patch_b.status_code == 404

    # User B attempts to list User A's keys -> 404
    assert client_b.get(f"/api/projects/{proj_a_id}/keys").status_code == 404

    # User B attempts to generate key in User A's project -> 404
    post_key_b = client_b.post(
        f"/api/projects/{proj_a_id}/keys",
        json={"name": "Evil Key"},
        headers={CSRF_HEADER_NAME: csrf_b},
    )
    assert post_key_b.status_code == 404


# -----------------------------------------------------------------------------
# 4. API Key Lifecycle: Creation, Revocation, and Rotation
# -----------------------------------------------------------------------------

def test_api_key_lifecycle(client):
    auth = register_user(client, "charlie@example.com", "Charlie")
    csrf = auth["csrf"]

    create_res = client.post("/api/projects", json={"name": "Key Test Project"}, headers={CSRF_HEADER_NAME: csrf})
    project_id = create_res.json()["id"]

    # 1. Generate additional API key
    key_res = client.post(
        f"/api/projects/{project_id}/keys",
        json={"name": "Secondary CI Key"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert key_res.status_code == 201
    key_data = key_res.json()
    assert key_data["name"] == "Secondary CI Key"
    raw_key = key_data["api_key"]
    key_id = key_data["id"]

    # 2. List keys (raw plaintext key must NEVER be included)
    list_keys = client.get(f"/api/projects/{project_id}/keys")
    assert list_keys.status_code == 200
    for k in list_keys.json():
        assert "api_key" not in k and "key_hash" not in k

    # 3. Rotate key
    rotate_res = client.post(
        f"/api/projects/{project_id}/keys/{key_id}/rotate",
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert rotate_res.status_code == 200
    new_raw_key = rotate_res.json()["api_key"]
    assert new_raw_key != raw_key

    # 4. Old key is revoked
    keys_after_rotate = client.get(f"/api/projects/{project_id}/keys").json()
    old_k = next(k for k in keys_after_rotate if k["id"] == key_id)
    assert old_k["revoked_at"] is not None


# -----------------------------------------------------------------------------
# 5. SDK Ingestion with Active vs. Revoked Keys
# -----------------------------------------------------------------------------

def test_sdk_ingestion_with_valid_and_revoked_keys(client):
    auth = register_user(client, "dave@example.com", "Dave")
    csrf = auth["csrf"]

    # Create project & get key
    proj = client.post("/api/projects", json={"name": "SDK Project"}, headers={CSRF_HEADER_NAME: csrf}).json()
    project_id = proj["id"]
    active_key = proj["api_key"]

    event_payload = {
        "events": [
            {
                "event_id": "ev_test_12345",
                "execution_id": "exec_test_12345",
                "agent_name": "test-agent",
                "type": "execution_start",
                "timestamp": "2026-01-01T10:00:00Z",
                "metadata": {}
            }
        ]
    }

    # 1. Ingestion succeeds with active key
    ingest_res = client.post(
        "/api/v1/traces/events",
        json=event_payload,
        headers={"X-API-Key": active_key},
    )
    assert ingest_res.status_code == 200
    assert ingest_res.json()["accepted"] == 1

    # 2. Revoke key
    keys = client.get(f"/api/projects/{project_id}/keys").json()
    first_key_id = keys[0]["id"]
    client.delete(f"/api/projects/{project_id}/keys/{first_key_id}", headers={CSRF_HEADER_NAME: csrf})

    # 3. Ingestion fails with revoked key
    ingest_fail = client.post(
        "/api/v1/traces/events",
        json=event_payload,
        headers={"X-API-Key": active_key},
    )
    assert ingest_fail.status_code == 401
    assert "Invalid API key" in ingest_fail.json()["detail"]


# -----------------------------------------------------------------------------
# 6. CSRF Enforcement on Mutating Project Operations
# -----------------------------------------------------------------------------

def test_csrf_enforcement_on_project_endpoints(client):
    register_user(client, "eve@example.com", "Eve")

    # Creating a project without CSRF header must be blocked with 403
    no_csrf_res = client.post("/api/projects", json={"name": "No CSRF Project"})
    assert no_csrf_res.status_code == 403
    assert "CSRF validation failed" in no_csrf_res.json()["detail"]


# -----------------------------------------------------------------------------
# 7. Production Password Reset Non-Disclosure
# -----------------------------------------------------------------------------

def test_production_password_reset_never_exposes_token(client, monkeypatch):
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "production")
    email = "prod_user@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "Password123!"})

    # Request reset in production mode
    res = client.post("/api/auth/forgot-password", json={"email": email})
    assert res.status_code == 200
    data = res.json()

    # In production, dev_reset_token MUST be strictly None
    assert data["dev_reset_token"] is None

    # In-memory dev email sink MUST fail closed
    assert dev_email_sink.get_latest_token(email) is None
