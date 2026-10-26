# LangChain Integration Guide

The **AgentReliability AI** LangChain integration enables zero-friction, production-grade observability, latency profiling, and error capture for LangChain applications (LCEL pipelines, agents, tools, and runnables).

---

## 1. Installation

The LangChain integration is packaged as an optional extra within the `agentreliability` SDK so core SDK users remain free of heavyweight dependencies.

```bash
# Option A: Install SDK with the LangChain extra
pip install "agentreliability[langchain]"

# Option B: Install individually in an existing environment
pip install agentreliability langchain-core>=0.3.0
```

### Supported Framework Versions
- **Python**: `>= 3.9` (including Python 3.10, 3.11, 3.12, 3.13, 3.14)
- **`langchain-core`**: `>= 0.3.0` (tested with `1.6.x` / `0.3.x`)
- **`langchain`**: Compatibility with standard LCEL runnables and agents

---

## 2. Configuration & Quickstart

To connect your LangChain workflows, import `AgentReliabilityCallbackHandler` and attach it to the `callbacks` list in your execution config:

```python
import os
from agentreliability.integrations.langchain import AgentReliabilityCallbackHandler
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 1. Initialize callback handler with your project API key
handler = AgentReliabilityCallbackHandler(
    agent_name="support_chat_agent",
    api_key=os.environ.get("AGENTRELIABILITY_API_KEY"),
    endpoint="http://127.0.0.1:8001",
    capture_io=True,  # Optional: captures prompt and output texts
)

# 2. Build your LCEL chain
prompt = ChatPromptTemplate.from_template("Translate to French: {text}")
chain = prompt | llm | StrOutputParser()

# 3. Invoke with handler attached
result = chain.invoke({"text": "Hello world"}, config={"callbacks": [handler]})

# 4. Flush background transmission before script exit
handler.flush()
```

---

## 3. Configuration Options

`AgentReliabilityCallbackHandler` accepts standard SDK configuration parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_name` | `Optional[str]` | `"langchain_agent"` | Name displayed in the Live Agent Monitoring dashboard. |
| `api_key` | `Optional[str]` | `ENV: AGENTRELIABILITY_API_KEY` | Project secret key (`ar_live_...`). |
| `endpoint` | `Optional[str]` | `http://127.0.0.1:8001` | URL of the AgentReliability FastAPI backend. |
| `capture_io` | `Optional[bool]` | `False` | Whether to record inputs and outputs (privacy-safe, defaults to off). |
| `metadata` | `Optional[dict]` | `{}` | Key-value pairs attached to execution start (e.g. environment, version). |
| `redact_keys` | `Iterable[str]` | `()` | Additional field keys to mask in captured dictionaries. |
| `redact_patterns` | `Iterable[Pattern]` | `()` | Additional regex patterns to mask in text payloads. |
| `ignore_llm` | `bool` | `False` | When `True`, skips creating spans for raw LLM model calls. |
| `ignore_chain` | `bool` | `False` | When `True`, skips creating spans for intermediate child runnables. |

---

## 4. Synchronous and Asynchronous Execution

The callback handler seamlessly supports both synchronous (`invoke`) and asynchronous (`ainvoke`) LangChain calls:

### Async Example (`ainvoke`)

```python
import asyncio
from agentreliability.integrations.langchain import AgentReliabilityCallbackHandler

async def run_async_pipeline():
    handler = AgentReliabilityCallbackHandler(
        agent_name="async_support_agent",
        capture_io=True,
    )

    # Async invocation
    result = await chain.ainvoke({"input": "test"}, config={"callbacks": [handler]})
    
    # Flush asynchronously or synchronously
    handler.flush()
    return result

asyncio.run(run_async_pipeline())
```

---

## 5. Capturing Tool Executions & Span Hierarchy

When functions decorated with `@tool` are invoked within your chain, `AgentReliabilityCallbackHandler` captures each tool invocation as a child span:

```python
from langchain_core.tools import tool

@tool
def calculate_tax(amount: float) -> float:
    """Calculate standard 10% sales tax."""
    return round(amount * 0.10, 2)

# Tool calls inside a chain automatically appear nested in the waterfall timeline!
```

### Generated Trace Structure:
- **`execution_start`**: Root execution created with chain name and inputs.
- **`tool_call` (Node Span)**: Intermediate runnables and step boundaries.
- **`tool_call` (Tool Span)**: Explicit tool calls with tool name, arguments, and return values.
- **`tool_call` (LLM Span)**: LLM calls with latency and reported token counts.
- **`execution_end`**: Root execution duration and status (`success` or `failed`).

---

## 6. Privacy & Redaction Behavior

1. **Client-Side Redaction**: Sensitive keys like `api_key`, `authorization`, `password`, `secret`, and `token` are masked (`"[REDACTED]"`) on the client machine before HTTP transmission.
2. **Payload Bounding**: Payloads larger than 16 KB are safely bounded to prevent memory or storage exhaustion.
3. **Opt-in Input/Output**: By default, `capture_io=False`. Telemetry only records step durations, statuses, and tool sequences unless explicitly enabled.
4. **Token Counts**: Token metrics (`prompt_tokens`, `completion_tokens`, `total_tokens`) are only recorded when reported by the underlying model's `llm_output`. No token costs are ever fabricated.

---

## 7. Common Errors & Troubleshooting

### `ImportError: LangChain is not installed`
- **Cause**: Attempting to import `agentreliability.integrations.langchain` without `langchain-core` installed.
- **Fix**: Run `pip install "agentreliability[langchain]"` or `pip install langchain-core`.

### Traces not appearing in dashboard
1. Confirm your FastAPI backend is running on port `8001` (`http://localhost:8001/api/health`).
2. Verify you called `handler.flush()` before short scripts terminate.
3. Ensure your `AGENTRELIABILITY_API_KEY` matches the active project in the dashboard.

---

## 8. Known Limitations
- Streaming tokens (`on_llm_new_token`) are not recorded as individual spans to avoid flooding the network with thousands of micro-events.
- Arbitrary custom callback events (`on_custom_event`) are ignored unless mapped to standard tool or node events.

