"""SQLite storage for test cases and test runs (reuses database.connect)."""
import json
from datetime import datetime, timezone

from .database import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_tables() -> None:
    with connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS test_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                agent_name TEXT NOT NULL,
                source_execution_id INTEGER,
                input_json TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                expected_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        # test_name is a snapshot so history stays readable after a test is deleted.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_case_id INTEGER NOT NULL,
                test_name TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                mismatches_json TEXT NOT NULL,
                observed_json TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        # Phase 3 migration: remember where a test came from. Safe to run on old databases.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(test_cases)")}
        if "source_type" not in cols:
            conn.execute("ALTER TABLE test_cases ADD COLUMN source_type TEXT NOT NULL DEFAULT 'uploaded_log'")
        if "source_trace_id" not in cols:
            conn.execute("ALTER TABLE test_cases ADD COLUMN source_trace_id TEXT")


def _case(row, with_body=True) -> dict:
    d = {k: row[k] for k in ("id", "name", "description", "agent_name", "source_execution_id", "created_at", "updated_at")}
    d["last_run_status"] = row["last_run_status"] if "last_run_status" in row.keys() else None
    d["last_run_at"] = row["last_run_at"] if "last_run_at" in row.keys() else None
    d["source_type"] = row["source_type"]  # uploaded_log | recorded_real_execution
    d["source_trace_id"] = row["source_trace_id"]
    if with_body:
        d["input"] = json.loads(row["input_json"])
        d["steps"] = json.loads(row["steps_json"])
        d["expected"] = json.loads(row["expected_json"])
    else:
        d["step_count"] = len(json.loads(row["steps_json"]))
    return d


_LAST_RUN = """(SELECT status FROM test_runs r WHERE r.test_case_id = t.id ORDER BY r.id DESC LIMIT 1) AS last_run_status,
               (SELECT created_at FROM test_runs r WHERE r.test_case_id = t.id ORDER BY r.id DESC LIMIT 1) AS last_run_at"""


def create_case(data: dict, source_execution_id: int | None = None,
                source_type: str = "uploaded_log", source_trace_id: str | None = None) -> int:
    now = _now()
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO test_cases (name, description, agent_name, source_execution_id,
               input_json, steps_json, expected_json, created_at, updated_at, source_type, source_trace_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (data["name"], data.get("description"), data["agent_name"], source_execution_id,
             json.dumps(data.get("input")), json.dumps(data["steps"]), json.dumps(data["expected"]), now, now,
             source_type, source_trace_id),
        )
        return cur.lastrowid


def update_case(case_id: int, data: dict) -> bool:
    with connect() as conn:
        cur = conn.execute(
            """UPDATE test_cases SET name=?, description=?, agent_name=?, input_json=?, steps_json=?,
               expected_json=?, updated_at=? WHERE id=?""",
            (data["name"], data.get("description"), data["agent_name"], json.dumps(data.get("input")),
             json.dumps(data["steps"]), json.dumps(data["expected"]), _now(), case_id),
        )
        return cur.rowcount > 0


def delete_case(case_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM test_cases WHERE id=?", (case_id,)).rowcount > 0


def get_case(case_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(f"SELECT t.*, {_LAST_RUN} FROM test_cases t WHERE t.id=?", (case_id,)).fetchone()
    return _case(row) if row else None


def list_cases() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(f"SELECT t.*, {_LAST_RUN} FROM test_cases t ORDER BY t.id DESC").fetchall()
    return [_case(r, with_body=False) for r in rows]


def save_run(case: dict, result: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO test_runs (test_case_id, test_name, status, mode, mismatches_json,
               observed_json, duration_ms, created_at) VALUES (?,?,?,?,?,?,?,?)""",
            (case["id"], case["name"], result["status"], result["mode"], json.dumps(result["mismatches"]),
             json.dumps(result["observed"]), result["duration_ms"], _now()),
        )
        return cur.lastrowid


def _run(row, with_body=True) -> dict:
    d = {k: row[k] for k in ("id", "test_case_id", "test_name", "status", "mode", "duration_ms", "created_at")}
    mismatches = json.loads(row["mismatches_json"])
    d["mismatch_count"] = len(mismatches)
    if with_body:
        from .replay import DISCLAIMER
        d["mismatches"] = mismatches
        d["observed"] = json.loads(row["observed_json"])
        d["disclaimer"] = DISCLAIMER
    return d


def get_run(run_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM test_runs WHERE id=?", (run_id,)).fetchone()
    return _run(row) if row else None


def list_runs(test_id: int | None = None, limit: int = 200) -> list[dict]:
    sql, args = "SELECT * FROM test_runs", []
    if test_id is not None:
        sql += " WHERE test_case_id=?"
        args.append(test_id)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_run(r, with_body=False) for r in rows]


def latest_runs_per_test() -> list[dict]:
    """The most recent run of every test that still exists (full detail)."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.* FROM test_runs r
               WHERE r.id = (SELECT MAX(id) FROM test_runs WHERE test_case_id = r.test_case_id)
                 AND r.test_case_id IN (SELECT id FROM test_cases)
               ORDER BY r.id DESC"""
        ).fetchall()
    return [_run(r) for r in rows]


def execution_finding_counts() -> dict:
    counts: dict[str, int] = {}
    with connect() as conn:
        for row in conn.execute("SELECT findings_json FROM executions"):
            for f in json.loads(row["findings_json"]):
                counts[f["category"]] = counts.get(f["category"], 0) + 1
    return counts

