"""SQLite storage using Python's built-in sqlite3 with migrations and foreign key support."""
import json
import os
import sqlite3
from datetime import datetime, timezone

from .migrations import run_migrations

DEFAULT_DB = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "agentreliability.db"))


def db_path() -> str:
    """Resolve database path from environment, local config, or installation default."""
    # 1. Tests or dev runner set AGENTRELIABILITY_DB explicitly
    env_db = os.environ.get("AGENTRELIABILITY_DB")
    if env_db and env_db.strip():
        return os.path.abspath(env_db.strip())

    # 2. Check local .agentreliability.json in workspace root or current directory
    try:
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workspace_dir = os.path.dirname(backend_dir)
        for candidate in [workspace_dir, backend_dir, os.getcwd()]:
            cfg_file = os.path.join(candidate, ".agentreliability.json")
            if os.path.isfile(cfg_file):
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and data.get("database_path"):
                        return os.path.abspath(data["database_path"])
    except Exception:
        pass

    # 3. Fallback to default path relative to this backend package
    return DEFAULT_DB


def connect() -> sqlite3.Connection:
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    return conn


def init_db() -> None:
    with connect() as conn:
        run_migrations(conn)


def save_execution(log: dict, analysis: dict, project_id: int = 1) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO executions
               (agent_name, run_id, status, step_count, failure_count, steps_json, findings_json, created_at, project_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                log["agent_name"],
                log.get("run_id"),
                analysis["status"],
                len(log["steps"]),
                len(analysis["findings"]),
                json.dumps(log["steps"]),
                json.dumps(analysis["findings"]),
                datetime.now(timezone.utc).isoformat(),
                project_id,
            ),
        )
        return cur.lastrowid


def _summary(row: sqlite3.Row) -> dict:
    d = {k: row[k] for k in ("id", "agent_name", "run_id", "status", "step_count", "failure_count", "created_at")}
    if "project_id" in row.keys():
        d["project_id"] = row["project_id"]
    return d


def list_executions(project_id: int | None = None) -> list[dict]:
    with connect() as conn:
        if project_id is not None:
            rows = conn.execute("SELECT * FROM executions WHERE project_id = ? ORDER BY id DESC", (project_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM executions ORDER BY id DESC").fetchall()
    return [_summary(r) for r in rows]


def get_execution(exec_id: int, project_id: int | None = None) -> dict | None:
    with connect() as conn:
        if project_id is not None:
            row = conn.execute("SELECT * FROM executions WHERE id = ? AND project_id = ?", (exec_id, project_id)).fetchone()
        else:
            row = conn.execute("SELECT * FROM executions WHERE id = ?", (exec_id,)).fetchone()
    if row is None:
        return None
    data = _summary(row)
    data["steps"] = json.loads(row["steps_json"])
    data["findings"] = json.loads(row["findings_json"])
    return data


def count_executions(project_id: int | None = None) -> int:
    with connect() as conn:
        if project_id is not None:
            return conn.execute("SELECT COUNT(*) FROM executions WHERE project_id = ?", (project_id,)).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
