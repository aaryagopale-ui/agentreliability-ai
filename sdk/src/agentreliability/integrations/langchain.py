"""LangChain and LangGraph Callback Integration for AgentReliability AI.

Provides `AgentReliabilityCallbackHandler` which attaches directly to LangChain
and LangGraph execution configurations:

```python
from agentreliability.integrations.langchain import AgentReliabilityCallbackHandler

handler = AgentReliabilityCallbackHandler(
    agent_name="support_agent",
    api_key="ar_live_...",
    endpoint="http://127.0.0.1:8001",
)

# Use in LangChain LCEL or LangGraph:
result = chain.invoke(inputs, config={"callbacks": [handler]})
handler.flush()
```

Golden Invariants:
1. MONITORING MUST NEVER CRASH THE AGENT. Every callback is wrapped in defensive try/except.
2. Zero external dependencies required for users who only use core SDK.
3. Accurate parent-child span hierarchy for execution timelines.
4. Privacy-conscious client-side redaction and payload bounding.
5. Token counts recorded only when actually reported by the LLM provider.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Union

try:
    from langchain_core.callbacks.base import BaseCallbackHandler
    from langchain_core.outputs import LLMResult
except ImportError as err:
    raise ImportError(
        "LangChain is not installed. To use the LangChain / LangGraph integration, "
        "install langchain-core: pip install 'agentreliability[langchain]' or pip install langchain-core"
    ) from err

from ..monitor import AgentMonitor, MAX_ERROR_CHARS, MAX_PAYLOAD_LIMIT

log = logging.getLogger("agentreliability.integrations.langchain")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentReliabilityCallbackHandler(BaseCallbackHandler):
    """LangChain & LangGraph callback handler for AgentReliability AI."""

    def __init__(
        self,
        agent_name: Optional[str] = None,
        *,
        monitor: Optional[AgentMonitor] = None,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        capture_io: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
        redact_keys: Iterable[str] = (),
        redact_patterns: Iterable[Any] = (),
        max_payload_chars: int = 2000,
        ignore_llm: bool = False,
        ignore_chain: bool = False,
        record_stream_tokens: bool = False,
        execution_id: Optional[str] = None,
    ):
        super().__init__()
        self.agent_name = agent_name
        self._ignore_llm = bool(ignore_llm)
        self._ignore_chain = bool(ignore_chain)
        self.record_stream_tokens = bool(record_stream_tokens)
        self.custom_metadata = dict(metadata or {})
        self._preset_execution_id = execution_id

        # Use provided monitor or initialize one with matching credentials
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

        # Thread-safe run lifecycle state tracking
        self._lock = threading.Lock()
        # Maps run_id (str) -> dict of run metadata and timing
        self._runs: Dict[str, Dict[str, Any]] = {}
        # Maps root run_id (str) -> execution_id (str)
        self._root_runs: Dict[str, str] = {}
        # Maps run_id (str) -> retry_count (int)
        self._retry_counts: Dict[str, int] = {}

    @property
    def monitor(self) -> AgentMonitor:
        """Access the underlying AgentMonitor instance."""
        return self._monitor

    @property
    def ignore_llm(self) -> bool:
        return self._ignore_llm

    @property
    def ignore_chain(self) -> bool:
        return self._ignore_chain

    @property
    def ignore_chat_model(self) -> bool:
        return self._ignore_llm

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait for pending traces to be transmitted to the backend."""
        return self._monitor.flush(timeout)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _resolve_agent_name(self, fallback: str = "langchain_agent") -> str:
        return (self.agent_name or fallback)[:120]

    def _get_or_create_execution_id(self, run_id_str: str) -> str:
        """Ensure each root execution has a clean, validated 8-100 char ID."""
        if self._preset_execution_id:
            return self._preset_execution_id
        clean = run_id_str.replace("-", "")
        return f"exec-{clean[:24]}"

    def _sanitize_id(self, val: str) -> str:
        return "".join(c for c in val if c.isalnum() or c in "._:-")

    # -------------------------------------------------------------------------
    # Chain / Graph Callbacks (Root and Node executions)
    # -------------------------------------------------------------------------

    def on_chain_start(
        self,
        serialized: Optional[Dict[str, Any]],
        inputs: Dict[str, Any],
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        try:
            if not self._monitor.enabled:
                return

            run_id_str = str(run_id)
            parent_run_str = str(parent_run_id) if parent_run_id else None
            now_ts = _now()
            start_clock = time.perf_counter()

            # Determine human-friendly name
            name = (
                kwargs.get("name")
                or (metadata or {}).get("langgraph_node")
                or (serialized or {}).get("name")
                or (serialized or {}).get("id", ["Chain"])[-1]
                or "chain"
            )

            with self._lock:
                if parent_run_str is None:
                    # ROOT EXECUTION (e.g. graph.invoke or chain.invoke)
                    exec_id = self._get_or_create_execution_id(run_id_str)
                    self._root_runs[run_id_str] = exec_id
                    agent_name = self._resolve_agent_name(name)

                    merged_meta = {
                        **self.custom_metadata,
                        **(metadata or {}),
                        "framework": "langchain",
                    }
                    if tags:
                        merged_meta["tags"] = ",".join(str(t) for t in tags[:10])

                    event = {
                        "event_id": f"{exec_id}:start",
                        "execution_id": exec_id,
                        "agent_name": agent_name,
                        "type": "execution_start",
                        "timestamp": now_ts,
                        "input": self._monitor._capture(inputs),
                        "metadata": self._monitor._clean_metadata(merged_meta),
                    }
                    self._runs[run_id_str] = {
                        "run_id": run_id_str,
                        "is_root": True,
                        "execution_id": exec_id,
                        "event_id": f"{exec_id}:start",
                        "agent_name": agent_name,
                        "name": name,
                        "start_clock": start_clock,
                        "inputs": inputs,
                    }
                    self._monitor._emit(event)
                else:
                    # CHILD CHAIN / GRAPH NODE
                    if self.ignore_chain:
                        return

                    parent_info = self._runs.get(parent_run_str)
                    exec_id = parent_info["execution_id"] if parent_info else self._get_or_create_execution_id(parent_run_str)
                    agent_name = parent_info["agent_name"] if parent_info else self._resolve_agent_name()

                    # Direct children of root have parent_call_id = None; sub-nodes reference parent span
                    parent_call_id = None
                    if parent_info and not parent_info.get("is_root"):
                        parent_call_id = parent_info.get("event_id")

                    span_id = f"{exec_id}:node:{self._sanitize_id(run_id_str)}"
                    self._runs[run_id_str] = {
                        "run_id": run_id_str,
                        "is_root": False,
                        "execution_id": exec_id,
                        "event_id": span_id,
                        "agent_name": agent_name,
                        "name": name,
                        "start_clock": start_clock,
                        "start_timestamp": now_ts,
                        "inputs": inputs,
                        "parent_call_id": parent_call_id,
                    }
        except Exception:
            log.debug("agentreliability: on_chain_start failed", exc_info=True)

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        try:
            if not self._monitor.enabled:
                return

            run_id_str = str(run_id)
            with self._lock:
                run_info = self._runs.pop(run_id_str, None)
                if not run_info:
                    return

            duration_ms = max(0.0, (time.perf_counter() - run_info["start_clock"]) * 1000)

            if run_info.get("is_root"):
                # ROOT EXECUTION END
                exec_id = run_info["execution_id"]
                with self._lock:
                    self._root_runs.pop(run_id_str, None)

                event = {
                    "event_id": f"{exec_id}:end",
                    "execution_id": exec_id,
                    "agent_name": run_info["agent_name"],
                    "type": "execution_end",
                    "timestamp": _now(),
                    "duration_ms": round(duration_ms, 3),
                    "status": "success",
                    "output": self._monitor._capture(outputs),
                }
                self._monitor._emit(event)
            else:
                # CHILD CHAIN / NODE END (emitted as a tool_call span)
                event = {
                    "event_id": run_info["event_id"],
                    "execution_id": run_info["execution_id"],
                    "agent_name": run_info["agent_name"],
                    "type": "tool_call",
                    "timestamp": run_info["start_timestamp"],
                    "tool_name": str(run_info["name"])[:120],
                    "duration_ms": round(duration_ms, 3),
                    "status": "success",
                    "input": self._monitor._capture(run_info["inputs"]),
                    "output": self._monitor._capture(outputs),
                    "parent_call_id": run_info.get("parent_call_id"),
                    "retry_count": self._retry_counts.pop(run_id_str, 0),
                }
                self._monitor._emit(event)
        except Exception:
            log.debug("agentreliability: on_chain_end failed", exc_info=True)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        try:
            if not self._monitor.enabled:
                return

            run_id_str = str(run_id)
            with self._lock:
                run_info = self._runs.pop(run_id_str, None)
                if not run_info:
                    return

            duration_ms = max(0.0, (time.perf_counter() - run_info["start_clock"]) * 1000)
            is_timeout = isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower()

            if run_info.get("is_root"):
                exec_id = run_info["execution_id"]
                with self._lock:
                    self._root_runs.pop(run_id_str, None)

                event = {
                    "event_id": f"{exec_id}:end",
                    "execution_id": exec_id,
                    "agent_name": run_info["agent_name"],
                    "type": "execution_end",
                    "timestamp": _now(),
                    "duration_ms": round(duration_ms, 3),
                    "status": "failed",
                    "error_type": type(error).__name__[:200],
                    "error_message": self._monitor._error_text(error),
                }
                self._monitor._emit(event)
            else:
                event = {
                    "event_id": run_info["event_id"],
                    "execution_id": run_info["execution_id"],
                    "agent_name": run_info["agent_name"],
                    "type": "tool_call",
                    "timestamp": run_info["start_timestamp"],
                    "tool_name": str(run_info["name"])[:120],
                    "duration_ms": round(duration_ms, 3),
                    "status": "timeout" if is_timeout else "error",
                    "input": self._monitor._capture(run_info["inputs"]),
                    "output": None,
                    "parent_call_id": run_info.get("parent_call_id"),
                    "error_type": type(error).__name__[:200],
                    "error_message": self._monitor._error_text(error),
                    "retry_count": self._retry_counts.pop(run_id_str, 0),
                }
                self._monitor._emit(event)
        except Exception:
            log.debug("agentreliability: on_chain_error failed", exc_info=True)

    # -------------------------------------------------------------------------
    # Tool Callbacks
    # -------------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: Optional[Dict[str, Any]],
        input_str: str,
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        inputs: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        try:
            if not self._monitor.enabled:
                return

            run_id_str = str(run_id)
            parent_run_str = str(parent_run_id) if parent_run_id else None
            now_ts = _now()
            start_clock = time.perf_counter()

            tool_name = (
                (serialized or {}).get("name")
                or kwargs.get("name")
                or "tool"
            )

            with self._lock:
                parent_info = self._runs.get(parent_run_str) if parent_run_str else None
                if parent_info:
                    exec_id = parent_info["execution_id"]
                    agent_name = parent_info["agent_name"]
                    parent_call_id = None if parent_info.get("is_root") else parent_info.get("event_id")
                else:
                    # Standalone tool call without outer chain
                    exec_id = self._get_or_create_execution_id(run_id_str)
                    agent_name = self._resolve_agent_name("tool_runner")
                    parent_call_id = None
                    # Emit standalone start
                    self._monitor._emit({
                        "event_id": f"{exec_id}:start",
                        "execution_id": exec_id,
                        "agent_name": agent_name,
                        "type": "execution_start",
                        "timestamp": now_ts,
                        "input": self._monitor._capture(inputs or input_str),
                        "metadata": self._monitor._clean_metadata(self.custom_metadata),
                    })

                span_id = f"{exec_id}:tool:{self._sanitize_id(run_id_str)}"
                self._runs[run_id_str] = {
                    "run_id": run_id_str,
                    "is_root": False,
                    "is_standalone_tool": parent_info is None,
                    "execution_id": exec_id,
                    "event_id": span_id,
                    "agent_name": agent_name,
                    "name": tool_name,
                    "start_clock": start_clock,
                    "start_timestamp": now_ts,
                    "inputs": inputs if inputs is not None else input_str,
                    "parent_call_id": parent_call_id,
                }
        except Exception:
            log.debug("agentreliability: on_tool_start failed", exc_info=True)

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        try:
            if not self._monitor.enabled:
                return

            run_id_str = str(run_id)
            with self._lock:
                run_info = self._runs.pop(run_id_str, None)
                if not run_info:
                    return

            duration_ms = max(0.0, (time.perf_counter() - run_info["start_clock"]) * 1000)

            event = {
                "event_id": run_info["event_id"],
                "execution_id": run_info["execution_id"],
                "agent_name": run_info["agent_name"],
                "type": "tool_call",
                "timestamp": run_info["start_timestamp"],
                "tool_name": str(run_info["name"])[:120],
                "duration_ms": round(duration_ms, 3),
                "status": "success",
                "input": self._monitor._capture(run_info["inputs"]),
                "output": self._monitor._capture(output),
                "parent_call_id": run_info.get("parent_call_id"),
                "retry_count": self._retry_counts.pop(run_id_str, 0),
            }
            self._monitor._emit(event)

            if run_info.get("is_standalone_tool"):
                exec_id = run_info["execution_id"]
                self._monitor._emit({
                    "event_id": f"{exec_id}:end",
                    "execution_id": exec_id,
                    "agent_name": run_info["agent_name"],
                    "type": "execution_end",
                    "timestamp": _now(),
                    "duration_ms": round(duration_ms, 3),
                    "status": "success",
                    "output": self._monitor._capture(output),
                })
        except Exception:
            log.debug("agentreliability: on_tool_end failed", exc_info=True)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        try:
            if not self._monitor.enabled:
                return

            run_id_str = str(run_id)
            with self._lock:
                run_info = self._runs.pop(run_id_str, None)
                if not run_info:
                    return

            duration_ms = max(0.0, (time.perf_counter() - run_info["start_clock"]) * 1000)
            is_timeout = isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower()

            event = {
                "event_id": run_info["event_id"],
                "execution_id": run_info["execution_id"],
                "agent_name": run_info["agent_name"],
                "type": "tool_call",
                "timestamp": run_info["start_timestamp"],
                "tool_name": str(run_info["name"])[:120],
                "duration_ms": round(duration_ms, 3),
                "status": "timeout" if is_timeout else "error",
                "input": self._monitor._capture(run_info["inputs"]),
                "output": None,
                "parent_call_id": run_info.get("parent_call_id"),
                "error_type": type(error).__name__[:200],
                "error_message": self._monitor._error_text(error),
                "retry_count": self._retry_counts.pop(run_id_str, 0),
            }
            self._monitor._emit(event)

            if run_info.get("is_standalone_tool"):
                exec_id = run_info["execution_id"]
                self._monitor._emit({
                    "event_id": f"{exec_id}:end",
                    "execution_id": exec_id,
                    "agent_name": run_info["agent_name"],
                    "type": "execution_end",
                    "timestamp": _now(),
                    "duration_ms": round(duration_ms, 3),
                    "status": "failed",
                    "error_type": type(error).__name__[:200],
                    "error_message": self._monitor._error_text(error),
                })
        except Exception:
            log.debug("agentreliability: on_tool_error failed", exc_info=True)

    # -------------------------------------------------------------------------
    # LLM / Chat Model Callbacks
    # -------------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: Optional[Dict[str, Any]],
        prompts: List[str],
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        try:
            if not self._monitor.enabled or self.ignore_llm:
                return

            run_id_str = str(run_id)
            parent_run_str = str(parent_run_id) if parent_run_id else None
            now_ts = _now()
            start_clock = time.perf_counter()

            model_name = (
                (serialized or {}).get("name")
                or (serialized or {}).get("id", ["LLM"])[-1]
                or (metadata or {}).get("ls_model_name")
                or kwargs.get("name")
                or "llm"
            )

            with self._lock:
                parent_info = self._runs.get(parent_run_str) if parent_run_str else None
                if parent_info:
                    exec_id = parent_info["execution_id"]
                    agent_name = parent_info["agent_name"]
                    parent_call_id = None if parent_info.get("is_root") else parent_info.get("event_id")
                else:
                    exec_id = self._get_or_create_execution_id(run_id_str)
                    agent_name = self._resolve_agent_name("llm_runner")
                    parent_call_id = None
                    self._monitor._emit({
                        "event_id": f"{exec_id}:start",
                        "execution_id": exec_id,
                        "agent_name": agent_name,
                        "type": "execution_start",
                        "timestamp": now_ts,
                        "input": self._monitor._capture(prompts),
                        "metadata": self._monitor._clean_metadata(self.custom_metadata),
                    })

                span_id = f"{exec_id}:llm:{self._sanitize_id(run_id_str)}"
                self._runs[run_id_str] = {
                    "run_id": run_id_str,
                    "is_root": False,
                    "is_standalone_llm": parent_info is None,
                    "execution_id": exec_id,
                    "event_id": span_id,
                    "agent_name": agent_name,
                    "name": f"llm:{model_name}",
                    "start_clock": start_clock,
                    "start_timestamp": now_ts,
                    "inputs": prompts,
                    "parent_call_id": parent_call_id,
                }
        except Exception:
            log.debug("agentreliability: on_llm_start failed", exc_info=True)

    def on_chat_model_start(
        self,
        serialized: Optional[Dict[str, Any]],
        messages: List[List[Any]],
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        try:
            # Flatten or format messages safely for logging
            formatted_messages = []
            for batch in messages:
                for msg in batch:
                    formatted_messages.append(
                        getattr(msg, "content", str(msg))
                    )
            self.on_llm_start(
                serialized,
                formatted_messages,
                run_id=run_id,
                parent_run_id=parent_run_id,
                tags=tags,
                metadata=metadata,
                **kwargs,
            )
        except Exception:
            log.debug("agentreliability: on_chat_model_start failed", exc_info=True)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        try:
            if not self._monitor.enabled or self.ignore_llm:
                return

            run_id_str = str(run_id)
            with self._lock:
                run_info = self._runs.pop(run_id_str, None)
                if not run_info:
                    return

            duration_ms = max(0.0, (time.perf_counter() - run_info["start_clock"]) * 1000)

            # Extract generated texts
            generated_texts = []
            for gen_list in response.generations:
                for gen in gen_list:
                    generated_texts.append(gen.text)

            output_payload: Dict[str, Any] = {
                "generations": generated_texts,
            }

            # Only record token usage if reported by the model (never fabricate)
            llm_output = response.llm_output or {}
            token_usage = llm_output.get("token_usage") or llm_output.get("usage")
            if token_usage and isinstance(token_usage, dict):
                output_payload["token_usage"] = {
                    k: int(v) for k, v in token_usage.items() if isinstance(v, (int, float))
                }

            event = {
                "event_id": run_info["event_id"],
                "execution_id": run_info["execution_id"],
                "agent_name": run_info["agent_name"],
                "type": "tool_call",
                "timestamp": run_info["start_timestamp"],
                "tool_name": str(run_info["name"])[:120],
                "duration_ms": round(duration_ms, 3),
                "status": "success",
                "input": self._monitor._capture(run_info["inputs"]),
                "output": self._monitor._capture(output_payload),
                "parent_call_id": run_info.get("parent_call_id"),
                "retry_count": self._retry_counts.pop(run_id_str, 0),
            }
            self._monitor._emit(event)

            if run_info.get("is_standalone_llm"):
                exec_id = run_info["execution_id"]
                self._monitor._emit({
                    "event_id": f"{exec_id}:end",
                    "execution_id": exec_id,
                    "agent_name": run_info["agent_name"],
                    "type": "execution_end",
                    "timestamp": _now(),
                    "duration_ms": round(duration_ms, 3),
                    "status": "success",
                    "output": self._monitor._capture(output_payload),
                })
        except Exception:
            log.debug("agentreliability: on_llm_end failed", exc_info=True)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        try:
            if not self._monitor.enabled or self.ignore_llm:
                return

            run_id_str = str(run_id)
            with self._lock:
                run_info = self._runs.pop(run_id_str, None)
                if not run_info:
                    return

            duration_ms = max(0.0, (time.perf_counter() - run_info["start_clock"]) * 1000)
            is_timeout = isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower()

            event = {
                "event_id": run_info["event_id"],
                "execution_id": run_info["execution_id"],
                "agent_name": run_info["agent_name"],
                "type": "tool_call",
                "timestamp": run_info["start_timestamp"],
                "tool_name": str(run_info["name"])[:120],
                "duration_ms": round(duration_ms, 3),
                "status": "timeout" if is_timeout else "error",
                "input": self._monitor._capture(run_info["inputs"]),
                "output": None,
                "parent_call_id": run_info.get("parent_call_id"),
                "error_type": type(error).__name__[:200],
                "error_message": self._monitor._error_text(error),
                "retry_count": self._retry_counts.pop(run_id_str, 0),
            }
            self._monitor._emit(event)

            if run_info.get("is_standalone_llm"):
                exec_id = run_info["execution_id"]
                self._monitor._emit({
                    "event_id": f"{exec_id}:end",
                    "execution_id": exec_id,
                    "agent_name": run_info["agent_name"],
                    "type": "execution_end",
                    "timestamp": _now(),
                    "duration_ms": round(duration_ms, 3),
                    "status": "failed",
                    "error_type": type(error).__name__[:200],
                    "error_message": self._monitor._error_text(error),
                })
        except Exception:
            log.debug("agentreliability: on_llm_error failed", exc_info=True)

    # -------------------------------------------------------------------------
    # Streaming & Retries
    # -------------------------------------------------------------------------

    def on_llm_new_token(
        self,
        token: str,
        *,
        chunk: Optional[Any] = None,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Streaming callback - intentionally does NOT emit spans per token to prevent network overload."""
        pass

    def on_retry(
        self,
        retry_state: Any,
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Record retry attempts for the given run."""
        try:
            run_id_str = str(run_id)
            with self._lock:
                self._retry_counts[run_id_str] = self._retry_counts.get(run_id_str, 0) + 1
        except Exception:
            pass
