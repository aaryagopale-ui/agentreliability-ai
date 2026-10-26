#!/usr/bin/env python3
"""Example 3: Controlled Failures and Exception Capture with AgentReliability.

Demonstrates:
- Capturing tool call errors without altering agent exception flow
- Capturing TimeoutError as category 'timeout'
- Capturing unhandled agent logic bugs
- How exceptions are passed through untouched to caller code
- How the dashboard diagnostic engine uses this recorded evidence

Usage:
  python examples/03_failure_scenarios.py [scenario]
  Scenarios: tool_error | timeout | unhandled_bug | all
"""
import argparse
import os
import sys
import time
from pathlib import Path

# Add sdk/src to sys.path if running from git checkout
sdk_path = str(Path(__file__).resolve().parent.parent / "sdk" / "src")
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from agentreliability import AgentMonitor

monitor = AgentMonitor(
    endpoint=os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001"),
    api_key=os.environ.get("AGENTRELIABILITY_API_KEY", ""),
    capture_io=True,
    metadata={"example": "03_failure_scenarios"},
)


# --- Healthy Tool ---
@monitor.trace_tool("validate_auth_token")
def validate_auth_token(token: str) -> dict:
    time.sleep(0.01)
    return {"valid": True, "scope": "write:orders"}


# --- Failing Tool ---
@monitor.trace_tool("charge_credit_card")
def charge_credit_card(card_token: str, amount_cents: int) -> dict:
    time.sleep(0.02)
    # Simulate a payment processor rejection
    raise RuntimeError("Payment gateway error: Declined (Code 402 Card Expired)")


# --- Slow Tool Simulating Timeout ---
@monitor.trace_tool("remote_inventory_rpc")
def remote_inventory_rpc(warehouse_id: str):
    time.sleep(0.03)
    # Simulate network socket timeout
    raise TimeoutError(f"RPC connection to warehouse '{warehouse_id}' timed out after 5000ms")


# --- Traced Agent ---
@monitor.trace_agent("checkout_agent")
def run_checkout_agent(scenario: str) -> dict:
    print(f"\n[Agent] Starting checkout scenario: '{scenario}'...")

    # Step 1: Preceding step that succeeds
    auth = validate_auth_token("test-bearer-token")
    print(f"[Agent] Auth validated: {auth['valid']}")

    # Step 2: Trigger requested failure scenario
    if scenario == "tool_error":
        print("[Agent] Attempting credit card charge...")
        return charge_credit_card("tok_12345", 4999)

    elif scenario == "timeout":
        print("[Agent] Calling remote inventory RPC...")
        return remote_inventory_rpc("wh-us-east-1")

    elif scenario == "unhandled_bug":
        print("[Agent] Encountering internal data formatting error...")
        raw_items = None
        return len(raw_items)  # TypeError: object of type 'NoneType' has no len()

    else:
        return {"status": "success", "message": "Standard path"}


def run_scenario_safely(scenario: str):
    print(f"\n----------------------------------------------------")
    print(f"Running Scenario: {scenario}")
    print(f"----------------------------------------------------")
    try:
        res = run_checkout_agent(scenario)
        print(f"[Success Result]: {res}")
    except Exception as exc:
        print(f"\n[Captured Exception Passed Through Untouched]:")
        print(f"  Type    : {type(exc).__name__}")
        print(f"  Message : {exc}")
        print("  -> The agent received the exact exception it threw.")
        print("  -> Meanwhile, AgentReliability SDK recorded the failure trace in the background.")


def main():
    parser = argparse.ArgumentParser(description="Run failure tracing examples.")
    parser.add_argument("scenario", nargs="?", default="all", choices=["tool_error", "timeout", "unhandled_bug", "all"])
    args = parser.parse_args()

    scenarios = ["tool_error", "timeout", "unhandled_bug"] if args.scenario == "all" else [args.scenario]
    for sc in scenarios:
        run_scenario_safely(sc)

    flushed = monitor.flush(timeout=3.0)
    print(f"\n[SDK] All traces flushed to backend: {flushed}")


if __name__ == "__main__":
    main()

