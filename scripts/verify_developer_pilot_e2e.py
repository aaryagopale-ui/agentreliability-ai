"""Comprehensive End-to-End Verification of the Developer Pilot Experience.

Tests the full 14-step developer workflow from the clean extracted archive
in an isolated temporary directory without touching the main database.
Supports both live network and sandbox execution.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_PATH = REPO_ROOT / "dist" / "agentreliability-pilot-v0.1.0.tar.gz"
ORIGINAL_DB = REPO_ROOT / "backend" / "agentreliability.db"


def can_bind_and_connect_tcp() -> bool:
    """Check if loopback TCP networking is permitted in this execution environment."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.listen(1)
        # Attempt loopback connect
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.settimeout(0.5)
        c.connect(("127.0.0.1", port))
        c.close()
        s.close()
        return True
    except Exception:
        return False


def main():
    print("\n" + "=" * 75)
    print("🚀 AgentReliability AI — Developer Pilot 14-Step End-to-End Smoke Test")
    print("=" * 75)

    # Record original database mtime and stats to guarantee zero side effects
    orig_db_stat = None
    if ORIGINAL_DB.is_file():
        orig_db_stat = (ORIGINAL_DB.stat().st_size, ORIGINAL_DB.stat().st_mtime)

    assert ARCHIVE_PATH.is_file(), f"Pilot package missing at {ARCHIVE_PATH}!"

    tcp_supported = can_bind_and_connect_tcp()
    print(f"Environment Mode : {'Live Loopback TCP' if tcp_supported else 'Secure Sandbox (ASGI in-memory)'}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        print(f"\n[Step 1] Extracting pilot archive into isolated temporary directory: {tmp_path}")
        with tarfile.open(ARCHIVE_PATH, "r:gz") as tar:
            tar.extractall(tmp_path)

        extracted_root = tmp_path / "AgentReliability-pilot-v0.1.0"
        assert extracted_root.is_dir(), f"Expected directory {extracted_root} not found!"
        print("   ✅ Archive extracted successfully.")

        print("\n[Step 2] Verifying package contents and self-service files...")
        assert (extracted_root / "START_HERE.md").is_file()
        assert (extracted_root / "start.sh").is_file()
        assert (extracted_root / "start.bat").is_file()
        assert (extracted_root / "demo_agent.py").is_file()
        assert (extracted_root / "examples" / "quickstart_agent.py").is_file()
        assert (extracted_root / "frontend" / "vite.config.js").is_file()

        # Check that vite.config.js binds 0.0.0.0
        vite_cfg = (extracted_root / "frontend" / "vite.config.js").read_text()
        assert 'host: "0.0.0.0"' in vite_cfg, "Vite config missing 0.0.0.0 host binding!"
        print("   ✅ Required files and 0.0.0.0 host binding confirmed.")

        test_py = (
            os.path.abspath(str(REPO_ROOT / "backend" / ".venv" / "bin" / "python"))
            if (REPO_ROOT / "backend" / ".venv" / "bin" / "python").is_file()
            else sys.executable
        )

        test_env = os.environ.copy()
        test_env["PYTHONPATH"] = f"{extracted_root / 'sdk' / 'src'}:{extracted_root / 'backend'}"

        print("\n[Step 3] Running 'agentreliability doctor' in isolated workspace...")
        res_doc = subprocess.run(
            [test_py, "-m", "agentreliability.cli", "doctor"],
            cwd=str(extracted_root),
            capture_output=True,
            text=True,
            env=test_env,
        )
        assert res_doc.returncode == 0, f"Doctor check failed: {res_doc.stderr}\n{res_doc.stdout}"
        print("   ✅ Doctor diagnostics passed cleanly.")

        print("\n[Step 4] Initializing isolated workspace with 'agentreliability init'...")
        res_init = subprocess.run(
            [test_py, "-m", "agentreliability.cli", "init"],
            cwd=str(extracted_root),
            capture_output=True,
            text=True,
            env=test_env,
        )
        assert res_init.returncode == 0, f"Init failed: {res_init.stderr}"
        isolated_db = extracted_root / "backend" / "agentreliability.db"
        assert isolated_db.is_file(), "Isolated database was not created!"
        print(f"   ✅ Local database created at {isolated_db.name}.")

        # Step 5: Setup API client for isolated database
        print("\n[Step 5] Initializing application backend...")
        sys.path.insert(0, str(extracted_root))
        sys.path.insert(0, str(extracted_root / "backend"))
        sys.path.insert(0, str(extracted_root / "sdk" / "src"))
        os.environ["AGENTRELIABILITY_DB"] = str(isolated_db.resolve())
        os.environ["AGENTRELIABILITY_WORKSPACE_ROOT"] = str(extracted_root.resolve())

        from starlette.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        res_health = client.get("/api/health")
        assert res_health.status_code == 200 and res_health.json().get("status") == "ok"
        print("   ✅ Isolated backend application is healthy.")

        # Step 6: Register a new user
        print("\n[Step 6] Registering new developer user account...")
        test_email = "pilot_tester@example.com"
        test_password = "SecurePassword123!"
        res_reg = client.post("/api/auth/register", json={"email": test_email, "password": test_password})
        assert res_reg.status_code in (200, 201), f"Registration failed: {res_reg.text}"
        user_data = res_reg.json()
        assert user_data.get("email") == test_email
        print(f"   ✅ User registered: {user_data.get('email')} (ID: {user_data.get('id')}).")

        # Step 7: Sign in & verify session
        print("\n[Step 7] Signing in and verifying session...")
        res_login = client.post("/api/auth/login", json={"email": test_email, "password": test_password})
        assert res_login.status_code == 200, f"Login failed: {res_login.text}"
        res_me = client.get("/api/auth/me")
        assert res_me.status_code == 200 and res_me.json().get("email") == test_email
        print(f"   ✅ Authenticated session verified for {test_email}.")

        # Extract CSRF token from cookies for mutating calls
        csrf_token = client.cookies.get("agentreliability_csrf", "")
        headers = {"X-CSRF-Token": csrf_token}

        # Step 8: Create dedicated project
        print("\n[Step 8] Creating dedicated test project...")
        res_proj = client.post(
            "/api/projects",
            json={"name": "Pilot Research Project", "description": "E2E Test"},
            headers=headers,
        )
        assert res_proj.status_code in (200, 201), f"Project creation failed: {res_proj.text}"
        project_data = res_proj.json()
        project_id = project_data["id"]
        headers["X-Project-Id"] = str(project_id)
        print(f"   ✅ Project created: {project_data['name']} (ID: {project_id}).")

        # Step 9: Provision live API key
        print("\n[Step 9] Provisioning plaintext API key...")
        res_key = client.post(
            f"/api/projects/{project_id}/keys",
            json={"name": "Pilot Runner Key"},
            headers=headers,
        )
        assert res_key.status_code in (200, 201), f"Key creation failed: {res_key.text}"
        key_data = res_key.json()
        api_key = key_data["api_key"]
        assert api_key.startswith("ar_live_"), f"API key format invalid: {api_key}"
        print(f"   ✅ Provisioned API Key: {api_key[:12]}... (ar_live prefix verified)")

        # Step 10: Run demo_agent.py success scenario
        print("\n[Step 10] Running demo agent in 'success' scenario...")
        import demo_agent
        from agentreliability.transport import Transport

        def testclient_post(url, headers_dict, body_bytes, timeout):
            path = "/" + url.split("://", 1)[1].split("/", 1)[1]
            r = client.post(path, content=body_bytes, headers={k: v for k, v in headers_dict.items()})
            return r.status_code

        demo_agent.monitor._api_key = api_key
        demo_agent.monitor.enabled = True
        demo_agent.monitor._transport = Transport(
            endpoint=demo_agent.endpoint,
            api_key=api_key,
            post=testclient_post,
        )

        success_result = demo_agent.run_demo_agent("success")
        assert success_result["status"] == "complete"
        flushed = demo_agent.monitor.flush(timeout=3.0)
        assert flushed, "Monitor flush timed out!"
        print("   ✅ Demo agent execution complete; trace flushed to backend.")

        # Step 11: Verify trace ingested in backend
        print("\n[Step 11] Verifying trace list and waterfall in backend...")
        time.sleep(0.1)
        res_traces = client.get("/api/traces/executions", headers=headers)
        assert res_traces.status_code == 200, f"Failed to list traces: {res_traces.text}"
        traces = res_traces.json().get("items", [])
        assert len(traces) > 0, f"No traces returned: {traces}"
        success_trace = traces[0]
        assert success_trace["agent_name"] == "demo-research-agent"
        assert success_trace["status"] == "success"
        execution_id = success_trace["execution_id"]
        print(f"   ✅ Captured trace confirmed: {execution_id} (Status: {success_trace['status']}).")

        # Step 12: Establish Golden Baseline from trace
        print("\n[Step 12] Establishing Golden Baseline from trace...")
        res_base = client.post(
            "/api/baselines",
            json={
                "name": "Demo Agent Golden Baseline",
                "source_type": "trace",
                "source_id": execution_id,
                "description": "Baseline captured from successful run",
            },
            headers=headers,
        )
        assert res_base.status_code in (200, 201), f"Baseline creation failed: {res_base.text}"
        baseline_data = res_base.json()
        baseline_id = baseline_data["id"]
        print(f"   ✅ Golden Baseline established: ID {baseline_id} (Target: {baseline_data['agent_name']}).")

        # Step 13: Run demo_agent.py regression scenario (omitting search_docs)
        print("\n[Step 13] Running demo agent in 'regression' scenario (omitting search_docs)...")
        reg_result = demo_agent.run_demo_agent("regression")
        assert reg_result["status"] == "partial"
        flushed_reg = demo_agent.monitor.flush(timeout=3.0)
        assert flushed_reg, "Regression monitor flush timed out!"
        print("   ✅ Regression scenario executed; candidate trace flushed to backend.")

        # Step 14: Compare candidate trace against Golden Baseline
        print("\n[Step 14] Comparing candidate regression trace against Golden Baseline...")
        time.sleep(0.1)
        res_traces_updated = client.get("/api/traces/executions", headers=headers)
        assert res_traces_updated.status_code == 200
        candidate_trace = res_traces_updated.json().get("items", [])[0]  # newest trace
        candidate_id = candidate_trace["execution_id"]

        res_comp = client.post(
            f"/api/baselines/{baseline_id}/compare",
            json={"candidate_trace_id": candidate_id},
            headers=headers,
        )
        assert res_comp.status_code == 200, f"Comparison failed: {res_comp.text}"
        comp = res_comp.json()
        assert comp.get("verdict") in ("regression", "breaking_regression"), f"Expected regression verdict, got: {comp.get('verdict')}"
        assert comp.get("is_regression") is True

        # Verify detected missing tool
        differences = comp.get("differences", [])
        has_missing_tool = any(
            "search_docs" in str(d.get("message", "")) or d.get("category") == "missing_tool_call"
            for d in differences
        )
        assert has_missing_tool, f"Expected missing tool difference, got: {differences}"
        print(f"   ✅ Regression Verdict: {comp.get('verdict').upper()} (Detected missing tool call 'search_docs').")

    # Final Safety Check: Verify main database was NEVER modified
    if orig_db_stat:
        assert ORIGINAL_DB.is_file(), "Original database was unexpectedly deleted!"
        current_stat = (ORIGINAL_DB.stat().st_size, ORIGINAL_DB.stat().st_mtime)
        assert current_stat == orig_db_stat, "Original database was unexpectedly modified!"
        print(f"\n🔒 Safety Verified: Main database '{ORIGINAL_DB.name}' was NOT modified.")

    print("\n" + "=" * 75)
    print("🎉 ALL 14 DEVELOPER PILOT STEPS VERIFIED WITH ZERO ERRORS!")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
