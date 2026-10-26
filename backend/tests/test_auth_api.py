"""Automated tests for Authentication APIs (Phase 5A Step 3)."""
import pytest
from fastapi.testclient import TestClient

from app import database
from app.email_sink import dev_email_sink
from app.main import app
from app.migrations.runner import run_migrations
from app.security import (
    AUTH_FAILED_MESSAGE,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    RESET_SENT_MESSAGE,
    SESSION_COOKIE_NAME,
    auth_rate_limiter,
    create_password_reset_token,
    create_session,
)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Isolate every test in an ephemeral temporary database with migrations applied."""
    db_file = str(tmp_path / "test_auth_api.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", db_file)
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "test")
    auth_rate_limiter.clear_all()
    with database.connect() as conn:
        run_migrations(conn)


@pytest.fixture
def client():
    return TestClient(app)


# -----------------------------------------------------------------------------
# Registration Tests
# -----------------------------------------------------------------------------

def test_register_success(client):
    res = client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "password": "Password123!", "name": "Alice"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "alice@example.com"
    assert data["name"] == "Alice"
    assert "password" not in data and "password_hash" not in data

    # Verify session and CSRF cookies are set
    cookies = res.cookies
    assert SESSION_COOKIE_NAME in cookies
    assert CSRF_COOKIE_NAME in cookies
    assert res.headers.get("X-CSRF-Token") == cookies[CSRF_COOKIE_NAME]


def test_register_rejects_duplicate_email(client):
    payload = {"email": "bob@example.com", "password": "Password123!", "name": "Bob"}
    res1 = client.post("/api/auth/register", json=payload)
    assert res1.status_code == 201

    # Second attempt with same email
    res2 = client.post("/api/auth/register", json=payload)
    assert res2.status_code == 400
    assert "Unable to complete registration" in res2.json()["detail"]


def test_register_validates_password_length(client):
    res = client.post(
        "/api/auth/register",
        json={"email": "charlie@example.com", "password": "short", "name": "Charlie"},
    )
    assert res.status_code == 422


# -----------------------------------------------------------------------------
# Login & Profile Tests
# -----------------------------------------------------------------------------

def test_login_success_and_me(client):
    # 1. Register
    client.post(
        "/api/auth/register",
        json={"email": "dave@example.com", "password": "DavePassword123!", "name": "Dave"},
    )

    # 2. Login with separate client
    new_client = TestClient(app)
    res = new_client.post(
        "/api/auth/login",
        json={"email": "dave@example.com", "password": "DavePassword123!"},
    )
    assert res.status_code == 200
    assert res.json()["email"] == "dave@example.com"
    assert SESSION_COOKIE_NAME in res.cookies

    # 3. Access /api/auth/me
    me_res = new_client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "dave@example.com"
    assert me_res.json()["name"] == "Dave"


def test_login_invalid_password(client):
    client.post(
        "/api/auth/register",
        json={"email": "eve@example.com", "password": "EvePassword123!", "name": "Eve"},
    )

    res = client.post(
        "/api/auth/login",
        json={"email": "eve@example.com", "password": "WrongPassword!"},
    )
    assert res.status_code == 401
    assert res.json()["detail"] == AUTH_FAILED_MESSAGE


def test_unauthenticated_me_returns_401(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert "Not authenticated" in res.json()["detail"]


# -----------------------------------------------------------------------------
# Logout & CSRF Tests
# -----------------------------------------------------------------------------

def test_logout_with_csrf_revokes_session(client):
    # 1. Register & login
    reg = client.post(
        "/api/auth/register",
        json={"email": "frank@example.com", "password": "FrankPassword123!", "name": "Frank"},
    )
    csrf_token = reg.cookies[CSRF_COOKIE_NAME]

    # 2. Logout with matching CSRF header
    logout_res = client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: csrf_token})
    assert logout_res.status_code == 200
    assert logout_res.json()["message"] == "Logged out successfully."

    # 3. Subsequent call to /me must fail with 401
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 401


def test_logout_rejects_missing_or_invalid_csrf(client):
    # 1. Register & login
    client.post(
        "/api/auth/register",
        json={"email": "grace@example.com", "password": "GracePassword123!", "name": "Grace"},
    )

    # 2. Attempt logout without CSRF header
    res_no_csrf = client.post("/api/auth/logout")
    assert res_no_csrf.status_code == 403
    assert "CSRF validation failed" in res_no_csrf.json()["detail"]

    # 3. Attempt logout with bogus CSRF header
    res_bad_csrf = client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: "bogus_token"})
    assert res_bad_csrf.status_code == 403


# -----------------------------------------------------------------------------
# Rate Limiting Tests
# -----------------------------------------------------------------------------

def test_login_rate_limiting(client):
    email = "target@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "TargetPassword123!"},
    )

    # Exceed rate limit (max 5 failed attempts)
    for _ in range(5):
        res = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
        assert res.status_code == 401

    # 6th attempt must be blocked by rate limiter with 429
    blocked = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
    assert blocked.status_code == 429
    assert "Too many attempts" in blocked.json()["detail"]


# -----------------------------------------------------------------------------
# Password Reset Flow Tests
# -----------------------------------------------------------------------------

def test_forgot_and_reset_password_flow(client):
    # 1. Register user
    email = "heidi@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "OldPassword123!", "name": "Heidi"},
    )

    # 2. Request reset
    forgot_res = client.post("/api/auth/forgot-password", json={"email": email})
    assert forgot_res.status_code == 200
    assert forgot_res.json()["message"] == RESET_SENT_MESSAGE
    dev_token = dev_email_sink.get_latest_token(email)
    assert dev_token is not None

    # 3. Reset password
    reset_res = client.post(
        "/api/auth/reset-password",
        json={"token": dev_token, "new_password": "NewPassword123!"},
    )
    assert reset_res.status_code == 200
    assert "successfully reset" in reset_res.json()["message"]

    # 4. Login with old password fails
    login_old = client.post("/api/auth/login", json={"email": email, "password": "OldPassword123!"})
    assert login_old.status_code == 401

    # 5. Login with new password succeeds
    login_new = client.post("/api/auth/login", json={"email": email, "password": "NewPassword123!"})
    assert login_new.status_code == 200


def test_forgot_password_anti_enumeration(client):
    # Non-existent email receives the exact same message
    res = client.post("/api/auth/forgot-password", json={"email": "nonexistent@example.com"})
    assert res.status_code == 200
    assert res.json()["message"] == RESET_SENT_MESSAGE
    assert dev_email_sink.get_latest_token("nonexistent@example.com") is None


def test_reset_password_token_single_use(client):
    email = "ivan@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "Password123!"})
    forgot_res = client.post("/api/auth/forgot-password", json={"email": email})
    dev_token = dev_email_sink.get_latest_token(email)

    # First reset succeeds
    res1 = client.post("/api/auth/reset-password", json={"token": dev_token, "new_password": "NewPassword1!"})
    assert res1.status_code == 200

    # Second reset with same token fails
    res2 = client.post("/api/auth/reset-password", json={"token": dev_token, "new_password": "AnotherPassword2!"})
    assert res2.status_code == 400
    assert "already been used" in res2.json()["detail"]


def test_password_reset_revokes_existing_sessions(client):
    # 1. Register & login with client1
    email = "judy@example.com"
    client1 = TestClient(app)
    client1.post("/api/auth/register", json={"email": email, "password": "Password123!"})
    assert client1.get("/api/auth/me").status_code == 200

    # 2. Trigger password reset
    forgot_res = client1.post("/api/auth/forgot-password", json={"email": email})
    dev_token = dev_email_sink.get_latest_token(email)

    client2 = TestClient(app)
    client2.post("/api/auth/reset-password", json={"token": dev_token, "new_password": "BrandNewPassword1!"})

    # 3. client1's prior session must now be invalidated
    assert client1.get("/api/auth/me").status_code == 401

