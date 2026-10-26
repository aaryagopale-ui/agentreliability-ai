"""SQLite storage for test cases and test runs (reuses database.connect)."""
import json
from datetime import datetime, timezone
from typing import Optional

from .database import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_tables() -> None:
    # Tables and columns are managed via versioned database migrations (app.migrations)
    pass


def _case(row, with_body=True) -> dict:
    d = {k: row[k] for k in ("id", "name", "description", "agent_name", "source_execution_id", "created_at", "updated_at")}
    d["last_run_status"] = row["last_run_status"] if "last_run_status" in row.keys() else None
    d["last_run_at"] = row["last_run_at"] if "last_run_at" in row.keys() else None
    d["source_type"] = row["source_type"] if "source_type" in row.keys() else "uploaded_log"
    d["source_trace_id"] = row["source_trace_id"] if "source_trace_id" in row.keys() else None
    d["project_id"] = row["project_id"] if "project_id" in row.keys() else 1
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
                source_type: str = "uploaded_log", source_trace_id: str | None = None,
                project_id: int = 1) -> int:
    now = _now()
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO test_cases (name, description, agent_name, source_execution_id,
               input_json, steps_json, expected_json, created_at, updated_at, source_type, source_trace_id, project_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data["name"], data.get("description"), data["agent_name"], source_execution_id,
             json.dumps(data.get("input")), json.dumps(data["steps"]), json.dumps(data["expected"]), now, now,
             source_type, source_trace_id, project_id),
        )
        return cur.lastrowid


def update_case(case_id: int, data: dict, project_id: int | None = None) -> bool:
    with connect() as conn:
        if project_id is not None:
            cur = conn.execute(
                """UPDATE test_cases SET name=?, description=?, agent_name=?, input_json=?, steps_json=?,
                   expected_json=?, updated_at=? WHERE id=? AND project_id=?""",
                (data["name"], data.get("description"), data["agent_name"], json.dumps(data.get("input")),
                 json.dumps(data["steps"]), json.dumps(data["expected"]), _now(), case_id, project_id),
            )
        else:
            cur = conn.execute(
                """UPDATE test_cases SET name=?, description=?, agent_name=?, input_json=?, steps_json=?,
                   expected_json=?, updated_at=? WHERE id=?""",
                (data["name"], data.get("description"), data["agent_name"], json.dumps(data.get("input")),
                 json.dumps(data["steps"]), json.dumps(data["expected"]), _now(), case_id),
            )
        return cur.rowcount > 0


def delete_case(case_id: int, project_id: int | None = None) -> bool:
    with connect() as conn:
        if project_id is not None:
            return conn.execute("DELETE FROM test_cases WHERE id=? AND project_id=?", (case_id, project_id)).rowcount > 0
        return conn.execute("DELETE FROM test_cases WHERE id=?", (case_id,)).rowcount > 0


def get_case(case_id: int, project_id: int | None = None) -> dict | None:
    with connect() as conn:
        if project_id is not None:
            row = conn.execute(f"SELECT t.*, {_LAST_RUN} FROM test_cases t WHERE t.id=? AND t.project_id=?", (case_id, project_id)).fetchone()
        else:
            row = conn.execute(f"SELECT t.*, {_LAST_RUN} FROM test_cases t WHERE t.id=?", (case_id,)).fetchone()
    return _case(row) if row else None


def list_cases(project_id: int | None = None) -> list[dict]:
    with connect() as conn:
        if project_id is not None:
            rows = conn.execute(f"SELECT t.*, {_LAST_RUN} FROM test_cases t WHERE t.project_id=? ORDER BY t.id DESC", (project_id,)).fetchall()
        else:
            rows = conn.execute(f"SELECT t.*, {_LAST_RUN} FROM test_cases t ORDER BY t.id DESC").fetchall()
    return [_case(r, with_body=False) for r in rows]


def save_run(case: dict, result: dict, project_id: int = 1) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO test_runs (test_case_id, test_name, status, mode, mismatches_json,
               observed_json, duration_ms, created_at, project_id) VALUES (?,?,?,?,?,?,?,?,?)""",
            (case["id"], case["name"], result["status"], result["mode"], json.dumps(result["mismatches"]),
             json.dumps(result["observed"]), result["duration_ms"], _now(), project_id),
        )
        return cur.lastrowid


def _run(row, with_body=True) -> dict:
    d = {k: row[k] for k in ("id", "test_case_id", "test_name", "status", "mode", "duration_ms", "created_at")}
    if "project_id" in row.keys():
        d["project_id"] = row["project_id"]
    mismatches = json.loads(row["mismatches_json"])
    d["mismatch_count"] = len(mismatches)
    if with_body:
        from .replay import DISCLAIMER
        d["mismatches"] = mismatches
        d["observed"] = json.loads(row["observed_json"])
        d["disclaimer"] = DISCLAIMER
    return d


def get_run(run_id: int, project_id: int | None = None) -> dict | None:
    with connect() as conn:
        if project_id is not None:
            row = conn.execute("SELECT * FROM test_runs WHERE id=? AND project_id=?", (run_id, project_id)).fetchone()
        else:
            row = conn.execute("SELECT * FROM test_runs WHERE id=?", (run_id,)).fetchone()
    return _run(row) if row else None


def list_runs(test_id: int | None = None, project_id: int | None = None, limit: int = 200) -> list[dict]:
    sql, args = "SELECT * FROM test_runs", []
    clauses = []
    if test_id is not None:
        clauses.append("test_case_id=?")
        args.append(test_id)
    if project_id is not None:
        clauses.append("project_id=?")
        args.append(project_id)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_run(r, with_body=False) for r in rows]


def latest_runs_per_test(project_id: int | None = None) -> list[dict]:
    """The most recent run of every test that still exists (full detail)."""
    with connect() as conn:
        if project_id is not None:
            rows = conn.execute(
                """SELECT r.* FROM test_runs r
                   WHERE r.id = (SELECT MAX(id) FROM test_runs WHERE test_case_id = r.test_case_id AND project_id = ?)
                     AND r.test_case_id IN (SELECT id FROM test_cases WHERE project_id = ?)
                   ORDER BY r.id DESC""",
                (project_id, project_id)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT r.* FROM test_runs r
                   WHERE r.id = (SELECT MAX(id) FROM test_runs WHERE test_case_id = r.test_case_id)
                     AND r.test_case_id IN (SELECT id FROM test_cases)
                   ORDER BY r.id DESC"""
            ).fetchall()
    return [_run(r) for r in rows]


def execution_finding_counts(project_id: int | None = None) -> dict:
    counts: dict[str, int] = {}
    with connect() as conn:
        if project_id is not None:
            rows = conn.execute("SELECT findings_json FROM executions WHERE project_id = ?", (project_id,))
        else:
            rows = conn.execute("SELECT findings_json FROM executions")
        for row in rows:
            for f in json.loads(row["findings_json"]):
                counts[f["category"]] = counts.get(f["category"], 0) + 1
    return counts
