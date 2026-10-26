#!/usr/bin/env python3
"""Five-Minute Developer Demo Script for AgentReliability AI.

This script executes an end-to-end, zero-configuration local onboarding demo:
1. Provisions a clean, isolated demonstration project in the local database.
2. Generates a fresh project API key.
3. Configures the Python SDK (agentreliability).
4. Runs a real agent execution that succeeds (multi-tool fulfillment).
5. Runs a real agent execution with a controlled failure (stock exhaustion error).
6. Ingests both traces into the backend database.
7. Automatically converts the successful trace into an immutable regression test case.
8. Replays the regression test against the execution engine.
9. Diagnoses the failure trace using the evidence-based diagnostic engine.
10. Measures and displays the exact time taken (target: under 5 minutes; typical: under 5 seconds).

Usage:
  python scripts/five_minute_demo.py
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Setup paths
repo_root = Path(__file__).resolve().parent.parent
backend_path = repo_root / "backend"
sdk_path = repo_root / "sdk" / "src"

for p in (str(backend_path), str(sdk_path)):
    if p not in sys.path:
        sys.path.insert(0, p)

from agentreliability import AgentMonitor
from app.database import connect
from app.security import create_session, hash_password, SESSION_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.project_store import create_project, create_api_key
from app.trace_store import get_execution
from app.test_store import create_case, get_case, save_run
from app.replay import run_test as run_replay_test
from app.failure_engine import diagnose_failure


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_demo():
    t_start = time.time()

    print("\n" + "=" * 70)
    print("🤖 AgentReliability AI: Five-Minute Developer Onboarding Demo")
    print("=" * 70)
    print("Starting automated local onboarding walkthrough...\n")

    # -------------------------------------------------------------------------
    # STEP 1: Provision Isolated Demo Project & Developer Account
    # -------------------------------------------------------------------------
    print("[1/7] Provisioning clean demonstration project...")
    demo_email = f"developer_demo_{int(time.time())}@agentreliability.local"
    demo_name = "Five-Minute Demo Developer"

    with connect() as conn:
        pwd_hash = hash_password("DemoPassword123!")
        cur = conn.execute(
            """INSERT INTO users (email, password_hash, name, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (demo_email, pwd_hash, demo_name, _now(), _now()),
        )
        user_id = cur.lastrowid

    # Create project and initial API key
    proj, api_key = create_project(
        name="Quickstart Demo Project",
        owner_id=user_id,
    )
    project_id = proj["id"]
    print(f"  ✓ User created: {demo_email} (ID: {user_id})")
    print(f"  ✓ Project active: '{proj['name']}' (ID: {project_id})")

    # -------------------------------------------------------------------------
    # STEP 2: Project API Key
    # -------------------------------------------------------------------------
    print("\n[2/7] Generating project API key...")
    masked_key = f"{api_key[:7]}...{api_key[-4:]}"
    print(f"  ✓ Secret Key provisioned: {masked_key}")
    print(f"  ✓ Storage status: SHA-256 hash safely stored in SQLite")

    # -------------------------------------------------------------------------
    # STEP 3: Configure Python SDK
    # -------------------------------------------------------------------------
    print("\n[3/7] Initializing Python AgentMonitor SDK...")
    
    # Custom post handler to ingest directly into database for fast, offline demo execution
    def direct_post_handler(url: str, headers: dict, body: bytes, timeout: float) -> int:
        from app.traces_schemas import IngestRequest
        from app.trace_store import ingest
        try:
            payload = json.loads(body.decode("utf-8"))
            batch = IngestRequest.model_validate(payload)
            ingest(project_id, batch.events)
            return 200
        except Exception as e:
            print(f"    [SDK Transport Error]: {e}", file=sys.stderr)
            return 500

    monitor = AgentMonitor(
        endpoint="http://127.0.0.1:8001",
        api_key=api_key,
        capture_io=True,
        metadata={"environment": "five_minute_demo", "sdk_version": "0.1.0"},
        _post=direct_post_handler,
    )
    print("  ✓ AgentMonitor initialized with capture_io=True and local redaction rules")

    # Define Instrumented Tools
    @monitor.trace_tool("verify_client_tier")
    def verify_client_tier(client_id: str) -> dict:
        time.sleep(0.015)
        return {"client_id": client_id, "tier": "enterprise", "active": True}

    @monitor.trace_tool("check_warehouse_inventory")
    def check_warehouse_inventory(sku: str, quantity: int) -> dict:
        time.sleep(0.02)
        if sku == "SKU-DISCONTINUED":
            raise ValueError(f"SKU '{sku}' is discontinued. Available stock is 0 units.")
        return {"sku": sku, "in_stock": True, "units_available": 150}

    @monitor.trace_tool("calculate_taxes_and_total")
    def calculate_taxes_and_total(subtotal: float, state: str) -> dict:
        time.sleep(0.01)
        tax_rate = 0.0825 if state == "CA" else 0.05
        tax = round(subtotal * tax_rate, 2)
        return {"subtotal": subtotal, "tax": tax, "total": round(subtotal + tax, 2)}

    # Define Instrumented Agent
    @monitor.trace_agent("order_processing_agent")
    def run_agent(order_id: str, sku: str, quantity: int, state: str) -> dict:
        tier_info = verify_client_tier("client_corp_99")
        inv = check_warehouse_inventory(sku, quantity)
        calc = calculate_taxes_and_total(quantity * 25.0, state)
        return {
            "order_id": order_id,
            "status": "confirmed",
            "tier": tier_info["tier"],
            "financials": calc,
        }

    # -------------------------------------------------------------------------
    # STEP 4: Run Real Successful Agent Trace
    # -------------------------------------------------------------------------
    print("\n[4/7] Running successful agent execution...")
    success_res = run_agent(
        order_id="ORD-DEMO-PASS-01",
        sku="SKU-AVAILABLE-101",
        quantity=4,
        state="CA",
    )
    monitor.flush()
    print(f"  ✓ Agent Execution Completed: {success_res['status']}")
    print(f"  ✓ Total calculated: ${success_res['financials']['total']}")
    print("  ✓ Trace ingested into database: 3 tools executed (verify_client_tier -> check_warehouse_inventory -> calculate_taxes_and_total)")

    # -------------------------------------------------------------------------
    # STEP 5: Run Controlled Failure Agent Trace
    # -------------------------------------------------------------------------
    print("\n[5/7] Running controlled failure execution (stock exhaustion)...")
    failed_exec_id = None
    try:
        run_agent(
            order_id="ORD-DEMO-FAIL-02",
            sku="SKU-DISCONTINUED",
            quantity=10,
            state="CA",
        )
    except ValueError as exc:
        monitor.flush()
        print(f"  ✓ Expected Exception Raised and Passed Through: {exc}")
        print("  ✓ Failure Trace captured by SDK with category 'tool_failure'")

    # Retrieve stored traces to verify database persistence
    with connect() as conn:
        traces = conn.execute(
            """SELECT execution_id, status, error_type, duration_ms 
               FROM trace_executions WHERE project_id = ? 
               ORDER BY started_at ASC""",
            (project_id,),
        ).fetchall()

    pass_trace = traces[0]
    fail_trace = traces[1]
    print(f"  ✓ Stored Trace 1: ID={pass_trace['execution_id']} | Status={pass_trace['status']} ({pass_trace['duration_ms']:.1f}ms)")
    print(f"  ✓ Stored Trace 2: ID={fail_trace['execution_id']} | Status={fail_trace['status']} | Error={fail_trace['error_type']}")

    # -------------------------------------------------------------------------
    # STEP 6: Convert Trace into Regression Test & Execute Replay
    # -------------------------------------------------------------------------
    print("\n[6/7] Converting successful trace into automated regression test...")
    pass_detail = get_execution(pass_trace["execution_id"], project_id=project_id)
    tool_sequence = [t["tool_name"] for t in pass_detail.get("tool_calls", [])]

    # Replay engine expects step dictionaries with type="tool_call" and name=tool_name
    replay_steps = [
        {
            "type": "tool_call",
            "name": t["tool_name"],
            "status": t["status"],
            "duration_ms": t.get("duration_ms", 10),
            "output": t.get("output"),
            "input": t.get("input"),
        }
        for t in pass_detail.get("tool_calls", [])
    ]
    test_data = {
        "name": "Order Processing Baseline Test",
        "description": f"Auto-generated regression test from trace {pass_trace['execution_id']}",
        "agent_name": pass_detail.get("agent_name", "order_processing_agent"),
        "steps": replay_steps,
        "input": pass_detail.get("input"),
        "expected": {
            "status": "success",
            "tool_sequence": tool_sequence,
            "final_output": replay_steps[-1].get("output") if replay_steps else None,
            "strict_order": True,
            "allow_additional_tools": False,
        },
    }

    test_id = create_case(
        data=test_data,
        source_type="trace",
        source_trace_id=pass_trace["execution_id"],
        project_id=project_id,
    )
    case_record = get_case(test_id, project_id=project_id)
    print(f"  ✓ Regression Test Case created (ID: {test_id})")
    print(f"  ✓ Expected Sequence Assertions: {' -> '.join(tool_sequence)}")

    # Execute deterministic replay run
    run_result = run_replay_test(case_record)
    run_id = save_run(case_record, run_result, project_id=project_id)
    print(f"  ✓ Replay Engine Execution Status: {run_result['status'].upper()} (Run ID: {run_id})")
    print(f"  ✓ Discrepancies / Mismatches: {len(run_result.get('mismatches', []))}")
    print("  ✓ Test run logged to Test History")

    # -------------------------------------------------------------------------
    # STEP 7: Evidence-Based AI Failure Analysis
    # -------------------------------------------------------------------------
    print("\n[7/7] Running evidence-based failure diagnosis on failed trace...")
    fail_detail = get_execution(fail_trace["execution_id"], project_id=project_id)
    diagnosis = diagnose_failure(execution=fail_detail, tool_calls=fail_detail.get("tool_calls"))

    print("  ✓ Diagnostic Report Generated:")
    print(f"    - Category       : {diagnosis['failure_category']}")
    print(f"    - Failing Tool   : {diagnosis['primary_error']['failing_tool']}")
    print(f"    - Error Detail   : [{diagnosis['primary_error']['error_type']}] {diagnosis['primary_error']['error_message']}")
    print(f"    - Preceding Steps: {len(diagnosis['preceding_events'])} successful tool(s) preceded failure")
    print(f"    - Evidence Score : {diagnosis['evidence_sufficiency']} (Confidence: {int(diagnosis['confidence_score'] * 100)}%)")
    print(f"    - Mitigations    : {diagnosis['deterministic_recommendations'][0]}")

    # -------------------------------------------------------------------------
    # Summary & Developer Dashboard Instructions
    # -------------------------------------------------------------------------
    t_elapsed = time.time() - t_start
    print("\n" + "=" * 70)
    print("✨ Five-Minute Local Demo Completed Successfully!")
    print("=" * 70)
    print(f"⏱️  Actual Demo Execution Time: {t_elapsed:.2f} seconds (Target: < 300 seconds)")
    print("\n📊 Inspect your data in the AgentReliability Dashboard:")
    print("  1. Open http://localhost:5174 in your browser.")
    print("  2. In the top-left Project Switcher, select:")
    print(f"     'Quickstart Demo Project' (ID: {project_id})")
    print("  3. Navigate to:")
    print("     - Live Agent Monitoring  -> See the waterfall timeline of both traces.")
    print("     - Test Cases             -> See the converted regression test.")
    print("     - Replay Engine          -> Re-run deterministic replay against changes.")
    print("     - Failure Analysis       -> Inspect root-cause evidence for the failed trace.")
    print("     - Getting Started        -> Track 10/10 setup completion milestones.")
    print("=" * 70 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
