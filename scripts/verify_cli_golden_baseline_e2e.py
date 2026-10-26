#!/usr/bin/env python3
"""End-to-end local verification of AgentReliability CLI Golden Baseline comparison.

Executes real agent tracing via the SDK, saves a Golden Baseline, executes CLI comparisons
for matching and regressed traces, verifies multi-tenant isolation, and checks dashboard visibility.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
SDK_SRC = ROOT_DIR / "sdk" / "src"
CLI_BIN = str(BACKEND_DIR / ".venv" / "bin" / "agentreliability")

# Ensure imports resolve
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SDK_SRC))

from app import baseline_store, database, project_store, trace_store
from agentreliability import AgentMonitor
from agentreliability.monitor import _current

BACKEND_URL = "http://127.0.0.1:8001"
AGENT_NAME = "customer_triage_e2e_agent"


def run_e2e_verification():
    print("=" * 70)
    print("🚀 AgentReliability CLI Golden Baseline E2E Local Verification")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # STEP 1: Check backend health on port 8001 (do not touch port 8000)
    # -------------------------------------------------------------------------
    print("\n--- Step 1: Checking Backend Health at http://127.0.0.1:8001 ---")
    health_url = f"{BACKEND_URL}/api/health"
    try:
        with urllib.request.urlopen(health_url, timeout=3.0) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("status") == "ok", f"Unexpected health status: {data}"
            print("  ✅ Backend is healthy and running on port 8001.")
    except Exception as exc:
        print(f"  ❌ Backend unreachable at {health_url}: {exc}", file=sys.stderr)
        sys.exit(1)

    # -------------------------------------------------------------------------
    # STEP 2: Dedicated Test Project & Secure Authentication
    # -------------------------------------------------------------------------
    print("\n--- Step 2: Preparing Dedicated Test Projects & API Keys ---")
    owner_id = 2  # Existing developer account
    project_name = "CLI E2E Golden Baseline Verification"
    unauth_project_name = "CLI E2E Unauthorized Project"

    # Find or create primary dedicated project
    with database.connect() as conn:
        row = conn.execute("SELECT id, name FROM projects WHERE name = ?", (project_name,)).fetchone()
        if row:
            project_id = row[0]
            print(f"  ✓ Using existing test project: '{project_name}' (ID: {project_id})")
        else:
            proj_dict, _ = project_store.create_project(name=project_name, owner_id=owner_id)
            project_id = proj_dict["id"]
            print(f"  ✓ Created dedicated test project: '{project_name}' (ID: {project_id})")

        # Create/obtain fresh API key for the test project (key value kept secret)
        _, raw_primary_key = project_store.create_api_key(project_id, name="E2E Primary Key")
        assert raw_primary_key.startswith("ar_"), "Valid API key generated"
        print("  ✓ Created valid project API key [ar_***] (not printed)")

        # Find or create unauthorized second project for isolation verification
        unauth_row = conn.execute("SELECT id, name FROM projects WHERE name = ?", (unauth_project_name,)).fetchone()
        if unauth_row:
            unauth_project_id = unauth_row[0]
            print(f"  ✓ Using existing unauthorized project: '{unauth_project_name}' (ID: {unauth_project_id})")
        else:
            unauth_proj_dict, _ = project_store.create_project(name=unauth_project_name, owner_id=owner_id)
            unauth_project_id = unauth_proj_dict["id"]
            print(f"  ✓ Created unauthorized project: '{unauth_project_name}' (ID: {unauth_project_id})")

        _, raw_unauth_key = project_store.create_api_key(unauth_project_id, name="E2E Unauth Key")
        assert raw_unauth_key.startswith("ar_"), "Valid unauthorized API key generated"
        print("  ✓ Created secondary project API key [ar_***] for cross-project isolation tests")

    # -------------------------------------------------------------------------
    # STEP 3: Capture Successful Agent Trace (Trace 1 - Golden Source)
    # -------------------------------------------------------------------------
    print("\n--- Step 3: Capturing Golden Source Agent Trace via SDK ---")
    monitor = AgentMonitor(
        endpoint=BACKEND_URL,
        api_key=raw_primary_key,
        capture_io=True,
        metadata={"env": "e2e_test", "suite": "golden_baseline"},
    )

    captured_exec_ids = []

    @monitor.trace_tool("parse_customer_intent")
    def tool_intent(query: str) -> dict:
        cur = _current.get()
        if cur and cur.execution_id not in captured_exec_ids:
            captured_exec_ids.append(cur.execution_id)
        time.sleep(0.01)
        return {"intent": "order_lookup", "confidence": 0.98}

    @monitor.trace_tool("fetch_order_records")
    def tool_fetch_order(order_id: str) -> dict:
        time.sleep(0.015)
        return {"order_id": order_id, "status": "shipped", "tracking": "TRK-88123"}

    @monitor.trace_tool("format_triage_summary")
    def tool_format_summary(intent_data: dict, order_data: dict) -> dict:
        time.sleep(0.005)
        return {
            "ticket_status": "resolved",
            "summary": f"Order {order_data['order_id']} is {order_data['status']}.",
            "resolution_code": "NOTIFY_CUSTOMER",
        }

    @monitor.trace_agent(AGENT_NAME)
    def run_support_agent(order_id: str, query: str) -> dict:
        intent = tool_intent(query)
        order = tool_fetch_order(order_id)
        return tool_format_summary(intent, order)

    # Execute Golden Run (Trace 1)
    res_1 = run_support_agent("ORD-E2E-101", "Where is my order?")
    assert res_1["ticket_status"] == "resolved"
    assert monitor.flush(timeout=5.0), "SDK flush failed"

    # Wait briefly for background ingestion worker to persist
    time.sleep(0.5)

    trace_1_id = captured_exec_ids[-1]
    t1_record = trace_store.get_execution(trace_1_id, project_id=project_id)
    assert t1_record is not None, f"Trace 1 ({trace_1_id}) was not ingested into project {project_id}!"
    assert t1_record["status"] == "success"
    assert len(t1_record["tool_calls"]) == 3
    print(f"  ✅ Golden source trace captured: ID '{trace_1_id}'")
    print(f"     Tools called: {[t['tool_name'] for t in t1_record['tool_calls']]}")
    print(f"     Status: {t1_record['status']}, Duration: {t1_record['duration_ms']:.1f}ms")

    # -------------------------------------------------------------------------
    # STEP 4: Create Golden Baseline from Trace 1
    # -------------------------------------------------------------------------
    print("\n--- Step 4: Creating Golden Baseline on Backend ---")
    tool_sequence = [t["tool_name"] for t in t1_record["tool_calls"]]
    expected_rules = {
        "status": "success",
        "tool_sequence": tool_sequence,
        "final_output": t1_record["output"],
        "strict_order": True,
        "allow_additional_tools": False,
        "max_duration_ms": round(t1_record["duration_ms"] * 2.0, 2),
    }

    baseline_record = baseline_store.create_baseline(
        project_id=project_id,
        agent_name=AGENT_NAME,
        name="Customer Triage Golden Baseline",
        description="Golden baseline for customer support triage workflow",
        source_type="trace",
        source_id=trace_1_id,
        status="success",
        duration_ms=t1_record["duration_ms"],
        input_val=t1_record.get("input"),
        output_val=t1_record.get("output"),
        tools=t1_record.get("tool_calls", []),
        expected=expected_rules,
        user_id=owner_id,
    )
    baseline_id = baseline_record["id"]
    print(f"  ✅ Golden Baseline created: ID {baseline_id} (Version 1 locked)")
    print(f"     Agent: {AGENT_NAME}")
    print(f"     Expected tool sequence: {tool_sequence}")

    # -------------------------------------------------------------------------
    # STEP 5 & 6: Capture Matching Trace (Trace 2) & Run CLI compare (Expect Exit Code 0)
    # -------------------------------------------------------------------------
    print("\n--- Step 5: Capturing Matching Candidate Trace (Trace 2) ---")
    res_2 = run_support_agent("ORD-E2E-102", "Check delivery status for my order")
    assert res_2["ticket_status"] == "resolved"
    assert monitor.flush(timeout=5.0), "SDK flush failed"
    time.sleep(0.5)

    trace_2_id = captured_exec_ids[-1]
    t2_record = trace_store.get_execution(trace_2_id, project_id=project_id)
    assert t2_record is not None, f"Trace 2 ({trace_2_id}) not found"
    print(f"  ✅ Matching trace captured: ID '{trace_2_id}'")

    print("\n--- Step 6: Running 'agentreliability compare' on Matching Trace ---")
    # Subprocess execution of the CLI
    cli_cmd_match = [
        CLI_BIN, "compare",
        "--trace", trace_2_id,
        "--baseline-id", str(baseline_id),
        "--endpoint", BACKEND_URL,
        "--api-key", raw_primary_key,
    ]
    p_match = subprocess.run(cli_cmd_match, capture_output=True, text=True)
    print("CLI Output (Matching Run):")
    print(p_match.stdout)
    if p_match.stderr:
        print("CLI Stderr:", p_match.stderr)

    assert p_match.returncode == 0, f"Expected exit code 0 for matching comparison, got {p_match.returncode}"
    assert "PASSED - Matches Golden Baseline" in p_match.stdout
    assert "0 breaking" in p_match.stdout
    print("  ✅ CLI Comparison PASSED with exit code 0.")

    # Also test CLI automatic baseline resolution via --agent
    print("\n--- Testing Automatic Baseline Discovery via --agent ---")
    cli_cmd_agent = [
        CLI_BIN, "compare",
        "--trace", trace_2_id,
        "--agent", AGENT_NAME,
        "--endpoint", BACKEND_URL,
        "--api-key", raw_primary_key,
    ]
    p_agent = subprocess.run(cli_cmd_agent, capture_output=True, text=True)
    assert p_agent.returncode == 0, f"Expected exit code 0 for --agent lookup, got {p_agent.returncode}"
    assert "PASSED - Matches Golden Baseline" in p_agent.stdout
    print("  ✅ CLI auto-resolved baseline by agent name with exit code 0.")

    # -------------------------------------------------------------------------
    # STEP 7 & 8: Capture Deliberately Regressed Trace (Trace 3) & Run CLI compare (Expect Exit Code 1)
    # -------------------------------------------------------------------------
    print("\n--- Step 7: Capturing Deliberately Regressed Trace (Missing Tool Call) ---")
    # Define regressed execution that skips 'fetch_order_records'
    @monitor.trace_agent(AGENT_NAME)
    def run_regressed_agent(order_id: str, query: str) -> dict:
        intent = tool_intent(query)
        # BUG: Simulated regression - tool_fetch_order was omitted!
        mock_order = {"order_id": order_id, "status": "unknown"}
        return tool_format_summary(intent, mock_order)

    res_3 = run_regressed_agent("ORD-E2E-103", "Order inquiry bugged")
    assert monitor.flush(timeout=5.0), "SDK flush failed"
    time.sleep(0.5)

    trace_3_id = captured_exec_ids[-1]
    t3_record = trace_store.get_execution(trace_3_id, project_id=project_id)
    assert t3_record is not None, f"Trace 3 ({trace_3_id}) not found"
    t3_tools = [t["tool_name"] for t in t3_record["tool_calls"]]
    print(f"  ✅ Regressed trace captured: ID '{trace_3_id}'")
    print(f"     Observed tools: {t3_tools} (Missing 'fetch_order_records')")

    print("\n--- Step 8: Running 'agentreliability compare' on Regressed Trace ---")
    cli_cmd_regress = [
        CLI_BIN, "compare",
        "--trace", trace_3_id,
        "--baseline-id", str(baseline_id),
        "--endpoint", BACKEND_URL,
        "--api-key", raw_primary_key,
    ]
    p_regress = subprocess.run(cli_cmd_regress, capture_output=True, text=True)
    print("CLI Output (Regressed Run):")
    print(p_regress.stdout)
    if p_regress.stderr:
        print("CLI Stderr:", p_regress.stderr)

    assert p_regress.returncode == 1, f"Expected exit code 1 for regression, got {p_regress.returncode}"
    assert "❌ Result: REGRESSION DETECTED (Exit code 1)" in p_regress.stdout
    assert "❌ [BREAKING]" in p_regress.stdout
    assert "fetch_order_records" in p_regress.stdout
    print("  ✅ CLI correctly detected breaking regression with exit code 1.")

    # -------------------------------------------------------------------------
    # STEP 9: Cross-Project Isolation Verification (Unauthorized Access)
    # -------------------------------------------------------------------------
    print("\n--- Step 9: Verifying Multi-Tenant Isolation (Unauthorized Project) ---")
    cli_cmd_unauth = [
        CLI_BIN, "compare",
        "--trace", trace_2_id,
        "--baseline-id", str(baseline_id),
        "--endpoint", BACKEND_URL,
        "--api-key", raw_unauth_key,  # Belongs to unauth_project_id, NOT project_id
    ]
    p_unauth = subprocess.run(cli_cmd_unauth, capture_output=True, text=True)
    print("CLI Output (Unauthorized Run):")
    print("Stdout:", p_unauth.stdout.strip())
    print("Stderr:", p_unauth.stderr.strip())

    assert p_unauth.returncode == 1, f"Expected exit code 1 for unauthorized project, got {p_unauth.returncode}"
    assert "Baseline not found" in p_unauth.stderr or "not found in active project" in p_unauth.stderr, (
        f"Expected 404 project boundary error, got: {p_unauth.stderr}"
    )
    print("  ✅ Cross-project isolation verified: Unauthorized project cannot access foreign baseline/traces.")

    # -------------------------------------------------------------------------
    # STEP 10: Confirm Dashboard & API Visibility
    # -------------------------------------------------------------------------
    print("\n--- Step 10: Confirming Dashboard / Backend API Visibility ---")
    # Verify baseline is listed under GET /api/v1/baselines
    req_baselines = urllib.request.Request(
        f"{BACKEND_URL}/api/v1/baselines?agent_name={AGENT_NAME}",
        headers={"X-API-Key": raw_primary_key},
        method="GET",
    )
    with urllib.request.urlopen(req_baselines, timeout=3.0) as resp:
        assert resp.status == 200
        baselines_list = json.loads(resp.read().decode("utf-8"))
        matched_b = [b for b in baselines_list if b["id"] == baseline_id]
        assert len(matched_b) == 1, f"Baseline {baseline_id} not visible in GET /api/v1/baselines"
        print(f"  ✓ Dashboard API lists Golden Baseline ID {baseline_id} for agent '{AGENT_NAME}'")

    # Verify trace executions are stored and visible
    traces = trace_store.list_executions(project_id=project_id, agent=AGENT_NAME)["items"]
    trace_ids_in_store = {t["execution_id"] for t in traces}
    assert trace_1_id in trace_ids_in_store, f"Trace 1 ({trace_1_id}) missing from store"
    assert trace_2_id in trace_ids_in_store, f"Trace 2 ({trace_2_id}) missing from store"
    assert trace_3_id in trace_ids_in_store, f"Trace 3 ({trace_3_id}) missing from store"
    print(f"  ✓ All 3 test traces are persisted in trace store (Total {len(traces)} traces for agent)")

    print("\n" + "=" * 70)
    print("🎉 ALL 10 E2E LOCAL VERIFICATION STEPS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_e2e_verification()
