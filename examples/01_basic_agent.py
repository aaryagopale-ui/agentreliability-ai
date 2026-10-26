#!/usr/bin/env python3
"""Example 1: Basic Python Agent Tracing with AgentReliability.

Demonstrates:
- Initializing the AgentMonitor
- Tracing an agent execution using @monitor.trace_agent
- Preserving function arguments, return values, and behavior untouched
- Flushing pending traces before process exit

Prerequisites:
  export AGENTRELIABILITY_ENDPOINT="http://127.0.0.1:8001"
  export AGENTRELIABILITY_API_KEY="ar_live_your_project_key"

Usage:
  python examples/01_basic_agent.py
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

# Initialize monitor from environment variables with local fallback
monitor = AgentMonitor(
    endpoint=os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001"),
    api_key=os.environ.get("AGENTRELIABILITY_API_KEY", ""),
    capture_io=True,  # Enable I/O capture for visibility in the dashboard
    metadata={"example": "01_basic_agent", "version": "1.0"},
)


@monitor.trace_agent("greeting_agent")
def run_greeting_agent(user_name: str, topic: str) -> dict:
    """A simple agent that generates a personalized greeting."""
    print(f"[Agent] Generating greeting for {user_name} on topic '{topic}'...")
    time.sleep(0.05)  # Simulate agent deliberation
    return {
        "greeting": f"Hello {user_name}! Welcome to AgentReliability AI.",
        "topic": topic,
        "status": "ready",
    }


def main():
    print("=== AgentReliability Example 1: Basic Agent Tracing ===")
    if not os.environ.get("AGENTRELIABILITY_API_KEY"):
        print("Note: AGENTRELIABILITY_API_KEY is not set.")
        print("Traces will execute locally, but won't be ingested into the dashboard.")
        print("To send traces: export AGENTRELIABILITY_API_KEY='ar_live_...'")

    result = run_greeting_agent("Alice", "Reliability Testing")
    print(f"[Result] {result}")

    # Flush background transport thread so all events are delivered before exit
    flushed = monitor.flush(timeout=3.0)
    print(f"[SDK] Pending traces flushed: {flushed}")


if __name__ == "__main__":
    main()

