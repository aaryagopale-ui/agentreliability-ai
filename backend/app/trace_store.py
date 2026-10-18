"""SQLite storage for SDK traces, projects and API keys.

Key facts for beginners:
  * API keys are long random strings. We store only their SHA-256 hash, so a stolen
    database file does not reveal usable keys. (A fast hash is fine here because the key is
    256 bits of randomness; slow hashes like bcrypt are for human-chosen passwords.)
  * All timestamps are stored as UTC text in ONE fixed format, so sorting/filtering as text works.
  * trace_events has UNIQUE(project_id, event_id): inserting the same event twice is ignored.
"""
import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from .database import connect

KEY_PREFIX = "ar_"


def utc_iso(dt: datetime) -> str:
    """Normalize any datetime to 'YYYY-MM-DDTHH:MM:SS.ffffffZ' in UTC (naive = UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def now_iso() -> str:
    return utc_iso(datetime.now(timezone.utc))


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def init_tables() -> None:
    with connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                key_prefix TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS trace_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                type TEXT NOT NULL,
                received_at TEXT NOT NULL,
                UNIQUE (project_id, event_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS trace_executions (
                project_id INTEGER NOT NULL,
                execution_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                status TEXT NOT NULL,
                failure_kind TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_ms REAL,
                input_json TEXT,
                output_json TEXT,
                error_type TEXT,
                error_message TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, execution_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS trace_tool_calls (
                project_id INTEGER NOT NULL,
                call_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                duration_ms REAL,
                status TEXT NOT NULL,
                input_json TEXT,
                output_json TEXT,
                error_type TEXT,
                error_message TEXT,
                PRIMARY KEY (project_id, call_id)
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_exec_started ON trace_executions (started_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_exec_agent ON trace_executions (agent_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_tool_exec ON trace_tool_calls (execution_id)")


# ---------------------------------------------------------------- projects / keys

def create_project(name: str) -> tuple[int, str]:
    """Create a project and return (project_id, plaintext_key). The key is NOT stored."""
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, key_hash, key_prefix, created_at) VALUES (?,?,?,?)",
            (name, hash_key(key), key[:8], now_iso()),
        )
        return cur.lastrowid, key


def find_project_by_key(key: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute("SELECT id, name FROM projects WHERE key_hash = ?", (hash_key(key),)).fetchone()
    return {"id": row["id"], "name": row["name"]} if row else None


# ---------------------------------------------------------------- ingestion

def _dump(value) -> Optional[str]:
    return None if value is None else json.dumps(value)


def _load(text):
    return None if text is None else json.loads(text)


def _ensure_execution(conn, pid, ev, now) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO trace_executions
           (project_id, execution_id, agent_name, status, started_at, metadata_json, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (pid, ev.execution_id, ev.agent_name, "running", utc_iso(ev.timestamp), "{}", now, now),
    )


def _is_timeout(error_type: Optional[str]) -> bool:
    return bool(error_type) and "timeout" in error_type.lower()


def _recompute_failure_kind(conn, pid, execution_id) -> None:
    """failure_kind: timeout | tool_failure | unexpected_exception (NULL unless the run failed)."""
    row = conn.execute(
        "SELECT status, error_type FROM trace_executions WHERE project_id=? AND execution_id=?",
        (pid, execution_id),
    ).fetchone()
    kind = None
    if row["status"] == "failed":
        tools = conn.execute(
            "SELECT status FROM trace_tool_calls WHERE project_id=? AND execution_id=?", (pid, execution_id)
        ).fetchall()
        statuses = {t["status"] for t in tools}
        if _is_timeout(row["error_type"]) or "timeout" in statuses:
            kind = "timeout"
        elif "error" in statuses:
            kind = "tool_failure"
        else:
            kind = "unexpected_exception"
    conn.execute(
        "UPDATE trace_executions SET failure_kind=? WHERE project_id=? AND execution_id=?",
        (kind, pid, execution_id),
    )


def _apply(conn, pid, ev, now) -> None:
    _ensure_execution(conn, pid, ev, now)
    if ev.type == "execution_start":
        conn.execute(
            """UPDATE trace_executions SET agent_name=?, started_at=?, input_json=?, metadata_json=?, updated_at=?
               WHERE project_id=? AND execution_id=?""",
            (ev.agent_name, utc_iso(ev.timestamp), _dump(ev.input), json.dumps(ev.metadata), now, pid, ev.execution_id),
        )
    elif ev.type == "tool_call":
        conn.execute(
            """INSERT INTO trace_tool_calls (project_id, call_id, execution_id, tool_name, started_at, duration_ms,
               status, input_json, output_json, error_type, error_message) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, ev.event_id, ev.execution_id, ev.tool_name, utc_iso(ev.timestamp), ev.duration_ms, ev.status,
             _dump(ev.input), _dump(ev.output), ev.error_type, ev.error_message),
        )
    else:  # execution_end
        conn.execute(
            """UPDATE trace_executions SET status=?, ended_at=?, duration_ms=?, output_json=?, error_type=?,
               error_message=?, updated_at=? WHERE project_id=? AND execution_id=?""",
            (ev.status, utc_iso(ev.timestamp), ev.duration_ms, _dump(ev.output), ev.error_type,
             ev.error_message, now, pid, ev.execution_id),
        )
    _recompute_failure_kind(conn, pid, ev.execution_id)


def ingest(project_id: int, events: list) -> tuple[int, int]:
    """Store events in ONE transaction. Returns (accepted, duplicates)."""
    accepted = duplicates = 0
    now = now_iso()
    with connect() as conn:
        for ev in events:
            cur = conn.execute(
                "INSERT OR IGNORE INTO trace_events (project_id, event_id, execution_id, type, received_at) VALUES (?,?,?,?,?)",
                (project_id, ev.event_id, ev.execution_id, ev.type, now),
            )
            if cur.rowcount == 0:
                duplicates += 1
                continue
            _apply(conn, project_id, ev, now)
            accepted += 1
    return accepted, duplicates


# ---------------------------------------------------------------- reads

def _tool(row) -> dict:
    return {
        "call_id": row["call_id"], "execution_id": row["execution_id"], "tool_name": row["tool_name"],
        "started_at": row["started_at"], "duration_ms": row["duration_ms"], "status": row["status"],
        "input": _load(row["input_json"]), "output": _load(row["output_json"]),
        "error_type": row["error_type"], "error_message": row["error_message"],
    }


def _execution(row, tool_counts) -> dict:
    total, failed = tool_counts.get(row["execution_id"], (0, 0))
    return {
        "execution_id": row["execution_id"], "agent_name": row["agent_name"], "status": row["status"],
        "failure_kind": row["failure_kind"], "started_at": row["started_at"], "ended_at": row["ended_at"],
        "duration_ms": row["duration_ms"], "tool_call_count": total, "failed_tool_calls": failed,
        "error_type": row["error_type"], "error_message": row["error_message"],
        "metadata": json.loads(row["metadata_json"]),
        "source": "recorded_real_execution",
    }


def _tool_counts(conn, ids) -> dict:
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT execution_id, COUNT(*) AS total, SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS failed
            FROM trace_tool_calls WHERE execution_id IN ({marks}) GROUP BY execution_id""", ids
    ).fetchall()
    return {r["execution_id"]: (r["total"], r["failed"] or 0) for r in rows}


def list_executions(agent=None, status=None, failure_kind=None, since=None, until=None,
                    limit=50, offset=0) -> dict:
    where, args = [], []
    for column, value in (("agent_name", agent), ("status", status), ("failure_kind", failure_kind)):
        if value:
            where.append(f"{column} = ?")
            args.append(value)
    if since:
        where.append("started_at >= ?")
        args.append(utc_iso(since))
    if until:
        where.append("started_at <= ?")
        args.append(utc_iso(until))
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM trace_executions{clause}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM trace_executions{clause} ORDER BY started_at DESC, execution_id LIMIT ? OFFSET ?",
            args + [limit, offset],
        ).fetchall()
        counts = _tool_counts(conn, [r["execution_id"] for r in rows])
    return {"total": total, "items": [_execution(r, counts) for r in rows]}


def get_execution(execution_id: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM trace_executions WHERE execution_id=? ORDER BY created_at DESC LIMIT 1", (execution_id,)
        ).fetchone()
        if row is None:
            return None
        tools = conn.execute(
            "SELECT * FROM trace_tool_calls WHERE project_id=? AND execution_id=? ORDER BY started_at, call_id",
            (row["project_id"], execution_id),
        ).fetchall()
    data = _execution(row, {execution_id: (len(tools), sum(1 for t in tools if t["status"] != "success"))})
    data["input"] = _load(row["input_json"])
    data["output"] = _load(row["output_json"])
    data["tool_calls"] = [_tool(t) for t in tools]
    return data


def list_tool_calls(execution_id=None, status=None, tool_name=None, agent=None, since=None, limit=100) -> list:
    where, args = [], []
    join = ""
    if agent:
        join = " JOIN trace_executions e ON e.project_id = t.project_id AND e.execution_id = t.execution_id"
        where.append("e.agent_name = ?")
        args.append(agent)
    for column, value in (("t.execution_id", execution_id), ("t.status", status), ("t.tool_name", tool_name)):
        if value:
            where.append(f"{column} = ?")
            args.append(value)
    if since:
        where.append("t.started_at >= ?")
        args.append(utc_iso(since))
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT t.* FROM trace_tool_calls t{join}{clause} ORDER BY t.started_at DESC LIMIT ?", args + [limit]
        ).fetchall()
    return [_tool(r) for r in rows]


def list_agents() -> list:
    with connect() as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT agent_name FROM trace_executions ORDER BY agent_name")]

