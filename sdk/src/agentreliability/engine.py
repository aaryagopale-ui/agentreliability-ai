"""Pure Python deterministic replay engine for offline testing and CLI.

Zero external dependencies - runs identically in CLI, CI, or server.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

MODE = "deterministic_simulation"
DISCLAIMER = (
    "Deterministic simulation: recorded steps were replayed with mocked tool responses. "
    "No real agent, model or external tool was executed, so this does not reproduce live model behavior."
)

FAIL_STATUSES = {"error", "failed", "failure", "exception"}
TIMEOUT_WORDS = ("timeout", "timed out", "time out")


def classify_step(step: dict) -> Optional[Tuple[str, str]]:
    """Return (category, explanation) for a failing step, or None if healthy."""
    stype = str(step.get("type", "")).lower()
    name = step.get("name")
    status = str(step.get("status", "success")).lower()
    err = str(step.get("error") or "").strip()
    label = f"'{name}'" if name else stype
    is_tool = (stype == "tool_call")

    duration_ms = step.get("duration_ms")
    timeout_ms = step.get("timeout_ms")

    # Rule 1: timeouts
    if status == "timeout":
        return "timeout", f"Step {label} has status 'timeout'."
    if duration_ms is not None and timeout_ms is not None and duration_ms > timeout_ms:
        return "timeout", f"Step {label} took {duration_ms:g} ms, exceeding its limit of {timeout_ms:g} ms."
    if err and any(w in err.lower() for w in TIMEOUT_WORDS):
        return "timeout", f"Step {label} reported a timeout: {err}"

    # Rule 1b: unexpected exception
    if status == "exception" or "traceback" in err.lower() or "exception" in err.lower():
        detail = f": {err}" if err else ""
        return "unexpected_exception", f"Step {label} raised an unexpected exception{detail}"

    failed = (status in FAIL_STATUSES) or bool(err)

    # Rule 2: failed tool calls
    if is_tool and failed:
        return "failed_tool_call", f"Tool call {label} failed" + (f": {err}" if err else f" (status '{status}').")

    # Rule 3: explicit errors
    if stype == "error" or failed:
        return "explicit_error", f"Step {label} reported an error" + (f": {err}" if err else f" (status '{status}').")

    return None


class MockToolError(Exception):
    """Raised when the replay asks for a tool that has no mock response."""


class MockToolRegistry:
    """Hands out recorded tool responses in order per tool name."""

    def __init__(self, steps: List[dict]):
        self._queues: Dict[str, deque] = defaultdict(deque)
        for s in steps:
            if str(s.get("type", "")).lower() == "tool_call" and s.get("name"):
                self._queues[s["name"]].append(s)

    def call(self, name: Optional[str]) -> dict:
        if not name:
            raise MockToolError("tool call has no name, so no mock response can be found")
        if not self._queues[name]:
            raise MockToolError(f"no mock response registered for tool '{name}'")
        return self._queues[name].popleft()


def analyze_steps(steps: List[dict]) -> List[dict]:
    findings = []
    for i, step in enumerate(steps):
        res = classify_step(step)
        if res:
            findings.append({"step_index": i, "category": res[0], "explanation": res[1]})
    return findings


def _norm(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, sort_keys=True, default=str)


def final_output_of(steps: List[dict]) -> Any:
    for s in reversed(steps):
        if s.get("output") is not None:
            return s["output"]
    return None


def tool_sequence_of(steps: List[dict]) -> List[str]:
    return [s.get("name") or "<unnamed>" for s in steps if str(s.get("type", "")).lower() == "tool_call"]


def replay_steps(steps: List[dict]) -> List[dict]:
    registry = MockToolRegistry(steps)
    observed = []
    for s in steps:
        try:
            if str(s.get("type", "")).lower() == "tool_call":
                s = registry.call(s.get("name"))
            observed.append(dict(s))
        except MockToolError as e:
            observed.append({**s, "status": "exception", "error": f"MockToolError: {e}"})
        except Exception as e:
            observed.append({**s, "status": "exception", "error": f"{type(e).__name__}: {e}"})
    return observed


def run_test(test: dict) -> dict:
    started = time.perf_counter()
    expected = test.get("expected", {})
    steps = test.get("steps", [])
    observed = replay_steps(steps)
    findings = analyze_steps(observed)
    mismatches = []

    # 1. Error conditions
    expected_set = {(c["step_index"], c["category"]) for c in expected.get("error_conditions", [])}
    for f in findings:
        if (f["step_index"], f["category"]) not in expected_set:
            mismatches.append({
                "kind": f["category"],
                "step_index": f["step_index"],
                "message": "Unexpected: " + f["explanation"]
            })
    observed_set = {(f["step_index"], f["category"]) for f in findings}
    for idx, cat in sorted(expected_set - observed_set):
        mismatches.append({
            "kind": "missing_expected_error",
            "step_index": idx,
            "message": f"Expected a '{cat}' at step {idx + 1}, but it did not happen."
        })

    # 2. Tool-call sequence
    exp_seq = expected.get("tool_sequence", [])
    obs_seq = tool_sequence_of(observed)
    if exp_seq != obs_seq:
        pos = next((i for i, (a, b) in enumerate(zip(exp_seq, obs_seq)) if a != b), min(len(exp_seq), len(obs_seq)))
        want = exp_seq[pos] if pos < len(exp_seq) else "(nothing)"
        got = obs_seq[pos] if pos < len(obs_seq) else "(nothing)"
        mismatches.append({
            "kind": "sequence_mismatch",
            "step_index": None,
            "message": f"Tool-call sequence differs at position {pos + 1}: expected {want}, observed {got}. Expected {exp_seq}, observed {obs_seq}."
        })

    # 3. Final output
    obs_out = final_output_of(observed)
    exp_out = expected.get("final_output")
    if exp_out is not None:
        if obs_out is None:
            mismatches.append({
                "kind": "missing_output",
                "step_index": None,
                "message": "Expected a final output but none was produced."
            })
        elif _norm(exp_out) != _norm(obs_out):
            mismatches.append({
                "kind": "output_mismatch",
                "step_index": None,
                "message": f"Final output differs. Expected {_norm(exp_out)!r}, observed {_norm(obs_out)!r}."
            })

    # 4. Overall status
    obs_status = "failed" if findings else "success"
    if obs_status != expected.get("status", "success"):
        mismatches.append({
            "kind": "status_mismatch",
            "step_index": None,
            "message": f"Expected overall status '{expected.get('status')}', observed '{obs_status}'."
        })

    return {
        "status": "failed" if mismatches else "passed",
        "mode": MODE,
        "disclaimer": DISCLAIMER,
        "observed": {
            "steps": observed,
            "findings": findings,
            "status": obs_status,
            "tool_sequence": obs_seq,
            "final_output": obs_out
        },
        "mismatches": mismatches,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3)
    }

