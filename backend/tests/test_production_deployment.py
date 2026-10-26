"""Tests for production deployment readiness: CORS, cookies, CSRF, health checks, and database config."""
import os
import sqlite3
import pytest
from starlette.testclient import TestClient

from app.database import (
    PostgresConnectionWrapper,
    connect,
    get_database_engine,
    get_database_url,
    init_db,
    is_postgres,
)
from tests.test_postgres_integration import PostgresHarnessConnection


@pytest.fixture
def prod_client(tmp_path, monkeypatch):
    """Create a client configured with production environment variables and an isolated database."""
    test_db = str(tmp_path / "test_prod.db")

    def mock_pg_connect(*args, **kwargs):
        r = sqlite3.connect(test_db)
        h = PostgresHarnessConnection(r)
        return PostgresConnectionWrapper(h)

    monkeypatch.setenv("DATABASE_URL", "postgresql://beta_user:beta_pass@ep-cool-fog.neon.tech/neondb?sslmode=require")
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "production")
    monkeypatch.setenv("AGENTRELIABILITY_COOKIE_SAMESITE", "none")
    monkeypatch.setenv("AGENTRELIABILITY_COOKIE_SECURE", "true")
    monkeypatch.setenv("AGENTRELIABILITY_ALLOWED_ORIGINS", "https://agentreliability.vercel.app,https://app.agentreliability.com")
    monkeypatch.delenv("AGENTRELIABILITY_ALLOWED_ORIGIN_REGEX", raising=False)
    monkeypatch.setattr("app.database._CONNECT_HOOK", mock_pg_connect)

    # Initialize isolated database schema via Postgres migrations
    init_db()

    # Re-import main to rebuild middleware with the production environment variables
    import importlib
    import app.security
    import app.main
    importlib.reload(app.security)
    importlib.reload(app.main)

    client = TestClient(app.main.app)
    yield client

    # Teardown: reload modules to restore default configuration
    monkeypatch.undo()
    importlib.reload(app.security)
    importlib.reload(app.main)


def test_production_health_check(prod_client):
    """Verify health endpoint responds 200 OK with correct production headers."""
    res = prod_client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "x-service" in res.headers
    assert res.headers["x-service"] == "agentreliability-backend"
    assert "x-instance-id" in res.headers


def test_production_cors_allowed_origin(prod_client):
    """Verify CORS preflight and request from configured production origin."""
    origin = "https://agentreliability.vercel.app"
    # Preflight OPTIONS
    res_opt = prod_client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_opt.headers.get("access-control-allow-origin") == origin
    assert res_opt.headers.get("access-control-allow-credentials") == "true"

    # Actual GET request emits Access-Control-Expose-Headers
    res_get = prod_client.get("/api/health", headers={"Origin": origin})
    assert res_get.headers.get("access-control-allow-origin") == origin
    assert "x-csrf-token" in res_get.headers.get("access-control-expose-headers", "").lower()


def test_production_cors_arbitrary_vercel_subdomain_rejected(prod_client):
    """Verify arbitrary *.vercel.app deployments are REJECTED in production when not explicitly allowed."""
    arbitrary_origin = "https://arbitrary-attacker-site.vercel.app"
    res_opt = prod_client.options(
        "/api/health",
        headers={
            "Origin": arbitrary_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_opt.headers.get("access-control-allow-origin") != arbitrary_origin


def test_production_cors_unauthorized_origin_rejected(prod_client):
    """Verify malicious or unconfigured origin does not receive allow-origin header."""
    bad_origin = "https://evil-hacker.com"
    res_opt = prod_client.options(
        "/api/health",
        headers={
            "Origin": bad_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_opt.headers.get("access-control-allow-origin") != bad_origin


def test_production_cookie_samesite_none_and_secure(prod_client):
    """Verify cookies emitted in production mode have SameSite=None and Secure for cross-origin Vercel support."""
    res = prod_client.post(
        "/api/auth/register",
        json={
            "email": "prod_tester@example.com",
            "name": "Production Tester",
            "password": "Password123!",
        },
    )
    assert res.status_code == 201

    # Check Set-Cookie headers
    cookie_headers = res.headers.get_list("set-cookie")
    session_cookie = next((c for c in cookie_headers if "agentreliability_session" in c), None)
    csrf_cookie = next((c for c in cookie_headers if "agentreliability_csrf" in c), None)

    assert session_cookie is not None, "Session cookie was not set!"
    assert csrf_cookie is not None, "CSRF cookie was not set!"

    # Must have SameSite=none and Secure
    assert "samesite=none" in session_cookie.lower()
    assert "secure" in session_cookie.lower()
    assert "httponly" in session_cookie.lower()

    assert "samesite=none" in csrf_cookie.lower()
    assert "secure" in csrf_cookie.lower()

    # Must expose X-CSRF-Token header for cross-origin JavaScript client
    assert "x-csrf-token" in res.headers
    assert len(res.headers["x-csrf-token"]) >= 16


def test_production_logout_cookie_clearing(prod_client):
    """Verify cookies deleted on logout retain SameSite=None and Secure for cross-origin cleanup."""
    res = prod_client.post("/api/auth/logout")
    assert res.status_code == 200

    cookie_headers = res.headers.get_list("set-cookie")
    session_cookie = next((c for c in cookie_headers if "agentreliability_session" in c), None)
    csrf_cookie = next((c for c in cookie_headers if "agentreliability_csrf" in c), None)

    assert session_cookie is not None
    assert csrf_cookie is not None
    assert "samesite=none" in session_cookie.lower()
    assert "secure" in session_cookie.lower()
    assert "samesite=none" in csrf_cookie.lower()
    assert "secure" in csrf_cookie.lower()


def test_production_database_url_requirement(monkeypatch):
    """Verify production requires DATABASE_URL and detects engine."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://neon_user:neon_pass@ep-cool-fog.neon.tech/neondb?sslmode=require")
    assert is_postgres() is True
    assert get_database_engine() == "postgres"
    assert "ep-cool-fog.neon.tech" in get_database_url()
