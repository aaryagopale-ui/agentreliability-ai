"""Security primitives for authentication, sessions, CSRF, rate-limiting, and tokens.

Key Security Design Principles:
1. Passwords hashed using scrypt (RFC 7914 / NIST SP 800-63B) with unique 16-byte random salts.
2. Constant-time string comparisons (hmac.compare_digest) to prevent timing attacks.
3. Cryptographically secure random tokens (secrets.token_urlsafe) for sessions and reset links.
4. Server-side session storage with token SHA-256 hashing (unusable if database is leaked).
5. Generic error messages to prevent user enumeration attacks.
6. Rate limiting for brute-force protection.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .database import connect

# -----------------------------------------------------------------------------
# Configuration (loaded from environment variables, no hardcoded secrets)
# -----------------------------------------------------------------------------

SESSION_COOKIE_NAME = "agentreliability_session"
CSRF_COOKIE_NAME = "agentreliability_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

SESSION_MAX_AGE_SECONDS = int(os.environ.get("AGENTRELIABILITY_SESSION_MAX_AGE_SECONDS", 7 * 24 * 3600))  # 7 days
RESET_TOKEN_MAX_AGE_SECONDS = int(os.environ.get("AGENTRELIABILITY_RESET_TOKEN_MAX_AGE_SECONDS", 3600))  # 1 hour
_is_prod = os.environ.get("AGENTRELIABILITY_ENV", "development").strip().lower() == "production"
COOKIE_SAMESITE = os.environ.get("AGENTRELIABILITY_COOKIE_SAMESITE", "none" if _is_prod else "lax").lower()
# Browsers mandate that SameSite=None cookies MUST have Secure=True
_force_secure = COOKIE_SAMESITE == "none" or _is_prod
COOKIE_SECURE = os.environ.get("AGENTRELIABILITY_COOKIE_SECURE", "true" if _force_secure else "false").lower() in ("true", "1", "yes")
if COOKIE_SAMESITE == "none":
    COOKIE_SECURE = True


def get_cookie_samesite() -> str:
    is_prod = os.environ.get("AGENTRELIABILITY_ENV", "development").strip().lower() == "production"
    return os.environ.get("AGENTRELIABILITY_COOKIE_SAMESITE", "none" if is_prod else "lax").lower()


def get_cookie_secure() -> bool:
    samesite = get_cookie_samesite()
    if samesite == "none":
        return True
    is_prod = os.environ.get("AGENTRELIABILITY_ENV", "development").strip().lower() == "production"
    return os.environ.get("AGENTRELIABILITY_COOKIE_SECURE", "true" if is_prod else "false").lower() in ("true", "1", "yes")

RATE_LIMIT_MAX_ATTEMPTS = int(os.environ.get("AGENTRELIABILITY_RATE_LIMIT_MAX", 5))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("AGENTRELIABILITY_RATE_LIMIT_WINDOW", 900))  # 15 minutes

# Generic messages to prevent user enumeration
AUTH_FAILED_MESSAGE = "Invalid email or password."
RESET_SENT_MESSAGE = "If an account exists with that email, password reset instructions have been generated."


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def hash_token(raw_token: str) -> str:
    """Fast SHA-256 hash for high-entropy tokens (sessions, API keys, reset tokens)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# 1. Password Hashing (scrypt: Memory-Hard, GPU/ASIC-Resistant)
# -----------------------------------------------------------------------------

SCRYPT_N = 16384  # CPU/memory cost
SCRYPT_R = 8      # Block size
SCRYPT_P = 1      # Parallelization


def hash_password(password: str) -> str:
    """Hash a plaintext password using scrypt with a fresh 16-byte cryptographic salt."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=32 * 1024 * 1024,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored scrypt hash in constant time."""
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = bytes.fromhex(parts[4])
        expected = bytes.fromhex(parts[5])

        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            maxmem=32 * 1024 * 1024,
        )
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False


# -----------------------------------------------------------------------------
# 2. Cryptographic Sessions
# -----------------------------------------------------------------------------

def create_session(
    user_id: int,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    max_age_seconds: int = SESSION_MAX_AGE_SECONDS,
) -> Tuple[str, dict]:
    """Create a new server-side session. Returns (plaintext_cookie_token, session_record)."""
    raw_token = secrets.token_urlsafe(32)
    token_h = hash_token(raw_token)
    now = now_utc()
    expires_at = (now + timedelta(seconds=max_age_seconds)).isoformat()
    now_str = now.isoformat()

    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO sessions (user_id, token_hash, created_at, expires_at, user_agent, ip_address)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, token_h, now_str, expires_at, user_agent, ip_address),
        )
        sess_id = cur.lastrowid
        return raw_token, {
            "id": sess_id,
            "user_id": user_id,
            "created_at": now_str,
            "expires_at": expires_at,
            "user_agent": user_agent,
            "ip_address": ip_address,
        }


def _parse_datetime(val: Any) -> Optional[datetime]:
    """Parse datetime from datetime object or ISO string safely."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(val))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def validate_session(raw_token: str) -> Optional[dict]:
    """Validate session token. Returns session dict with user_id, or None if expired/invalid."""
    if not raw_token:
        return None
    token_h = hash_token(raw_token)
    with connect() as conn:
        row = conn.execute(
            """SELECT id, user_id, created_at, expires_at, user_agent, ip_address
               FROM sessions WHERE token_hash = ?""",
            (token_h,),
        ).fetchone()
        if not row:
            return None

        # Check expiration safely supporting string or native datetime
        expires = _parse_datetime(row["expires_at"])

        if now_utc() > expires:
            conn.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
            return None

        return dict(row)


def revoke_session(raw_token: str) -> bool:
    """Revoke a single session token (logout)."""
    if not raw_token:
        return False
    token_h = hash_token(raw_token)
    with connect() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_h,))
        return cur.rowcount > 0


def revoke_all_user_sessions(user_id: int) -> int:
    """Revoke all sessions for a user (password reset / account security)."""
    with connect() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return cur.rowcount


def cleanup_expired_sessions() -> int:
    """Delete all expired sessions from the database."""
    now_str = now_iso()
    with connect() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now_str,))
        return cur.rowcount


# -----------------------------------------------------------------------------
# 3. Password Reset Tokens
# -----------------------------------------------------------------------------

def create_password_reset_token(user_id: int, max_age_seconds: int = RESET_TOKEN_MAX_AGE_SECONDS) -> str:
    """Create a single-use password reset token. Returns plaintext token."""
    raw_token = secrets.token_urlsafe(32)
    token_h = hash_token(raw_token)
    now = now_utc()
    expires_at = (now + timedelta(seconds=max_age_seconds)).isoformat()

    with connect() as conn:
        conn.execute(
            """INSERT INTO password_resets (user_id, token_hash, expires_at, created_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, token_h, expires_at, now.isoformat()),
        )
    return raw_token


def validate_password_reset_token(raw_token: str) -> Optional[int]:
    """Verify reset token is valid, unused, and unexpired. Returns user_id or None."""
    if not raw_token:
        return None
    token_h = hash_token(raw_token)
    with connect() as conn:
        row = conn.execute(
            """SELECT id, user_id, expires_at, used_at FROM password_resets WHERE token_hash = ?""",
            (token_h,),
        ).fetchone()
        if not row:
            return None
        if row["used_at"] is not None:
            return None  # already used

        expires = _parse_datetime(row["expires_at"])

        if now_utc() > expires:
            return None  # expired

        return row["user_id"]


def consume_password_reset_token(raw_token: str) -> Optional[int]:
    """Mark reset token as used (single-use enforcement). Returns user_id if successful."""
    user_id = validate_password_reset_token(raw_token)
    if user_id is None:
        return None
    token_h = hash_token(raw_token)
    with connect() as conn:
        conn.execute("UPDATE password_resets SET used_at = ? WHERE token_hash = ?", (now_iso(), token_h))
    return user_id


# -----------------------------------------------------------------------------
# 4. In-Memory Sliding-Window Rate Limiter
# -----------------------------------------------------------------------------

class RateLimiter:
    """Sliding-window rate limiter for brute-force sensitive endpoints."""

    def __init__(self, max_attempts: int = RATE_LIMIT_MAX_ATTEMPTS, window_seconds: int = RATE_LIMIT_WINDOW_SECONDS):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if action is allowed without recording a failure."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
        return len(self._attempts[key]) < self.max_attempts

    def record_attempt(self, key: str) -> None:
        """Record an attempt (e.g. failed login)."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
        self._attempts[key].append(now)

    def reset(self, key: str) -> None:
        """Clear attempts on successful login."""
        if key in self._attempts:
            del self._attempts[key]

    def clear_all(self) -> None:
        self._attempts.clear()


# Global limiter instances
auth_rate_limiter = RateLimiter(max_attempts=RATE_LIMIT_MAX_ATTEMPTS, window_seconds=RATE_LIMIT_WINDOW_SECONDS)


# -----------------------------------------------------------------------------
# 5. CSRF Protection
# -----------------------------------------------------------------------------

def generate_csrf_token() -> str:
    """Generate a cryptographic double-submit CSRF token."""
    return secrets.token_urlsafe(32)


def verify_csrf_token(header_token: Optional[str], cookie_token: Optional[str]) -> bool:
    """Verify that header CSRF token matches cookie CSRF token in constant time."""
    if not header_token or not cookie_token:
        return False
    return hmac.compare_digest(header_token, cookie_token)

