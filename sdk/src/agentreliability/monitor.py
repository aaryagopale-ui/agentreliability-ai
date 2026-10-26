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
from typing import Any, Callable, Dict, Iterable, Optional, Union

from .config import resolve_api_key, resolve_endpoint
from .redaction import Redactor
from .transport import PostFunc, Transport

log = logging.getLogger("agentreliability")

ENV_ENDPOINT = "AGENTRELIABILITY_ENDPOINT"
ENV_API_KEY = "AGENTRELIABILITY_API_KEY"
ENV_CAPTURE_IO = "AGENTRELIABILITY_CAPTURE_IO"
DEFAULT_ENDPOINT = "http://127.0.0.1:8001"

MAX_PAYLOAD_LIMIT = 16_000   # matches the backend limit
MAX_ERROR_CHARS = 1_000

# The trace that is "currently running" in this thread / async context.
_current: "contextvars.ContextVar[Optional[_Trace]]" = contextvars.ContextVar("agentreliability_trace", default=None)
# The parent tool call that is "currently running" in this execution (for nesting)
_current_tool: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar("agentreliability_current_tool", default=None)


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
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False


class _ToolCall:
    def __init__(self, monitor: "AgentMonitor", trace: _Trace, name: str, input_value: Any, retry_count: int = 0):
        self._monitor, self._trace, self._name = monitor, trace, name
        self._input, self._output = input_value, None
        self._start_ts = _now()
        self._start = time.perf_counter()
        self._call_id = trace.next_tool_id()
        self._parent_id = _current_tool.get()
        self._retry_count = int(retry_count) if retry_count else 0
        self._token = None

    def set_input(self, value: Any) -> None:
        self._input = value

    def set_output(self, value: Any) -> None:
        self._output = value

    def __enter__(self):
        try:
            self._token = _current_tool.set(self._call_id)
        except Exception:
            self._token = None
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
                "parent_call_id": self._parent_id,
                "retry_count": self._retry_count,
            }
            if exc is not None:
                event["status"] = "timeout" if _is_timeout(exc) else "error"
                event["error_type"] = type(exc).__name__[:200]
                event["error_message"] = m._error_text(exc)
            m._emit(event)
        except Exception:
            log.debug("agentreliability: failed to record tool call", exc_info=True)
        finally:
            if self._token is not None:
                try:
                    _current_tool.reset(self._token)
                except Exception:
                    pass
        return False  # never swallow the developer's exception

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb):
        return self.__exit__(exc_type, exc, tb)


class _NullExecution:
    """Returned when trace_execution() is called with monitoring disabled."""

    def __init__(self, name: str = "disabled"):
        self.execution_id = ""
        self.name = name
        self.duration_ms = 0.0

    def set_input(self, value: Any) -> None:
        pass

    def set_output(self, value: Any) -> None:
        pass

    def set_error(self, error: Any) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _ExecutionTrace:
    """Context manager for tracing an arbitrary code execution block.

    Supports both synchronous ('with monitor.trace_execution(...) as trace:')
    and asynchronous ('async with monitor.trace_execution(...) as trace:').
    """

    def __init__(
        self,
        monitor: "AgentMonitor",
        name: str,
        input_data: Any = None,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self._monitor = monitor
        self.name = str(name)[:120]
        self._input = input_data
        self._metadata = metadata or {}
        self._output = None
        self._manual_error = None
        self._start_perf: Optional[float] = None
        self._duration_ms: Optional[float] = None
        self._token = None
        self._input_update_counter = 0

        # Create the underlying _Trace instance
        self._trace = _Trace(uuid.uuid4().hex, self.name)
        self.execution_id = self._trace.execution_id

    @property
    def duration_ms(self) -> Optional[float]:
        if self._duration_ms is not None:
            return self._duration_ms
        if self._start_perf is not None:
            return round((time.perf_counter() - self._start_perf) * 1000, 3)
        return None

    def set_input(self, value: Any) -> None:
        """Set or update the execution input payload."""
        self._input = value
        # If execution already started, emit an updated start event so backend captures latest input
        if self._start_perf is not None:
            self._input_update_counter += 1
            try:
                update_event = {
                    "event_id": f"{self.execution_id}:start:update_{self._input_update_counter}",
                    "execution_id": self.execution_id,
                    "agent_name": self.name,
                    "type": "execution_start",
                    "timestamp": _now(),
                    "input": self._monitor._capture(self._input),
                    "metadata": self._monitor._clean_metadata(self._metadata),
                }
                self._monitor._emit(update_event)
            except Exception:
                log.debug("agentreliability: failed to emit updated execution_start", exc_info=True)

    def set_output(self, value: Any) -> None:
        """Set or update the execution output payload."""
        self._output = value

    def set_error(self, error: Any) -> None:
        """Explicitly flag this execution block as failed with an error message or exception."""
        self._manual_error = error

    def _enter(self) -> "_ExecutionTrace":
        self._start_perf = time.perf_counter()
        self._trace.started = self._start_perf
        try:
            self._token = _current.set(self._trace)
        except Exception:
            self._token = None

        try:
            start_event = {
                "event_id": f"{self.execution_id}:start",
                "execution_id": self.execution_id,
                "agent_name": self.name,
                "type": "execution_start",
                "timestamp": _now(),
                "input": self._monitor._capture(self._input),
                "metadata": self._monitor._clean_metadata(self._metadata),
            }
            self._monitor._emit(start_event)
        except Exception:
            log.debug("agentreliability: failed to emit execution_start for block", exc_info=True)

        return self

    def _exit(self, exc_type, exc, tb) -> bool:
        try:
            end_perf = time.perf_counter()
            self._duration_ms = (
                round((end_perf - self._start_perf) * 1000, 3) if self._start_perf is not None else 0.0
            )

            status = "success"
            err_type = None
            err_msg = None

            if exc is not None:
                status = "failed"
                err_type = type(exc).__name__[:200]
                err_msg = self._monitor._error_text(exc)
            elif self._manual_error is not None:
                status = "failed"
                if isinstance(self._manual_error, BaseException):
                    err_type = type(self._manual_error).__name__[:200]
                    err_msg = self._monitor._error_text(self._manual_error)
                else:
                    err_type = "ExecutionError"
                    err_msg = (
                        self._monitor._redactor.prepare_text(str(self._manual_error), MAX_ERROR_CHARS) or ""
                    )

            end_event = {
                "event_id": f"{self.execution_id}:end",
                "execution_id": self.execution_id,
                "agent_name": self.name,
                "type": "execution_end",
                "timestamp": _now(),
                "duration_ms": self._duration_ms,
                "status": status,
            }

            if status == "success":
                end_event["output"] = self._monitor._capture(self._output)
            else:
                end_event["error_type"] = err_type
                end_event["error_message"] = err_msg
                if self._output is not None:
                    end_event["output"] = self._monitor._capture(self._output)

            self._monitor._emit(end_event)
        except Exception:
            log.debug("agentreliability: failed to emit execution_end for block", exc_info=True)
        finally:
            if self._token is not None:
                try:
                    _current.reset(self._token)
                except Exception:
                    pass

        return False  # never swallow the developer's exception

    def __enter__(self) -> "_ExecutionTrace":
        return self._enter()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return self._exit(exc_type, exc, tb)

    async def __aenter__(self) -> "_ExecutionTrace":
        return self._enter()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return self._exit(exc_type, exc, tb)


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
        self.endpoint = (endpoint or os.environ.get(ENV_ENDPOINT) or resolve_endpoint()).rstrip("/")
        self._api_key = api_key or os.environ.get(ENV_API_KEY) or resolve_api_key()
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
        """Decorator: record every call of a synchronous or asynchronous function as one execution."""

        def decorator(func: Callable) -> Callable:
            if inspect.isasyncgenfunction(func):
                warnings.warn(
                    f"agentreliability: async generators are not supported yet; '{func.__name__}' runs untraced.",
                    stacklevel=2,
                )
                return func

            if inspect.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    if not self.enabled:
                        return await func(*args, **kwargs)
                    trace = self._begin(agent_name, metadata, func, args, kwargs)
                    token = None
                    if trace is not None:
                        try:
                            token = _current.set(trace)
                        except Exception:
                            trace = None
                    try:
                        result = await func(*args, **kwargs)
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

                return async_wrapper

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

    def trace_execution(
        self,
        name: str,
        input_data: Any = None,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Union[_ExecutionTrace, _NullExecution]:
        """Context manager to trace an arbitrary code execution block.

        Usage:
            with monitor.trace_execution("order_processing", input_data={"order_id": 123}) as trace:
                result = process()
                trace.set_output(result)

            async with monitor.trace_execution("async_worker", input_data={"query": "test"}) as trace:
                result = await fetch()
                trace.set_output(result)
        """
        if not self.enabled:
            return _NullExecution(name=name)
        try:
            return _ExecutionTrace(self, name, input_data=input_data, metadata=metadata)
        except Exception:
            log.debug("agentreliability: trace_execution setup failed", exc_info=True)
            return _NullExecution(name=name)

    def tool_call(self, name: str, input: Any = None, *, retry_count: int = 0, **kwargs: Any):
        """Context manager that records one tool call inside a traced agent."""
        inp = input if input is not None else kwargs.get("input_data")
        try:
            trace = _current.get()
            if self.enabled and trace is not None:
                return _ToolCall(self, trace, name, inp, retry_count=retry_count)
        except Exception:
            log.debug("agentreliability: tool_call setup failed", exc_info=True)
        return _NullToolCall()

    def trace_tool(self, name: Optional[str] = None, *, retry_count: int = 0) -> Callable:
        """Decorator for tool functions (synchronous or asynchronous). Arguments are the input, the return value is the output."""

        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__

            if inspect.isasyncgenfunction(func):
                warnings.warn(
                    f"agentreliability: async generator tools are not supported yet; '{func.__name__}' runs untraced.",
                    stacklevel=2,
                )
                return func

            if inspect.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    call = self.tool_call(tool_name, self._args_payload(func, args, kwargs), retry_count=retry_count)
                    async with call:
                        result = await func(*args, **kwargs)
                        call.set_output(result)
                        return result

                return async_wrapper

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                call = self.tool_call(tool_name, self._args_payload(func, args, kwargs), retry_count=retry_count)
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

