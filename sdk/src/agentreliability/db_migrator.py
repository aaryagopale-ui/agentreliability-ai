"""Database migration and import utility for AgentReliability.

Provides safe, transaction-wrapped copying of user accounts, projects,
API keys, baselines, traces, executions, and test runs from an external
AgentReliability SQLite database into the current local installation.

Key safety properties:
- Source database is opened strictly in read-only mode (file:...?mode=ro).
- Target operations run inside a single atomic SQLite transaction.
- Preserves unique constraints and handles collisions cleanly (INSERT OR IGNORE).
- Auto-updates sqlite_sequence to protect subsequent autoincrement inserts.
- Provides dry-run validation option.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import find_workspace_root, resolve_database_path, resolve_instance_id


TABLE_IMPORT_ORDER = [
    "users",
    "projects",
    "api_keys",
    "executions",
    "baselines",
    "baseline_versions",
    "trace_executions",
    "trace_events",
    "trace_tool_calls",
    "test_cases",
    "test_runs",
    "ci_runs",
]


def ensure_target_schema(target_path: Path) -> None:
    """Ensure all required tables and migrations are initialized on target database."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    root = find_workspace_root()
    if root:
        backend_dir = str((root / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    orig_env = os.environ.get("AGENTRELIABILITY_DB")
    try:
        os.environ["AGENTRELIABILITY_DB"] = str(target_path.resolve())
        from app.database import init_db  # type: ignore
        from app import ci_store, test_store, trace_store  # type: ignore

        init_db()
        test_store.init_tables()
        trace_store.init_tables()
        ci_store.init_tables()
    finally:
        if orig_env is not None:
            os.environ["AGENTRELIABILITY_DB"] = orig_env
        else:
            os.environ.pop("AGENTRELIABILITY_DB", None)


def import_database(
    source_path: Path,
    target_path: Optional[Path] = None,
    dry_run: bool = False,
) -> Tuple[bool, str, Dict[str, int]]:
    """Import records from an external SQLite database into target database.

    Returns:
        (success: bool, message: str, table_counts: Dict[str, int])
    """
    source_resolved = source_path.resolve()
    if not source_resolved.is_file():
        return False, f"Source database file does not exist: {source_resolved}", {}

    target_resolved = (target_path or resolve_database_path()).resolve()
    if source_resolved == target_resolved:
        return False, "Source and target database paths are identical.", {}

    # Initialize schema on target if needed
    try:
        ensure_target_schema(target_resolved)
    except Exception as exc:
        return False, f"Could not prepare target database schema: {exc}", {}

    # Connect to source in read-only mode using SQLite URI
    src_uri = f"file:{source_resolved}?mode=ro"
    try:
        src_conn = sqlite3.connect(src_uri, uri=True, timeout=10.0)
        src_conn.row_factory = sqlite3.Row
    except Exception as exc:
        return False, f"Failed to open source database in read-only mode: {exc}", {}

    # Connect to target
    try:
        dst_conn = sqlite3.connect(str(target_resolved), timeout=30.0)
        dst_conn.row_factory = sqlite3.Row
        dst_conn.execute("PRAGMA foreign_keys = OFF")  # temporarily disable during bulk insert
    except Exception as exc:
        src_conn.close()
        return False, f"Failed to open target database: {exc}", {}

    counts: Dict[str, int] = {}
    try:
        # Check source tables
        src_tables = {
            r[0]
            for r in src_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        # Check target tables
        dst_tables = {
            r[0]
            for r in dst_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        dst_conn.execute("BEGIN TRANSACTION")

        for table in TABLE_IMPORT_ORDER:
            if table not in src_tables or table not in dst_tables:
                continue

            src_cols = [
                r[1]
                for r in src_conn.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            dst_cols = [
                r[1]
                for r in dst_conn.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            common_cols = [c for c in src_cols if c in dst_cols]
            if not common_cols:
                continue

            # Count before
            pre_count_row = dst_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            pre_count = pre_count_row[0] if pre_count_row else 0

            cols_str = ", ".join(f'"{c}"' for c in common_cols)
            placeholders = ", ".join("?" for _ in common_cols)
            insert_sql = f"INSERT OR IGNORE INTO {table} ({cols_str}) VALUES ({placeholders})"

            rows = src_conn.execute(f"SELECT {cols_str} FROM {table}").fetchall()
            for r in rows:
                dst_conn.execute(insert_sql, tuple(r))

            post_count_row = dst_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            post_count = post_count_row[0] if post_count_row else 0
            inserted = max(0, post_count - pre_count)
            counts[table] = inserted

        # Update sqlite_sequence for tables with autoincrement primary key
        seq_exists = dst_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        ).fetchone()
        if seq_exists:
            for tbl in TABLE_IMPORT_ORDER:
                if tbl in dst_tables:
                    try:
                        max_row = dst_conn.execute(f"SELECT MAX(id) FROM {tbl}").fetchone()
                        if max_row and max_row[0] is not None:
                            dst_conn.execute(
                                "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?) "
                                "ON CONFLICT(name) DO UPDATE SET seq = MAX(seq, excluded.seq)",
                                (tbl, max_row[0]),
                            )
                    except Exception:
                        pass

        if dry_run:
            dst_conn.rollback()
            msg = "Dry-run completed successfully (no changes committed)."
        else:
            dst_conn.commit()
            msg = "Database import completed successfully."

        # Re-enable foreign keys
        dst_conn.execute("PRAGMA foreign_keys = ON")
        return True, msg, counts

    except Exception as exc:
        try:
            dst_conn.rollback()
        except Exception:
            pass
        return False, f"Import transaction failed and was rolled back: {exc}", counts
    finally:
        src_conn.close()
        dst_conn.close()


def run_import_db(
    source: str,
    target: Optional[str] = None,
    dry_run: bool = False,
) -> int:
    """CLI action for `agentreliability import-db`."""
    source_p = Path(source)
    target_p = Path(target) if target else None

    print("\n📦 AgentReliability Database Import & Migration")
    print("=" * 68)
    print(f"Source Database : {source_p.resolve()} (Read-Only Mode)")
    target_resolved = (target_p or resolve_database_path()).resolve()
    print(f"Target Database : {target_resolved}")
    if dry_run:
        print("Mode            : DRY RUN (Validation only, no data written)")
    print("------------------------------------------------------------------")

    success, message, counts = import_database(
        source_path=source_p,
        target_path=target_p,
        dry_run=dry_run,
    )

    if not success:
        print(f"❌ Migration Error: {message}\n", file=sys.stderr)
        return 1

    print(f"✅ {message}\n")
    print("Imported Records Summary:")
    print(f"  • Users               : {counts.get('users', 0)} added")
    print(f"  • Projects            : {counts.get('projects', 0)} added")
    print(f"  • API Keys            : {counts.get('api_keys', 0)} added")
    print(f"  • Executions          : {counts.get('executions', 0)} added")
    print(f"  • Golden Baselines    : {counts.get('baselines', 0)} added")
    print(f"  • Baseline Versions   : {counts.get('baseline_versions', 0)} added")
    print(f"  • Trace Executions    : {counts.get('trace_executions', 0)} added")
    print(f"  • Trace Tool Calls    : {counts.get('trace_tool_calls', 0)} added")
    print(f"  • Test Cases          : {counts.get('test_cases', 0)} added")
    print(f"  • CI Runs             : {counts.get('ci_runs', 0)} added")
    print("=" * 68 + "\n")
    return 0

