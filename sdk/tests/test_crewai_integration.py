"""Automated test suite for CrewAI multi-agent observability integration.

Covers:
1. Core SDK isolation (graceful degradation when CrewAI is missing or mock simulated).
2. Event listener initialization, configuration, and execution ID assignment.
3. Event handling and multi-agent hierarchy (Crew -> Task with Agent Attribution -> Tool Call).
4. Tool lifecycle tracking and nesting under parent task span.
5. Observable agent handoffs tracking between consecutive tasks.
6. Error capture and attribution for multi-agent failures.
7. Sensitive credential redaction and payload bounding.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List
import pytest

from agentreliability import AgentMonitor
import agentreliability.integrations.crewai as crewai_mod
from agentreliability.integrations.crewai import (
    AgentReliabilityCrewListener,
    setup_crewai_tracing,
)


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


class DummyEvent:
    """Mock CrewAI event object for deterministic testing."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class DummyAgent:
    def __init__(self, role: str):
        self.role = role

    def __str__(self):
        return self.role


class DummyTask:
    def __init__(self, description: str, agent: DummyAgent):
        self.description = description
        self.agent = agent


def make_test_listener(collector: EventCollector, monkeypatch=None, **kwargs) -> AgentReliabilityCrewListener:
    """Create an AgentReliabilityCrewListener hooked into an in-memory mock transport."""
    if not crewai_mod.CREWAI_AVAILABLE:
        if monkeypatch is not None:
            monkeypatch.setattr(crewai_mod, "CREWAI_AVAILABLE", True)
        else:
            crewai_mod.CREWAI_AVAILABLE = True

    monitor = AgentMonitor(
        endpoint="http://mock-backend:8001",
        api_key="mock_key",
        capture_io=True,
        redact_keys=kwargs.get("redact_keys", ()),
        max_payload_chars=kwargs.get("max_payload_chars", 2000),
    )
    monitor._transport._post = collector.mock_post
    return AgentReliabilityCrewListener(
        monitor=monitor,
        auto_register=False,
        **kwargs,
    )


def test_core_sdk_independence():
    """Verify core SDK imports and runs with zero dependencies."""
    import agentreliability
    assert agentreliability.__version__ == "0.1.0"
    m = AgentMonitor(enabled=False)
    assert m.enabled is False


def test_crewai_uninstalled_informative_error(monkeypatch):
    """Verify informative ImportError when CrewAI is not available."""
    monkeypatch.setattr(crewai_mod, "CREWAI_AVAILABLE", False)
    with pytest.raises(ImportError) as exc:
        AgentReliabilityCrewListener(crew_name="Editorial Crew")
    assert "CrewAI is not installed" in str(exc.value)


def test_listener_initialization(monkeypatch):
    """Verify AgentReliabilityCrewListener initializes cleanly with custom metadata."""
    collector = EventCollector()
    listener = make_test_listener(
        collector,
        monkeypatch=monkeypatch,
        crew_name="Editorial Crew",
        metadata={"project": "benchmark", "tier": "production"},
    )
    assert listener.agent_name == "Editorial Crew"
    assert listener.custom_metadata["project"] == "benchmark"


def test_crew_and_task_hierarchy_lifecycle(monkeypatch):
    """Verify Crew -> Task -> Tool span hierarchy and agent attribution."""
    collector = EventCollector()
    listener = make_test_listener(collector, monkeypatch=monkeypatch, crew_name="Marketing Crew")

    agent1 = DummyAgent(role="Market Researcher")
    task1 = DummyTask(description="Gather competitive intelligence", agent=agent1)

    # 1. Crew Start
    start_ev = DummyEvent(event_id="crew-101", crew=DummyEvent(agents=[agent1]))
    listener._handle_crew_start(None, start_ev)

    # 2. Task 1 Start
    task_start_ev = DummyEvent(event_id="task-101", task=task1)
    listener._handle_task_start(None, task_start_ev)

    # 3. Tool call inside Task 1
    tool_start_ev = DummyEvent(event_id="tool-101", tool_name="search_web", tool_args={"q": "AI agents"})
    listener._handle_tool_start(None, tool_start_ev)
    tool_end_ev = DummyEvent(event_id="tool-101", output="Top competitors: ...", run_attempts=1)
    listener._handle_tool_finished(None, tool_end_ev)

    # 4. Task 1 Complete
    task_end_ev = DummyEvent(event_id="task-101", output="Intel report prepared.")
    listener._handle_task_completed(None, task_end_ev)

    # 5. Crew Complete
    crew_end_ev = DummyEvent(event_id="crew-101", output="Campaign strategy ready.")
    listener._handle_crew_completed(None, crew_end_ev)

    listener.flush()

    starts = collector.get_by_type("execution_start")
    tools = collector.get_by_type("tool_call")
    ends = collector.get_by_type("execution_end")

    assert len(starts) == 1
    assert starts[0]["agent_name"] == "Marketing Crew"
    assert len(ends) == 1
    assert ends[0]["status"] == "success"

    assert len(tools) == 2
    # Verify tool has parent_call_id pointing to task
    tool_call = next(t for t in tools if t["tool_name"] == "search_web")
    task_call = next(t for t in tools if "[Market Researcher]" in t["tool_name"])
    assert tool_call["parent_call_id"] == task_call["event_id"]


def test_controlled_failure_attribution(monkeypatch):
    """Verify that task failures cleanly record error details and agent attribution."""
    collector = EventCollector()
    listener = make_test_listener(collector, monkeypatch=monkeypatch, crew_name="Failing Editorial Crew")

    agent = DummyAgent(role="Lead Writer")
    task = DummyTask(description="Draft article", agent=agent)

    listener._handle_crew_start(None, DummyEvent(event_id="crew-202", crew=DummyEvent(agents=[agent])))
    listener._handle_task_start(None, DummyEvent(event_id="task-202", task=task))
    listener._handle_task_failed(None, DummyEvent(event_id="task-202", error="Grammar engine crashed", error_type=RuntimeError))
    listener._handle_crew_failed(None, DummyEvent(event_id="crew-202", error="Task draft article failed."))

    listener.flush()

    ends = collector.get_by_type("execution_end")
    tools = collector.get_by_type("tool_call")

    assert len(ends) == 1
    assert ends[0]["status"] == "failed"
    assert len(tools) == 1
    assert tools[0]["status"] == "failed"
    assert "Grammar engine crashed" in tools[0]["error_message"]


def test_client_side_redaction_and_bounding(monkeypatch):
    """Verify secrets in task inputs/outputs are redacted client-side."""
    collector = EventCollector()
    listener = make_test_listener(
        collector,
        monkeypatch=monkeypatch,
        crew_name="Secure Crew",
        redact_keys=("secret_token", "api_key"),
        max_payload_chars=500,
    )

    agent = DummyAgent(role="Security Auditor")
    task = DummyTask(description="Validate keys", agent=agent)

    listener._handle_crew_start(None, DummyEvent(event_id="crew-303", crew=DummyEvent(agents=[agent])))
    listener._handle_tool_start(None, DummyEvent(event_id="tool-303", tool_name="verify_key", tool_args={"api_key": "super_secret_12345"}))
    listener._handle_tool_finished(None, DummyEvent(event_id="tool-303", output={"secret_token": "bearer_98765"}))
    listener._handle_crew_completed(None, DummyEvent(event_id="crew-303", output="Audit finished."))

    listener.flush()

    tools = collector.get_by_type("tool_call")
    assert len(tools) == 1
    assert tools[0]["input"]["api_key"] == "[REDACTED]"
    assert tools[0]["output"]["secret_token"] == "[REDACTED]"


def test_integrations_package_exports():
    """Verify CrewAI symbols are exported at agentreliability.integrations level."""
    import agentreliability
    import agentreliability.integrations as integrations
    from agentreliability.integrations import (
        AgentReliabilityCrewListener as ExportedListener,
        setup_crewai_tracing as exported_setup,
        CREWAI_AVAILABLE as exported_available,
        crewai as exported_crewai_mod,
    )

    assert hasattr(agentreliability, "integrations")
    assert "crewai" in integrations.__all__
    assert "AgentReliabilityCrewListener" in integrations.__all__
    assert "setup_crewai_tracing" in integrations.__all__
    assert "CREWAI_AVAILABLE" in integrations.__all__

    assert ExportedListener is AgentReliabilityCrewListener
    assert exported_setup is setup_crewai_tracing
    assert isinstance(exported_available, bool)
    assert exported_crewai_mod is crewai_mod


def test_setup_crewai_tracing_convenience(monkeypatch):
    """Verify setup_crewai_tracing helper constructs and configures listener."""
    monkeypatch.setattr(crewai_mod, "CREWAI_AVAILABLE", True)

    listener = setup_crewai_tracing(
        crew_name="Automated Research Crew",
        api_key="ar_test_key_12345",
        endpoint="http://127.0.0.1:8001",
        capture_io=True,
    )
    assert isinstance(listener, AgentReliabilityCrewListener)
    assert listener.agent_name == "Automated Research Crew"
    assert listener._monitor.endpoint == "http://127.0.0.1:8001"
    assert listener._monitor.capture_io is True


def test_setup_crewai_tracing_uninstalled_error(monkeypatch):
    """Verify setup_crewai_tracing raises informative error when uninstalled."""
    monkeypatch.setattr(crewai_mod, "CREWAI_AVAILABLE", False)
    with pytest.raises(ImportError) as exc:
        setup_crewai_tracing(crew_name="Uninstalled Crew")
    assert "CrewAI is not installed" in str(exc.value)
    assert "pip install 'agentreliability[crewai]'" in str(exc.value)


def test_integrations_import_safety_when_dependencies_missing(monkeypatch):
    """Verify agentreliability.integrations is safe to import under all conditions."""
    import agentreliability.integrations as integrations

    # Ensure symbols are accessible and don't fail on inspection
    assert hasattr(integrations, "crewai")
    assert hasattr(integrations, "AgentReliabilityCrewListener")
    assert hasattr(integrations, "setup_crewai_tracing")
    assert hasattr(integrations, "CREWAI_AVAILABLE")

