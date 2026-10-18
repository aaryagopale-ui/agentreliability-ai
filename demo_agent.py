"""Deterministic Demo Agent for testing and verifying AgentReliability monitoring.

Can generate 4 deterministic scenarios:
  1. success: smooth multi-tool execution
  2. tool_failure: external tool raises an error (HTTP 500)
  3. timeout: slow tool exceeds timeout threshold
  4. exception: agent encounters an unexpected logic error

Usage:
  python demo_agent.py [scenario]
  e.g.:
  python demo_agent.py success
  python demo_agent.py tool_failure
  python demo_agent.py timeout
  python demo_agent.py exception
  python demo_agent.py all
"""
import os
import sys
import time
from pathlib import Path

# Add sdk to path if running directly from repo without pip install
sdk_path = str(Path(__file__).resolve().parent / "sdk" / "src")
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from agentreliability import AgentMonitor

# Initialize monitor using environment or local default
endpoint = os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8000")
api_key = os.environ.get("AGENTRELIABILITY_API_KEY", "")

if not api_key:
    # If no key in env, see if we can find or generate one using the backend CLI
    print("Warning: AGENTRELIABILITY_API_KEY not set. Set it before running to send traces.")

monitor = AgentMonitor(
    endpoint=endpoint,
    api_key=api_key,
    capture_io=True,  # enabled for demonstration
    metadata={"environment": "demo", "demo_version": "1.0"}
)

# ----------------- Tools -----------------

@monitor.trace_tool("search_docs")
def search_docs(query: str):
    time.sleep(0.02)
    return {"results": [f"Document discussing {query}", "Guide on agent reliability"]}

@monitor.trace_tool("fetch_user_profile")
def fetch_user_profile(user_id: int):
    time.sleep(0.01)
    return {"user_id": user_id, "tier": "enterprise", "email": "developer@example.com"}

@monitor.trace_tool("external_weather_api")
def external_weather_api(city: str):
    time.sleep(0.02)
    raise ConnectionError("HTTP 503: Weather service upstream gateway timeout")

@monitor.trace_tool("slow_database_query")
def slow_database_query(query: str):
    # Simulate timeout
    time.sleep(0.05)
    raise TimeoutError("Database connection timed out after 5000ms")

# ----------------- Agent -----------------

@monitor.trace_agent("demo-research-agent")
def run_demo_agent(scenario: str, user_id: int = 101):
    print(f"\n[Agent] Executing scenario: {scenario}...")
    
    # Tool 1: lookup profile
    profile = fetch_user_profile(user_id)
    print(f"[Agent] Retrieved profile for user {profile['user_id']}")
    
    if scenario == "success":
        docs = search_docs("agent reliability architecture")
        print(f"[Agent] Retrieved {len(docs['results'])} documents")
        return {
            "status": "complete",
            "message": "Report generated successfully.",
            "sources": docs["results"]
        }
        
    elif scenario == "tool_failure":
        print("[Agent] Calling external_weather_api...")
        weather = external_weather_api("San Francisco")
        return {"weather": weather}
        
    elif scenario == "timeout":
        print("[Agent] Running slow database query...")
        slow_database_query("SELECT * FROM agent_logs WHERE date > NOW() - INTERVAL 1 YEAR")
        return {"data": "query_result"}
        
    elif scenario == "exception":
        docs = search_docs("unhandled syntax test")
        print("[Agent] Encountered unexpected divide-by-zero calculation...")
        # Simulate unexpected internal bug
        val = 100 / 0
        return {"calc": val}
        
    else:
        raise ValueError(f"Unknown scenario: {scenario}. Choose from: success, tool_failure, timeout, exception")

def main():
    scenario = sys.argv[1] if len(sys.argv) > 1 else "success"
    
    scenarios_to_run = [scenario]
    if scenario == "all":
        scenarios_to_run = ["success", "tool_failure", "timeout", "exception"]
        
    for sc in scenarios_to_run:
        try:
            res = run_demo_agent(sc)
            print(f"[Result: SUCCESS] {res}")
        except Exception as e:
            print(f"[Result: CAUGHT {type(e).__name__}] {e}")
            
    print("\nFlushing monitor traces to backend...")
    flushed = monitor.flush(timeout=5.0)
    print(f"Flush complete: {flushed}. Dropped events: {monitor.dropped_events}")

if __name__ == "__main__":
    main()

