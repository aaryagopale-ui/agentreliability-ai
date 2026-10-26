"""Development server manager and project initialization for AgentReliability.

Provides:
- `agentreliability init`: checks prerequisites, creates safe local config, initializes database.
- `agentreliability dev`: starts backend and frontend with automatic port conflict resolution,
  safe reuse of existing instances, and clean process supervision.
"""
from __future__ import annotations

import collections
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    CONFIG_FILE_NAME,
    DEFAULT_BACKEND_PORT,
    DEFAULT_FRONTEND_PORT,
    find_workspace_root,
    load_config,
    resolve_database_path,
    resolve_instance_id,
    save_config,
)
from .ports import (
    find_available_port,
    is_port_available,
    is_port_in_use,
    probe_backend,
    probe_frontend,
    resolve_service_ports,
)

logger = logging.getLogger("agentreliability.dev")


class StreamDrainer:
    """Continuously drains a subprocess pipe in chunks to prevent OS kernel pipe buffer deadlocks.

    Features:
    - Non-blocking chunk-based reading so output without newlines does not block.
    - Strictly bounded in-memory circular buffer (O(1) memory, oldest lines discarded).
    - Optional persistent appending to managed log files on disk.
    - Thread-safe access to recent diagnostic output.
    """

    def __init__(
        self,
        stream,
        name: str = "stream",
        max_lines: int = 250,
        log_file_path: Optional[Path] = None,
    ):
        self.stream = stream
        self.name = name
        self.max_lines = max_lines
        self.log_file_path = log_file_path
        self._buffer: collections.deque[str] = collections.deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self.total_bytes = 0
        self.total_lines = 0
        self._closed = False
        self._thread = threading.Thread(
            target=self._drain_loop,
            daemon=True,
            name=f"stream-drainer-{name}",
        )
        if self.stream is not None:
            self._thread.start()

    def _drain_loop(self) -> None:
        log_file = None
        if self.log_file_path:
            try:
                self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
                log_file = open(self.log_file_path, "a", encoding="utf-8", errors="replace")
            except Exception:
                log_file = None

        line_acc = ""
        try:
            while True:
                # Read chunks to avoid waiting for newlines if large outputs or long lines are emitted
                chunk = self.stream.read(4096)
                if not chunk or not isinstance(chunk, (str, bytes)):
                    break

                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8", errors="replace")

                chunk_len = len(chunk)
                with self._lock:
                    self.total_bytes += chunk_len

                if log_file:
                    try:
                        log_file.write(chunk)
                        log_file.flush()
                    except Exception:
                        pass

                line_acc += chunk
                while "\n" in line_acc:
                    line, line_acc = line_acc.split("\n", 1)
                    with self._lock:
                        self.total_lines += 1
                        self._buffer.append(line + "\n")

                # Guard against unbounded memory if output contains no newlines
                if len(line_acc) > 8192:
                    with self._lock:
                        self.total_lines += 1
                        self._buffer.append(line_acc[:8192] + "\n")
                    line_acc = line_acc[8192:]
        except Exception:
            pass
        finally:
            if line_acc:
                with self._lock:
                    self.total_lines += 1
                    self._buffer.append(line_acc)
            if log_file:
                try:
                    log_file.flush()
                    log_file.close()
                except Exception:
                    pass
            try:
                self.stream.close()
            except Exception:
                pass
            self._closed = True

    def get_recent_lines(self) -> List[str]:
        with self._lock:
            return list(self._buffer)

    def get_recent_text(self) -> str:
        with self._lock:
            return "".join(self._buffer)

    def close(self) -> None:
        try:
            if self.stream is not None:
                self.stream.close()
        except Exception:
            pass


def get_process_diagnostics(
    proc: Any,
    out_drainer: Optional[StreamDrainer] = None,
    err_drainer: Optional[StreamDrainer] = None,
) -> Tuple[str, str]:
    """Retrieve captured stdout and stderr diagnostics from drainers, with fallback for mocked objects."""
    stdout_text = out_drainer.get_recent_text() if out_drainer else ""
    stderr_text = err_drainer.get_recent_text() if err_drainer else ""

    # Fallback if drainers have no data (e.g. mock objects in unit tests)
    if not stdout_text and not stderr_text and hasattr(proc, "communicate"):
        try:
            comm_out, comm_err = proc.communicate(timeout=0.1)
            stdout_text = stdout_text or (comm_out or "")
            stderr_text = stderr_text or (comm_err or "")
        except Exception:
            pass

    return stdout_text, stderr_text


def find_backend_python(root: Path) -> Tuple[str, List[str]]:
    """Determine the best Python executable for running the backend and detect missing packages."""
    candidates = []

    # 1. Check backend/.venv
    if os.name == "nt":
        venv_py = root / "backend" / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = root / "backend" / ".venv" / "bin" / "python"
    if venv_py.is_file():
        candidates.append(str(venv_py))

    # 2. Check active virtualenv
    active_venv = os.environ.get("VIRTUAL_ENV")
    if active_venv:
        if os.name == "nt":
            candidates.append(os.path.join(active_venv, "Scripts", "python.exe"))
        else:
            candidates.append(os.path.join(active_venv, "bin", "python"))

    # 3. Current python interpreter
    candidates.append(sys.executable)

    chosen_py = sys.executable
    missing_packages: List[str] = []

    for py in candidates:
        if not os.path.isfile(py) or not os.access(py, os.X_OK):
            continue
        try:
            check_cmd = [py, "-c", "import fastapi, uvicorn, pydantic, sqlite3, agentreliability; print('OK')"]
            res = subprocess.run(check_cmd, capture_output=True, text=True, timeout=5.0)
            if res.returncode == 0 and "OK" in res.stdout:
                return py, []
        except Exception:
            pass

    # If none had all packages, check what's missing in chosen interpreter
    for pkg in ["fastapi", "uvicorn", "pydantic", "agentreliability"]:
        try:
            check_cmd = [chosen_py, "-c", f"import {pkg}"]
            res = subprocess.run(check_cmd, capture_output=True, text=True, timeout=3.0)
            if res.returncode != 0:
                missing_packages.append(pkg)
        except Exception:
            missing_packages.append(pkg)

    return chosen_py, missing_packages


def initialize_local_database(root: Path, python_bin: str, db_path: Optional[Path] = None) -> Tuple[bool, str]:
    """Initialize SQLite database using the backend schema."""
    target_db = db_path or (root / "backend" / "agentreliability.db")
    if target_db.is_file():
        return True, f"Existing database detected at {target_db.name}."

    target_db.parent.mkdir(parents=True, exist_ok=True)
    init_script = (
        "import sys, os; "
        "sys.path.insert(0, 'backend'); "
        f"os.environ['AGENTRELIABILITY_DB'] = {repr(str(target_db))}; "
        "from app.database import init_db; "
        "from app import test_store, trace_store, ci_store; "
        "init_db(); "
        "test_store.init_tables(); "
        "trace_store.init_tables(); "
        "ci_store.init_tables(); "
        "print('INIT_OK')"
    )

    try:
        res = subprocess.run(
            [python_bin, "-c", init_script],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10.0,
        )
        if res.returncode == 0 and "INIT_OK" in res.stdout:
            return True, "SQLite database initialized successfully."
        err_msg = res.stderr.strip() or res.stdout.strip()
        return False, f"Failed to initialize database: {err_msg}"
    except Exception as exc:
        return False, f"Database initialization error: {exc}"


def run_init(
    install_frontend: bool = False,
    install_deps: bool = False,
    force: bool = False,
) -> int:
    """Execute `agentreliability init` command."""
    if install_deps:
        install_frontend = True

    print("\n🚀 AgentReliability Setup & Initialization")
    print("=" * 68)

    root = find_workspace_root()
    if not root:
        print("❌ Error: Could not locate AgentReliability workspace root.", file=sys.stderr)
        print("   Please run this command from within the AgentReliability project directory.", file=sys.stderr)
        return 1

    instance_id = resolve_instance_id(root)
    database_path = resolve_database_path(start_dir=root)

    print(f"Workspace Root       : {root}")
    print(f"Instance ID          : {instance_id}")
    print(f"Database Path        : {database_path}")

    # 1. Check Python & Dependencies
    python_bin, missing_pkgs = find_backend_python(root)
    print(f"Python Interpreter   : {python_bin}")
    if missing_pkgs and install_deps:
        print(f"Installing missing backend packages ({', '.join(missing_pkgs)})...")
        req_file = root / "backend" / "requirements.txt"
        if req_file.is_file():
            try:
                pip_res = subprocess.run([python_bin, "-m", "pip", "install", "-r", str(req_file)], cwd=str(root))
                if pip_res.returncode == 0:
                    subprocess.run([python_bin, "-m", "pip", "install", "-e", str(root / "sdk")], cwd=str(root))
                    python_bin, missing_pkgs = find_backend_python(root)
            except Exception as exc:
                print(f"⚠️ Dependency installation warning: {exc}")

    if missing_pkgs:
        print(f"⚠️  Missing Backend Packages : {', '.join(missing_pkgs)}")
        print("   ↳ Run: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt")
    else:
        print("Backend Dependencies : All installed ✅")

    # 2. Initialize Database
    db_ok, db_msg = initialize_local_database(root, python_bin, database_path)
    if db_ok:
        print(f"Database             : {db_msg} ✅")
    else:
        print(f"Database Warning     : {db_msg}")

    # 3. Detect Ports & Check Collisions
    try:
        backend_port, reuse_b, frontend_port, reuse_f = resolve_service_ports(
            preferred_backend_port=DEFAULT_BACKEND_PORT,
            preferred_frontend_port=DEFAULT_FRONTEND_PORT,
            expected_instance_id=instance_id,
            expected_db_path=database_path,
        )
    except TypeError:
        backend_port, reuse_b, frontend_port, reuse_f = resolve_service_ports(
            preferred_backend_port=DEFAULT_BACKEND_PORT,
            preferred_frontend_port=DEFAULT_FRONTEND_PORT,
        )

    print(f"Backend Target Port  : {backend_port} {'(Reusing active instance)' if reuse_b else '(Available)'}")
    print(f"Dashboard Target Port: {frontend_port} {'(Reusing active instance)' if reuse_f else '(Available)'}")

    # 4. Check Frontend Dependencies
    npm_bin = shutil.which("npm") or shutil.which("npm.cmd")
    node_modules = root / "frontend" / "node_modules"
    has_node_modules = node_modules.is_dir() and any(node_modules.iterdir())

    if not has_node_modules:
        if install_frontend and npm_bin:
            print("Installing frontend dependencies with npm...")
            try:
                npm_res = subprocess.run([npm_bin, "--prefix", "frontend", "install"], cwd=str(root))
                if npm_res.returncode == 0:
                    print("Frontend Dependencies : Installed successfully ✅")
                else:
                    print("⚠️ Frontend installation failed. You can run 'npm --prefix frontend install' manually.")
            except Exception as exc:
                print(f"⚠️ Could not run npm: {exc}")
        else:
            print("Frontend Dependencies : Missing (Run 'npm --prefix frontend install' or use --install-frontend)")
    else:
        print("Frontend Dependencies : Installed ✅")

    # 5. Write local config
    config_data = {
        "instance_id": instance_id,
        "workspace_root": str(root.resolve()),
        "database_path": str(database_path.resolve()),
        "backend_host": "127.0.0.1",
        "backend_port": backend_port,
        "backend_url": f"http://127.0.0.1:{backend_port}",
        "frontend_port": frontend_port,
        "frontend_url": f"http://127.0.0.1:{frontend_port}",
    }
    cfg_path = save_config(config_data, target_dir=root)
    print(f"Local Configuration  : Saved to {cfg_path.name} ✅")
    print(f"Local Configuration  : Saved to {cfg_path.name} ✅")

    print("=" * 68)
    print("✅ Initialization complete! Next steps:")
    print("  1. Start the stack    : agentreliability dev")
    print("  2. Run system checks  : agentreliability doctor")
    print("  3. Run sample agent   : python examples/quickstart_agent.py\n")
    return 0


def run_dev(
    backend_port: Optional[int] = None,
    frontend_port: Optional[int] = None,
    backend_only: bool = False,
    frontend_only: bool = False,
    host: str = "127.0.0.1",
    no_banner: bool = False,
    open_browser: bool = True,
) -> int:
    """Execute `agentreliability dev` command."""
    root = find_workspace_root()
    if not root:
        print("❌ Error: Could not locate AgentReliability workspace root.", file=sys.stderr)
        return 1

    cfg = load_config(root)
    instance_id = resolve_instance_id(root)
    database_path = resolve_database_path(start_dir=root)

    pref_b_port = backend_port or cfg.get("backend_port", DEFAULT_BACKEND_PORT)
    pref_f_port = frontend_port or cfg.get("frontend_port", DEFAULT_FRONTEND_PORT)

    # Check status of preferred backend port for tailored messaging
    try:
        probe_initial = probe_backend(
            pref_b_port,
            host=host,
            expected_instance_id=instance_id,
            expected_db_path=database_path,
        )
    except TypeError:
        probe_initial = probe_backend(pref_b_port, host=host)

    # 1. Resolve Ports with Collision Detection & Safe Reuse
    try:
        b_port, reuse_backend, f_port, reuse_frontend = resolve_service_ports(
            preferred_backend_port=pref_b_port,
            preferred_frontend_port=pref_f_port,
            host=host,
            expected_instance_id=instance_id,
            expected_db_path=database_path,
        )
    except TypeError:
        b_port, reuse_backend, f_port, reuse_frontend = resolve_service_ports(
            preferred_backend_port=pref_b_port,
            preferred_frontend_port=pref_f_port,
            host=host,
        )

    if b_port != pref_b_port and not reuse_backend:
        if probe_initial.get("is_agentreliability") and not probe_initial.get("same_installation"):
            print(f"⚠️  Port {pref_b_port} is running an AgentReliability instance from a different directory:")
            print(f"   ↳ {probe_initial.get('details')}")
            print(f"   Selecting available port {b_port} to preserve independent database & project isolation.")
        else:
            print(f"⚠️  Port {pref_b_port} is occupied by an external service.")
            print(f"   Selecting available port {b_port} for AgentReliability backend (unrelated process untouched).")
    elif reuse_backend:
        print(f"ℹ️  Port {b_port} is running an active AgentReliability backend from this installation. Reusing instance.")

    if f_port != pref_f_port and not reuse_frontend:
        print(f"⚠️  Port {pref_f_port} is occupied by an external service or another instance.")
        print(f"   Selecting available port {f_port} for AgentReliability dashboard (unrelated process untouched).")
    elif reuse_frontend:
        print(f"ℹ️  Port {f_port} is running an active AgentReliability dashboard. Reusing instance.")

    # 2. Update local config with chosen ports and instance identity
    backend_url = f"http://{host}:{b_port}"
    frontend_url = f"http://{host}:{f_port}"
    save_config(
        {
            "instance_id": instance_id,
            "workspace_root": str(root.resolve()),
            "database_path": str(database_path.resolve()),
            "backend_host": host,
            "backend_port": b_port,
            "backend_url": backend_url,
            "frontend_port": f_port,
            "frontend_url": frontend_url,
        },
        target_dir=root,
    )

    # 3. Verify / resolve python binary
    python_bin, missing_pkgs = find_backend_python(root)
    if missing_pkgs and not reuse_backend and not frontend_only:
        print(f"❌ Error: Missing required backend dependencies: {', '.join(missing_pkgs)}", file=sys.stderr)
        print("   ↳ Run: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt", file=sys.stderr)
        return 1

    spawned_processes: List[subprocess.Popen] = []
    drainers: List[StreamDrainer] = []
    b_proc: Optional[subprocess.Popen] = None
    f_proc: Optional[subprocess.Popen] = None
    b_out_drainer: Optional[StreamDrainer] = None
    b_err_drainer: Optional[StreamDrainer] = None
    f_out_drainer: Optional[StreamDrainer] = None
    f_err_drainer: Optional[StreamDrainer] = None

    logs_dir = root / ".agentreliability" / "logs"

    def cleanup_processes(signum=None, frame=None):
        print("\n\nStopping AgentReliability services...")
        # 1. Terminate only processes spawned and owned by this launcher run
        for proc in spawned_processes:
            try:
                if os.name != "nt":
                    try:
                        pgid = os.getpgid(proc.pid)
                        if pgid == proc.pid:
                            os.killpg(pgid, signal.SIGTERM)
                        else:
                            proc.terminate()
                    except (ProcessLookupError, PermissionError):
                        pass
                else:
                    proc.terminate()
            except Exception:
                pass

        # 2. Wait bounded time for owned processes to exit
        for proc in spawned_processes:
            try:
                proc.wait(timeout=3.0)
            except Exception:
                try:
                    if os.name != "nt":
                        try:
                            pgid = os.getpgid(proc.pid)
                            if pgid == proc.pid:
                                os.killpg(pgid, signal.SIGKILL)
                            else:
                                proc.kill()
                        except (ProcessLookupError, PermissionError):
                            pass
                    else:
                        proc.kill()
                except Exception:
                    pass

        # 3. Clean up active stream drainers
        for drainer in drainers:
            drainer.close()

        print("✅ Services stopped safely.")
        if signum is not None:
            sys.exit(0)

    try:
        signal.signal(signal.SIGINT, cleanup_processes)
        signal.signal(signal.SIGTERM, cleanup_processes)
    except (ValueError, AttributeError):
        pass  # Signal handlers can only be set from the main thread

    # 4. Start Backend (if needed)
    if not reuse_backend and not frontend_only:
        print(f"Starting backend on {backend_url}...")
        backend_env = os.environ.copy()
        backend_env["PYTHONPATH"] = str(root / "backend")
        backend_env["AGENTRELIABILITY_DB"] = str(database_path.resolve())
        backend_env["AGENTRELIABILITY_INSTANCE_ID"] = instance_id
        backend_env["AGENTRELIABILITY_WORKSPACE_ROOT"] = str(root.resolve())
        backend_env["AGENTRELIABILITY_ALLOWED_ORIGINS"] = f"{frontend_url},http://localhost:{f_port},http://127.0.0.1:{f_port}"

        backend_cmd = [
            python_bin,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(b_port),
        ]

        try:
            b_proc = subprocess.Popen(
                backend_cmd,
                cwd=str(root / "backend"),
                env=backend_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=(os.name != "nt"),
            )
            spawned_processes.append(b_proc)

            # Continuously drain stdout and stderr pipes in real time to prevent OS pipe deadlocks
            b_out_drainer = StreamDrainer(
                b_proc.stdout,
                name="backend-stdout",
                log_file_path=logs_dir / "backend.log",
            )
            b_err_drainer = StreamDrainer(
                b_proc.stderr,
                name="backend-stderr",
                log_file_path=logs_dir / "backend.log",
            )
            drainers.extend([b_out_drainer, b_err_drainer])
        except Exception as exc:
            print(f"❌ Failed to launch backend process: {exc}", file=sys.stderr)
            cleanup_processes()
            return 1

        # Wait for backend health probe
        healthy = False
        health_url = f"{backend_url}/api/health"
        for _ in range(50):  # 50 * 0.2s = 10s max
            if b_proc.poll() is not None:
                # Backend exited early
                _, stderr = get_process_diagnostics(b_proc, b_out_drainer, b_err_drainer)
                print(f"❌ Backend exited unexpectedly with code {b_proc.returncode}:", file=sys.stderr)
                if stderr:
                    print(stderr.strip(), file=sys.stderr)
                cleanup_processes()
                return 1
            try:
                req = urllib.request.Request(health_url, headers={"User-Agent": "agentreliability-dev"})
                with urllib.request.urlopen(req, timeout=0.5) as resp:
                    if resp.status == 200:
                        healthy = True
                        break
            except Exception:
                pass
            time.sleep(0.2)

        if not healthy:
            print(f"❌ Backend failed to respond healthy at {health_url} within 10 seconds.", file=sys.stderr)
            _, stderr = get_process_diagnostics(b_proc, b_out_drainer, b_err_drainer)
            if stderr:
                print(f"Backend output:\n{stderr.strip()}", file=sys.stderr)
            cleanup_processes()
            return 1

    # 5. Start Frontend (if needed)
    npm_bin = shutil.which("npm") or shutil.which("npm.cmd")
    frontend_started = False

    if not reuse_frontend and not backend_only:
        node_modules = root / "frontend" / "node_modules"
        if not node_modules.is_dir() or not any(node_modules.iterdir()):
            print("⚠️  Frontend dependencies missing. Run 'npm --prefix frontend install' to enable dashboard.")
        elif not npm_bin:
            print("⚠️  npm was not found in PATH. Install Node.js to enable the dashboard.")
        else:
            print(f"Starting dashboard on {frontend_url}...")
            frontend_env = os.environ.copy()
            frontend_env["API_TARGET"] = backend_url

            frontend_cmd = [npm_bin, "run", "dev", "--", "--host", "0.0.0.0", "--port", str(f_port)]
            try:
                f_proc = subprocess.Popen(
                    frontend_cmd,
                    cwd=str(root / "frontend"),
                    env=frontend_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=(os.name != "nt"),
                )
                spawned_processes.append(f_proc)

                # Continuously drain frontend stdout and stderr pipes in real time
                f_out_drainer = StreamDrainer(
                    f_proc.stdout,
                    name="frontend-stdout",
                    log_file_path=logs_dir / "frontend.log",
                )
                f_err_drainer = StreamDrainer(
                    f_proc.stderr,
                    name="frontend-stderr",
                    log_file_path=logs_dir / "frontend.log",
                )
                drainers.extend([f_out_drainer, f_err_drainer])
                frontend_started = True
            except Exception as exc:
                print(f"⚠️ Failed to launch dashboard: {exc}")

            # Give frontend a moment to bind
            if frontend_started and f_proc is not None:
                for _ in range(25):
                    if f_proc.poll() is not None:
                        _, f_err = get_process_diagnostics(f_proc, f_out_drainer, f_err_drainer)
                        print(f"⚠️ Dashboard process exited: {f_err.strip()}")
                        frontend_started = False
                        break
                    if is_port_in_use(f_port, host):
                        break
                    time.sleep(0.2)

    # 6. Friendly Summary Banner
    if not no_banner:
        print("\n" + "=" * 70)
        print("🚀 AgentReliability AI — Local Development Environment")
        print("=" * 70)
        print(f"Backend API   : {backend_url} [Healthy ✅]")
        if reuse_frontend or frontend_started:
            print(f"Dashboard UI  : {frontend_url} [Ready ✅]")
        else:
            print(f"Dashboard UI  : Offline (run 'npm --prefix frontend install' to enable)")
        print(f"Instance ID   : {instance_id}")
        print(f"Database      : {database_path}")
        print(f"Config File   : {CONFIG_FILE_NAME} (local-only, not committed)")
        print(f"Logs Directory: {logs_dir}")
        print("\nQuick Actions:")
        if reuse_frontend or frontend_started:
            print(f"  • Open Dashboard : {frontend_url}")
            print(f"  • Explore Demo   : Click 'Getting Started' -> 'Load Demo Agent & Traces'")
        print(f"  • Run Quickstart : python examples/quickstart_agent.py")
        print(f"  • Run Diagnostics: agentreliability doctor")
        print(f"  • Offline CI Test: agentreliability test --project examples/quickstart_agent.py")
        print("\nPress Ctrl+C to stop services.")
        print("=" * 70 + "\n")

    # 7. Automatically open browser if frontend dashboard is available
    if not backend_only and open_browser and (reuse_frontend or frontend_started):
        if not os.environ.get("CI") and not os.environ.get("AGENTRELIABILITY_NO_BROWSER"):
            try:
                import webbrowser
                webbrowser.open(frontend_url)
                print(f"🌐 Opened {frontend_url} in your browser.")
            except Exception:
                pass

    # 8. Supervise until exit with continuous unresponsiveness detection
    last_health_check = time.time()
    health_interval = 5.0
    consecutive_health_failures = 0
    max_consecutive_health_failures = 3

    try:
        while True:
            for proc in spawned_processes:
                ret = proc.poll()
                if ret is not None:
                    out_diag, err_diag = get_process_diagnostics(
                        proc,
                        b_out_drainer if proc is b_proc else f_out_drainer if proc is f_proc else None,
                        b_err_drainer if proc is b_proc else f_err_drainer if proc is f_proc else None,
                    )
                    diag = err_diag.strip() or out_diag.strip()
                    print(f"⚠️ Service process (PID {proc.pid}) exited with code {ret}.", file=sys.stderr)
                    if diag:
                        print(f"--- Last Output ---\n{diag}\n-------------------", file=sys.stderr)
                    cleanup_processes()
                    return ret

            # Periodically verify backend responsiveness if we own the running backend
            now = time.time()
            if b_proc is not None and (now - last_health_check) >= health_interval:
                last_health_check = now
                try:
                    probe_req = urllib.request.Request(
                        f"{backend_url}/api/health",
                        headers={"User-Agent": "agentreliability-watchdog"},
                    )
                    with urllib.request.urlopen(probe_req, timeout=2.0) as probe_resp:
                        if probe_resp.status == 200:
                            consecutive_health_failures = 0
                        else:
                            consecutive_health_failures += 1
                except Exception as exc:
                    consecutive_health_failures += 1
                    logger.debug(
                        "Backend health probe failed (%d/%d): %s",
                        consecutive_health_failures,
                        max_consecutive_health_failures,
                        exc,
                    )

                if consecutive_health_failures >= max_consecutive_health_failures:
                    print(
                        f"\n❌ Backend Unresponsiveness Detected: Backend at {backend_url} stopped responding to health probes for {int(consecutive_health_failures * health_interval)}s.",
                        file=sys.stderr,
                    )
                    _, b_err = get_process_diagnostics(b_proc, b_out_drainer, b_err_drainer)
                    if b_err:
                        print(f"--- Recent Backend Diagnostics ---\n{b_err.strip()}\n----------------------------------", file=sys.stderr)
                    cleanup_processes()
                    return 1

            time.sleep(0.5)
    except KeyboardInterrupt:
        cleanup_processes()
        return 0
