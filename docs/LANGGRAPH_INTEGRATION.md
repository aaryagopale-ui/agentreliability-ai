# LangGraph Integration Guide

The **AgentReliability AI** LangGraph integration provides native tracing, step latency breakdown, node error isolation, and replay compatibility for multi-agent and stateful graph architectures.

---

## 1. Installation

Install the `agentreliability` SDK with the `langgraph` extra:

```bash
# Option A: Install SDK with the LangGraph extra
pip install "agentreliability[langgraph]"

# Option B: Install in an existing LangGraph environment
pip install agentreliability langgraph>=0.2.0 langchain-core>=0.3.0
```

### Supported Framework Versions
- **Python**: `>= 3.9` (including Python 3.10 - 3.14)
- **`langgraph`**: `>= 0.2.0` (tested with `1.2.x`)
- **`langchain-core`**: `>= 0.3.0`

---

## 2. Configuration & Quickstart

Attach `AgentReliabilityCallbackHandler` to your graph invocations using standard LangGraph `config`:

```python
import os
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from agentreliability.integrations.langgraph import AgentReliabilityCallbackHandler

# 1. Define State
class AgentState(TypedDict):
    input_text: str
    processed_text: str
    status: str

# 2. Define Nodes
def clean_input_node(state: AgentState):
    return {"processed_text": state["input_text"].strip().lower()}

def process_node(state: AgentState):
    return {"status": "completed"}

# 3. Assemble Graph
builder = StateGraph(AgentState)
builder.add_node("clean_input", clean_input_node)
builder.add_node("process", process_node)
builder.add_edge(START, "clean_input")
builder.add_edge("clean_input", "process")
builder.add_edge("process", END)

graph = builder.compile()

# 4. Attach Handler and Execute
handler = AgentReliabilityCallbackHandler(
    agent_name="data_processing_graph",
    api_key=os.environ.get("AGENTRELIABILITY_API_KEY"),
    endpoint="http://127.0.0.1:8001",
    capture_io=True,
)

state = {"input_text": "  Sample Raw Input  ", "processed_text": "", "status": "pending"}
result = graph.invoke(state, config={"callbacks": [handler]})

# 5. Flush traces
handler.flush()
```

---

## 3. Observable Graph Telemetry vs. Limitations

### What is Captured:
- **Graph Execution Lifecycle**: Start timestamp, overall graph duration, final status (`success` or `failed`).
- **Node Execution Spans**: Each executed node is captured with its name (e.g. `clean_input`, `process`), duration in milliseconds, inputs, and outputs.
- **Tools Invoked Inside Nodes**: When tools (`@tool`) are invoked inside nodes with propagated config, they appear hierarchically nested under the corresponding node in the visual waterfall timeline.
- **Failures & Exceptions**: If a node raises an unhandled exception, AgentReliability records the failing node name, exception type, and stack trace message while letting Python propagate the exception cleanly.

### What is NOT Captured (Framework Boundary):
- AgentReliability observes the framework via the public callback API. Internal Pregel channel pointers, checkpoint binary blobs, and uninvoked conditional branches are not intercepted or fabricated.

---

## 4. Error Handling and Failure Analysis

When a node fails, AgentReliability records the error evidence directly into the trace:

```python
def failing_node(state: AgentState):
    # Simulated failure
    raise ValueError("Inventory check failed: Product out of stock")
```

### Dashboard Failure Analysis:
- The execution timeline highlights the failing node in **Red**.
- The **Failure Analysis Dashboard** automatically analyzes the error:
  - Categorizes the root cause (e.g., `failed_tool_call` or `unexpected_exception`).
  - Identifies preceding successful steps.
  - Suggests targeted remediation steps.

---

## 5. Trace-to-Test Regression Testing

Any captured LangGraph trace can be converted into an automated regression test with one click in the AgentReliability Dashboard:
1. Open **Live Agent Monitoring**.
2. Select the completed LangGraph execution.
3. Click **"Convert to Test Case"**.
4. The deterministic replay engine will assert that future changes to your graph logic preserve expected node execution sequences and outputs!

