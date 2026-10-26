"""AgentReliability AI Python SDK."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional
from . import integrations
from .monitor import AgentMonitor
from .redaction import Redactor

__version__ = "0.1.0"

_default_monitor: Optional[AgentMonitor] = None


def get_default_monitor() -> AgentMonitor:
    """Get or create the singleton AgentMonitor initialized from environment variables."""
    global _default_monitor
    if _default_monitor is None:
        _default_monitor = AgentMonitor()
    return _default_monitor


def trace_agent(agent_name: str, *, metadata: Optional[Dict[str, Any]] = None) -> Callable:
    """Convenience decorator to trace agent executions using environment configuration."""
    return get_default_monitor().trace_agent(agent_name, metadata=metadata)


def trace_tool(tool_name: str, *, retry_count: int = 0) -> Callable:
    """Convenience decorator to trace tool calls using environment configuration."""
    return get_default_monitor().trace_tool(tool_name, retry_count=retry_count)


def trace_execution(
    name: str,
    input_data: Any = None,
    *,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Convenience context manager to trace an execution block using environment configuration."""
    return get_default_monitor().trace_execution(name, input_data=input_data, metadata=metadata)


def tool_call(name: str, input: Any = None, *, retry_count: int = 0, **kwargs: Any):
    """Convenience context manager to trace a tool call inside an execution using environment configuration."""
    return get_default_monitor().tool_call(name, input=input, retry_count=retry_count, **kwargs)


def flush(timeout: float = 5.0) -> bool:
    """Flush pending traces on the default monitor before process exit."""
    return get_default_monitor().flush(timeout)


def init(
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    *,
    capture_io: Optional[bool] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> AgentMonitor:
    """Explicitly initialize or reconfigure the default singleton AgentMonitor."""
    global _default_monitor
    _default_monitor = AgentMonitor(
        endpoint=endpoint,
        api_key=api_key,
        capture_io=capture_io,
        metadata=metadata,
        **kwargs,
    )
    return _default_monitor


__all__ = [
    "AgentMonitor",
    "Redactor",
    "init",
    "trace_agent",
    "trace_tool",
    "trace_execution",
    "tool_call",
    "flush",
    "get_default_monitor",
    "integrations",
    "__version__",
]
