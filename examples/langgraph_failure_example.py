"""Example 4: LangGraph Controlled Failure Execution.

Demonstrates:
- How AgentReliability AI captures and pinpoints errors inside a LangGraph node.
- The failing node is recorded with error type, message, and execution duration.
- The root execution status is flagged as 'failed'.
- The developer's Python exception passes through untouched (never swallowed).
- The failed trace feeds into the AgentReliability Failure Analysis dashboard.
"""
import os
import sys
from pathlib import Path
from typing import TypedDict

# Ensure sdk is in python path for local execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk" / "src"))

from agentreliability.integrations.langgraph import AgentReliabilityCallbackHandler
from langgraph.graph import StateGraph, START, END


class PaymentState(TypedDict):
    account_id: str
    amount: float
    status: str


def check_account_balance(state: PaymentState) -> dict:
    """Pre-flight check node."""
    print("  [Node 1] Checking account balance: Verified active.")
    return {"status": "balance_checked"}


def process_payment_gateway(state: PaymentState) -> dict:
    """Failing gateway node (simulating an external API rejection)."""
    print("  [Node 2] Attempting payment processing...")
    # Controlled simulated failure
    raise ConnectionResetError(
        f"PaymentGatewayError: Connection to merchant bank for account '{state['account_id']}' timed out after 3000ms."
    )


def send_confirmation(state: PaymentState) -> dict:
    """Should never be reached due to upstream failure."""
    return {"status": "confirmed"}


def main():
    api_key = os.environ.get("AGENTRELIABILITY_API_KEY", "ar_live_demo_key_example")
    endpoint = os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001")

    print("🚀 Running LangGraph Controlled Failure Example...")

    handler = AgentReliabilityCallbackHandler(
        agent_name="payment_processing_graph",
        api_key=api_key,
        endpoint=endpoint,
        capture_io=True,
    )

    builder = StateGraph(PaymentState)
    builder.add_node("check_balance", check_account_balance)
    builder.add_node("process_payment", process_payment_gateway)
    builder.add_node("send_confirmation", send_confirmation)

    builder.add_edge(START, "check_balance")
    builder.add_edge("check_balance", "process_payment")
    builder.add_edge("process_payment", "send_confirmation")
    builder.add_edge("send_confirmation", END)

    graph = builder.compile()

    state = {
        "account_id": "ACC-5491-PREMIUM",
        "amount": 299.99,
        "status": "initiated",
    }

    try:
        graph.invoke(state, config={"callbacks": [handler]})
        print("❌ Unexpected: Graph was expected to raise an error.")
    except ConnectionResetError as exc:
        print(f"✅ Caught expected transparent exception: {exc}")

    # Flush trace telemetry to backend
    handler.flush(timeout=3.0)
    print("✅ Failure evidence successfully transmitted to AgentReliability AI dashboard.")


if __name__ == "__main__":
    main()

