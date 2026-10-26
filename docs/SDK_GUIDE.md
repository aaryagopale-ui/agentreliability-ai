# 🐍 AgentReliability AI: Python SDK Guide

The `agentreliability` SDK provides lightweight, non-invasive execution tracing for Python AI agents and tools.

---

## 🌟 The Core Principle

> **Monitoring must NEVER break or alter the developer's agent.**
> 
> * Every piece of SDK bookkeeping runs inside defensive exception isolation.
> * Functions receive exact arguments and return exact values.
> * If an exception is raised, the exact exception object passes through untouched.
> * Network trace transmission runs asynchronously on a background daemon thread.

---

## 📦 Installation

Install the package in your active virtual environment:

```bash
# In editable/development mode
pip install -e sdk

# Or via wheel/dist
pip install agentreliability
```

---

## ⚙️ Configuration & Environment Variables

| Environment Variable | Default | Purpose |
| :--- | :---: | :--- |
| `AGENTRELIABILITY_ENDPOINT` | `http://127.0.0.1:8001` | FastAPI backend URL |
| `AGENTRELIABILITY_API_KEY` | *(None)* | Secret project API key (`ar_live_...`) |
| `AGENTRELIABILITY_CAPTURE_IO` | `false` | Enable/disable input and output capturing |

---

## 🚀 Basic Usage

### Option A: `AgentMonitor` Instance (Recommended)

```python
import os
from agentreliability import AgentMonitor

monitor = AgentMonitor(
    endpoint=os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001"),
    api_key=os.environ.get("AGENTRELIABILITY_API_KEY"),
    capture_io=True,  # Captures arguments & outputs (sensitive keys redacted)
    metadata={"environment": "production", "version": "1.2.0"},
)

@monitor.trace_tool("search_docs")
def search(query: str) -> list[str]:
    return ["Doc A", "Doc B"]

@monitor.trace_agent("researcher")
def run(query: str):
    return search(query)

if __name__ == "__main__":
    result = run("AI reliability")
    monitor.flush()  # Ensures all queued background events are sent before script terminates
```

### Option B: Module-Level Convenience Decorators

```python
from agentreliability import trace_agent, trace_tool, flush

@trace_tool("calculate_sum")
def add(a: int, b: int) -> int:
    return a + b

@trace_agent("math_agent")
def solve():
    return add(10, 20)

if __name__ == "__main__":
    print("Answer:", solve())
    flush()
```

---

## 🌲 Nested Tool Calls & Parent-Child Hierarchy

The SDK automatically tracks nested tool calls using `contextvars`. When tool A invokes tool B, tool B records `parent_call_id = tool_A.call_id`.

```python
@monitor.trace_tool("query_sql")
def query_sql(query: str):
    # Leaf tool call
    return {"rows": 5}

@monitor.trace_tool("check_inventory")
def check_inventory(sku: str):
    # Parent tool call: calls query_sql internally
    return query_sql(f"SELECT * FROM inventory WHERE sku='{sku}'")

@monitor.trace_agent("fulfillment_agent")
def fulfill(sku: str):
    return check_inventory(sku)
```

In the **Visual Execution Waterfall**, `check_inventory` renders as a parent span containing `query_sql` as an indented child span.

---

## 🛡️ Built-in Secret Redaction & Privacy

By default, the SDK automatically sanitizes sensitive keys and high-entropy secrets from inputs, outputs, and metadata:

### Protected Dictionary Keys (Masked to `[REDACTED]`):
- `password`, `secret`, `token`, `api_key`, `authorization`, `private_key`

### Protected Regex Patterns:
- OpenAI API Keys: `sk-[a-zA-Z0-9]{20,}`
- AgentReliability Keys: `ar_live_[a-f0-9]{32}`
- AWS Access Keys: `AKIA[0-9A-Z]{16}`
- Bearer Tokens: `Bearer [a-zA-Z0-9_\-\.]{16,}`
- Email Addresses: `user@domain.com` -> `u***@domain.com`

### Custom Redaction Rules:
```python
monitor = AgentMonitor(
    redact_keys=["ssn", "credit_card", "pin"],
    redact_patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
)
```

---

## ⏱️ Latency & Timeout Measurement

The SDK measures execution duration with microsecond precision:
- Standard tool latency is recorded as `duration_ms`.
- If a tool raises `TimeoutError` or takes longer than expected, the step is automatically tagged with failure category `timeout`.

---

## ⚠️ Safe Shutdown & Background Transport

Because events are batched and transmitted in the background:
```python
# Before short-lived scripts or CLI utilities exit, call flush:
flushed = monitor.flush(timeout=5.0)
```
If the backend server is temporarily unreachable or offline, the background thread gracefully drops queued events after retrying without crashing your application.

