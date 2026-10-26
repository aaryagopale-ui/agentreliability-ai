"""LangGraph Integration for AgentReliability AI.

Provides convenient re-exports and helpers for LangGraph workflows.

```python
from agentreliability.integrations.langgraph import AgentReliabilityCallbackHandler

handler = AgentReliabilityCallbackHandler(
    agent_name="support_graph",
    api_key="ar_live_...",
    endpoint="http://127.0.0.1:8001",
)

result = graph.invoke(initial_state, config={"callbacks": [handler]})
handler.flush()
```
"""
from __future__ import annotations

from .langchain import AgentReliabilityCallbackHandler

# Alias for developers preferring explicit graph naming
AgentReliabilityGraphHandler = AgentReliabilityCallbackHandler

__all__ = ["AgentReliabilityCallbackHandler", "AgentReliabilityGraphHandler"]

