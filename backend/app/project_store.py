"""SQLite storage operations for projects and API keys."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from .database import connect

KEY_PREFIX = "ar_live_"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# Projects
# -----------------------------------------------------------------------------

def list_user_projects(owner_id: int, include_archived: bool = False) -> List[dict]:
    """List projects owned by the specified user."""
    sql = "SELECT id, name, owner_id, created_at, updated_at, archived_at FROM projects WHERE owner_id = ?"
    if not include_archived:
        sql += " AND archived_at IS NULL"
    sql += " ORDER BY id DESC"

    with connect() as conn:
        rows = conn.execute(sql, (owner_id,)).fetchall()
        return [dict(r) for r in rows]


def get_project(project_id: int, owner_id: Optional[int] = None) -> Optional[dict]:
    """Retrieve a project. If owner_id is provided, enforces ownership check."""
    sql = "SELECT id, name, owner_id, created_at, updated_at, archived_at FROM projects WHERE id = ? AND archived_at IS NULL"
    params = [project_id]
    if owner_id is not None:
        sql += " AND owner_id = ?"
        params.append(owner_id)

    with connect() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def create_project(name: str, owner_id: int) -> Tuple[dict, str]:
    """Create a project and its initial API key. Returns (project_record, plaintext_key)."""
    now = _now()
    clean_name = name.strip()
    plaintext_key = KEY_PREFIX + secrets.token_urlsafe(32)

    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO projects (name, owner_id, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (clean_name, owner_id, now, now),
        )
        project_id = cur.lastrowid

        # Create initial API key for project
        conn.execute(
            """INSERT INTO api_keys (project_id, name, key_prefix, key_hash, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, f"{clean_name} Default Key", plaintext_key[:12], hash_key(plaintext_key), now),
        )

        project_record = {
            "id": project_id,
            "name": clean_name,
            "owner_id": owner_id,
            "created_at": now,
            "updated_at": now,
            "archived_at": None,
        }
        return project_record, plaintext_key


def update_project_name(project_id: int, new_name: str, owner_id: int) -> Optional[dict]:
    """Rename a project owned by the user."""
    now = _now()
    clean_name = new_name.strip()
    with connect() as conn:
        cur = conn.execute(
            """UPDATE projects SET name = ?, updated_at = ?
               WHERE id = ? AND owner_id = ? AND archived_at IS NULL""",
            (clean_name, now, project_id, owner_id),
        )
        if cur.rowcount == 0:
            return None
    return get_project(project_id, owner_id)


def archive_project(project_id: int, owner_id: int) -> bool:
    """Soft-delete / archive project. Historical executions, tests, and traces are preserved."""
    now = _now()
    with connect() as conn:
        cur = conn.execute(
            """UPDATE projects SET archived_at = ?, updated_at = ?
               WHERE id = ? AND owner_id = ? AND archived_at IS NULL""",
            (now, now, project_id, owner_id),
        )
        return cur.rowcount > 0


def claim_legacy_project(project_id: int, new_owner_id: int) -> bool:
    """Claim an unowned legacy project (where owner_id is NULL)."""
    now = _now()
    with connect() as conn:
        cur = conn.execute(
            """UPDATE projects SET owner_id = ?, updated_at = ?
               WHERE id = ? AND owner_id IS NULL AND archived_at IS NULL""",
            (new_owner_id, now, project_id),
        )
        return cur.rowcount > 0


# -----------------------------------------------------------------------------
# API Keys
# -----------------------------------------------------------------------------

def list_project_keys(project_id: int) -> List[dict]:
    """List API keys for a project with safe metadata (no plaintext or key_hash)."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, project_id, name, key_prefix, created_at, last_used_at, revoked_at
               FROM api_keys WHERE project_id = ? ORDER BY id DESC""",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_api_key(project_id: int, key_id: int) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            """SELECT id, project_id, name, key_prefix, created_at, last_used_at, revoked_at
               FROM api_keys WHERE id = ? AND project_id = ?""",
            (key_id, project_id),
        ).fetchone()
        return dict(row) if row else None


def create_api_key(project_id: int, name: str = "API Key") -> Tuple[dict, str]:
    """Generate a new API key. Returns (safe_key_record, plaintext_key_shown_once)."""
    now = _now()
    clean_name = name.strip() or "API Key"
    plaintext_key = KEY_PREFIX + secrets.token_urlsafe(32)

    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO api_keys (project_id, name, key_prefix, key_hash, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, clean_name, plaintext_key[:12], hash_key(plaintext_key), now),
        )
        key_id = cur.lastrowid
        key_record = {
            "id": key_id,
            "project_id": project_id,
            "name": clean_name,
            "key_prefix": plaintext_key[:12],
            "created_at": now,
            "last_used_at": None,
            "revoked_at": None,
        }
        return key_record, plaintext_key


def revoke_api_key(project_id: int, key_id: int) -> bool:
    """Revoke an API key."""
    now = _now()
    with connect() as conn:
        cur = conn.execute(
            """UPDATE api_keys SET revoked_at = ?
               WHERE id = ? AND project_id = ? AND revoked_at IS NULL""",
            (now, key_id, project_id),
        )
        return cur.rowcount > 0


def rotate_api_key(project_id: int, key_id: int) -> Optional[Tuple[dict, str]]:
    """Rotate an existing key: revokes the old key and generates a fresh active key."""
    existing = get_api_key(project_id, key_id)
    if not existing:
        return None

    # Revoke old key
    revoke_api_key(project_id, key_id)

    # Generate new key with the same name
    new_record, new_plaintext = create_api_key(project_id, name=existing["name"])
    return new_record, new_plaintext
