#!/usr/bin/env python3
"""Example Instrumented AI Agent for AgentReliability AI (Phase 6 Step 1).

A deterministic, real Python agent instrumented with the agentreliability SDK.
Executes real Python tools (tax calculation, inventory check, credential verification)
without requiring any paid LLM API.

Key Capabilities Verified:
1. Agent-level execution tracing (@monitor.trace_agent)
2. Tool-call execution tracing (@monitor.trace_tool)
3. Latency measurement (duration_ms per tool and overall)
4. Success & Controlled Failure capturing (clean error classification)
5. Automatic secret redaction (credentials & sensitive inputs sanitized)
6. Direct trace ingestion into AgentReliability backend (http://127.0.0.1:8001)

Usage:
  export AGENTRELIABILITY_ENDPOINT="http://127.0.0.1:8001"
  export AGENTRELIABILITY_API_KEY="ar_live_your_project_key"
  python example_agent.py --scenario success
  python example_agent.py --scenario failure
  python example_agent.py --scenario all
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Ensure local SDK source is on sys.path if not installed in current venv
sdk_path = str(Path(__file__).resolve().parent / "sdk" / "src")
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from agentreliability import AgentMonitor

# Configure SDK endpoint and project API key from environment
ENDPOINT = os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001").rstrip("/")
API_KEY = os.environ.get("AGENTRELIABILITY_API_KEY", "")

monitor = AgentMonitor(
    endpoint=ENDPOINT,
    api_key=API_KEY,
    capture_io=True,  # Capture tool inputs and outputs
    metadata={
        "agent_type": "deterministic_order_fulfillment",
        "runtime": "python-3.14",
        "environment": "local_dev",
    },
)

# -----------------------------------------------------------------------------
# Real Tool Implementations (Instrumented)
# -----------------------------------------------------------------------------

@monitor.trace_tool("verify_client_credentials")
def verify_client_credentials(client_id: str, api_secret: str) -> dict:
    """Authenticates the client. Demonstrates secret redaction of 'api_secret'."""
    time.sleep(0.015)  # Simulate network hop
    if not client_id:
        raise ValueError("Invalid client_id provided.")
    # Notice: api_secret is received and processed, but will be redacted in traces
    return {"authenticated": True, "client_id": client_id, "tier": "enterprise"}


@monitor.trace_tool("query_warehouse_shelf")
def query_warehouse_shelf(sku: str) -> dict:
    """Sub-tool: Locates aisle and shelf bin for SKU (demonstrates nested tool call hierarchy)."""
    time.sleep(0.008)  # Simulate shelf locator query
    locations = {
        "SKU-WIDGET-A": {"aisle": "A-04", "bin": "Shelf-12"},
        "SKU-WIDGET-B": {"aisle": "B-09", "bin": "Shelf-03"},
        "SKU-DISCONTINUED": {"aisle": "Z-99", "bin": "Deprec-Archive"},
    }
    return locations.get(sku, {"aisle": "Unknown", "bin": "Unknown"})


@monitor.trace_tool("check_inventory")
def check_inventory(sku: str, quantity: int) -> dict:
    """Verifies warehouse inventory stock and calls nested shelf locator tool."""
    time.sleep(0.015)  # Simulate database query latency
    inventory_db = {
        "SKU-WIDGET-A": 150,
        "SKU-WIDGET-B": 45,
        "SKU-DISCONTINUED": 0,
    }

    # Nested tool call demonstrating parent-child relationship
    shelf_info = query_warehouse_shelf(sku)

    if sku not in inventory_db:
        raise KeyError(f"Item SKU '{sku}' not recognized in catalog.")

    available = inventory_db[sku]
    if available < quantity:
        raise ValueError(f"Requested quantity ({quantity}) exceeds available stock ({available}) for {sku}.")

    return {
        "sku": sku,
        "requested": quantity,
        "available": available,
        "in_stock": True,
        "location": shelf_info,
    }


@monitor.trace_tool("calculate_order_totals")
def calculate_order_totals(items: list[dict], discount_pct: float = 0.0) -> dict:
    """Computes line items, discounts, tax, and final total."""
    time.sleep(0.010)  # Simulate calculation
    subtotal = sum(i["price"] * i["quantity"] for i in items)
    discount_amount = round(subtotal * (discount_pct / 100.0), 2)
    tax = round((subtotal - discount_amount) * 0.0825, 2)  # 8.25% sales tax
    total = round(subtotal - discount_amount + tax, 2)

    return {
        "subtotal": subtotal,
        "discount_applied": discount_amount,
        "tax": tax,
        "total": total,
        "currency": "USD",
    }


# -----------------------------------------------------------------------------
# Agent Core Execution Logic (Instrumented)
# -----------------------------------------------------------------------------

@monitor.trace_agent("order_fulfillment_agent")
def run_order_agent(query: str, sku: str, quantity: int, discount_pct: float = 0.0, simulate_failure: bool = False) -> dict:
    """Executes the agent workflow: auth -> inventory check -> pricing -> final response."""
    print(f"\n🤖 [Agent] Processing user query: '{query}'")

    # Step 1: Authenticate client with sensitive token (verifies redaction)
    auth_result = verify_client_credentials(
        client_id="corp-client-42",
        api_secret="sk-live-super-secret-token-xyz987",
    )
    print(f"   ✓ Authenticated client: {auth_result['client_id']} (tier: {auth_result['tier']})")

    # Step 2: Check Inventory
    target_sku = "SKU-DISCONTINUED" if simulate_failure else sku
    print(f"   ✓ Checking inventory for {quantity} unit(s) of {target_sku}...")
    stock = check_inventory(sku=target_sku, quantity=quantity)
    print(f"   ✓ Stock confirmed: {stock['available']} available.")

    # Step 3: Compute Pricing
    order_items = [{"sku": sku, "price": 49.99, "quantity": quantity}]
    pricing = calculate_order_totals(items=order_items, discount_pct=discount_pct)
    print(f"   ✓ Pricing computed: Total = ${pricing['total']} {pricing['currency']}")

    # Step 4: Final Agent Response
    final_response = {
        "status": "order_confirmed",
        "order_id": f"ORD-{int(time.time())}",
        "sku": sku,
        "quantity": quantity,
        "pricing": pricing,
        "summary": f"Successfully processed order for {quantity} x {sku} totaling ${pricing['total']}.",
    }
    return final_response


# -----------------------------------------------------------------------------
# CLI Runner
# -----------------------------------------------------------------------------

def execute_scenario(scenario_name: str) -> bool:
    print(f"\n=======================================================")
    print(f"  SCENARIO: {scenario_name.upper()}")
    print(f"=======================================================")

    if scenario_name == "success":
        try:
            res = run_order_agent(
                query="Order 2 units of Widget-A with a 10% discount",
                sku="SKU-WIDGET-A",
                quantity=2,
                discount_pct=10.0,
                simulate_failure=False,
            )
            print(f"\n[Result: SUCCESS]")
            print(f"  Order ID: {res['order_id']}")
            print(f"  Total: ${res['pricing']['total']}")
            print(f"  Summary: {res['summary']}")
            return True
        except Exception as exc:
            print(f"\n[Result: UNEXPECTED FAILURE] {type(exc).__name__}: {exc}")
            return False

    elif scenario_name == "failure":
        try:
            res = run_order_agent(
                query="Order 10 units of Discontinued Item",
                sku="SKU-DISCONTINUED",
                quantity=10,
                discount_pct=0.0,
                simulate_failure=True,
            )
            print(f"\n[Result: UNEXPECTED SUCCESS] {res}")
            return False
        except Exception as exc:
            print(f"\n[Result: CONTROLLED FAILURE CAUGHT AS EXPECTED]")
            print(f"  Error Type: {type(exc).__name__}")
            print(f"  Error Message: {exc}")
            return True
    else:
        print(f"[!] Unknown scenario: {scenario_name}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run example instrumented AI agent")
    parser.add_argument(
        "--scenario",
        choices=["success", "failure", "all"],
        default="success",
        help="Execution scenario to run (default: success)",
    )
    args = parser.parse_args()

    print(f"[*] AgentReliability Target Endpoint: {ENDPOINT}")
    if API_KEY:
        masked_key = f"{API_KEY[:8]}...{API_KEY[-4:]}" if len(API_KEY) > 12 else "***"
        print(f"[*] Configured API Key: {masked_key}")
    else:
        print("[!] Warning: AGENTRELIABILITY_API_KEY is not set. Traces will not be sent to backend.")

    scenarios = ["success", "failure"] if args.scenario == "all" else [args.scenario]
    for s in scenarios:
        execute_scenario(s)

    # Flush events to backend
    if API_KEY:
        print("\n[*] Flushing trace events to AgentReliability backend...")
        success = monitor.flush(timeout=5.0)
        print(f"[+] Flush completed. Success: {success}, Dropped: {monitor.dropped_events}")
    else:
        print("\n[*] Skipping trace flush because no API key was provided.")


if __name__ == "__main__":
    main()

