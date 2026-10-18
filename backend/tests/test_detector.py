import pytest
from pydantic import ValidationError

from app.detector import analyze
from app.schemas import AgentLog


def make(*steps):
    return AgentLog(agent_name="a", steps=list(steps))


def test_healthy_run_is_success():
    r = analyze(make({"type": "llm_call", "status": "success"}))
    assert r["status"] == "success" and r["findings"] == []


def test_explicit_error_step():
    r = analyze(make({"type": "error", "error": "boom"}))
    assert r["findings"][0]["category"] == "explicit_error"
    assert "boom" in r["findings"][0]["explanation"]


def test_failed_tool_call():
    r = analyze(make({"type": "tool_call", "name": "x", "status": "failed", "error": "503"}))
    assert r["status"] == "failed"
    assert r["findings"][0]["category"] == "failed_tool_call"


def test_timeout_by_status():
    r = analyze(make({"type": "tool_call", "status": "timeout"}))
    assert r["findings"][0]["category"] == "timeout"


def test_timeout_by_duration():
    r = analyze(make({"type": "tool_call", "duration_ms": 200, "timeout_ms": 100}))
    assert r["findings"][0]["category"] == "timeout"


def test_timeout_by_message():
    r = analyze(make({"type": "llm_call", "status": "error", "error": "Request timed out"}))
    assert r["findings"][0]["category"] == "timeout"


def test_duration_within_limit_is_ok():
    r = analyze(make({"type": "tool_call", "duration_ms": 50, "timeout_ms": 100}))
    assert r["status"] == "success"


def test_one_finding_per_step_and_index():
    r = analyze(make({"type": "llm_call"}, {"type": "tool_call", "status": "failed"}))
    assert len(r["findings"]) == 1 and r["findings"][0]["step_index"] == 1


def test_validation_rejects_empty_steps_and_missing_agent():
    with pytest.raises(ValidationError):
        AgentLog(agent_name="a", steps=[])
    with pytest.raises(ValidationError):
        AgentLog.model_validate({"steps": [{"type": "x"}]})

