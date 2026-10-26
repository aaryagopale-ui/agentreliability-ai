"""Validation for incoming SDK trace events.

All limits live here so they are easy to find and change.
"""
import json
import re
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_EVENTS_PER_BATCH = 100
MAX_BODY_BYTES = 1_000_000
MAX_PAYLOAD_CHARS = 16_000      # serialized size of one input/output value
MAX_METADATA_KEYS = 20
MAX_ERROR_MESSAGE_CHARS = 2_000

# Stable event IDs: letters, digits and . _ : - only (no spaces, no weird characters).
ID_PATTERN = re.compile(r"^[A-Za-z0-9._:\-]{8,100}$")


def _check_id(value: str, label: str) -> str:
    if not ID_PATTERN.match(value):
        raise ValueError(f"{label} must be 8-100 characters of letters, digits, . _ : -")
    return value


class TraceEvent(BaseModel):
    event_id: str                      # unique per project; used to ignore duplicates
    execution_id: str
    agent_name: str = Field(min_length=1, max_length=120)
    type: Literal["execution_start", "tool_call", "execution_end"]
    timestamp: datetime                # naive timestamps are treated as UTC
    input: Any = None
    output: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    # tool_call fields
    tool_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    duration_ms: Optional[float] = Field(default=None, ge=0, le=7 * 24 * 3600 * 1000)
    # tool_call: success | error | timeout      execution_end: success | failed
    status: Optional[Literal["success", "error", "timeout", "failed"]] = None
    error_type: Optional[str] = Field(default=None, max_length=200)
    error_message: Optional[str] = None
    parent_call_id: Optional[str] = Field(default=None, max_length=100)
    retry_count: Optional[int] = Field(default=0, ge=0, le=100)

    @field_validator("event_id")
    @classmethod
    def _event_id(cls, v):
        return _check_id(v, "event_id")

    @field_validator("execution_id")
    @classmethod
    def _execution_id(cls, v):
        return _check_id(v, "execution_id")

    @field_validator("input", "output")
    @classmethod
    def _payload_size(cls, v):
        if v is not None and len(json.dumps(v, default=str)) > MAX_PAYLOAD_CHARS:
            raise ValueError(f"payload is larger than {MAX_PAYLOAD_CHARS} characters")
        return v

    @field_validator("metadata")
    @classmethod
    def _metadata(cls, v):
        if len(v) > MAX_METADATA_KEYS:
            raise ValueError(f"metadata can have at most {MAX_METADATA_KEYS} keys")
        for k, val in v.items():
            if len(k) > 64:
                raise ValueError("metadata keys must be at most 64 characters")
            if not isinstance(val, (str, int, float, bool)) and val is not None:
                raise ValueError("metadata values must be text, numbers or booleans")
            if isinstance(val, str) and len(val) > 256:
                raise ValueError("metadata text values must be at most 256 characters")
        return v

    @field_validator("error_message")
    @classmethod
    def _truncate_error(cls, v):
        return v[:MAX_ERROR_MESSAGE_CHARS] if v else v

    @model_validator(mode="after")
    def _per_type_rules(self):
        if self.type == "tool_call":
            if not self.tool_name:
                raise ValueError("tool_name is required for tool_call events")
            if self.status not in ("success", "error", "timeout"):
                raise ValueError("tool_call status must be success, error or timeout")
        elif self.type == "execution_end":
            if self.status not in ("success", "failed"):
                raise ValueError("execution_end status must be success or failed")
        return self


class IngestRequest(BaseModel):
    events: list[TraceEvent] = Field(min_length=1, max_length=MAX_EVENTS_PER_BATCH)

