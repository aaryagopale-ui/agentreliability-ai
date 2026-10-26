"""Example 3: Basic LangGraph StateGraph with AgentReliability Tracing.

Demonstrates:
- Connecting AgentReliabilityCallbackHandler to a compiled LangGraph StateGraph.
- Observing node execution steps in sequence.
- Invoking tools from within graph nodes with callback propagation.
- Viewing the complete visual execution timeline on the dashboard.
"""
import os
import sys
from pathlib import Path
from typing import TypedDict

# Ensure sdk is in python path for local execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk" / "src"))

from agentreliability.integrations.langgraph import AgentReliabilityCallbackHandler
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END


# 1. Define tools used in graph nodes
@tool
def calculate_shipping_cost(weight_kg: float, destination: str) -> float:
    """Calculate shipping cost based on package weight and destination zone."""
    base = 5.0 if destination.upper() == "LOCAL" else 15.0
    return round(base + (weight_kg * 1.5), 2)


# 2. Define State Schema
class OrderState(TypedDict):
    order_id: str
    weight_kg: float
    destination: str
    subtotal: float
    shipping_cost: float
    grand_total: float
    status: str


# 3. Define Graph Nodes
def validate_order(state: OrderState) -> dict:
    """Validate order inputs before pricing."""
    if state["weight_kg"] <= 0:
        raise ValueError("Package weight must be greater than zero.")
    return {"status": "validated"}


def compute_shipping(state: OrderState, config) -> dict:
    """Calculate shipping using tool invocation."""
    cost = calculate_shipping_cost.invoke(
        {"weight_kg": state["weight_kg"], "destination": state["destination"]},
        config=config,
    )
    return {"shipping_cost": cost}


def finalize_order(state: OrderState) -> dict:
    """Compute grand total and confirm order."""
    total = round(state["subtotal"] + state["shipping_cost"], 2)
    return {"grand_total": total, "status": "confirmed"}


def main():
    api_key = os.environ.get("AGENTRELIABILITY_API_KEY", "ar_live_demo_key_example")
    endpoint = os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001")

    print("🚀 Running LangGraph Basic Graph Example...")

    handler = AgentReliabilityCallbackHandler(
        agent_name="order_fulfillment_graph",
        api_key=api_key,
        endpoint=endpoint,
        capture_io=True,
        metadata={"graph_type": "state_graph", "version": "1.0.0"},
    )

    # 4. Compile the state graph
    builder = StateGraph(OrderState)
    builder.add_node("validate_order", validate_order)
    builder.add_node("compute_shipping", compute_shipping)
    builder.add_node("finalize_order", finalize_order)

    builder.add_edge(START, "validate_order")
    builder.add_edge("validate_order", "compute_shipping")
    builder.add_edge("compute_shipping", "finalize_order")
    builder.add_edge("finalize_order", END)

    graph = builder.compile()

    # 5. Invoke graph with the callback handler
    initial_state = {
        "order_id": "ORD-9872",
        "weight_kg": 3.5,
        "destination": "LOCAL",
        "subtotal": 85.0,
        "shipping_cost": 0.0,
        "grand_total": 0.0,
        "status": "pending",
    }
    print(f"Initial State: {initial_state}")

    final_state = graph.invoke(initial_state, config={"callbacks": [handler]})
    print(f"Final State: {final_state}")

    # 6. Flush traces
    handler.flush(timeout=3.0)
    print("✅ LangGraph nodes and tool spans successfully recorded in AgentReliability AI.")


if __name__ == "__main__":
    main()

