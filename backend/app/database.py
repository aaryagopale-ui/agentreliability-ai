"""Unified database storage module supporting SQLite (local) and PostgreSQL (Neon/production).

Guarantees:
1. Seamless local development with SQLite (`AGENTRELIABILITY_DB` or local default).
2. Production reliability with PostgreSQL via `DATABASE_URL`.
3. Never silently falls back to ephemeral SQLite in production mode.
4. Parameterized query translation, RETURNING id emulation, and row mapping parity.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from .migrations.runner import run_migrations
from .migrations.postgres_runner import run_postgres_migrations

logger = logging.getLogger("agentreliability.database")

DEFAULT_DB = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "agentreliability.db"))

TABLES_WITH_ID = {
    "users", "projects", "api_keys", "sessions", "password_resets",
    "executions", "test_cases", "test_runs", "trace_events", "ci_runs",
    "baselines", "baseline_versions",
}


def get_database_url() -> Optional[str]:
    """Retrieve raw DATABASE_URL from environment if set and non-empty."""
    url = os.environ.get("DATABASE_URL")
    if url and url.strip():
        return url.strip()
    return None


def is_postgres() -> bool:
    """Return True if configured to use PostgreSQL."""
    return get_database_url() is not None or os.environ.get("AGENTRELIABILITY_ENGINE") == "postgres"


def get_database_engine() -> str:
    """Return active engine name: 'postgres' or 'sqlite'."""
    return "postgres" if is_postgres() else "sqlite"


def db_path() -> str:
    """Resolve SQLite database path from environment, local config, or installation default."""
    env_db = os.environ.get("AGENTRELIABILITY_DB")
    if env_db and env_db.strip():
        return os.path.abspath(env_db.strip())

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

    return DEFAULT_DB


# -----------------------------------------------------------------------------
# Unified Row & Query Translation
# -----------------------------------------------------------------------------

class UnifiedRow(dict):
    """Row wrapper that supports both key-based access ('name') and index-based access (0),
    as well as .keys() and dict() conversions."""
    def __init__(self, mapping: dict, seq: tuple | None = None):
        super().__init__(mapping)
        self._seq = tuple(seq) if seq is not None else tuple(mapping.values())

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, int):
            return self._seq[item]
        return super().__getitem__(item)


def translate_query_for_postgres(sql: str) -> Tuple[str, bool]:
    """Translates SQLite-compatible SQL into standard PostgreSQL SQL.
    Returns (translated_sql, expects_returning_id).
    """
    s = sql.strip()

    # 1. INSERT OR IGNORE INTO <table> ... -> INSERT INTO <table> ... ON CONFLICT DO NOTHING
    if re.match(r"(?i)^INSERT\s+OR\s+IGNORE\s+INTO\s+", s):
        s = re.sub(r"(?i)^INSERT\s+OR\s+IGNORE\s+INTO\s+", "INSERT INTO ", s)
        if "ON CONFLICT" not in s.upper():
            s = s + " ON CONFLICT DO NOTHING"

    # 2. COLLATE NOCASE -> remove (Postgres matches email case-sensitively or through Lower)
    s = re.sub(r"(?i)\s+COLLATE\s+NOCASE", "", s)

    # 3. Replace ? placeholders with %s (ignoring inside string literals)
    parts = re.split(r"('[^']*'|\"[^\"]*\")", s)
    for i in range(len(parts)):
        if not (parts[i].startswith("'") or parts[i].startswith('"')):
            parts[i] = parts[i].replace("?", "%s")
    s = "".join(parts)

    # 4. If INSERT INTO on a table with an autoincrement ID and no RETURNING clause, append RETURNING id
    expects_returning = False
    m = re.match(r"(?i)^INSERT\s+INTO\s+([a-zA-Z0-9_]+)", s)
    if m:
        table_name = m.group(1).lower()
        if table_name in TABLES_WITH_ID and "RETURNING" not in s.upper() and "DO NOTHING" not in s.upper():
            s = s + " RETURNING id"
            expects_returning = True

    return s, expects_returning


class PostgresCursorWrapper:
    """Cursor wrapper providing sqlite3.Cursor parity over psycopg."""
    def __init__(self, raw_cur: Any):
        self._cur = raw_cur
        self.lastrowid: Optional[int] = None
        self._cached_returning_row: Any = None

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    @property
    def description(self) -> Any:
        return self._cur.description

    def execute(self, sql: str, params: tuple | list | None = None) -> PostgresCursorWrapper:
        self._cached_returning_row = None
        translated_sql, expects_returning = translate_query_for_postgres(sql)
        if params is not None:
            self._cur.execute(translated_sql, params)
        else:
            self._cur.execute(translated_sql)

        if expects_returning:
            row = self._cur.fetchone()
            if row is not None:
                if isinstance(row, dict):
                    self.lastrowid = row.get("id") if "id" in row else (next(iter(row.values())) if row else None)
                else:
                    try:
                        self.lastrowid = row[0]
                    except (KeyError, TypeError, IndexError):
                        self.lastrowid = row.get("id") if hasattr(row, "get") else None
                self._cached_returning_row = row
        return self

    def executemany(self, sql: str, seq_of_params: list | tuple) -> PostgresCursorWrapper:
        self._cached_returning_row = None
        translated_sql, _ = translate_query_for_postgres(sql)
        self._cur.executemany(translated_sql, seq_of_params)
        return self

    def fetchone(self) -> Optional[UnifiedRow]:
        if self._cached_returning_row is not None:
            row = self._cached_returning_row
            self._cached_returning_row = None
            return self._wrap_row(row)
        row = self._cur.fetchone()
        return self._wrap_row(row) if row is not None else None

    def fetchall(self) -> List[UnifiedRow]:
        rows = self._cur.fetchall()
        return [self._wrap_row(r) for r in rows]

    def _wrap_row(self, row: Any) -> Optional[UnifiedRow]:
        if row is None:
            return None
        if isinstance(row, dict):
            clean_dict = {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in row.items()
            }
            return UnifiedRow(clean_dict, tuple(clean_dict.values()))
        if self._cur.description:
            col_names = [col.name for col in self._cur.description]
            clean_vals = [
                v.isoformat() if hasattr(v, "isoformat") else v
                for v in row
            ]
            mapping = dict(zip(col_names, clean_vals))
            return UnifiedRow(mapping, tuple(clean_vals))
        return row

    def __iter__(self):
        for row in self._cur:
            yield self._wrap_row(row)

    def close(self) -> None:
        self._cur.close()


class PostgresTransactionWrapper:
    """Transaction context manager providing psycopg 3 .transaction() parity."""
    def __init__(self, conn: PostgresConnectionWrapper):
        self._conn = conn

    def __enter__(self) -> PostgresTransactionWrapper:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self._conn.rollback()
        else:
            self._conn.commit()


class PostgresConnectionWrapper:
    """Connection wrapper providing sqlite3.Connection parity over psycopg."""
    def __init__(self, raw_conn: Any):
        self._conn = raw_conn

    def cursor(self) -> PostgresCursorWrapper:
        return PostgresCursorWrapper(self._conn.cursor())

    def execute(self, sql: str, params: tuple | list | None = None) -> PostgresCursorWrapper:
        cur = self.cursor()
        return cur.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def transaction(self) -> Any:
        """Return a transaction context manager compatible with psycopg 3."""
        if hasattr(self._conn, "transaction"):
            return self._conn.transaction()
        return PostgresTransactionWrapper(self)

    def __enter__(self) -> PostgresConnectionWrapper:
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)


# -----------------------------------------------------------------------------
# Connection & Initialization
# -----------------------------------------------------------------------------

_CONNECT_HOOK = None


def set_connect_hook(hook: Any) -> None:
    """Register a custom connection factory hook (primarily for testing)."""
    global _CONNECT_HOOK
    _CONNECT_HOOK = hook


def get_connect_hook() -> Any:
    return _CONNECT_HOOK


def connect() -> Any:
    """Establish and return database connection (PostgreSQL or SQLite)."""
    if _CONNECT_HOOK is not None:
        return _CONNECT_HOOK()

    is_production = os.environ.get("AGENTRELIABILITY_ENV") == "production"
    db_url = get_database_url()

    # Requirement 5: Never silently fall back to ephemeral SQLite in production
    if is_production and not db_url and not os.environ.get("AGENTRELIABILITY_DB"):
        raise RuntimeError(
            "DATABASE_URL environment variable is required in production mode. "
            "Silently falling back to ephemeral SQLite in production is strictly prohibited "
            "to prevent data loss on container restart."
        )

    if db_url or is_postgres():
        if not db_url:
            raise RuntimeError("PostgreSQL engine requested but DATABASE_URL is not set.")

        # Normalize postgres:// to postgresql://
        clean_url = db_url
        if clean_url.startswith("postgres://"):
            clean_url = "postgresql://" + clean_url[len("postgres://"):]

        try:
            import psycopg
            raw_conn = psycopg.connect(clean_url, connect_timeout=15)
            return PostgresConnectionWrapper(raw_conn)
        except Exception as exc:
            raise RuntimeError(f"PostgreSQL connection failed for DATABASE_URL: {exc}") from exc

    # Local development SQLite connection
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
    """Initialize database tables and run versioned migrations."""
    with connect() as conn:
        if is_postgres():
            run_postgres_migrations(conn)
        else:
            run_migrations(conn)


# -----------------------------------------------------------------------------
# Execution Store Helpers
# -----------------------------------------------------------------------------

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


def _summary(row: Any) -> dict:
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
