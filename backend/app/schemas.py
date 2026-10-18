"""Log format validation.

A valid log is a JSON object:
{
  "agent_name": "support-bot",          (required)
  "run_id": "abc",                      (optional)
  "steps": [                            (required, at least 1)
    {"type": "llm_call|tool_call|error|...",   (required)
     "name": "search_web",                      (optional)
     "status": "success|error|failed|timeout",  (optional, default "success")
     "timestamp": "2026-01-01T10:00:00Z",       (optional)
     "duration_ms": 120,                        (optional)
     "timeout_ms": 5000,                        (optional)
     "input": ..., "output": ..., "error": "message"}
  ]
}
"""
from typing import Any, Optional

from pydantic import BaseModel, Field


class Step(BaseModel):
    type: str = Field(min_length=1)
    name: Optional[str] = None
    status: str = "success"
    timestamp: Optional[str] = None
    duration_ms: Optional[float] = Field(default=None, ge=0)
    timeout_ms: Optional[float] = Field(default=None, gt=0)
    input: Any = None
    output: Any = None
    error: Optional[str] = None


class AgentLog(BaseModel):
    agent_name: str = Field(min_length=1)
    run_id: Optional[str] = None
    steps: list[Step] = Field(min_length=1)

