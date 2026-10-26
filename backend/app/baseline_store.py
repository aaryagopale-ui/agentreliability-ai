"""SQLite storage operations for regression baselines and baseline versions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .database import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(v: Any) -> Optional[str]:
    return None if v is None else json.dumps(v)


def _load(v: Optional[str]) -> Any:
    return None if v is None else json.loads(v)


def _baseline_version_dict(row) -> dict:
    return {
        "id": row["id"],
        "baseline_id": row["baseline_id"],
        "version": row["version"],
        "source_type": row["source_type"],
        "source_id": row["source_id"],
        "status": row["status"],
        "duration_ms": row["duration_ms"],
        "input": _load(row["input_json"]),
        "output": _load(row["output_json"]),
        "tools": _load(row["tools_json"]) or [],
        "expected": _load(row["expected_json"]) or {},
        "created_at": row["created_at"],
        "created_by_user_id": row["created_by_user_id"],
    }


def _baseline_dict(row, version_row=None) -> dict:
    d = {
        "id": row["id"],
        "project_id": row["project_id"],
        "agent_name": row["agent_name"],
        "name": row["name"],
        "description": row["description"],
        "current_version": row["current_version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if version_row:
        d["version_data"] = _baseline_version_dict(version_row)
    return d


def create_baseline(
    project_id: int,
    agent_name: str,
    name: str,
    description: Optional[str],
    source_type: str,
    source_id: str,
    status: str,
    duration_ms: Optional[float],
    input_val: Any,
    output_val: Any,
    tools: List[dict],
    expected: dict,
    user_id: Optional[int] = None,
) -> dict:
    """Create a new regression baseline with version 1."""
    now = _now()
    clean_name = name.strip() or f"{agent_name} Baseline"

    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO baselines (project_id, agent_name, name, description, current_version, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (project_id, agent_name, clean_name, description, now, now),
        )
        baseline_id = cur.lastrowid

        conn.execute(
            """INSERT INTO baseline_versions
               (baseline_id, version, source_type, source_id, status, duration_ms,
                input_json, output_json, tools_json, expected_json, created_at, created_by_user_id)
               VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                baseline_id, source_type, source_id, status, duration_ms,
                _dump(input_val), _dump(output_val), _dump(tools), _dump(expected), now, user_id,
            ),
        )

        b_row = conn.execute("SELECT * FROM baselines WHERE id = ?", (baseline_id,)).fetchone()
        v_row = conn.execute("SELECT * FROM baseline_versions WHERE baseline_id = ? AND version = 1", (baseline_id,)).fetchone()
        return _baseline_dict(b_row, v_row)


def create_baseline_version(
    baseline_id: int,
    project_id: int,
    source_type: str,
    source_id: str,
    status: str,
    duration_ms: Optional[float],
    input_val: Any,
    output_val: Any,
    tools: List[dict],
    expected: dict,
    user_id: Optional[int] = None,
    description: Optional[str] = None,
) -> Optional[dict]:
    """Non-destructively add a new version to an existing baseline."""
    now = _now()
    with connect() as conn:
        b_row = conn.execute("SELECT * FROM baselines WHERE id = ? AND project_id = ?", (baseline_id, project_id)).fetchone()
        if not b_row:
            return None

        current_ver = b_row["current_version"]
        next_ver = current_ver + 1

        conn.execute(
            """INSERT INTO baseline_versions
               (baseline_id, version, source_type, source_id, status, duration_ms,
                input_json, output_json, tools_json, expected_json, created_at, created_by_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                baseline_id, next_ver, source_type, source_id, status, duration_ms,
                _dump(input_val), _dump(output_val), _dump(tools), _dump(expected), now, user_id,
            ),
        )

        desc_to_set = description if description is not None else b_row["description"]
        conn.execute(
            """UPDATE baselines SET current_version = ?, description = ?, updated_at = ?
               WHERE id = ? AND project_id = ?""",
            (next_ver, desc_to_set, now, baseline_id, project_id),
        )

        updated_b = conn.execute("SELECT * FROM baselines WHERE id = ?", (baseline_id,)).fetchone()
        v_row = conn.execute("SELECT * FROM baseline_versions WHERE baseline_id = ? AND version = ?", (baseline_id, next_ver)).fetchone()
        return _baseline_dict(updated_b, v_row)


def get_baseline(baseline_id: int, project_id: Optional[int] = None) -> Optional[dict]:
    """Retrieve baseline and its latest version."""
    with connect() as conn:
        sql = "SELECT * FROM baselines WHERE id = ?"
        args = [baseline_id]
        if project_id is not None:
            sql += " AND project_id = ?"
            args.append(project_id)
        b_row = conn.execute(sql, args).fetchone()
        if not b_row:
            return None

        v_row = conn.execute(
            "SELECT * FROM baseline_versions WHERE baseline_id = ? AND version = ?",
            (baseline_id, b_row["current_version"]),
        ).fetchone()
        return _baseline_dict(b_row, v_row)


def list_baselines(project_id: int, agent_name: Optional[str] = None) -> List[dict]:
    """List all baselines for the project."""
    with connect() as conn:
        sql = "SELECT * FROM baselines WHERE project_id = ?"
        args: list[Any] = [project_id]
        if agent_name:
            sql += " AND agent_name = ?"
            args.append(agent_name)
        sql += " ORDER BY id DESC"

        rows = conn.execute(sql, args).fetchall()
        result = []
        for r in rows:
            v_row = conn.execute(
                "SELECT * FROM baseline_versions WHERE baseline_id = ? AND version = ?",
                (r["id"], r["current_version"]),
            ).fetchone()
            result.append(_baseline_dict(r, v_row))
        return result


def list_baseline_versions(baseline_id: int, project_id: Optional[int] = None) -> List[dict]:
    """List all historical versions of a baseline."""
    with connect() as conn:
        if project_id is not None:
            b_row = conn.execute("SELECT id FROM baselines WHERE id = ? AND project_id = ?", (baseline_id, project_id)).fetchone()
            if not b_row:
                return []
        rows = conn.execute(
            "SELECT * FROM baseline_versions WHERE baseline_id = ? ORDER BY version DESC",
            (baseline_id,),
        ).fetchall()
        return [_baseline_version_dict(r) for r in rows]


def get_baseline_version(baseline_id: int, version: int, project_id: Optional[int] = None) -> Optional[dict]:
    """Retrieve a specific historical version of a baseline."""
    with connect() as conn:
        if project_id is not None:
            b_row = conn.execute("SELECT id FROM baselines WHERE id = ? AND project_id = ?", (baseline_id, project_id)).fetchone()
            if not b_row:
                return None
        row = conn.execute(
            "SELECT * FROM baseline_versions WHERE baseline_id = ? AND version = ?",
            (baseline_id, version),
        ).fetchone()
        return _baseline_version_dict(row) if row else None


def delete_baseline(baseline_id: int, project_id: int) -> bool:
    """Delete a baseline and all its versions."""
    with connect() as conn:
        cur = conn.execute("DELETE FROM baselines WHERE id = ? AND project_id = ?", (baseline_id, project_id))
        return cur.rowcount > 0

