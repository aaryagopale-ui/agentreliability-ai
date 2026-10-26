"""CrewAI Multi-Agent Observability Integration for AgentReliability AI.

Provides `AgentReliabilityCrewListener` and `setup_crewai_tracing` to capture
real multi-agent executions, task lifecycles, tool calls, errors, and observable
handoffs from CrewAI workflows.

Usage:
```python
from agentreliability.integrations.crewai import setup_crewai_tracing

# 1. Attach listener to CrewAI event bus
listener = setup_crewai_tracing(
    agent_name="research_and_writer_crew",
    api_key="ar_live_...",
    endpoint="http://127.0.0.1:8001",
    capture_io=True,
)

# 2. Run CrewAI crew normally
crew = Crew(agents=[researcher, writer], tasks=[task1, task2])
result = crew.kickoff()

# 3. Transmit telemetry to dashboard
listener.flush()
```

Golden Invariants:
1. Never crashes agent execution. All callbacks run in defensive try/except.
2. Truly optional: core SDK works 100% without CrewAI installed.
3. Observes real CrewAI events (no fabricated spans or handoffs).
4. Full parent-child hierarchy: Crew -> Task -> Tool Call.
5. Client-side sensitive credential redaction and payload bounding.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Union

try:
    from crewai.events import BaseEventListener, crewai_event_bus
    from crewai.events.types.crew_events import (
        CrewKickoffStartedEvent,
        CrewKickoffCompletedEvent,
        CrewKickoffFailedEvent,
    )
    from crewai.events.types.task_events import (
        TaskStartedEvent,
        TaskCompletedEvent,
        TaskFailedEvent,
    )
    from crewai.events.types.agent_events import (
        AgentExecutionStartedEvent,
        AgentExecutionCompletedEvent,
        AgentExecutionErrorEvent,
    )
    from crewai.events.types.tool_usage_events import (
        ToolUsageStartedEvent,
        ToolUsageFinishedEvent,
        ToolUsageErrorEvent,
    )
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    BaseEventListener = object  # type: ignore[misc,assignment]
    crewai_event_bus = None  # type: ignore[assignment]
    CrewKickoffStartedEvent = None  # type: ignore[assignment]
    CrewKickoffCompletedEvent = None  # type: ignore[assignment]
    CrewKickoffFailedEvent = None  # type: ignore[assignment]
    TaskStartedEvent = None  # type: ignore[assignment]
    TaskCompletedEvent = None  # type: ignore[assignment]
    TaskFailedEvent = None  # type: ignore[assignment]
    AgentExecutionStartedEvent = None  # type: ignore[assignment]
    AgentExecutionCompletedEvent = None  # type: ignore[assignment]
    AgentExecutionErrorEvent = None  # type: ignore[assignment]
    ToolUsageStartedEvent = None  # type: ignore[assignment]
    ToolUsageFinishedEvent = None  # type: ignore[assignment]
    ToolUsageErrorEvent = None  # type: ignore[assignment]

from agentreliability.monitor import AgentMonitor

log = logging.getLogger("agentreliability.integrations.crewai")


def _now() -> str:
    """Return current ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class AgentReliabilityCrewListener(BaseEventListener):
    """CrewAI Event Listener that maps multi-agent events to AgentReliability AI traces."""

    def __init__(
        self,
        agent_name: Optional[str] = None,
        *,
        crew_name: Optional[str] = None,
        monitor: Optional[AgentMonitor] = None,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        capture_io: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
        redact_keys: Iterable[str] = (),
        redact_patterns: Iterable[Any] = (),
        max_payload_chars: int = 2000,
        execution_id: Optional[str] = None,
        auto_register: bool = True,
    ):
        if not CREWAI_AVAILABLE:
            raise ImportError(
                "CrewAI is not installed. To use the CrewAI integration, install crewai: "
                "pip install 'agentreliability[crewai]' or pip install crewai"
            )

        self.agent_name = agent_name or crew_name
        self.custom_metadata = dict(metadata or {})
        self._preset_execution_id = execution_id
        self._last_execution_id = execution_id

        if monitor is not None:
            self._monitor = monitor
        else:
            self._monitor = AgentMonitor(
                endpoint=endpoint,
                api_key=api_key,
                capture_io=capture_io,
                metadata=self.custom_metadata,
                redact_keys=redact_keys,
                redact_patterns=redact_patterns,
                max_payload_chars=max_payload_chars,
            )

        self._lock = threading.Lock()
        self._active_crews: Dict[str, Dict[str, Any]] = {}
        self._active_tasks: Dict[str, Dict[str, Any]] = {}
        self._active_tools: Dict[str, Dict[str, Any]] = {}
        self._active_agents: Dict[str, Dict[str, Any]] = {}
        self._last_agent_by_crew: Dict[str, str] = {}
        self._handoffs: List[Dict[str, Any]] = []

        self._listeners_registered = False
        if auto_register and crewai_event_bus is not None:
            super().__init__()
            self._listeners_registered = True

    @property
    def execution_id(self) -> Optional[str]:
        """Return the current or most recent crew execution ID."""
        with self._lock:
            if self._last_execution_id:
                return self._last_execution_id
            if self._active_crews:
                latest = list(self._active_crews.values())[-1]
                return latest.get("execution_id")
            return self._preset_execution_id

    @property
    def monitor(self) -> AgentMonitor:
        """Access the underlying AgentMonitor instance."""
        return self._monitor

    def flush(self, timeout: float = 3.0) -> None:
        """Wait for pending traces to be transmitted to the backend."""
        self._monitor.flush(timeout=timeout)

    def setup_listeners(self, bus: Any) -> None:
        """Setup event listeners on the CrewAI event bus."""
        if not bus or self._listeners_registered:
            return

        try:
            @bus.on(CrewKickoffStartedEvent)
            def on_crew_start(source: Any, event: Any) -> None:
                self._handle_crew_start(source, event)

            @bus.on(CrewKickoffCompletedEvent)
            def on_crew_completed(source: Any, event: Any) -> None:
                self._handle_crew_completed(source, event)

            @bus.on(CrewKickoffFailedEvent)
            def on_crew_failed(source: Any, event: Any) -> None:
                self._handle_crew_failed(source, event)

            @bus.on(TaskStartedEvent)
            def on_task_start(source: Any, event: Any) -> None:
                self._handle_task_start(source, event)

            @bus.on(TaskCompletedEvent)
            def on_task_completed(source: Any, event: Any) -> None:
                self._handle_task_completed(source, event)

            @bus.on(TaskFailedEvent)
            def on_task_failed(source: Any, event: Any) -> None:
                self._handle_task_failed(source, event)

            @bus.on(AgentExecutionStartedEvent)
            def on_agent_start(source: Any, event: Any) -> None:
                self._handle_agent_start(source, event)

            @bus.on(AgentExecutionCompletedEvent)
            def on_agent_completed(source: Any, event: Any) -> None:
                self._handle_agent_completed(source, event)

            @bus.on(AgentExecutionErrorEvent)
            def on_agent_error(source: Any, event: Any) -> None:
                self._handle_agent_error(source, event)

            @bus.on(ToolUsageStartedEvent)
            def on_tool_start(source: Any, event: Any) -> None:
                self._handle_tool_start(source, event)

            @bus.on(ToolUsageFinishedEvent)
            def on_tool_finished(source: Any, event: Any) -> None:
                self._handle_tool_finished(source, event)

            @bus.on(ToolUsageErrorEvent)
            def on_tool_error(source: Any, event: Any) -> None:
                self._handle_tool_error(source, event)

            self._listeners_registered = True
        except Exception:
            log.debug("agentreliability: failed to register CrewAI event listeners", exc_info=True)

    def _handle_crew_start(self, source: Any, event: Any) -> None:
        try:
            if not self._monitor.enabled:
                return

            event_id = str(getattr(event, "event_id", uuid.uuid4().hex))
            exec_id = self._preset_execution_id or f"exec-crew-{event_id.replace('-', '')[:20]}"
            self._last_execution_id = exec_id

            crew_name = self.agent_name or getattr(event, "crew_name", None) or "CrewAI"
            now_ts = _now()
            start_clock = time.perf_counter()

            participating_agents = []
            crew_obj = getattr(event, "crew", None) or source
            if hasattr(crew_obj, "agents") and crew_obj.agents:
                for ag in crew_obj.agents:
                    role = getattr(ag, "role", str(ag))
                    if role not in participating_agents:
                        participating_agents.append(role)

            merged_meta = dict(self.custom_metadata)
            merged_meta["framework"] = "crewai"
            merged_meta["crew_name"] = crew_name
            if participating_agents:
                merged_meta["agents"] = ",".join(participating_agents[:10])

            start_event = {
                "event_id": f"{exec_id}:start",
                "execution_id": exec_id,
                "agent_name": crew_name[:120],
                "type": "execution_start",
                "timestamp": now_ts,
                "input": self._monitor._capture(getattr(event, "inputs", None)),
                "metadata": self._monitor._clean_metadata(merged_meta),
            }

            with self._lock:
                self._active_crews[event_id] = {
                    "execution_id": exec_id,
                    "agent_name": crew_name[:120],
                    "start_clock": start_clock,
                    "participating_agents": participating_agents,
                }
                self._active_crews["_latest_crew"] = self._active_crews[event_id]

            self._monitor._emit(start_event)
        except Exception:
            log.debug("agentreliability: _handle_crew_start failed", exc_info=True)

    def _handle_crew_completed(self, source: Any, event: Any) -> None:
        try:
            if not self._monitor.enabled:
                return

            event_id = str(getattr(event, "event_id", ""))
            with self._lock:
                crew_info = self._active_crews.pop(event_id, None) or self._active_crews.pop("_latest_crew", None)

            duration_ms = 0.0
            if crew_info:
                duration_ms = max(0.0, (time.perf_counter() - crew_info["start_clock"]) * 1000)
                exec_id = crew_info["execution_id"]
            else:
                exec_id = self.execution_id or f"exec-crew-{uuid.uuid4().hex[:16]}"

            raw_output = getattr(event, "output", None)
            if hasattr(raw_output, "raw"):
                output_val = raw_output.raw
            else:
                output_val = raw_output

            end_event = {
                "event_id": f"{exec_id}:end",
                "execution_id": exec_id,
                "agent_name": crew_info["agent_name"] if crew_info else (self.agent_name or "CrewAI"),
                "type": "execution_end",
                "timestamp": _now(),
                "duration_ms": round(duration_ms, 3),
                "status": "success",
                "output": self._monitor._capture(output_val),
            }
            self._monitor._emit(end_event)
        except Exception:
            log.debug("agentreliability: _handle_crew_completed failed", exc_info=True)

    def _handle_crew_failed(self, source: Any, event: Any) -> None:
        try:
            if not self._monitor.enabled:
                return

            event_id = str(getattr(event, "event_id", ""))
            with self._lock:
                crew_info = self._active_crews.pop(event_id, None) or self._active_crews.pop("_latest_crew", None)

            duration_ms = 0.0
            if crew_info:
                duration_ms = max(0.0, (time.perf_counter() - crew_info["start_clock"]) * 1000)
                exec_id = crew_info["execution_id"]
            else:
                exec_id = self.execution_id or f"exec-crew-{uuid.uuid4().hex[:16]}"

            err_msg = str(getattr(event, "error", "Crew execution failed"))

            end_event = {
                "event_id": f"{exec_id}:end",
                "execution_id": exec_id,
                "agent_name": crew_info["agent_name"] if crew_info else (self.agent_name or "CrewAI"),
                "type": "execution_end",
                "timestamp": _now(),
                "duration_ms": round(duration_ms, 3),
                "status": "failed",
                "error": self._monitor._redactor.prepare_text(err_msg, 2000),
            }
            self._monitor._emit(end_event)
        except Exception:
            log.debug("agentreliability: _handle_crew_failed failed", exc_info=True)

    def _handle_task_start(self, source: Any, event: Any) -> None:
        try:
            if not self._monitor.enabled:
                return

            task_obj = getattr(event, "task", source)
            task_name = (
                getattr(event, "task_name", None)
                or getattr(task_obj, "description", None)
                or getattr(task_obj, "name", "Task")
            )
            clean_task_name = str(task_name).strip().split("\n")[0][:80]

            agent_role = getattr(event, "agent_role", None)
            if not agent_role and hasattr(task_obj, "agent") and task_obj.agent:
                agent_role = getattr(task_obj.agent, "role", "Agent")
            agent_role = str(agent_role or "Agent")

            with self._lock:
                crew_info = self._active_crews.get("_latest_crew", {})
                exec_id = crew_info.get("execution_id") or self.execution_id or f"exec-crew-{uuid.uuid4().hex[:16]}"
                agent_name = crew_info.get("agent_name") or self.agent_name or "CrewAI"

                last_agent = self._last_agent_by_crew.get(exec_id)
                if last_agent and last_agent != agent_role:
                    self._handoffs.append({
                        "from_agent": last_agent,
                        "to_agent": agent_role,
                        "task": clean_task_name,
                        "timestamp": _now(),
                    })
                self._last_agent_by_crew[exec_id] = agent_role

            task_id = str(getattr(event, "task_id", getattr(event, "event_id", uuid.uuid4().hex)))
            task_span_id = f"{exec_id}:task:{task_id.replace('-', '')[:16]}"

            with self._lock:
                self._active_tasks[task_id] = {
                    "task_id": task_id,
                    "span_id": task_span_id,
                    "execution_id": exec_id,
                    "agent_name": agent_name,
                    "task_name": clean_task_name,
                    "agent_role": agent_role,
                    "start_clock": time.perf_counter(),
                    "start_timestamp": _now(),
                    "inputs": self._monitor._capture(getattr(task_obj, "context", None)),
                }
                self._active_tasks["_latest_task"] = self._active_tasks[task_id]
        except Exception:
            log.debug("agentreliability: _handle_task_start failed", exc_info=True)

    def _handle_task_completed(self, source: Any, event: Any) -> None:
        try:
            if not self._monitor.enabled:
                return

            task_id = str(getattr(event, "task_id", getattr(event, "event_id", "")))
            with self._lock:
                task_info = self._active_tasks.pop(task_id, None) or self._active_tasks.pop("_latest_task", None)

            if not task_info:
                return

            duration_ms = max(0.0, (time.perf_counter() - task_info["start_clock"]) * 1000)
            raw_out = getattr(event, "output", None)
            if hasattr(raw_out, "raw"):
                output_val = raw_out.raw
            else:
                output_val = raw_out

            span_name = f"[{task_info['agent_role']}] {task_info['task_name']}"

            event_dict = {
                "event_id": task_info["span_id"],
                "execution_id": task_info["execution_id"],
                "agent_name": task_info["agent_name"],
                "type": "tool_call",
                "timestamp": task_info["start_timestamp"],
                "tool_name": span_name[:120],
                "duration_ms": round(duration_ms, 3),
                "status": "success",
                "input": task_info["inputs"],
                "output": self._monitor._capture(output_val),
                "parent_call_id": None,
                "retry_count": 0,
            }
            self._monitor._emit(event_dict)
        except Exception:
            log.debug("agentreliability: _handle_task_completed failed", exc_info=True)

    def _handle_task_failed(self, source: Any, event: Any) -> None:
        try:
            if not self._monitor.enabled:
                return

            task_id = str(getattr(event, "task_id", getattr(event, "event_id", "")))
            with self._lock:
                task_info = self._active_tasks.pop(task_id, None) or self._active_tasks.pop("_latest_task", None)

            if not task_info:
                return

            duration_ms = max(0.0, (time.perf_counter() - task_info["start_clock"]) * 1000)
            err_msg = str(getattr(event, "error", "Task execution failed"))
            err_type = getattr(event, "error_type", None)
            err_type_name = err_type.__name__ if isinstance(err_type, type) else "TaskExecutionError"

            span_name = f"[{task_info['agent_role']}] {task_info['task_name']}"

            event_dict = {
                "event_id": task_info["span_id"],
                "execution_id": task_info["execution_id"],
                "agent_name": task_info["agent_name"],
                "type": "tool_call",
                "timestamp": task_info["start_timestamp"],
                "tool_name": span_name[:120],
                "duration_ms": round(duration_ms, 3),
                "status": "failed",
                "input": task_info["inputs"],
                "output": None,
                "parent_call_id": None,
                "error_type": err_type_name,
                "error_message": self._monitor._redactor.prepare_text(err_msg[:200], 200),
                "retry_count": 0,
            }
            self._monitor._emit(event_dict)
        except Exception:
            log.debug("agentreliability: _handle_task_failed failed", exc_info=True)

    def _handle_agent_start(self, source: Any, event: Any) -> None:
        try:
            agent_obj = getattr(event, "agent", source)
            agent_role = getattr(event, "agent_role", getattr(agent_obj, "role", "Agent"))
            agent_id = str(getattr(event, "agent_id", getattr(agent_obj, "id", uuid.uuid4().hex)))
            with self._lock:
                self._active_agents[agent_id] = {"role": str(agent_role)}
        except Exception:
            pass

    def _handle_agent_completed(self, source: Any, event: Any) -> None:
        pass

    def _handle_agent_error(self, source: Any, event: Any) -> None:
        pass

    def _handle_tool_start(self, source: Any, event: Any) -> None:
        try:
            if not self._monitor.enabled:
                return

            tool_name = str(getattr(event, "tool_name", getattr(source, "name", "tool")))
            tool_args = getattr(event, "tool_args", None)
            event_id = str(getattr(event, "event_id", uuid.uuid4().hex))

            with self._lock:
                crew_info = self._active_crews.get("_latest_crew", {})
                exec_id = crew_info.get("execution_id") or self.execution_id or f"exec-crew-{uuid.uuid4().hex[:16]}"
                agent_name = crew_info.get("agent_name") or self.agent_name or "CrewAI"

                active_task = self._active_tasks.get("_latest_task")
                parent_call_id = active_task["span_id"] if active_task else None

            tool_span_id = f"{exec_id}:tool:{event_id.replace('-', '')[:16]}"

            with self._lock:
                self._active_tools[event_id] = {
                    "span_id": tool_span_id,
                    "execution_id": exec_id,
                    "agent_name": agent_name,
                    "tool_name": tool_name[:120],
                    "parent_call_id": parent_call_id,
                    "inputs": self._monitor._capture(tool_args),
                    "start_clock": time.perf_counter(),
                    "start_timestamp": _now(),
                }
                self._active_tools["_latest_tool"] = self._active_tools[event_id]
        except Exception:
            log.debug("agentreliability: _handle_tool_start failed", exc_info=True)

    def _handle_tool_finished(self, source: Any, event: Any) -> None:
        try:
            if not self._monitor.enabled:
                return

            event_id = str(getattr(event, "event_id", ""))
            with self._lock:
                tool_info = self._active_tools.pop(event_id, None) or self._active_tools.pop("_latest_tool", None)

            if not tool_info:
                return

            duration_ms = max(0.0, (time.perf_counter() - tool_info["start_clock"]) * 1000)
            output_val = getattr(event, "output", None)

            event_dict = {
                "event_id": tool_info["span_id"],
                "execution_id": tool_info["execution_id"],
                "agent_name": tool_info["agent_name"],
                "type": "tool_call",
                "timestamp": tool_info["start_timestamp"],
                "tool_name": tool_info["tool_name"],
                "duration_ms": round(duration_ms, 3),
                "status": "success",
                "input": tool_info["inputs"],
                "output": self._monitor._capture(output_val),
                "parent_call_id": tool_info["parent_call_id"],
                "retry_count": int(getattr(event, "run_attempts", 0) or 0),
            }
            self._monitor._emit(event_dict)
        except Exception:
            log.debug("agentreliability: _handle_tool_finished failed", exc_info=True)

    def _handle_tool_error(self, source: Any, event: Any) -> None:
        try:
            if not self._monitor.enabled:
                return

            event_id = str(getattr(event, "event_id", ""))
            with self._lock:
                tool_info = self._active_tools.pop(event_id, None) or self._active_tools.pop("_latest_tool", None)

            if not tool_info:
                return

            duration_ms = max(0.0, (time.perf_counter() - tool_info["start_clock"]) * 1000)
            err = getattr(event, "error", "Tool execution error")
            err_msg = str(err)
            err_type = type(err).__name__ if isinstance(err, BaseException) else "ToolUsageError"

            event_dict = {
                "event_id": tool_info["span_id"],
                "execution_id": tool_info["execution_id"],
                "agent_name": tool_info["agent_name"],
                "type": "tool_call",
                "timestamp": tool_info["start_timestamp"],
                "tool_name": tool_info["tool_name"],
                "duration_ms": round(duration_ms, 3),
                "status": "error",
                "input": tool_info["inputs"],
                "output": None,
                "parent_call_id": tool_info["parent_call_id"],
                "error_type": err_type,
                "error_message": self._monitor._redactor.prepare_text(err_msg[:200], 200),
                "retry_count": int(getattr(event, "run_attempts", 0) or 0),
            }
            self._monitor._emit(event_dict)
        except Exception:
            log.debug("agentreliability: _handle_tool_error failed", exc_info=True)

    def step_callback(self, step_output: Any) -> None:
        """Direct step callback hook for Agent(step_callback=...)."""
        pass

    def task_callback(self, task_output: Any) -> None:
        """Direct task callback hook for Crew(task_callback=...)."""
        pass


def setup_crewai_tracing(
    agent_name: Optional[str] = None,
    *,
    crew_name: Optional[str] = None,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    capture_io: Optional[bool] = None,
    metadata: Optional[Dict[str, Any]] = None,
    redact_keys: Iterable[str] = (),
    redact_patterns: Iterable[Any] = (),
    max_payload_chars: int = 2000,
) -> AgentReliabilityCrewListener:
    """Convenience helper to initialize and attach an AgentReliabilityCrewListener."""
    return AgentReliabilityCrewListener(
        agent_name=agent_name,
        crew_name=crew_name,
        api_key=api_key,
        endpoint=endpoint,
        capture_io=capture_io,
        metadata=metadata,
        redact_keys=redact_keys,
        redact_patterns=redact_patterns,
        max_payload_chars=max_payload_chars,
        auto_register=True,
    )
