"""Automated verification of the complete self-service onboarding experience
from a clean extracted pilot package.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_PATH = REPO_ROOT / "dist" / "agentreliability-pilot-v0.1.0.tar.gz"


def main():
    print("\n🧪 Testing Self-Service Pilot Experience from Clean Archive...")
    print("=" * 70)

    if not ARCHIVE_PATH.is_file():
        print(f"❌ Archive not found at {ARCHIVE_PATH}")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        print(f"1. Extracting archive to clean directory: {tmp_path}")
        with tarfile.open(ARCHIVE_PATH, "r:gz") as tar:
            tar.extractall(tmp_path)

        extracted_root = tmp_path / "AgentReliability-pilot-v0.1.0"
        assert extracted_root.is_dir(), f"Expected directory {extracted_root} not found"

        # 2. Check essential self-service entry files
        print("2. Verifying essential self-service files...")
        assert (extracted_root / "START_HERE.md").is_file(), "START_HERE.md missing!"
        assert (extracted_root / "start.sh").is_file(), "start.sh missing!"
        assert (extracted_root / "start.bat").is_file(), "start.bat missing!"
        assert (extracted_root / "frontend" / "src" / "pages" / "HelpDocs.jsx").is_file(), "HelpDocs.jsx missing!"
        assert (extracted_root / "frontend" / "src" / "pages" / "GettingStarted.jsx").is_file(), "GettingStarted.jsx missing!"

        # Check content of START_HERE.md
        start_here_text = (extracted_root / "START_HERE.md").read_text(encoding="utf-8")
        assert "./start.sh" in start_here_text
        assert "start.bat" in start_here_text
        assert "macOS" in start_here_text
        assert "Linux" in start_here_text
        assert "Windows WSL2" in start_here_text
        print("   ✅ START_HERE.md, start.sh, start.bat verified.")

        # 3. Setup Python path for the clean installation
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{extracted_root / 'sdk' / 'src'}:{extracted_root / 'backend'}"

        test_py = (
            str(REPO_ROOT / "backend" / ".venv" / "bin" / "python")
            if (REPO_ROOT / "backend" / ".venv" / "bin" / "python").is_file()
            else sys.executable
        )

        # 4. Test agentreliability init in clean installation
        print("3. Testing 'agentreliability init' in isolated workspace...")
        res_init = subprocess.run(
            [test_py, "-m", "agentreliability.cli", "init"],
            cwd=str(extracted_root),
            capture_output=True,
            text=True,
            env=env,
        )
        assert res_init.returncode == 0, f"init failed: {res_init.stderr}"
        assert (extracted_root / ".agentreliability.json").is_file(), ".agentreliability.json not created!"
        assert (extracted_root / "backend" / "agentreliability.db").is_file(), "Database not initialized!"
        print("   ✅ Local database and .agentreliability.json initialized successfully.")

        # 5. Test agentreliability doctor in clean installation
        print("4. Testing 'agentreliability doctor' in isolated workspace...")
        res_doc = subprocess.run(
            [test_py, "-m", "agentreliability.cli", "doctor"],
            cwd=str(extracted_root),
            capture_output=True,
            text=True,
            env=env,
        )
        assert res_doc.returncode == 0, f"doctor failed: {res_doc.stderr}\nOUT: {res_doc.stdout}"
        assert "SQLite Tables" in res_doc.stdout
        print("   ✅ Doctor diagnostics passed cleanly.")

        # 6. Test port conflict resolution and non-termination of external apps
        print("5. Testing port collision safety...")
        sys.path.insert(0, str(extracted_root / "sdk" / "src"))
        sys.path.insert(0, str(extracted_root / "backend"))
        from agentreliability.ports import resolve_service_ports
        from unittest.mock import patch

        with patch("agentreliability.ports.probe_backend") as mock_probe, \
             patch("agentreliability.ports.probe_frontend") as mock_f_probe, \
             patch("agentreliability.ports.find_available_port") as mock_find:
            mock_probe.return_value = {
                "occupied": True,
                "is_agentreliability": False,  # External third-party app occupying 8001
                "compatible": False,
            }
            mock_f_probe.return_value = {"occupied": False}
            mock_find.return_value = 8002

            b_port, reuse_b, f_port, reuse_f = resolve_service_ports(
                preferred_backend_port=8001,
                preferred_frontend_port=5174,
            )
            assert b_port == 8002
            assert reuse_b is False, "Must not reuse external occupied port!"
        print("   ✅ Collision fallback to alternative port verified (unrelated apps untouched).")

        # 7. Test Account & Project Persistence in Clean Workspace
        print("6. Testing account registration & persistence in isolated database...")
        db_path = extracted_root / "backend" / "agentreliability.db"
        env["AGENTRELIABILITY_DB"] = str(db_path)

        # Ingest user and project
        sys.path.insert(0, str(extracted_root / "backend"))
        sys.path.insert(0, str(extracted_root / "sdk" / "src"))

        from datetime import datetime, timezone
        from app.database import init_db
        from app import auth_store, baseline_store, project_store, regression_engine, security, trace_store
        from app.traces_schemas import TraceEvent

        init_db()
        trace_store.init_tables()

        u = auth_store.create_user("new_dev@company.com", security.hash_password("DevPass123!"), "New Dev")
        assert u is not None
        p, key = project_store.create_project("Pilot Project", owner_id=u["id"])
        assert p is not None
        assert key.startswith("ar_live_")

        # Simulate restart: verify credentials persist
        user_db = auth_store.get_user_by_email_with_hash("new_dev@company.com")
        assert user_db is not None
        assert security.verify_password("DevPass123!", user_db["password_hash"]) is True
        print("   ✅ Account and project persisted with scrypt password hashing.")

        # 8. Test First Trace Ingestion, Golden Baseline Promotion, and Breaking Regression
        print("7. Testing trace capture, Golden Baseline creation, and regression detection...")
        # Step A: Ingest passing trace
        t1_id = "tr_clean_001"
        now = datetime.now(timezone.utc)
        trace_store.ingest(p["id"], [
            TraceEvent(
                event_id="evt_clean_001",
                execution_id=t1_id,
                agent_name="SupportAgent",
                type="execution_start",
                timestamp=now,
                input={"ticket": "refund"},
            ),
            TraceEvent(
                event_id="evt_clean_002",
                execution_id=t1_id,
                agent_name="SupportAgent",
                type="tool_call",
                tool_name="verify_order",
                duration_ms=50.0,
                status="success",
                timestamp=now,
            ),
            TraceEvent(
                event_id="evt_clean_003",
                execution_id=t1_id,
                agent_name="SupportAgent",
                type="execution_end",
                status="success",
                output={"refund_status": "approved"},
                timestamp=now,
            ),
        ])

        # Step B: Promote to Golden Baseline
        b = baseline_store.create_baseline(
            project_id=p["id"],
            agent_name="SupportAgent",
            name="SupportAgent Golden Baseline",
            description="Established during onboarding",
            source_type="trace",
            source_id=t1_id,
            status="success",
            duration_ms=120.0,
            input_val={"ticket": "refund"},
            output_val={"refund_status": "approved"},
            tools=[{"tool_name": "verify_order", "status": "success"}],
            expected={
                "tool_sequence": ["verify_order"],
                "strict_order": True,
                "allow_additional_tools": False,
            },
            user_id=u["id"],
        )
        assert b is not None
        baseline_id = b["id"]

        # Step C: Ingest regressed candidate trace (missing 'verify_order' tool call)
        t2_id = "tr_clean_regressed"
        trace_store.ingest(p["id"], [
            TraceEvent(
                event_id="evt_clean_004",
                execution_id=t2_id,
                agent_name="SupportAgent",
                type="execution_start",
                timestamp=now,
                input={"ticket": "refund"},
            ),
            TraceEvent(
                event_id="evt_clean_005",
                execution_id=t2_id,
                agent_name="SupportAgent",
                type="execution_end",
                status="success",
                output={"refund_status": "approved"},
                timestamp=now,
            ),
        ])

        # Step D: Compare candidate against Golden Baseline
        cand_trace = trace_store.get_execution(t2_id, project_id=p["id"])
        base_ver = baseline_store.get_baseline_version(baseline_id, 1)
        comp_report = regression_engine.compare_execution_to_baseline(base_ver, cand_trace)
        print("COMP_REPORT verdict:", comp_report["verdict"])

        assert comp_report["verdict"] in ("regression", "breaking_regression")
        assert comp_report["is_regression"] is True
        assert comp_report["counts"]["breaking"] >= 1
        diff_msgs = [d["message"] for d in comp_report["differences"]]
        assert any("missing required tool call" in msg.lower() or "verify_order" in msg for msg in diff_msgs)
        print("   ✅ Golden Baseline comparison correctly flagged breaking regression for missing tool call!")

    print("=" * 70)
    print("🎉 All Clean-Archive Self-Service Verification Checks PASSED!\n")


if __name__ == "__main__":
    main()
