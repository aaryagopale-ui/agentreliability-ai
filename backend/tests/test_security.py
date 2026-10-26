"""Automated security unit and integration tests for Phase 5A Step 2."""
import sqlite3
import time
from datetime import datetime, timedelta, timezone
import pytest

from app import database
from app.migrations.runner import run_migrations
from app.security import (
    AUTH_FAILED_MESSAGE,
    RESET_SENT_MESSAGE,
    RateLimiter,
    consume_password_reset_token,
    create_password_reset_token,
    create_session,
    generate_csrf_token,
    hash_password,
    hash_token,
    revoke_all_user_sessions,
    revoke_session,
    validate_password_reset_token,
    validate_session,
    verify_csrf_token,
    verify_password,
)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Isolate every test in an ephemeral temporary database with migrations applied."""
    db_file = str(tmp_path / "test_sec.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", db_file)
    with database.connect() as conn:
        run_migrations(conn)
        # Create a test user for session and reset tests
        conn.execute(
            """INSERT INTO users (email, password_hash, name, created_at, updated_at)
               VALUES ('user1@example.com', 'dummy_hash', 'User One', '2026-01-01', '2026-01-01')"""
        )


def _get_user_id() -> int:
    with database.connect() as conn:
        return conn.execute("SELECT id FROM users WHERE email='user1@example.com'").fetchone()[0]


# -----------------------------------------------------------------------------
# 1. Password Hashing Tests
# -----------------------------------------------------------------------------

def test_hash_password_produces_scrypt_format():
    pwd = "CorrectHorseBatteryStaple123"
    hashed = hash_password(pwd)
    assert hashed.startswith("scrypt$16384$8$1$")
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword123", hashed) is False


def test_hash_password_rejects_short_passwords():
    with pytest.raises(ValueError, match="at least 8 characters"):
        hash_password("short")


def test_verify_password_handles_corrupt_hashes():
    assert verify_password("Password123!", "corrupt$hash") is False
    assert verify_password("Password123!", "") is False
    assert verify_password("", "scrypt$16384$8$1$abc$def") is False


def test_unique_salts_for_identical_passwords():
    pwd = "SameSecretPassword123"
    h1 = hash_password(pwd)
    h2 = hash_password(pwd)
    assert h1 != h2, "Salts must be unique per password hash"
    assert verify_password(pwd, h1) is True
    assert verify_password(pwd, h2) is True


# -----------------------------------------------------------------------------
# 2. Session Management Tests
# -----------------------------------------------------------------------------

def test_create_and_validate_session():
    user_id = _get_user_id()
    token, sess = create_session(user_id, user_agent="Mozilla/5.0", ip_address="127.0.0.1")

    assert isinstance(token, str) and len(token) > 20
    assert sess["user_id"] == user_id

    # Verify session is stored as a hash, not plaintext token
    with database.connect() as conn:
        raw_in_db = conn.execute("SELECT token_hash FROM sessions WHERE user_id = ?", (user_id,)).fetchone()[0]
        assert raw_in_db != token
        assert raw_in_db == hash_token(token)

    # Validate session
    validated = validate_session(token)
    assert validated is not None
    assert validated["user_id"] == user_id


def test_session_expiration():
    user_id = _get_user_id()
    # Create session with -10 second lifetime (already expired)
    token, _ = create_session(user_id, max_age_seconds=-10)

    # Validating should fail and delete expired record
    assert validate_session(token) is None

    with database.connect() as conn:
        count = conn.execute("SELECT count(*) FROM sessions WHERE user_id = ?", (user_id,)).fetchone()[0]
        assert count == 0


def test_revoke_session_on_logout():
    user_id = _get_user_id()
    token, _ = create_session(user_id)
    assert validate_session(token) is not None

    revoked = revoke_session(token)
    assert revoked is True
    assert validate_session(token) is None


def test_revoke_all_user_sessions():
    user_id = _get_user_id()
    t1, _ = create_session(user_id)
    t2, _ = create_session(user_id)
    assert validate_session(t1) is not None
    assert validate_session(t2) is not None

    count = revoke_all_user_sessions(user_id)
    assert count == 2
    assert validate_session(t1) is None
    assert validate_session(t2) is None


# -----------------------------------------------------------------------------
# 3. Password Reset Token Tests
# -----------------------------------------------------------------------------

def test_password_reset_token_flow():
    user_id = _get_user_id()
    token = create_password_reset_token(user_id)

    # Token must be valid
    assert validate_password_reset_token(token) == user_id

    # Consume token (single use)
    consumed_id = consume_password_reset_token(token)
    assert consumed_id == user_id

    # Token cannot be reused
    assert validate_password_reset_token(token) is None
    assert consume_password_reset_token(token) is None


def test_password_reset_token_expiration():
    user_id = _get_user_id()
    token = create_password_reset_token(user_id, max_age_seconds=-5)

    assert validate_password_reset_token(token) is None
    assert consume_password_reset_token(token) is None


# -----------------------------------------------------------------------------
# 4. Rate Limiter Tests
# -----------------------------------------------------------------------------

def test_rate_limiter_blocks_after_max_attempts():
    limiter = RateLimiter(max_attempts=3, window_seconds=60)
    key = "127.0.0.1:login"

    assert limiter.is_allowed(key) is True
    limiter.record_attempt(key)
    assert limiter.is_allowed(key) is True
    limiter.record_attempt(key)
    assert limiter.is_allowed(key) is True
    limiter.record_attempt(key)

    # 4th attempt must be blocked
    assert limiter.is_allowed(key) is False

    # Successful login resets the counter
    limiter.reset(key)
    assert limiter.is_allowed(key) is True


# -----------------------------------------------------------------------------
# 5. CSRF Protection Tests
# -----------------------------------------------------------------------------

def test_csrf_token_verification():
    csrf = generate_csrf_token()
    assert isinstance(csrf, str) and len(csrf) > 20

    # Matching header and cookie pass
    assert verify_csrf_token(csrf, csrf) is True

    # Mismatched or missing tokens fail
    assert verify_csrf_token("invalid_header", csrf) is False
    assert verify_csrf_token(None, csrf) is False
    assert verify_csrf_token(csrf, None) is False


# -----------------------------------------------------------------------------
# 6. Anti-Enumeration Messages
# -----------------------------------------------------------------------------

def test_anti_enumeration_messages():
    # Errors must never disclose whether an account exists
    assert AUTH_FAILED_MESSAGE == "Invalid email or password."
    assert "If an account exists" in RESET_SENT_MESSAGE

