"""Deterministic replay engine.

IMPORTANT: this is a SIMULATION, not a re-run of a real agent.
  * No language model is called.
  * No real tool is called. Tool calls are answered by MockToolRegistry, which only
    returns responses stored in the test case.
  * Uploaded data is only ever treated as data (never executed).
Same test case in -> same result out, every time.
"""
import json
import time
from collections import defaultdict, deque

from .detector import classify_step
from .schemas import Step

MODE = "deterministic_simulation"
DISCLAIMER = (
    "Deterministic simulation: recorded steps were replayed with mocked tool responses. "
    "No real agent, model or external tool was executed, so this does not reproduce live model behavior."
)


class MockToolError(Exception):
    """Raised when the replay asks for a tool that has no mock response."""


class MockToolRegistry:
    """Hands out the recorded responses, in order, per tool name."""

    def __init__(self, steps: list[dict]):
        self._queues: dict[str, deque] = defaultdict(deque)
        for s in steps:
            if str(s.get("type", "")).lower() == "tool_call" and s.get("name"):
                self._queues[s["name"]].append(s)

    def call(self, name):
        if not name:
            raise MockToolError("tool call has no name, so no mock response can be found")
        if not self._queues[name]:
            raise MockToolError(f"no mock response registered for tool '{name}'")
        return self._queues[name].popleft()


def _is_exception_like(step: Step) -> bool:
    err = (step.error or "").lower()
    return step.status.lower() == "exception" or "traceback" in err or "exception" in err


def classify_replay_step(step: Step):
    """Same rules as Phase 1, plus 'unexpected_exception'. Timeouts win over everything."""
    result = classify_step(step)
    if result and result[0] == "timeout":
        return result
    if _is_exception_like(step):
        label = f"'{step.name}'" if step.name else step.type
        detail = f": {step.error}" if step.error else ""
        return "unexpected_exception", f"Step {label} raised an unexpected exception{detail}"
    return result


def analyze_steps(steps: list[dict]) -> list[dict]:
    """Return findings for raw step dicts (used by test generation and replay)."""
    findings = []
    for i, raw in enumerate(steps):
        res = classify_replay_step(Step.model_validate(raw))
        if res:
            findings.append({"step_index": i, "category": res[0], "explanation": res[1]})
    return findings


def _norm(value):
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, sort_keys=True, default=str)


def final_output_of(steps: list[dict]):
    for s in reversed(steps):
        if s.get("output") is not None:
            return s["output"]
    return None


def tool_sequence_of(steps: list[dict]) -> list[str]:
    return [s.get("name") or "<unnamed>" for s in steps if str(s.get("type", "")).lower() == "tool_call"]


def replay_steps(steps: list[dict]) -> list[dict]:
    """Play the script. Any problem becomes an observed 'exception' step, never a crash."""
    registry = MockToolRegistry(steps)
    observed = []
    for s in steps:
        try:
            if str(s.get("type", "")).lower() == "tool_call":
                s = registry.call(s.get("name"))
            observed.append(dict(s))
        except MockToolError as e:
            observed.append({**s, "status": "exception", "error": f"MockToolError: {e}"})
        except Exception as e:  # defensive: one bad step must not crash the run
            observed.append({**s, "status": "exception", "error": f"{type(e).__name__}: {e}"})
    return observed


def run_test(test: dict) -> dict:
    """Replay one stored test case and compare with its expected results."""
    started = time.perf_counter()
    expected = test["expected"]
    observed = replay_steps(test["steps"])
    findings = analyze_steps(observed)
    mismatches = []

    # 1. Unexpected failures (failed tool calls, timeouts, exceptions, errors)
    expected_set = {(c["step_index"], c["category"]) for c in expected.get("error_conditions", [])}
    for f in findings:
        if (f["step_index"], f["category"]) not in expected_set:
            mismatches.append({"kind": f["category"], "step_index": f["step_index"],
                               "message": "Unexpected: " + f["explanation"]})
    observed_set = {(f["step_index"], f["category"]) for f in findings}
    for idx, cat in sorted(expected_set - observed_set):
        mismatches.append({"kind": "missing_expected_error", "step_index": idx,
                           "message": f"Expected a '{cat}' at step {idx + 1}, but it did not happen."})

    # 2. Tool-call sequence
    exp_seq, obs_seq = expected.get("tool_sequence", []), tool_sequence_of(observed)
    if exp_seq != obs_seq:
        pos = next((i for i, (a, b) in enumerate(zip(exp_seq, obs_seq)) if a != b), min(len(exp_seq), len(obs_seq)))
        want = exp_seq[pos] if pos < len(exp_seq) else "(nothing)"
        got = obs_seq[pos] if pos < len(obs_seq) else "(nothing)"
        mismatches.append({"kind": "sequence_mismatch", "step_index": None,
                           "message": f"Tool-call sequence differs at position {pos + 1}: expected {want}, observed {got}. "
                                      f"Expected {exp_seq}, observed {obs_seq}."})

    # 3. Final output
    obs_out = final_output_of(observed)
    exp_out = expected.get("final_output")
    if exp_out is not None:
        if obs_out is None:
            mismatches.append({"kind": "missing_output", "step_index": None,
                               "message": "Expected a final output but none was produced."})
        elif _norm(exp_out) != _norm(obs_out):
            mismatches.append({"kind": "output_mismatch", "step_index": None,
                               "message": f"Final output differs. Expected {_norm(exp_out)!r}, observed {_norm(obs_out)!r}."})

    # 4. Overall status
    obs_status = "failed" if findings else "success"
    if obs_status != expected.get("status", "success"):
        mismatches.append({"kind": "status_mismatch", "step_index": None,
                           "message": f"Expected overall status '{expected.get('status')}', observed '{obs_status}'."})

    return {
        "status": "failed" if mismatches else "passed",
        "mode": MODE,
        "disclaimer": DISCLAIMER,
        "observed": {"steps": observed, "findings": findings, "status": obs_status,
                     "tool_sequence": obs_seq, "final_output": obs_out},
        "mismatches": mismatches,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
    }

