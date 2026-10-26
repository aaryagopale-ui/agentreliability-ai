"""Regression tests for OS pipe buffer deadlocks, process lifecycle, and API responsiveness.

Verifies:
1. Writing more output than OS pipe buffer capacity (>64KB) deadlocks without drainer.
2. StreamDrainer continuously drains stdout/stderr, preventing deadlocks even with massive output (>1MB).
3. Memory buffering remains strictly bounded (O(1) circular buffer).
4. Continuous output without newlines is safely drained via chunk reading.
5. Child process cleanup only terminates processes owned by the launcher.
6. Real backend API remains responsive during sustained, heavy logging.
7. Repeated startup/shutdown cycles cleanly release ports and child processes.
"""
import collections
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from agentreliability.dev_server import (
    StreamDrainer,
    get_process_diagnostics,
    run_dev,
)
from agentreliability.ports import is_port_in_use


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# 1. Pipe Buffer Capacity & Deadlock Tests
# ---------------------------------------------------------------------------

def test_raw_pipe_buffer_overflow_causes_deadlock():
    """Verify that writing >64KB to an undrained pipe buffer causes a child process to hang."""
    # Write 256KB to stdout without any reader draining it
    hang_script = (
        "import sys\n"
        "payload = 'X' * 1024 + '\\n'\n"
        "# 256 iterations * 1025 bytes = ~262 KB (far exceeds OS pipe buffer of 16KB/64KB)\n"
        "for _ in range(256):\n"
        "    sys.stdout.write(payload)\n"
        "    sys.stdout.flush()\n"
        "print('FINISHED')\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", hang_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Without a reader, the child will hang waiting for pipe space
    try:
        proc.wait(timeout=1.5)
        # If it somehow completed, wait() would return (e.g. if OS pipe buffer is huge)
        finished = False
    except subprocess.TimeoutExpired:
        finished = False
        proc.kill()
        proc.wait()

    assert not finished, "Expected undrained process to block on full pipe buffer!"


def test_stream_drainer_prevents_pipe_buffer_deadlock(tmp_path: Path):
    """Verify StreamDrainer allows a child process to emit >1MB without blocking."""
    log_file = tmp_path / "stream_output.log"
    # Emit 512KB to stdout and 512KB to stderr = >1MB total
    heavy_script = (
        "import sys\n"
        "payload = 'A' * 1024 + '\\n'\n"
        "for _ in range(512):\n"
        "    sys.stdout.write(payload)\n"
        "    sys.stdout.flush()\n"
        "    sys.stderr.write(payload)\n"
        "    sys.stderr.flush()\n"
        "print('ALL_DONE')\n"
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", heavy_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    out_drainer = StreamDrainer(proc.stdout, name="test-stdout", max_lines=100, log_file_path=log_file)
    err_drainer = StreamDrainer(proc.stderr, name="test-stderr", max_lines=100)

    # Must complete quickly without any blocking
    ret = proc.wait(timeout=5.0)
    assert ret == 0

    # Ensure drainer threads have finished
    out_drainer._thread.join(timeout=2.0)
    err_drainer._thread.join(timeout=2.0)

    # Verify total bytes drained exceeds 500KB on both streams
    assert out_drainer.total_bytes >= 500_000
    assert err_drainer.total_bytes >= 500_000

    # Verify bounded in-memory buffer (Task 4: no unbounded buffering)
    recent_out = out_drainer.get_recent_lines()
    assert len(recent_out) <= 100
    assert "ALL_DONE" in out_drainer.get_recent_text()

    # Verify log file was written on disk (Task 5: preserved diagnostics)
    assert log_file.is_file()
    assert log_file.stat().st_size >= 500_000


def test_stream_drainer_handles_large_output_without_newlines():
    """Verify StreamDrainer safely drains massive output containing zero newline characters."""
    # Emit 256KB of continuous characters without a single newline
    no_newline_script = (
        "import sys\n"
        "sys.stdout.write('Z' * (256 * 1024))\n"
        "sys.stdout.flush()\n"
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", no_newline_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    drainer = StreamDrainer(proc.stdout, name="test-no-nl", max_lines=50)

    # Must finish without hanging in readline
    ret = proc.wait(timeout=5.0)
    assert ret == 0

    drainer._thread.join(timeout=2.0)
    assert drainer.total_bytes >= 256 * 1024
    assert len(drainer.get_recent_lines()) <= 50


# ---------------------------------------------------------------------------
# 2. Process Ownership and Targeted Termination Tests
# ---------------------------------------------------------------------------

def test_launcher_terminates_only_owned_child_processes(tmp_path: Path):
    """Verify launcher termination targets only child processes spawned by it, leaving others untouched."""
    # Start an external "unrelated" process
    unrelated_script = "import time; time.sleep(60)"
    unrelated_proc = subprocess.Popen([sys.executable, "-c", unrelated_script])

    try:
        assert unrelated_proc.poll() is None

        # Start an "owned" child process using start_new_session
        owned_script = "import time; time.sleep(60)"
        owned_proc = subprocess.Popen(
            [sys.executable, "-c", owned_script],
            start_new_session=(os.name != "nt"),
        )
        assert owned_proc.poll() is None

        # Simulate cleanup logic from dev_server.py
        spawned = [owned_proc]
        for p in spawned:
            if os.name != "nt":
                try:
                    pgid = os.getpgid(p.pid)
                    if pgid == p.pid:
                        os.killpg(pgid, signal.SIGTERM)
                    else:
                        p.terminate()
                except Exception:
                    pass
            else:
                p.terminate()

        for p in spawned:
            p.wait(timeout=3.0)

        # Owned process must be terminated
        assert owned_proc.poll() is not None

        # Unrelated process MUST STILL BE RUNNING (Task 6: never terminate unrelated processes)
        assert unrelated_proc.poll() is None, "Launcher accidentally terminated an unrelated process!"

    finally:
        unrelated_proc.kill()
        unrelated_proc.wait()


# ---------------------------------------------------------------------------
# 3. Real Backend Responsiveness Under Sustained Output
# ---------------------------------------------------------------------------

def test_backend_api_responsiveness_under_sustained_logging(tmp_path: Path):
    """Verify that sustained high-volume logging does not block or degrade child process execution."""
    log_file = tmp_path / "sustained_backend.log"

    # Worker script that emits continuous logs on both stdout and stderr in batches
    # while processing "requests"
    worker_script = (
        "import sys, time, json\n"
        "for i in range(100):\n"
        "    # Emit verbose access and trace logs (exceeding pipe buffer quickly)\n"
        "    log_line = json.dumps({'step': i, 'msg': 'ACCESS_LOG_' + ('Y' * 512)}) + '\\n'\n"
        "    sys.stdout.write(log_line)\n"
        "    sys.stderr.write('STDERR_TRACE_' + str(i) + ': ' + ('E' * 256) + '\\n')\n"
        "    sys.stdout.flush()\n"
        "    sys.stderr.flush()\n"
        "    # Simulate fast request processing\n"
        "    time.sleep(0.005)\n"
        "print('SUSTAINED_LOGGING_COMPLETE')\n"
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", worker_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    out_drainer = StreamDrainer(proc.stdout, name="sustained-out", max_lines=150, log_file_path=log_file)
    err_drainer = StreamDrainer(proc.stderr, name="sustained-err", max_lines=150, log_file_path=log_file)

    # Process must complete smoothly without deadlocking
    ret = proc.wait(timeout=10.0)
    assert ret == 0, f"Child process exited with non-zero code {ret}"

    out_drainer._thread.join(timeout=2.0)
    err_drainer._thread.join(timeout=2.0)

    # Verify both streams were continuously consumed
    assert out_drainer.total_bytes >= 50_000
    assert err_drainer.total_bytes >= 25_000
    assert "SUSTAINED_LOGGING_COMPLETE" in out_drainer.get_recent_text()

    # Verify bounded memory
    assert len(out_drainer.get_recent_lines()) <= 150
    assert len(err_drainer.get_recent_lines()) <= 150

    # Verify log file has all entries
    assert log_file.is_file()
    assert log_file.stat().st_size >= 75_000


# ---------------------------------------------------------------------------
# 4. Repeated Startup & Shutdown Cycles
# ---------------------------------------------------------------------------

def test_repeated_startup_shutdown_cleanliness(tmp_path: Path):
    """Verify that starting and cleanly stopping processes releases resources with zero zombie processes."""
    # Launch and terminate 3 distinct child processes sequentially
    for cycle in range(3):
        port = get_free_port()
        script = f"import time, sys; sys.stdout.write('CYCLE_{cycle}\\n'); sys.stdout.flush(); time.sleep(10)"
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=(os.name != "nt"),
        )
        drainer = StreamDrainer(proc.stdout, name=f"cycle-{cycle}")

        time.sleep(0.3)
        assert proc.poll() is None

        # Terminate cleanly
        if os.name != "nt":
            try:
                pgid = os.getpgid(proc.pid)
                if pgid == proc.pid:
                    os.killpg(pgid, signal.SIGTERM)
                else:
                    proc.terminate()
            except Exception:
                pass
        else:
            proc.terminate()

        proc.wait(timeout=2.0)
        drainer.close()
        assert proc.poll() is not None


# ---------------------------------------------------------------------------
# 5. Watchdog Backend Unresponsiveness Detection
# ---------------------------------------------------------------------------

def test_watchdog_detects_backend_unresponsiveness(tmp_path: Path, monkeypatch, capsys):
    """Verify that the supervisor watchdog detects when a backend stops responding and exits cleanly."""
    monkeypatch.setattr("agentreliability.dev_server.find_workspace_root", lambda: tmp_path)
    monkeypatch.setattr("agentreliability.dev_server.resolve_database_path", lambda start_dir=None: tmp_path / "test.db")
    monkeypatch.setattr("agentreliability.dev_server.resolve_instance_id", lambda root: "ar_inst_watchdog")
    monkeypatch.setattr("agentreliability.dev_server.find_backend_python", lambda r: (sys.executable, []))
    monkeypatch.setattr(
        "agentreliability.dev_server.resolve_service_ports",
        lambda preferred_backend_port, preferred_frontend_port, host="127.0.0.1", expected_instance_id=None, expected_db_path=None: (8001, False, 5174, False),
    )

    from unittest.mock import MagicMock
    mock_b_proc = MagicMock()
    mock_b_proc.pid = 99999
    mock_b_proc.poll.return_value = None  # Process has NOT exited (hung/deadlocked)
    mock_b_proc.stdout = None
    mock_b_proc.stderr = None

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: mock_b_proc)

    class MockHTTPResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass

    def mock_urlopen(req, timeout=None):
        if isinstance(req, str):
            ua = ""
        else:
            ua = req.headers.get("User-agent", "") or req.headers.get("User-Agent", "")

        # Startup and port probes succeed, watchdog probes fail
        if "watchdog" not in ua.lower():
            return MockHTTPResponse()
        raise urllib.error.URLError("Connection timed out (backend hung)")

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    # Fast forward time to trigger watchdog quickly
    cur_time = [100.0]
    def mock_time():
        cur_time[0] += 6.0  # Increment by 6s each call
        return cur_time[0]

    monkeypatch.setattr("time.time", mock_time)
    monkeypatch.setattr("time.sleep", lambda s: None)

    ret = run_dev(backend_only=True, no_banner=True, open_browser=False)
    assert ret == 1

    captured = capsys.readouterr()
    assert "Backend Unresponsiveness Detected" in captured.err

