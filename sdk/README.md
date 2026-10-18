# agentreliability (Python SDK)

Trace your AI agent and send the traces to AgentReliability AI. See the main project README for the full guide.

```python
from agentreliability import AgentMonitor

monitor = AgentMonitor(endpoint="http://localhost:8000")   # key from AGENTRELIABILITY_API_KEY

@monitor.trace_tool("search")
def search(q): ...

@monitor.trace_agent("research-agent")
def run_agent(question):
    return search(question)
```

- Input/output capture is **off by default** (`capture_io=True` turns it on; secrets are redacted).
- Monitoring never raises into your code; if the backend is down, traces are dropped.
- Synchronous functions only (async support is a later milestone).

