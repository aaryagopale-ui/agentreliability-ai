"""AgentMonitor: the public SDK entry point.

Golden rule: MONITORING MUST NEVER BREAK THE DEVELOPER'S AGENT.
  * Every piece of SDK bookkeeping runs inside `try/except Exception`.
  * The wrapped function is called with the exact same arguments; its return value and
    its exceptions (the very same exception object) pass through untouched.
  * Network work happens on a background thread (see transport.py).
"""
from __future__ import annotations

import contextvars
import functools
import inspect
import itertools
import logging
import os
import threading
import time
import uuid
import warnings
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from .redaction import Redactor
from .transport import PostFunc, Transport

log = logging.getLogger("agentreliability")

ENV_ENDPOINT = "AGENTRELIABILITY_ENDPOINT"
ENV_API_KEY = "AGENTRELIABILITY_API_KEY"
ENV_CAPTURE_IO = "AGENTRELIABILITY_CAPTURE_IO"
DEFAULT_ENDPOINT = "http://localhost:8000"

MAX_PAYLOAD_LIMIT = 16_000   # matches the backend limit
MAX_ERROR_CHARS = 1_000

# The trace that is "currently running" in this thread / async context.
_current: "contextvars.ContextVar[Optional[_Trace]]" = contextvars.ContextVar("agentreliability_trace", default=None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # always UTC


class _Trace:
    """State of one agent execution."""

    def __init__(self, execution_id: str, agent_name: str):
        self.execution_id = execution_id
        self.agent_name = agent_name
        self.started = time.perf_counter()
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    def next_tool_id(self) -> str:
        with self._lock:
            return f"{self.execution_id}:tool:{next(self._counter)}"


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower()


class _NullToolCall:
    """Returned when tool_call() is used outside of a traced agent. Does nothing."""

    def set_input(self, value: Any) -> None: ...
    def set_output(self, value: Any) -> None: ...
    def __enter__(self): return self
    def __exit__(self, *exc): return False


class _ToolCall:
    def __init__(self, monitor: "AgentMonitor", trace: _Trace, name: str, input_value: Any):
        self._monitor, self._trace, self._name = monitor, trace, name
        self._input, self._output = input_value, None
        self._start_ts = _now()
        self._start = time.perf_counter()
        self._call_id = trace.next_tool_id()

    def set_input(self, value: Any) -> None:
        self._input = value

    def set_output(self, value: Any) -> None:
        self._output = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            m = self._monitor
            event = {
                "event_id": self._call_id, "execution_id": self._trace.execution_id,
                "agent_name": self._trace.agent_name, "type": "tool_call", "timestamp": self._start_ts,
                "tool_name": self._name[:120],
                "duration_ms": round((time.perf_counter() - self._start) * 1000, 3),
                "status": "success", "input": m._capture(self._input), "output": m._capture(self._output),
            }
            if exc is not None:
                event["status"] = "timeout" if _is_timeout(exc) else "error"
                event["error_type"] = type(exc).__name__[:200]
                event["error_message"] = m._error_text(exc)
            m._emit(event)
        except Exception:
            log.debug("agentreliability: failed to record tool call", exc_info=True)
        return False  # never swallow the developer's exception


class AgentMonitor:
    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        *,
        capture_io: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
        redact_keys: Iterable[str] = (),
        redact_patterns: Iterable[Any] = (),
        max_payload_chars: int = 2000,
        enabled: bool = True,
        timeout: float = 2.0,
        max_queue: int = 1000,
        retries: int = 2,
        retry_backoff: float = 0.25,
        _post: Optional[PostFunc] = None,
    ):
        self.endpoint = (endpoint or os.environ.get(ENV_ENDPOINT) or DEFAULT_ENDPOINT).rstrip("/")
        self._api_key = api_key or os.environ.get(ENV_API_KEY) or ""
        if capture_io is None:
            capture_io = os.environ.get(ENV_CAPTURE_IO, "").lower() in ("1", "true", "yes")
        self.capture_io = bool(capture_io)          # OFF by default: inputs/outputs may be sensitive
        self.metadata = dict(metadata or {})
        self.max_payload_chars = max(100, min(int(max_payload_chars), MAX_PAYLOAD_LIMIT))
        self._redactor = Redactor(redact_keys, redact_patterns)
        self.enabled = bool(enabled)
        self._transport: Optional[Transport] = None

        if self.enabled and not self._api_key:
            log.warning("agentreliability: no API key (set %s); monitoring is disabled", ENV_API_KEY)
            self.enabled = False
        if self.enabled and not self.endpoint.lower().startswith(("http://", "https://")):
            log.warning("agentreliability: endpoint must start with http:// or https://; monitoring is disabled")
            self.enabled = False
        if self.enabled:
            self._transport = Transport(self.endpoint, self._api_key, timeout=timeout, max_queue=max_queue,
                                        retries=retries, retry_backoff=retry_backoff, post=_post)

    def __repr__(self) -> str:  # the key is never shown
        return f"AgentMonitor(endpoint={self.endpoint!r}, enabled={self.enabled}, capture_io={self.capture_io})"

    # ------------------------------------------------------------------ public helpers

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait for queued traces to be sent. Call before a short script exits."""
        if self._transport is None:
            return True
        try:
            return self._transport.flush(timeout)
        except Exception:
            return False

    @property
    def dropped_events(self) -> int:
        return self._transport.dropped if self._transport else 0

    # ------------------------------------------------------------------ decorators

    def trace_agent(self, agent_name: str, *, metadata: Optional[Dict[str, Any]] = None) -> Callable:
        """Decorator: record every call of a (synchronous) function as one execution."""

        def decorator(func: Callable) -> Callable:
            if inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func):
                warnings.warn(
                    f"agentreliability: async functions are not supported yet; '{func.__name__}' runs untraced.",
                    stacklevel=2,
                )
                return func

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if not self.enabled:
                    return func(*args, **kwargs)
                trace = self._begin(agent_name, metadata, func, args, kwargs)
                token = None
                if trace is not None:
                    try:
                        token = _current.set(trace)
                    except Exception:
                        trace = None
                try:
                    result = func(*args, **kwargs)
                except BaseException as exc:
                    self._finish(trace, error=exc)
                    raise  # the original exception, unchanged
                else:
                    self._finish(trace, result=result)
                    return result
                finally:
                    if token is not None:
                        try:
                            _current.reset(token)
                        except Exception:
                            pass

            return wrapper

        return decorator

    def tool_call(self, name: str, input: Any = None):
        """Context manager that records one tool call inside a traced agent."""
        try:
            trace = _current.get()
            if self.enabled and trace is not None:
                return _ToolCall(self, trace, name, input)
        except Exception:
            log.debug("agentreliability: tool_call setup failed", exc_info=True)
        return _NullToolCall()

    def trace_tool(self, name: Optional[str] = None) -> Callable:
        """Decorator for tool functions. Arguments are the input, the return value is the output."""

        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            if inspect.iscoroutinefunction(func):
                warnings.warn("agentreliability: async tools are not supported yet; running untraced.", stacklevel=2)
                return func

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                call = self.tool_call(tool_name, self._args_payload(func, args, kwargs))
                with call:
                    result = func(*args, **kwargs)
                    call.set_output(result)
                    return result

            return wrapper

        return decorator

    # ------------------------------------------------------------------ internals (all failure-safe)

    def _capture(self, value: Any) -> Any:
        """Redacted, size-limited copy of a payload, or None when capture is disabled."""
        if not self.capture_io or value is None:
            return None
        try:
            return self._redactor.prepare(value, self.max_payload_chars)
        except Exception:
            return "[could not capture]"

    def _error_text(self, exc: BaseException) -> str:
        try:
            return self._redactor.prepare_text(str(exc), MAX_ERROR_CHARS) or ""
        except Exception:
            return ""

    def _args_payload(self, func: Callable, args: tuple, kwargs: dict) -> Any:
        if not self.capture_io:
            return None
        try:
            try:
                bound = inspect.signature(func).bind_partial(*args, **kwargs)
                return dict(bound.arguments)  # named arguments make sensitive-key redaction work
            except (TypeError, ValueError):
                return {"args": list(args), "kwargs": kwargs}
        except Exception:
            return None

    def _clean_metadata(self, extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        merged = {**self.metadata, **(extra or {})}
        for key, value in list(merged.items())[:20]:
            k = str(key)[:64]
            if self._redactor.is_sensitive_key(k):
                out[k] = "[REDACTED]"
            elif isinstance(value, (bool, int, float)) or value is None:
                out[k] = value
            else:
                out[k] = self._redactor.redact_text(str(value))[:256]
        return out

    def _emit(self, event: dict) -> None:
        try:
            if self._transport is not None:
                self._transport.submit(event)
        except Exception:
            log.debug("agentreliability: failed to queue event", exc_info=True)

    def _begin(self, agent_name, metadata, func, args, kwargs) -> Optional[_Trace]:
        try:
            trace = _Trace(uuid.uuid4().hex, str(agent_name)[:120])
            self._emit({
                "event_id": f"{trace.execution_id}:start", "execution_id": trace.execution_id,
                "agent_name": trace.agent_name, "type": "execution_start", "timestamp": _now(),
                "input": self._capture(self._args_payload(func, args, kwargs)),
                "metadata": self._clean_metadata(metadata),
            })
            return trace
        except Exception:
            log.debug("agentreliability: failed to start trace", exc_info=True)
            return None

    def _finish(self, trace: Optional[_Trace], *, result: Any = None, error: Optional[BaseException] = None) -> None:
        if trace is None:
            return
        try:
            event = {
                "event_id": f"{trace.execution_id}:end", "execution_id": trace.execution_id,
                "agent_name": trace.agent_name, "type": "execution_end", "timestamp": _now(),
                "duration_ms": round((time.perf_counter() - trace.started) * 1000, 3),
                "status": "success" if error is None else "failed",
            }
            if error is None:
                event["output"] = self._capture(result)
            else:
                event["error_type"] = type(error).__name__[:200]
                event["error_message"] = self._error_text(error)
            self._emit(event)
        except Exception:
            log.debug("agentreliability: failed to finish trace", exc_info=True)

