from app.replay import classify_replay_step, replay_steps, run_test
from app.schemas import Step
from app.testgen import generate_from_execution


def tool(name, **kw):
    return {"type": "tool_call", "name": name, "status": "success", **kw}


def case(steps, **expected):
    base = {"status": "success", "tool_sequence": [], "final_output": None, "error_conditions": []}
    return {"steps": steps, "expected": {**base, **expected}}


def kinds(result):
    return [m["kind"] for m in result["mismatches"]]


def test_clean_run_passes_and_is_labelled_simulation():
    r = run_test(case([tool("a", output="x")], tool_sequence=["a"], final_output="x"))
    assert r["status"] == "passed" and r["mismatches"] == []
    assert r["mode"] == "deterministic_simulation"
    assert "No real agent" in r["disclaimer"]


def test_replay_is_deterministic():
    c = case([tool("a", output=1), tool("b", status="failed", error="x")], tool_sequence=["a", "b"])
    r1, r2 = run_test(c), run_test(c)
    r1.pop("duration_ms"); r2.pop("duration_ms")
    assert r1 == r2


def test_unexpected_failed_tool_call():
    r = run_test(case([tool("a", status="failed", error="503")], tool_sequence=["a"]))
    assert r["status"] == "failed" and "failed_tool_call" in kinds(r)


def test_unexpected_timeout():
    r = run_test(case([tool("a", duration_ms=500, timeout_ms=100)], tool_sequence=["a"]))
    assert "timeout" in kinds(r)


def test_unexpected_exception():
    r = run_test(case([tool("a", status="exception", error="ValueError: bad")], tool_sequence=["a"]))
    assert "unexpected_exception" in kinds(r)


def test_exception_text_in_error_counts_as_exception():
    step = Step(type="llm_call", status="error", error="Traceback (most recent call last)")
    assert classify_replay_step(step)[0] == "unexpected_exception"


def test_timeout_beats_exception():
    step = Step(type="tool_call", status="timeout", error="Exception: timed out")
    assert classify_replay_step(step)[0] == "timeout"


def test_expected_failure_passes():
    c = case([tool("a", status="failed", error="x")], status="failed", tool_sequence=["a"],
             error_conditions=[{"step_index": 0, "category": "failed_tool_call"}])
    assert run_test(c)["status"] == "passed"


def test_missing_expected_error():
    c = case([tool("a")], tool_sequence=["a"], error_conditions=[{"step_index": 0, "category": "timeout"}])
    assert "missing_expected_error" in kinds(run_test(c))


def test_sequence_mismatch():
    r = run_test(case([tool("a"), tool("b")], tool_sequence=["a", "c"]))
    assert "sequence_mismatch" in kinds(r)


def test_missing_output():
    r = run_test(case([tool("a")], tool_sequence=["a"], final_output="hello"))
    assert "missing_output" in kinds(r)


def test_output_mismatch():
    r = run_test(case([tool("a", output="one")], tool_sequence=["a"], final_output="two"))
    assert "output_mismatch" in kinds(r)


def test_structured_output_compare_ignores_key_order():
    r = run_test(case([tool("a", output={"x": 1, "y": 2})], tool_sequence=["a"], final_output={"y": 2, "x": 1}))
    assert r["status"] == "passed"


def test_status_mismatch():
    r = run_test(case([tool("a", status="failed")], tool_sequence=["a"], status="success"))
    assert "status_mismatch" in kinds(r)


def test_unnamed_tool_call_becomes_exception_not_crash():
    observed = replay_steps([{"type": "tool_call", "status": "success"}])
    assert observed[0]["status"] == "exception" and "MockToolError" in observed[0]["error"]


def test_generate_from_execution_captures_expectations():
    execution = {
        "id": 7, "agent_name": "bot", "run_id": "r1",
        "steps": [
            {"type": "llm_call", "status": "success", "input": "hi", "output": "plan"},
            tool("search", status="failed", error="503"),
            {"type": "llm_call", "status": "success", "output": "sorry"},
        ],
    }
    g = generate_from_execution(execution)
    assert g["input"] == "hi" and g["agent_name"] == "bot"
    assert g["expected"]["tool_sequence"] == ["search"]
    assert g["expected"]["final_output"] == "sorry"
    assert g["expected"]["status"] == "failed"
    assert g["expected"]["error_conditions"] == [{"step_index": 1, "category": "failed_tool_call"}]
    # A freshly generated test replays to "passed" (it reproduces the recording).
    assert run_test(g)["status"] == "passed"

