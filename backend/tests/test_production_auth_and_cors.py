"""Tests for production CORS resolution, error preservation, and PostgreSQL datetime serialization in auth."""
import os
import sqlite3
import datetime
import pytest
from starlette.testclient import TestClient

from app.database import (
    PostgresConnectionWrapper,
    get_database_engine,
    get_database_url,
    init_db,
    is_postgres,
)
from app.auth_schemas import UserResponse
from app.project_schemas import ProjectResponse, ApiKeyResponse
from app.security import _parse_datetime, validate_session, hash_password
from tests.test_postgres_integration import PostgresHarnessConnection


class PostgresDatetimeHarnessConnection(PostgresHarnessConnection):
    """Extends PostgresHarnessConnection to return native datetime objects for TIMESTAMPTZ columns,

    faithfully replicating psycopg3's behavior on PostgreSQL.
    """

    def cursor(self):
        c = super().cursor()
        orig_execute = c.execute

        def execute_with_datetimes(query, params=None):
            orig_execute(query, params)
            # Decorate fetchone and fetchall to inject real datetime objects
            orig_fetchone = c.fetchone
            orig_fetchall = c.fetchall

            def _convert_row(r):
                if r is None:
                    return None
                d = dict(r)
                for k, v in d.items():
                    if k in ("created_at", "updated_at", "expires_at") and isinstance(v, str):
                        try:
                            # Replace with real datetime object
                            d[k] = datetime.datetime.fromisoformat(v)
                        except Exception:
                            pass
                return d

            def wrapped_fetchone():
                r = orig_fetchone()
                return _convert_row(r)

            def wrapped_fetchall():
                rows = orig_fetchall()
                return [_convert_row(r) for r in rows]

            c.fetchone = wrapped_fetchone
            c.fetchall = wrapped_fetchall
            return c

        c.execute = execute_with_datetimes
        return c


@pytest.fixture
def prod_neon_client(tmp_path, monkeypatch):
    """Client simulating production on Render with Neon PostgreSQL and native datetimes."""
    test_db = str(tmp_path / "test_prod_neon.db")

    def mock_pg_connect(*args, **kwargs):
        r = sqlite3.connect(test_db)
        h = PostgresDatetimeHarnessConnection(r)
        return PostgresConnectionWrapper(h)

    monkeypatch.setenv("DATABASE_URL", "postgresql://neon_user:s3cr3t_pass@ep-cool-fog.neon.tech/neondb?sslmode=require")
    monkeypatch.setenv("AGENTRELIABILITY_ENV", "production")
    monkeypatch.setenv("AGENTRELIABILITY_COOKIE_SAMESITE", "none")
    monkeypatch.setenv("AGENTRELIABILITY_COOKIE_SECURE", "true")
    # Leave AGENTRELIABILITY_ALLOWED_ORIGINS unset to test default production origins
    monkeypatch.delenv("AGENTRELIABILITY_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("AGENTRELIABILITY_ALLOWED_ORIGIN_REGEX", raising=False)
    monkeypatch.setattr("app.database._CONNECT_HOOK", mock_pg_connect)

    init_db()

    import importlib
    import app.security
    import app.main
    importlib.reload(app.security)
    importlib.reload(app.main)

    client = TestClient(app.main.app, base_url="https://testserver")
    yield client

    monkeypatch.undo()
    importlib.reload(app.security)
    importlib.reload(app.main)


def test_default_production_cors_allows_vercel_domain(prod_neon_client):
    """Ensure https://agentreliability-ai.vercel.app is allowed by default in production."""
    origin = "https://agentreliability-ai.vercel.app"
    res_opt = prod_neon_client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_opt.status_code == 200
    assert res_opt.headers.get("access-control-allow-origin") == origin
    assert res_opt.headers.get("access-control-allow-credentials") == "true"


def test_cors_resolution_strips_trailing_slashes_and_spaces(monkeypatch):
    """Test resolve_allowed_origins normalizes origins."""
    from app.main import resolve_allowed_origins
    monkeypatch.setenv("AGENTRELIABILITY_ALLOWED_ORIGINS", " https://custom-frontend.vercel.app/ , https://other.app/ ")
    origins = resolve_allowed_origins()
    assert "https://custom-frontend.vercel.app" in origins
    assert "https://other.app" in origins
    assert "https://agentreliability-ai.vercel.app" in origins
    # Trailing slashes stripped
    assert "https://custom-frontend.vercel.app/" not in origins


def test_cors_preserved_on_500_error(prod_neon_client):
    """Verify that unhandled 500 exceptions still return CORS headers to the browser."""
    origin = "https://agentreliability-ai.vercel.app"
    # Trigger an intentional unhandled exception
    from app.main import app

    @app.get("/api/test-crash")
    def crash_endpoint():
        raise RuntimeError("Simulated unhandled production crash")

    res = prod_neon_client.get("/api/test-crash", headers={"Origin": origin})
    assert res.status_code == 500
    assert res.headers.get("access-control-allow-origin") == origin
    assert res.headers.get("access-control-allow-credentials") == "true"
    assert "Internal server error" in res.json()["detail"]


def test_login_and_auth_with_native_postgres_datetimes(prod_neon_client):
    """Verify registration, login, and /api/auth/me succeed when database returns native datetimes."""
    origin = "https://agentreliability-ai.vercel.app"

    # Register
    reg_res = prod_neon_client.post(
        "/api/auth/register",
        json={
            "name": "Beta Pilot Developer",
            "email": "pilot@example.com",
            "password": "SecurePassword123!",
        },
        headers={"Origin": origin},
    )
    assert reg_res.status_code == 201, reg_res.text
    data = reg_res.json()
    assert data["email"] == "pilot@example.com"
    assert isinstance(data["created_at"], str)

    # Login - this was the exact endpoint failing with HTTP 500
    login_res = prod_neon_client.post(
        "/api/auth/login",
        json={
            "email": "pilot@example.com",
            "password": "SecurePassword123!",
        },
        headers={"Origin": origin},
    )
    assert login_res.status_code == 200, f"Login failed with {login_res.status_code}: {login_res.text}"
    user_data = login_res.json()
    assert user_data["email"] == "pilot@example.com"
    assert isinstance(user_data["created_at"], str)
    assert login_res.headers.get("access-control-allow-origin") == origin

    # Case-insensitive login check
    case_res = prod_neon_client.post(
        "/api/auth/login",
        json={
            "email": "PILOT@EXAMPLE.COM",
            "password": "SecurePassword123!",
        },
        headers={"Origin": origin},
    )
    assert case_res.status_code == 200

    # /api/auth/me with session cookie
    me_res = prod_neon_client.get("/api/auth/me", headers={"Origin": origin})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "pilot@example.com"


def test_system_info_under_postgres(prod_neon_client):
    """Verify /api/v1/system/info and get_instance_identity report Neon PostgreSQL with masked secrets."""
    res = prod_neon_client.get("/api/v1/system/info")
    assert res.status_code == 200
    data = res.json()
    assert data["database_engine"] == "postgres"
    assert "PostgreSQL" in data["database_name"]
    assert "ep-cool-fog.neon.tech" in data["database_name"]
    assert "ep-cool-fog.neon.tech" in data["database_path"]
    assert "s3cr3t_pass" not in data["database_path"]
    assert "***" in data["database_path"]


def test_schemas_accept_datetime_objects():
    """Verify Pydantic response models accept datetime objects directly without validation error."""
    now = datetime.datetime.now(datetime.timezone.utc)
    u = UserResponse(id=2, email="user@example.com", name="User", created_at=now)
    assert isinstance(u.created_at, str)
    assert u.created_at == now.isoformat()

    p = ProjectResponse(id=1, name="My Agent", owner_id=2, created_at=now)
    assert isinstance(p.created_at, str)

    k = ApiKeyResponse(id=1, project_id=1, name="Test Key", key_prefix="ar_live_", created_at=now)
    assert isinstance(k.created_at, str)


def test_parse_datetime_handles_both_types():
    """Verify _parse_datetime handles str, datetime, and invalid types."""
    now = datetime.datetime.now(datetime.timezone.utc)
    assert _parse_datetime(now) == now
    assert _parse_datetime(now.isoformat()) == now
    assert _parse_datetime(None) is None
    assert _parse_datetime(12345) is None
