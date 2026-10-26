"""Simple 10-Minute Quickstart Agent for AgentReliability AI.

A lightweight, deterministic customer support triage agent with zero paid API dependencies.
Runs in normal mode (passing) or regressed mode (deliberate breaking regression).

Usage:
  python quickstart_agent.py            # Normal execution (passes Golden Baseline)
  python quickstart_agent.py regressed  # Regressed execution (missing tool call)
"""
import os
import sys
import time
from pathlib import Path

# Add sdk/src to path if not installed in active environment
_sdk_src = str(Path(__file__).resolve().parent.parent / "sdk" / "src")
if _sdk_src not in sys.path and Path(_sdk_src).is_dir():
    sys.path.insert(0, _sdk_src)

from agentreliability import AgentMonitor

# Initialize monitor using environment variables
monitor = AgentMonitor(
    endpoint=os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001"),
    api_key=os.environ.get("AGENTRELIABILITY_API_KEY", ""),
    capture_io=True,
    metadata={"environment": "quickstart", "version": "1.0.0"}
)


@monitor.trace_tool("classify_ticket")
def classify_ticket(ticket_text: str) -> dict:
    """Analyze ticket text and categorize urgency."""
    time.sleep(0.01)
    is_urgent = any(word in ticket_text.lower() for word in ["urgent", "down", "error", "charge"])
    category = "billing" if "charge" in ticket_text.lower() else "technical"
    return {
        "category": category,
        "urgency": "high" if is_urgent else "normal",
    }


@monitor.trace_tool("lookup_customer")
def lookup_customer(customer_id: str) -> dict:
    """Fetch customer subscription tier and SLA guarantee."""
    time.sleep(0.01)
    return {
        "customer_id": customer_id,
        "tier": "enterprise",
        "sla_hours": 2,
    }


@monitor.trace_tool("assign_specialist")
def assign_specialist(category: str, tier: str) -> dict:
    """Route ticket to the designated support queue and specialist."""
    time.sleep(0.01)
    queue = "vip-billing" if category == "billing" and tier == "enterprise" else "general-support"
    return {
        "queue": queue,
        "assigned_to": "alice@support.example.com",
    }


@monitor.trace_agent("support_triage_agent")
def triage_ticket(customer_id: str, ticket_text: str, regressed: bool = False) -> dict:
    """Orchestrate customer support triage workflow."""
    print(f"\n[Agent] Triaging ticket for {customer_id}: '{ticket_text}' (regressed={regressed})...")

    # Step 1: Classify ticket
    classification = classify_ticket(ticket_text)
    print(f"  ↳ Classified as {classification['category']} (urgency: {classification['urgency']})")

    # Step 2: Customer lookup (omitted in regressed mode!)
    if not regressed:
        customer = lookup_customer(customer_id)
        tier = customer["tier"]
        print(f"  ↳ Customer tier: {tier}")
    else:
        # Deliberate regression: skipping required customer lookup tool
        print("  ⚠️ [Regression] Skipping lookup_customer tool call!")
        tier = "standard"

    # Step 3: Assign specialist
    assignment = assign_specialist(classification["category"], tier)
    print(f"  ↳ Assigned to: {assignment['assigned_to']} ({assignment['queue']})")

    return {
        "status": "triaged",
        "customer_id": customer_id,
        "category": classification["category"],
        "assigned_to": assignment["assigned_to"],
        "queue": assignment["queue"],
    }


if __name__ == "__main__":
    is_regressed = len(sys.argv) > 1 and sys.argv[1].lower() in ("regressed", "--regressed")
    result = triage_ticket("cust_99", "Urgent: unexpected double charge on invoice", regressed=is_regressed)
    print(f"[Agent] Result: {result}")

    # Ensure background traces are delivered before process exits
    monitor.flush()
    print("[Agent] Execution trace delivered to AgentReliability.\n")

