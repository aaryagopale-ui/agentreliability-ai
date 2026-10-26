"""Tests for same-origin Vercel-to-Render proxy architecture:

SameSite=Lax cookies, host-only cookies, session persistence, CSRF protection,
and absolute URL / redirect proxy leak prevention.
"""
import os
import sqlite3
import pytest
from starlette.testclient import TestClient

from app.database import (
    PostgresConnectionWrapper,
    init_db,
)
from app.security import (
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    get_cookie_samesite,
    get_cookie_secure,
)
from tests.test_postgres_integration import PostgresHarnessConnection


@pytest.fixture
def same_origin_proxy_client(tmp_path, monkeypatch):
    """Simulates Vercel forwarding requests to Render backend under production settings."""
    test_db = str(tmp_path / "test_same_origin_proxy.db")

    def mock_pg_connect(*args, **kwargs):
        r = sqlite3.connect(test_db)
        h = PostgresHarnessConnection(r)
        return PostgresConnectionWrapper(h)

    monkeypatch.setenv("DATABASE_URL", "postgresql://neon_user:neon_pass@ep-cool-fog.neon.tech/neondb?sslmode=require")
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "production")
    # For same-origin proxy, SameSite defaults to lax (no third-party cookie blocking in Safari ITP)
    monkeypatch.delenv("AGENTRELIABILITY_COOKIE_SAMESITE", raising=False)
    monkeypatch.setenv("AGENTRELIABILITY_COOKIE_SECURE", "true")
    monkeypatch.setenv("AGENTRELIABILITY_ALLOWED_ORIGINS", "https://agentreliability-ai.vercel.app")
    monkeypatch.delenv("AGENTRELIABILITY_ALLOWED_ORIGIN_REGEX", raising=False)
    monkeypatch.setattr("app.database._CONNECT_HOOK", mock_pg_connect)

    init_db()

    import importlib
    import app.security
    import app.main
    importlib.reload(app.security)
    importlib.reload(app.main)

    # Use HTTPS base URL to model production TLS through the proxy
    client = TestClient(app.main.app, base_url="https://agentreliability-ai.vercel.app")
    yield client

    monkeypatch.undo()
    importlib.reload(app.security)
    importlib.reload(app.main)


def test_default_production_cookie_samesite_is_lax_and_secure(same_origin_proxy_client):
    """Verify production cookies default to SameSite=Lax and Secure for Safari ITP immunity."""
    assert get_cookie_samesite() == "lax"
    assert get_cookie_secure() is True

    res = same_origin_proxy_client.post(
        "/api/auth/register",
        json={
            "name": "Same-Origin User",
            "email": "sameorigin@example.com",
            "password": "Password123!",
        },
        headers={
            "X-Forwarded-Host": "agentreliability-ai.vercel.app",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": "203.0.113.195",
        },
    )
    assert res.status_code == 201

    cookie_headers = res.headers.get_list("set-cookie")
    session_cookie = next((c for c in cookie_headers if SESSION_COOKIE_NAME in c), None)
    csrf_cookie = next((c for c in cookie_headers if CSRF_COOKIE_NAME in c), None)

    assert session_cookie is not None
    assert csrf_cookie is not None

    # Must be SameSite=Lax (safe for first-party same-origin, immune to Safari ITP block)
    assert "samesite=lax" in session_cookie.lower()
    assert "secure" in session_cookie.lower()
    assert "httponly" in session_cookie.lower()

    # Host-only cookie: NO domain= attribute in Set-Cookie header
    assert "domain=" not in session_cookie.lower()
    assert "domain=" not in csrf_cookie.lower()

    assert "samesite=lax" in csrf_cookie.lower()
    assert "secure" in csrf_cookie.lower()
    # CSRF cookie must be readable by JavaScript
    assert "httponly" not in csrf_cookie.lower()


def test_login_persistence_and_session_through_proxy(same_origin_proxy_client):
    """Verify user can register, log in, and maintain session persistence across requests."""
    proxy_headers = {
        "X-Forwarded-Host": "agentreliability-ai.vercel.app",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-For": "203.0.113.195",
    }

    # 1. Register
    reg = same_origin_proxy_client.post(
        "/api/auth/register",
        json={"name": "Pilot User", "email": "pilot.user@example.com", "password": "StrongPassword123!"},
        headers=proxy_headers,
    )
    assert reg.status_code == 201

    # 2. Login
    login_res = same_origin_proxy_client.post(
        "/api/auth/login",
        json={"email": "pilot.user@example.com", "password": "StrongPassword123!"},
        headers=proxy_headers,
    )
    assert login_res.status_code == 200
    assert login_res.json()["email"] == "pilot.user@example.com"

    # 3. Authenticated me endpoint (session persistence)
    me_res = same_origin_proxy_client.get("/api/auth/me", headers=proxy_headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "pilot.user@example.com"

    # 4. Access protected project endpoints
    projs_res = same_origin_proxy_client.get("/api/projects", headers=proxy_headers)
    assert projs_res.status_code == 200
    assert isinstance(projs_res.json(), list)


def test_csrf_protection_through_proxy(same_origin_proxy_client):
    """Verify CSRF token is required and verified for mutating requests using session cookies."""
    proxy_headers = {
        "X-Forwarded-Host": "agentreliability-ai.vercel.app",
        "X-Forwarded-Proto": "https",
    }

    # Login to establish session
    same_origin_proxy_client.post(
        "/api/auth/register",
        json={"name": "CSRF Tester", "email": "csrf.test@example.com", "password": "Password123!"},
        headers=proxy_headers,
    )
    login_res = same_origin_proxy_client.post(
        "/api/auth/login",
        json={"email": "csrf.test@example.com", "password": "Password123!"},
        headers=proxy_headers,
    )
    assert login_res.status_code == 200
    csrf_token = login_res.headers.get(CSRF_HEADER_NAME)
    assert csrf_token is not None

    # Mutating request WITHOUT CSRF header must be rejected with HTTP 403
    fail_res = same_origin_proxy_client.post(
        "/api/projects",
        json={"name": "Forged Project"},
        headers=proxy_headers,
    )
    assert fail_res.status_code == 403
    assert "CSRF" in fail_res.json()["detail"]

    # Mutating request with INVALID CSRF header must be rejected
    fail_bad_csrf = same_origin_proxy_client.post(
        "/api/projects",
        json={"name": "Forged Project"},
        headers={**proxy_headers, CSRF_HEADER_NAME: "invalid_attacker_token"},
    )
    assert fail_bad_csrf.status_code == 403

    # Mutating request with MATCHING CSRF header must succeed
    ok_res = same_origin_proxy_client.post(
        "/api/projects",
        json={"name": "Legitimate Project"},
        headers={**proxy_headers, CSRF_HEADER_NAME: csrf_token},
    )
    assert ok_res.status_code == 201
    assert ok_res.json()["name"] == "Legitimate Project"


def test_logout_revocation_through_proxy(same_origin_proxy_client):
    """Verify logout revokes session and clears host-only cookies."""
    proxy_headers = {
        "X-Forwarded-Host": "agentreliability-ai.vercel.app",
        "X-Forwarded-Proto": "https",
    }

    same_origin_proxy_client.post(
        "/api/auth/register",
        json={"name": "Logout User", "email": "logout.user@example.com", "password": "Password123!"},
        headers=proxy_headers,
    )
    login_res = same_origin_proxy_client.post(
        "/api/auth/login",
        json={"email": "logout.user@example.com", "password": "Password123!"},
        headers=proxy_headers,
    )
    csrf_token = login_res.headers.get(CSRF_HEADER_NAME)

    # Logout
    logout_res = same_origin_proxy_client.post(
        "/api/auth/logout",
        headers={**proxy_headers, CSRF_HEADER_NAME: csrf_token},
    )
    assert logout_res.status_code == 200

    # Cookie headers must clear both session and CSRF
    cookie_headers = logout_res.headers.get_list("set-cookie")
    session_del = next((c for c in cookie_headers if SESSION_COOKIE_NAME in c), None)
    csrf_del = next((c for c in cookie_headers if CSRF_COOKIE_NAME in c), None)
    assert session_del is not None
    assert csrf_del is not None
    assert "samesite=lax" in session_del.lower()
    assert "secure" in session_del.lower()

    # Subsequent /api/auth/me should return 401
    me_res = same_origin_proxy_client.get("/api/auth/me", headers=proxy_headers)
    assert me_res.status_code == 401


def test_redirect_sanitization_prevents_backend_leak(same_origin_proxy_client):
    """Verify 3xx redirects never leak absolute backend host URLs to the client."""
    from app.main import app
    from fastapi.responses import RedirectResponse

    @app.get("/api/test-redirect")
    def redirect_endpoint():
        return RedirectResponse(url="https://agentreliability-backend.onrender.com/api/target?param=1", status_code=307)

    res = same_origin_proxy_client.get(
        "/api/test-redirect",
        follow_redirects=False,
    )
    assert res.status_code == 307
    loc = res.headers["location"]
    # Location must be sanitized to relative URL so client does not bypass Vercel proxy
    assert loc == "/api/target?param=1"
    assert "onrender.com" not in loc

