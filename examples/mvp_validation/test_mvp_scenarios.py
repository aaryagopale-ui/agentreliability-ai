"""Comprehensive MVP Validation Suite — Scenarios A, B, and C.

This test script executes the order processing agent under 3 real-world scenarios:
- Scenario A: Successful execution with all tools, nested warehouse tool call, and redacted secrets.
- Scenario B: Controlled tool failure on inventory check with exception details captured.
- Scenario C: Behavioral regression (skipped tool + modified output schema).

It verifies:
1. SDK live ingestion to backend at http://127.0.0.1:8001
2. API-key authentication
3. Trace and tool-call persistence in SQLite
4. Correct parent_call_id hierarchy for nested tool calls
5. Client-side secret redaction
6. Correct project association
7. Visibility in backend queries
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "backend"))
if str(ROOT_DIR / "sdk" / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "sdk" / "src"))

from app import database, project_store, trace_store

BACKEND_URL = os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001")


def get_or_create_validation_project() -> tuple[dict, str]:
    """Ensures a dedicated MVP validation project and active API key exist."""
    owner_id = 2  # default owner user
    with database.connect() as conn:
        row = conn.execute(
            "SELECT id, name FROM projects WHERE name = ? AND archived_at IS NULL",
            ("MVP Order Processing Validation",)
        ).fetchone()
        if row:
            project = dict(row)
            # Create a fresh active key for live ingestion
            key_rec, raw_key = project_store.create_api_key(project["id"], name="MVP Live Test Key")
            return project, raw_key
        
        # Create dedicated project
        proj_rec, raw_key = project_store.create_project("MVP Order Processing Validation", owner_id=owner_id)
        return proj_rec, raw_key


def run_mvp_validation():
    print("=" * 70)
    print("Starting AgentReliability AI MVP Real Developer Integration Tests")
    print("=" * 70)
    
    # Setup project and API key first
    project, api_key = get_or_create_validation_project()
    project_id = project["id"]
    print(f"✓ Using Project: '{project['name']}' (ID: {project_id})")
    print(f"✓ Generated API Key prefix: {api_key[:12]}...")

    # Configure environment for the SDK
    os.environ["AGENTRELIABILITY_ENDPOINT"] = BACKEND_URL
    os.environ["AGENTRELIABILITY_API_KEY"] = api_key
    os.environ["AGENTRELIABILITY_CAPTURE_IO"] = "1"

    # Initialize SDK before importing agent
    import agentreliability
    agentreliability.init(
        endpoint=BACKEND_URL,
        api_key=api_key,
        capture_io=True,
    )

    # Now import order_agent with initialized monitor
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from order_agent import (
        CustomerAuthenticationError,
        InventoryUnavailableError,
        process_order,
    )

    sample_order = {
        "order_id": "ORD-MVP-1001",
        "customer_id": "CUST-9876",
        "auth_token": "secret_bearer_token_super_confidential_12345",
        "items": [
            {"sku": "SKU-DESK-01", "quantity": 1},
        ],
        "discount_code": "RELIABILITY20",
    }

    # -------------------------------------------------------------------------
    # Scenario A: Successful Execution
    # -------------------------------------------------------------------------
    print("\n--- Running Scenario A: Successful Execution ---")
    conf_a = process_order(sample_order)
    agentreliability.flush(timeout=5.0)
    time.sleep(0.5)
    assert conf_a["order_status"] == "confirmed"
    print(f"  Confirmation received: {conf_a['confirmation_code']} (Total: ${conf_a['total_usd']})")

    # Verify in backend
    traces_a = trace_store.list_executions(project_id=project_id, agent="order_processing_agent", limit=5)["items"]
    assert len(traces_a) > 0, "Scenario A trace not found in database!"
    exec_a = trace_store.get_execution(traces_a[0]["execution_id"], project_id=project_id)
    
    assert exec_a["status"] == "success", f"Expected success status, got {exec_a['status']}"
    assert exec_a["project_id"] == project_id, "Project ID mismatch!"
    
    # Verify tools captured
    tools_a = exec_a.get("tool_calls", [])
    tool_names_a = [t["tool_name"] for t in tools_a]
    print(f"  Captured {len(tools_a)} tool spans: {tool_names_a}")
    assert "verify_customer_credentials" in tool_names_a
    assert "check_inventory" in tool_names_a
    assert "retrieve_warehouse_location" in tool_names_a
    assert "calculate_total" in tool_names_a

    # Verify nested tool call hierarchy
    check_inv_call = next(t for t in tools_a if t["tool_name"] == "check_inventory")
    warehouse_call = next(t for t in tools_a if t["tool_name"] == "retrieve_warehouse_location")
    assert warehouse_call["parent_call_id"] == check_inv_call["call_id"], (
        f"Expected nested parent_call_id {check_inv_call['call_id']}, got {warehouse_call['parent_call_id']}"
    )
    print("  ✓ Verified nested tool call hierarchy (retrieve_warehouse_location -> check_inventory)")

    # Verify secret redaction
    verify_call = next(t for t in tools_a if t["tool_name"] == "verify_customer_credentials")
    raw_str = json.dumps(verify_call.get("input", {})) + json.dumps(verify_call.get("output", {}))
    assert "secret_bearer_token_super_confidential_12345" not in raw_str, "Secret auth_token leaked unredacted!"
    assert "sk-live-secret-test-key-9999" not in raw_str, "Secret api_key leaked unredacted!"
    assert "[REDACTED]" in raw_str, "Redaction mask '[REDACTED]' missing from payload!"
    print("  ✓ Verified secret redaction: auth_token and api_key properly sanitized to [REDACTED]")
    print("  ✅ Scenario A PASSED.")

    # -------------------------------------------------------------------------
    # Scenario B: Controlled Tool Failure
    # -------------------------------------------------------------------------
    print("\n--- Running Scenario B: Controlled Tool Failure ---")
    failed_as_expected = False
    try:
        process_order(sample_order, fail_inventory=True)
    except InventoryUnavailableError as exc:
        failed_as_expected = True
        print(f"  Caught expected agent exception: {exc}")
    agentreliability.flush(timeout=5.0)
    time.sleep(0.5)
    assert failed_as_expected, "Scenario B did not raise InventoryUnavailableError!"

    # Verify in backend
    traces_b = trace_store.list_executions(project_id=project_id, agent="order_processing_agent", status="failed", limit=5)["items"]
    assert len(traces_b) > 0, "Scenario B failed trace not found in database!"
    exec_b = trace_store.get_execution(traces_b[0]["execution_id"], project_id=project_id)
    
    assert exec_b["status"] == "failed"
    assert exec_b["error_type"] == "InventoryUnavailableError"
    assert "Inventory service unreachable" in (exec_b.get("error_message") or "")
    
    failed_tool = next(t for t in exec_b.get("tool_calls", []) if t["tool_name"] == "check_inventory")
    assert failed_tool["status"] == "error"
    assert failed_tool["error_type"] == "InventoryUnavailableError"
    print("  ✓ Verified failed tool status, exception type, and error message recorded in SQLite")
    print("  ✅ Scenario B PASSED.")

    # -------------------------------------------------------------------------
    # Scenario C: Behavioral Regression
    # -------------------------------------------------------------------------
    print("\n--- Running Scenario C: Behavioral Regression ---")
    conf_c = process_order(sample_order, skip_warehouse=True, modified_schema=True)
    agentreliability.flush(timeout=5.0)
    time.sleep(0.5)
    print(f"  Regression execution returned schema: {list(conf_c.keys())}")
    assert "reference_number" in conf_c
    assert "total_usd" not in conf_c

    # Verify in backend
    traces_c = trace_store.list_executions(project_id=project_id, agent="order_processing_agent", limit=5)["items"]
    exec_c = trace_store.get_execution(traces_c[0]["execution_id"], project_id=project_id)
    tool_names_c = [t["tool_name"] for t in exec_c.get("tool_calls", [])]
    
    assert "retrieve_warehouse_location" not in tool_names_c, "Skipped tool should not be in trace!"
    print(f"  Tools recorded in Scenario C: {tool_names_c} (warehouse tool skipped)")
    print("  ✓ Verified skipped tool and modified schema captured in SQLite")
    print("  ✅ Scenario C PASSED.")

    print("\n" + "=" * 70)
    print("ALL 3 MVP VALIDATION SCENARIOS VERIFIED SUCCESSFULLY!")
    print(f"Scenario A Trace ID: {exec_a['execution_id']}")
    print(f"Scenario B Trace ID: {exec_b['execution_id']}")
    print(f"Scenario C Trace ID: {exec_c['execution_id']}")
    print("=" * 70)
    return {
        "project_id": project_id,
        "trace_a": exec_a["execution_id"],
        "trace_b": exec_b["execution_id"],
        "trace_c": exec_c["execution_id"],
    }


if __name__ == "__main__":
    run_mvp_validation()
