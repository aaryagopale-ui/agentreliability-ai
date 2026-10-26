"""SQLite storage operations for users and authentication."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

try:
    import psycopg
    DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)
except ImportError:
    DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError,)

from .database import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_user(email: str, password_hash: str, name: str) -> Optional[dict]:
    """Create a new user. Returns safe user dictionary, or None if email already exists."""
    now = _now()
    clean_name = name.strip() or email.split("@")[0]
    with connect() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO users (email, password_hash, name, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (email.lower().strip(), password_hash, clean_name, now, now),
            )
            user_id = cur.lastrowid

            # Create an initial default project for this user
            conn.execute(
                """INSERT INTO projects (name, owner_id, created_at)
                   VALUES (?, ?, ?)""",
                (f"{clean_name}'s Project", user_id, now),
            )
            return {
                "id": user_id,
                "email": email.lower().strip(),
                "name": clean_name,
                "created_at": now,
            }
        except DB_INTEGRITY_ERRORS:
            # Duplicate email address
            return None


def get_user_by_email_with_hash(email: str) -> Optional[dict]:
    """Retrieve user with password hash (internal auth only; never return to API)."""
    with connect() as conn:
        row = conn.execute(
            """SELECT id, email, password_hash, name, created_at, updated_at
               FROM users WHERE email = ? COLLATE NOCASE""",
            (email.lower().strip(),),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Retrieve safe user profile (without password hash)."""
    with connect() as conn:
        row = conn.execute(
            """SELECT id, email, name, created_at, updated_at
               FROM users WHERE id = ?""",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def update_user_password(user_id: int, new_password_hash: str) -> bool:
    """Update a user's password hash and timestamp."""
    now = _now()
    with connect() as conn:
        cur = conn.execute(
            """UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?""",
            (new_password_hash, now, user_id),
        )
        return cur.rowcount > 0


def email_exists(email: str) -> bool:
    """Check if an email is registered."""
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE",
            (email.lower().strip(),),
        ).fetchone()
        return row is not None

