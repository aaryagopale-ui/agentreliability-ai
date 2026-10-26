"""System diagnostics and environment verification tool for AgentReliability.

Diagnoses:
- Python version, virtualenv, and backend dependencies
- Node.js, npm, and frontend dependencies
- SQLite database initialization and schema tables
- Port conflicts on 8001 and 5174
- Backend connectivity and API key validation
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    find_workspace_root,
    load_config,
    resolve_api_key,
    resolve_database_path,
    resolve_endpoint,
    resolve_instance_id,
)
from .ports import is_port_in_use, probe_backend, probe_frontend


def check_python() -> Dict[str, Any]:
    """Inspect Python version and backend dependencies."""
    vi = sys.version_info
    ver_str = f"{vi.major}.{vi.minor}.{vi.micro}"
    valid_version = vi >= (3, 9)

    root = find_workspace_root()
    venv_path = (root / "backend" / ".venv") if root else None
    has_backend_venv = venv_path.is_dir() if venv_path else False

    # Check required packages in current environment
    packages = ["fastapi", "uvicorn", "pydantic", "sqlite3"]
    missing_pkgs: List[str] = []
    for pkg in packages:
        try:
            __import__(pkg)
        except ImportError:
            missing_pkgs.append(pkg)

    return {
        "version": ver_str,
        "valid_version": valid_version,
        "executable": sys.executable,
        "backend_venv": str(venv_path) if has_backend_venv else None,
        "missing_packages": missing_pkgs,
        "ok": valid_version and len(missing_pkgs) == 0,
    }


def check_node_and_frontend() -> Dict[str, Any]:
    """Inspect Node.js, npm, and frontend dependencies."""
    node_bin = shutil.which("node") or shutil.which("node.exe")
    npm_bin = shutil.which("npm") or shutil.which("npm.cmd")

    node_ver: Optional[str] = None
    node_valid = False
    if node_bin:
        try:
            res = subprocess.run([node_bin, "-v"], capture_output=True, text=True, timeout=3.0)
            if res.returncode == 0:
                node_ver = res.stdout.strip()
                # e.g. "v20.18.0" -> major = 20
                clean = node_ver.lstrip("v").split(".")[0]
                if clean.isdigit() and int(clean) >= 18:
                    node_valid = True
        except Exception:
            pass

    npm_ver: Optional[str] = None
    if npm_bin:
        try:
            res = subprocess.run([npm_bin, "-v"], capture_output=True, text=True, timeout=3.0)
            if res.returncode == 0:
                npm_ver = res.stdout.strip()
        except Exception:
            pass

    root = find_workspace_root()
    node_modules = (root / "frontend" / "node_modules") if root else None
    has_node_modules = (node_modules.is_dir() and any(node_modules.iterdir())) if (node_modules and node_modules.exists()) else False

    return {
        "node_bin": node_bin,
        "node_version": node_ver,
        "node_valid": node_valid,
        "npm_bin": npm_bin,
        "npm_version": npm_ver,
        "has_node_modules": has_node_modules,
        "ok": bool(node_bin and node_valid and npm_bin and has_node_modules),
    }


def check_database() -> Dict[str, Any]:
    """Inspect local SQLite database existence and required tables."""
    root = find_workspace_root()
    instance_id = resolve_instance_id(root)
    db_path = resolve_database_path(start_dir=root)

    if not db_path.is_file():
        return {
            "exists": False,
            "path": str(db_path),
            "instance_id": instance_id,
            "tables": [],
            "ok": False,
            "details": "Database file does not exist (will be initialized on first run)",
        }

    expected_tables = {"users", "projects", "api_keys", "executions", "baselines", "trace_events"}
    found_tables = set()

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        rows = cursor.fetchall()
        found_tables = {r[0] for r in rows}
        conn.close()

        missing = expected_tables - found_tables
        return {
            "exists": True,
            "path": str(db_path),
            "instance_id": instance_id,
            "tables": sorted(list(found_tables)),
            "missing_tables": sorted(list(missing)),
            "ok": len(missing) == 0,
            "details": f"{len(found_tables)} tables initialized" if len(missing) == 0 else f"Missing tables: {missing}",
        }
    except Exception as exc:
        return {
            "exists": True,
            "path": str(db_path),
            "instance_id": instance_id,
            "tables": [],
            "ok": False,
            "details": f"Database corruption or connection failure: {exc}",
        }


def check_ports(backend_port: int = 8001, frontend_port: int = 5174, host: str = "127.0.0.1") -> Dict[str, Any]:
    """Inspect ports 8001 and 5174 for occupancy, compatibility, and collisions."""
    root = find_workspace_root()
    instance_id = resolve_instance_id(root)
    db_path = resolve_database_path(start_dir=root)
    b_probe = probe_backend(backend_port, host, expected_instance_id=instance_id, expected_db_path=db_path)
    f_probe = probe_frontend(frontend_port, host)

    return {
        "backend": {
            "port": backend_port,
            "probe": b_probe,
        },
        "frontend": {
            "port": frontend_port,
            "probe": f_probe,
        },
    }


def check_backend_and_auth(endpoint: str, api_key: str) -> Dict[str, Any]:
    """Inspect backend reachability and optional API key authorization."""
    health_url = f"{endpoint}/api/health"
    healthy = False
    details = ""

    try:
        req = urllib.request.Request(health_url, headers={"User-Agent": "agentreliability-doctor/0.1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                healthy = True
                details = "Online and healthy"
            else:
                details = f"HTTP {resp.status}"
    except Exception as exc:
        details = f"Unreachable ({exc})"

    key_status = "Not set"
    key_valid = False
    project_name = None

    if api_key:
        if healthy:
            verify_url = f"{endpoint}/api/v1/auth/verify"
            req = urllib.request.Request(
                verify_url,
                headers={"X-API-Key": api_key, "User-Agent": "agentreliability-doctor/0.1.0"},
            )
            try:
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        key_valid = True
                        data = json.loads(resp.read().decode("utf-8"))
                        project_name = data.get("project", {}).get("name")
                        key_status = f"Valid (Project: '{project_name}')"
                    else:
                        key_status = f"Invalid (HTTP {resp.status})"
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    key_status = "Invalid (HTTP 401 Unauthorized)"
                else:
                    key_status = f"Rejected (HTTP {exc.code})"
            except Exception as exc:
                key_status = f"Verification error ({exc})"
        else:
            key_status = "Configured (backend offline)"

    return {
        "endpoint": endpoint,
        "healthy": healthy,
        "details": details,
        "api_key_configured": bool(api_key),
        "api_key_valid": key_valid,
        "api_key_status": key_status,
        "project_name": project_name,
    }


def run_doctor() -> int:
    """Run full system diagnostics and print a friendly terminal report.

    Returns exit code 0 if healthy/warnings only, 1 if critical failures exist.
    """
    print("\n🩺 AgentReliability System Doctor")
    print("=" * 68)

    cfg = load_config()
    backend_port = cfg.get("backend_port", 8001)
    frontend_port = cfg.get("frontend_port", 5174)
    endpoint = resolve_endpoint()
    api_key = resolve_api_key()

    remediations: List[str] = []
    has_critical_failure = False

    # 1. Python Environment
    print("[Python Environment]")
    py = check_python()
    if py["valid_version"]:
        print(f"  ✅ Python Version        : {py['version']} (>= 3.9 required)")
    else:
        print(f"  ❌ Python Version        : {py['version']} (Python >= 3.9 required)")
        remediations.append("Install Python 3.9 or newer.")
        has_critical_failure = True

    if py["backend_venv"]:
        print(f"  ✅ Backend Virtualenv    : {py['backend_venv']}")
    else:
        print("  ⚠️  Backend Virtualenv    : Not detected at backend/.venv")

    if not py["missing_packages"]:
        print("  ✅ Core Dependencies     : fastapi, uvicorn, pydantic installed")
    else:
        print(f"  ❌ Missing Dependencies  : {', '.join(py['missing_packages'])}")
        remediations.append("Install backend dependencies: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt")
        # Critical if backend is also offline
        has_critical_failure = True

    # 2. Node & Frontend Environment
    print("\n[Frontend Environment]")
    fe = check_node_and_frontend()
    if fe["node_bin"] and fe["node_valid"]:
        print(f"  ✅ Node.js Version       : {fe['node_version']} (>= 18 required)")
    elif fe["node_bin"]:
        print(f"  ⚠️  Node.js Version       : {fe['node_version']} (Warning: Node.js >= 18 recommended)")
        remediations.append("Upgrade Node.js to version 18 or newer.")
    else:
        print("  ⚠️  Node.js Binary        : Not found in PATH")
        remediations.append("Install Node.js (>= 18) to run the frontend dashboard: https://nodejs.org")

    if fe["npm_bin"]:
        print(f"  ✅ Package Manager       : npm {fe['npm_version'] or ''}".rstrip())
    else:
        print("  ⚠️  Package Manager       : npm not found in PATH")

    if fe["has_node_modules"]:
        print("  ✅ Frontend Dependencies : frontend/node_modules present")
    else:
        print("  ⚠️  Frontend Dependencies : frontend/node_modules missing")
        remediations.append("Install frontend dependencies: npm --prefix frontend install")

    # 3. Database & Storage
    print("\n[Database & Storage]")
    db = check_database()
    print(f"  ℹ️  Instance ID          : {db.get('instance_id')}")
    print(f"  ℹ️  Database Path        : {db.get('path')}")
    if db["exists"] and db["ok"]:
        print(f"  ✅ SQLite Tables         : {db['details']}")
    elif db["exists"]:
        print(f"  ⚠️  SQLite Tables         : {db['details']}")
        remediations.append("Initialize missing database tables: python3 -c 'from app.database import init_db; init_db()'")
    else:
        print(f"  ℹ️  SQLite Tables         : {db['details']}")
        remediations.append("Initialize database: run 'agentreliability init'")

    # 4. Network Ports
    print("\n[Ports & Network]")
    ports = check_ports(backend_port=backend_port, frontend_port=frontend_port)
    b_info = ports["backend"]["probe"]
    f_info = ports["frontend"]["probe"]

    if not b_info["occupied"]:
        print(f"  ✅ Port {backend_port} (Backend)   : Available")
    elif b_info["is_agentreliability"] and b_info["compatible"]:
        print(f"  ✅ Port {backend_port} (Backend)   : In use by active AgentReliability backend ({b_info['details']})")
    else:
        print(f"  ⚠️  Port {backend_port} (Backend)   : Occupied by external process ({b_info['details']})")
        print(f"     ↳ 'agentreliability dev' will automatically select an available port (e.g. {backend_port + 1}).")

    if not f_info["occupied"]:
        print(f"  ✅ Port {frontend_port} (Frontend)  : Available")
    elif f_info["is_agentreliability"]:
        print(f"  ✅ Port {frontend_port} (Frontend)  : In use by active AgentReliability dashboard")
    else:
        print(f"  ⚠️  Port {frontend_port} (Frontend)  : Occupied by external process ({f_info['details']})")
        print(f"     ↳ 'agentreliability dev' will automatically select an available port (e.g. {frontend_port + 1}).")

    # 5. Connectivity & Auth
    print("\n[Connectivity & Authentication]")
    conn = check_backend_and_auth(endpoint, api_key)
    if conn["healthy"]:
        print(f"  ✅ Backend Server        : {conn['endpoint']} ({conn['details']})")
    else:
        print(f"  ℹ️  Backend Server        : {conn['endpoint']} ({conn['details']})")
        if not b_info["is_agentreliability"]:
            remediations.append("Start AgentReliability services: agentreliability dev")

    if conn["api_key_configured"]:
        masked = api_key[:7] + "..." + api_key[-4:] if len(api_key) > 12 else "********"
        if conn["api_key_valid"]:
            print(f"  ✅ API Key Auth          : {masked} — {conn['api_key_status']}")
        elif conn["healthy"]:
            print(f"  ❌ API Key Auth          : {masked} — {conn['api_key_status']}")
            remediations.append("Generate a valid API key in the dashboard (API Keys page) or run 'agentreliability init'.")
        else:
            print(f"  ℹ️  API Key Configured    : {masked}")
    else:
        print("  ℹ️  API Key Auth          : Not configured (Local mode: traces work without external keys)")

    # 6. Summary & Remediation
    print("=" * 68)
    if remediations:
        print("🔧 Recommended Actions:")
        for idx, rec in enumerate(remediations, 1):
            print(f"  {idx}. {rec}")
        print("=" * 68)

    if has_critical_failure:
        print("❌ Status: Issues detected that prevent running AgentReliability.\n")
        return 1
    else:
        print("✅ Status: Environment is healthy! Run 'agentreliability dev' to start.\n")
        return 0

