"""SQLite storage for CI/CD test runs.

Stores results uploaded from GitHub Actions or local CLI runs.
"""
import json
from datetime import datetime, timezone
from typing import List, Optional

from .database import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_tables() -> None:
    with connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ci_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                commit_sha TEXT NOT NULL,
                branch TEXT NOT NULL,
                actor TEXT NOT NULL,
                status TEXT NOT NULL,
                total INTEGER NOT NULL,
                passed INTEGER NOT NULL,
                failed INTEGER NOT NULL,
                duration_ms REAL NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ci_created ON ci_runs (created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ci_commit ON ci_runs (commit_sha)")


def save_ci_run(project_id: int, data: dict) -> int:
    report = data.get("report", {})
    failed = data.get("failed", 0)
    status = "passed" if failed == 0 else "failed"

    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO ci_runs 
               (project_id, commit_sha, branch, actor, status, total, passed, failed, duration_ms, report_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                data.get("commit_sha", "unknown")[:64],
                data.get("branch", "main")[:128],
                data.get("actor", "user")[:128],
                status,
                data.get("total", 0),
                data.get("passed", 0),
                failed,
                data.get("duration_ms", 0.0),
                json.dumps(report),
                _now()
            )
        )
        return cur.lastrowid


def list_ci_runs(limit: int = 50, offset: int = 0) -> List[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, project_id, commit_sha, branch, actor, status, total, passed, failed, duration_ms, created_at
               FROM ci_runs ORDER BY id DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        ).fetchall()

    return [dict(r) for r in rows]


def get_ci_run(run_id: int) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM ci_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["report"] = json.loads(row["report_json"])
    return d

