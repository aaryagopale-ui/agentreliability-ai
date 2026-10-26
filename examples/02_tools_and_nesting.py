#!/usr/bin/env python3
"""Example 2: Tool-Call Tracing and Nested Calls with AgentReliability.

Demonstrates:
- Decorating tool functions with @monitor.trace_tool
- Sequential tool calls within an agent
- Nested tool calls (a parent tool invoking a child tool)
- Parent-child call ID hierarchy tracking in the execution timeline

Usage:
  python examples/02_tools_and_nesting.py
"""
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
    metadata={"example": "02_tools_and_nesting"},
)


# --- Leaf Tool (Child) ---
@monitor.trace_tool("query_database")
def query_database(table: str, filter_id: str) -> dict:
    """Simulates a low-level database query."""
    print(f"    [Child Tool: query_database] Querying {table} for ID '{filter_id}'...")
    time.sleep(0.03)  # Simulate SQL latency
    return {"id": filter_id, "name": "Industrial Sensor Model X", "inventory_count": 42}


# --- Parent Tool (calls query_database) ---
@monitor.trace_tool("check_stock_availability")
def check_stock_availability(sku: str, required_qty: int) -> dict:
    """Parent tool that invokes query_database internally."""
    print(f"  [Parent Tool: check_stock_availability] Checking stock for SKU '{sku}'...")
    # This nested call automatically records check_stock_availability as parent_call_id
    item = query_database("inventory_catalog", sku)
    available = item.get("inventory_count", 0) >= required_qty
    return {
        "sku": sku,
        "available": available,
        "stock": item.get("inventory_count", 0),
    }


# --- Independent Sequential Tool ---
@monitor.trace_tool("calculate_shipping_estimate")
def calculate_shipping_estimate(destination_zip: str, weight_lbs: float) -> dict:
    """Calculates shipping cost and estimated delivery days."""
    print(f"  [Tool: calculate_shipping_estimate] Calculating delivery to {destination_zip}...")
    time.sleep(0.02)
    return {"destination": destination_zip, "carrier": "GroundExpress", "cost_usd": 14.50, "days": 2}


# --- Traced Agent ---
@monitor.trace_agent("fulfillment_coordinator")
def run_fulfillment_agent(order_id: str, sku: str, quantity: int, destination_zip: str) -> dict:
    print(f"\n[Agent: fulfillment_coordinator] Processing Order {order_id}...")

    # Step 1: Check stock (triggers nested database query)
    stock_info = check_stock_availability(sku, quantity)

    # Step 2: Calculate shipping
    shipping_info = calculate_shipping_estimate(destination_zip, 5.0)

    return {
        "order_id": order_id,
        "fulfilled": stock_info["available"],
        "stock_details": stock_info,
        "shipping": shipping_info,
    }


def main():
    print("=== AgentReliability Example 2: Tools and Nested Calls ===")
    result = run_fulfillment_agent(
        order_id="ORD-2026-001",
        sku="SKU-SENSOR-99",
        quantity=5,
        destination_zip="94107",
    )
    print("\n[Final Agent Result]:")
    print(result)

    flushed = monitor.flush(timeout=3.0)
    print(f"\n[SDK] Traces flushed: {flushed}")


if __name__ == "__main__":
    main()

