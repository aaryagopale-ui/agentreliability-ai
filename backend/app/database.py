"""SQLite storage using Python's built-in sqlite3 (no ORM, easy to read)."""
import json
import os
import sqlite3
from datetime import datetime, timezone

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agentreliability.db")


def db_path() -> str:
    # Tests set AGENTRELIABILITY_DB to use a temporary database.
    return os.environ.get("AGENTRELIABILITY_DB", DEFAULT_DB)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                run_id TEXT,
                status TEXT NOT NULL,
                step_count INTEGER NOT NULL,
                failure_count INTEGER NOT NULL,
                steps_json TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )


def save_execution(log: dict, analysis: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO executions
               (agent_name, run_id, status, step_count, failure_count, steps_json, findings_json, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                log["agent_name"],
                log.get("run_id"),
                analysis["status"],
                len(log["steps"]),
                len(analysis["findings"]),
                json.dumps(log["steps"]),
                json.dumps(analysis["findings"]),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def _summary(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in ("id", "agent_name", "run_id", "status", "step_count", "failure_count", "created_at")}


def list_executions() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM executions ORDER BY id DESC").fetchall()
    return [_summary(r) for r in rows]


def get_execution(exec_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM executions WHERE id = ?", (exec_id,)).fetchone()
    if row is None:
        return None
    data = _summary(row)
    data["steps"] = json.loads(row["steps_json"])
    data["findings"] = json.loads(row["findings_json"])
    return data


def count_executions() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]

