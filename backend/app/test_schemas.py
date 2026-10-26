"""Validation models for test cases.

A test case =
  input        what the agent was asked (informational; replay does not run a model)
  steps        the recorded script. Tool-call steps double as the MOCK responses.
  expected     what we expect the replay to produce (editable by the developer)
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .schemas import Step

Category = Literal["timeout", "failed_tool_call", "explicit_error", "unexpected_exception"]


class ErrorCondition(BaseModel):
    step_index: int = Field(ge=0)
    category: Category


class Expected(BaseModel):
    status: Literal["success", "failed"] = "success"
    tool_sequence: list[str] = Field(default_factory=list)
    final_output: Any = None  # None means "don't check the output"
    error_conditions: list[ErrorCondition] = Field(default_factory=list)
    # Phase 6 Step 3: Granular assertions for trace-derived regression tests
    expected_output_fields: Optional[list[str]] = Field(default=None)
    expected_error_type: Optional[str] = Field(default=None, max_length=200)
    max_duration_ms: Optional[float] = Field(default=None, ge=0)
    strict_order: bool = True
    allow_additional_tools: bool = False


class TestCaseIn(BaseModel):
    __test__ = False  # stop pytest from trying to collect this class

    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    agent_name: str = Field(min_length=1, max_length=120)
    input: Any = None
    steps: list[Step] = Field(min_length=1, max_length=500)
    expected: Expected


class FromExecutionIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    expected: Optional[Expected] = None


class FromTraceIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    expected: Optional[Expected] = None


class CreateBaselineIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    source_type: Literal["trace", "execution"] = "trace"
    source_id: str = Field(min_length=1, max_length=255)
    expected: Optional[Expected] = None


class UpdateBaselineIn(BaseModel):
    source_type: Literal["trace", "execution"] = "trace"
    source_id: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)
    expected: Optional[Expected] = None


class CompareRequestIn(BaseModel):
    candidate_trace_id: Optional[str] = None
    candidate_execution_id: Optional[int] = None
    duration_tolerance_pct: float = Field(default=50.0, ge=0.0, le=1000.0)  # flag regression if > 150% of baseline


