# agentreliability (Python SDK)

Lightweight, non-invasive execution tracing for Python AI agents and tools.

## Quick Example

```python
import os
from agentreliability import AgentMonitor

# Initialize monitor (reads AGENTRELIABILITY_ENDPOINT & AGENTRELIABILITY_API_KEY from environment)
monitor = AgentMonitor(
    endpoint=os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001"),
    api_key=os.environ.get("AGENTRELIABILITY_API_KEY"),
    capture_io=True,
)

@monitor.trace_tool("search")
def search(query: str):
    return [f"Result for {query}"]

@monitor.trace_agent("research-agent")
def run_agent(question: str):
    return search(question)

if __name__ == "__main__":
    result = run_agent("Agent reliability testing")
    print(result)
    monitor.flush()
```

## Key Capabilities
- **Non-Invasive:** Monitoring never throws into your code. If the backend is unreachable, traces are dropped and your agent is unaffected.
- **Secret Redaction:** High-entropy credentials (OpenAI keys, AWS keys, Bearer tokens, emails) are scrubbed before transmission.
- **Nested Tracking:** Supports nested tool calls (`parent_call_id`).
- **Context Managers:** Supports arbitrary block tracing via `with monitor.trace_execution("block_name") as trace:` and `with tool_call("tool_name"):`.
- **CLI Included:** `agentreliability init`, `agentreliability dev`, `agentreliability doctor`, `agentreliability status`, `agentreliability test`, and `agentreliability compare` (also runnable via `python -m agentreliability`).
- **Zero Paid Dependencies:** Runs out-of-the-box locally with standard library and local FastAPI backend.

## Documentation
- ⚡ [**10-Minute Developer Quickstart Guide**](../docs/QUICKSTART.md) — From installation to Golden Baseline comparison.
- 🐍 [**Python SDK Guide**](../docs/SDK_GUIDE.md) — Comprehensive guide to decorators, context managers, and redaction.
- 🛠️ [**CLI & CI/CD Guide**](../docs/CLI_GUIDE.md) — Full CLI command reference and GitHub Actions workflows.
- 🔧 [**Troubleshooting Guide**](../docs/TROUBLESHOOTING.md) — Step-by-step solutions for common error states.
