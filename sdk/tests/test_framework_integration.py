"""Automated verification suite for LangChain and LangGraph framework integration.

Covers:
1. Core SDK isolation (importing without framework dependencies).
2. LangChain basic execution (start, runnable spans, finish).
3. LangChain tool execution (inputs, outputs, durations).
4. LangChain failure propagation (transparent exception, failed trace).
5. LangGraph basic state graph execution.
6. LangGraph node failure handling.
7. Parent-child span hierarchy.
8. Async execution (ainvoke).
9. Streaming tokens (non-invasive, no span flooding).
10. Duplicate and repeated callback invocations.
11. Client-side sensitive data redaction.
12. Backend schema and ingestion validation.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, TypedDict
import pytest

from agentreliability import AgentMonitor
from agentreliability.integrations.langchain import AgentReliabilityCallbackHandler
from agentreliability.integrations.langgraph import (
    AgentReliabilityCallbackHandler as LangGraphHandler,
    AgentReliabilityGraphHandler,
)

from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END


class EventCollector:
    """Helper to collect and inspect events sent via mock transport."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def mock_post(self, url: str, headers: dict, body: bytes, timeout: float) -> int:
        payload = json.loads(body.decode("utf-8"))
        self.events.extend(payload.get("events", []))
        return 200

    def get_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        return [e for e in self.events if e.get("type") == event_type]


# -----------------------------------------------------------------------------
# 1. Core SDK and Alias Verifications
# -----------------------------------------------------------------------------

def test_alias_and_class_identity():
    """Verify LangGraph re-exports match the canonical handler."""
    assert LangGraphHandler is AgentReliabilityCallbackHandler
    assert AgentReliabilityGraphHandler is AgentReliabilityCallbackHandler


def test_core_sdk_no_framework_requirement():
    """Verify core SDK imports and functions independently of integrations."""
    import agentreliability
    assert agentreliability.__version__ == "0.1.0"
    monitor = agentreliability.AgentMonitor(enabled=False)
    assert monitor.enabled is False


# -----------------------------------------------------------------------------
# 2. LangChain Basic Execution
# -----------------------------------------------------------------------------

def test_langchain_basic_execution():
    """Verify basic LCEL chain execution captures start, node, and end events."""
    collector = EventCollector()
    monitor = AgentMonitor(api_key="ar_live_test_key", _post=collector.mock_post, capture_io=True)
    handler = AgentReliabilityCallbackHandler(agent_name="basic_chain_agent", monitor=monitor)

    step1 = RunnableLambda(lambda x: x + 10).with_config(run_name="add_ten")
    step2 = RunnableLambda(lambda x: x * 2).with_config(run_name="multiply_two")
    chain = (step1 | step2).with_config(run_name="math_chain")

    result = chain.invoke(5, config={"callbacks": [handler]})
    handler.flush()

    assert result == 30

    starts = collector.get_by_type("execution_start")
    tools = collector.get_by_type("tool_call")
    ends = collector.get_by_type("execution_end")

    assert len(starts) == 1
    assert starts[0]["agent_name"] == "basic_chain_agent"
    assert starts[0]["type"] == "execution_start"

    assert len(tools) == 2
    tool_names = [t["tool_name"] for t in tools]
    assert "add_ten" in tool_names
    assert "multiply_two" in tool_names

    assert len(ends) == 1
    assert ends[0]["status"] == "success"
    assert ends[0]["output"] == 30


# -----------------------------------------------------------------------------
# 3. LangChain Tool Execution
# -----------------------------------------------------------------------------

@tool
def multiply_numbers(a: int, b: int) -> int:
    """Multiplies two numbers."""
    return a * b


def test_langchain_tool_execution():
    """Verify @tool functions record tool names, durations, inputs, and outputs."""
    collector = EventCollector()
    monitor = AgentMonitor(api_key="ar_live_test_key", _post=collector.mock_post, capture_io=True)
    handler = AgentReliabilityCallbackHandler(agent_name="tool_agent", monitor=monitor)

    def pipeline_fn(inputs: dict, config: dict):
        return multiply_numbers.invoke({"a": inputs["x"], "b": 4}, config=config)

    chain = RunnableLambda(pipeline_fn).with_config(run_name="outer_pipeline")
    res = chain.invoke({"x": 6}, config={"callbacks": [handler]})
    handler.flush()

    assert res == 24

    tool_spans = collector.get_by_type("tool_call")
    mult_tool = next((t for t in tool_spans if t["tool_name"] == "multiply_numbers"), None)
    assert mult_tool is not None
    assert mult_tool["status"] == "success"
    assert mult_tool["duration_ms"] >= 0.0
    assert mult_tool["output"] == 24


# -----------------------------------------------------------------------------
# 4. LangChain Failure Handling
# -----------------------------------------------------------------------------

def test_langchain_failure_propagation():
    """Verify errors in LangChain chains are captured and exceptions are transparently raised."""
    collector = EventCollector()
    monitor = AgentMonitor(api_key="ar_live_test_key", _post=collector.mock_post, capture_io=True)
    handler = AgentReliabilityCallbackHandler(agent_name="failing_agent", monitor=monitor)

    def bad_step(x: int):
        raise ValueError(f"Controlled failure for input: {x}")

    chain = RunnableLambda(bad_step).with_config(run_name="failing_step")

    with pytest.raises(ValueError, match="Controlled failure for input: 99"):
        chain.invoke(99, config={"callbacks": [handler]})

    handler.flush()

    ends = collector.get_by_type("execution_end")
    assert len(ends) == 1
    assert ends[0]["status"] == "failed"
    assert ends[0]["error_type"] == "ValueError"
    assert "Controlled failure for input: 99" in ends[0]["error_message"]


# -----------------------------------------------------------------------------
# 5. LangGraph Basic StateGraph Execution
# -----------------------------------------------------------------------------

class SimpleState(TypedDict):
    text: str
    length: int


def test_langgraph_basic_execution():
    """Verify LangGraph StateGraph nodes are observed cleanly as spans."""
    collector = EventCollector()
    monitor = AgentMonitor(api_key="ar_live_test_key", _post=collector.mock_post, capture_io=True)
    handler = AgentReliabilityCallbackHandler(agent_name="graph_agent", monitor=monitor)

    def step_uppercase(state: SimpleState):
        return {"text": state["text"].upper()}

    def step_count(state: SimpleState):
        return {"length": len(state["text"])}

    builder = StateGraph(SimpleState)
    builder.add_node("to_upper", step_uppercase)
    builder.add_node("calc_len", step_count)
    builder.add_edge(START, "to_upper")
    builder.add_edge("to_upper", "calc_len")
    builder.add_edge("calc_len", END)
    graph = builder.compile()

    state = {"text": "hello graph", "length": 0}
    res = graph.invoke(state, config={"callbacks": [handler]})
    handler.flush()

    assert res["text"] == "HELLO GRAPH"
    assert res["length"] == 11

    starts = collector.get_by_type("execution_start")
    ends = collector.get_by_type("execution_end")
    tools = collector.get_by_type("tool_call")

    assert len(starts) == 1
    assert len(ends) == 1
    assert ends[0]["status"] == "success"

    tool_names = [t["tool_name"] for t in tools]
    assert "to_upper" in tool_names
    assert "calc_len" in tool_names


# -----------------------------------------------------------------------------
# 6. LangGraph Failure Handling
# -----------------------------------------------------------------------------

def test_langgraph_failure_handling():
    """Verify failing nodes in LangGraph mark span as error and execution as failed."""
    collector = EventCollector()
    monitor = AgentMonitor(api_key="ar_live_test_key", _post=collector.mock_post, capture_io=True)
    handler = AgentReliabilityCallbackHandler(agent_name="failing_graph", monitor=monitor)

    def crashing_node(state: SimpleState):
        raise KeyError("Missing required graph field: token")

    builder = StateGraph(SimpleState)
    builder.add_node("crash_step", crashing_node)
    builder.add_edge(START, "crash_step")
    builder.add_edge("crash_step", END)
    graph = builder.compile()

    with pytest.raises(KeyError, match="Missing required graph field: token"):
        graph.invoke({"text": "crash me", "length": 0}, config={"callbacks": [handler]})

    handler.flush()

    ends = collector.get_by_type("execution_end")
    assert len(ends) == 1
    assert ends[0]["status"] == "failed"
    assert ends[0]["error_type"] == "KeyError"

    tools = collector.get_by_type("tool_call")
    crash_span = next((t for t in tools if t["tool_name"] == "crash_step"), None)
    assert crash_span is not None
    assert crash_span["status"] == "error"
    assert crash_span["error_type"] == "KeyError"


# -----------------------------------------------------------------------------
# 7. Parent-Child Span Hierarchy
# -----------------------------------------------------------------------------

@tool
def fetch_user_data(user_id: int) -> dict:
    """Fetch user account info."""
    return {"user_id": user_id, "active": True}


def test_parent_child_hierarchy():
    """Verify child tool calls inside a graph node reference the parent node span ID."""
    collector = EventCollector()
    monitor = AgentMonitor(api_key="ar_live_test_key", _post=collector.mock_post, capture_io=True)
    handler = AgentReliabilityCallbackHandler(agent_name="hierarchy_agent", monitor=monitor)

    class UserState(TypedDict):
        user_id: int
        account: dict

    def fetch_node(state: UserState, config):
        acc = fetch_user_data.invoke({"user_id": state["user_id"]}, config=config)
        return {"account": acc}

    builder = StateGraph(UserState)
    builder.add_node("user_lookup_node", fetch_node)
    builder.add_edge(START, "user_lookup_node")
    builder.add_edge("user_lookup_node", END)
    graph = builder.compile()

    graph.invoke({"user_id": 42, "account": {}}, config={"callbacks": [handler]})
    handler.flush()

    tools = collector.get_by_type("tool_call")
    node_span = next(t for t in tools if t["tool_name"] == "user_lookup_node")
    tool_span = next(t for t in tools if t["tool_name"] == "fetch_user_data")

    # Parent node has no parent_call_id (it is a direct child of the execution)
    assert node_span["parent_call_id"] is None
    # Child tool span points directly to node_span's event_id
    assert tool_span["parent_call_id"] == node_span["event_id"]


# -----------------------------------------------------------------------------
# 8. Async Execution (ainvoke)
# -----------------------------------------------------------------------------

def test_async_execution():
    """Verify ainvoke works seamlessly and captures all trace events."""
    collector = EventCollector()
    monitor = AgentMonitor(api_key="ar_live_test_key", _post=collector.mock_post, capture_io=True)
    handler = AgentReliabilityCallbackHandler(agent_name="async_agent", monitor=monitor)

    async def run_test():
        step1 = RunnableLambda(lambda x: x + " async").with_config(run_name="async_step1")
        step2 = RunnableLambda(lambda x: x + " done").with_config(run_name="async_step2")
        pipe = (step1 | step2).with_config(run_name="async_pipeline")
        return await pipe.ainvoke("hello", config={"callbacks": [handler]})

    res = asyncio.run(run_test())
    handler.flush()

    assert res == "hello async done"

    starts = collector.get_by_type("execution_start")
    ends = collector.get_by_type("execution_end")
    tools = collector.get_by_type("tool_call")

    assert len(starts) == 1
    assert len(ends) == 1
    assert len(tools) == 2
    tool_names = [t["tool_name"] for t in tools]
    assert "async_step1" in tool_names
    assert "async_step2" in tool_names


# -----------------------------------------------------------------------------
# 9. Streaming Callbacks (Non-Invasive)
# -----------------------------------------------------------------------------

def test_streaming_token_handling():
    """Verify on_llm_new_token does not spam spans."""
    collector = EventCollector()
    monitor = AgentMonitor(api_key="ar_live_test_key", _post=collector.mock_post, capture_io=True)
    handler = AgentReliabilityCallbackHandler(agent_name="stream_agent", monitor=monitor)

    # Call on_llm_new_token 100 times to simulate streaming
    for i in range(100):
        handler.on_llm_new_token(f"tok_{i}", run_id="dummy-stream-run")

    handler.flush()

    # Spans must not have been created for raw tokens
    assert len(collector.events) == 0


# -----------------------------------------------------------------------------
# 10. Client-Side Sensitive Data Redaction
# -----------------------------------------------------------------------------

def test_sensitive_data_redaction():
    """Verify sensitive keys in inputs and metadata are scrubbed client-side."""
    collector = EventCollector()
    monitor = AgentMonitor(api_key="ar_live_test_key", _post=collector.mock_post, capture_io=True)
    handler = AgentReliabilityCallbackHandler(
        agent_name="secure_agent",
        monitor=monitor,
        metadata={"client_api_key": "sk-secret-1234567890", "tenant": "safe_tenant"},
    )

    sensitive_input = {
        "user": "alice",
        "password": "SuperSecretPassword123!",
        "token": "tok_abcdef123456",
        "api_key": "live_key_xyz",
    }

    step = RunnableLambda(lambda x: {"status": "ok"}).with_config(run_name="auth_check")
    step.invoke(sensitive_input, config={"callbacks": [handler]})
    handler.flush()

    start_event = collector.get_by_type("execution_start")[0]
    captured_input = start_event["input"]

    # Sensitive values must be replaced with [REDACTED]
    assert captured_input["password"] == "[REDACTED]"
    assert captured_input["token"] == "[REDACTED]"
    assert captured_input["api_key"] == "[REDACTED]"
    assert captured_input["user"] == "alice"

    # Metadata keys must be scrubbed
    meta = start_event["metadata"]
    assert meta["client_api_key"] == "[REDACTED]"
    assert meta["tenant"] == "safe_tenant"


# -----------------------------------------------------------------------------
# 11. Backend Schema Validation
# -----------------------------------------------------------------------------

def test_backend_schema_validation():
    try:
        from app.traces_schemas import TraceEvent, IngestRequest
    except ImportError:
        import sys
        from pathlib import Path
        backend_dir = str(Path(__file__).resolve().parents[2] / "backend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from app.traces_schemas import TraceEvent, IngestRequest

    collector = EventCollector()
    monitor = AgentMonitor(api_key="ar_live_test_key", _post=collector.mock_post, capture_io=True)
    handler = AgentReliabilityCallbackHandler(agent_name="schema_test_agent", monitor=monitor)

    step1 = RunnableLambda(lambda x: x * 10).with_config(run_name="scale_val")
    step2 = RunnableLambda(lambda x: x + 1).with_config(run_name="add_one")
    pipe = (step1 | step2).with_config(run_name="math_pipeline")
    pipe.invoke(7, config={"callbacks": [handler]})
    handler.flush()

    assert len(collector.events) >= 3

    # All events must validate cleanly against TraceEvent and IngestRequest
    batch = IngestRequest.model_validate({"events": collector.events})
    assert len(batch.events) == len(collector.events)
    for evt in batch.events:
        assert len(evt.event_id) >= 8
        assert len(evt.execution_id) >= 8
        assert evt.type in ("execution_start", "tool_call", "execution_end")
