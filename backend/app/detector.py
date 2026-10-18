"""Deterministic failure detection. No AI: same input always gives same output.

Each step yields at most ONE finding. Priority: timeout > failed_tool_call > explicit_error.
"""
from .schemas import AgentLog, Step

FAIL_STATUSES = {"error", "failed", "failure", "exception"}
TIMEOUT_WORDS = ("timeout", "timed out", "time out")


def classify_step(step: Step) -> tuple[str, str] | None:
    """Return (category, explanation) for a failing step, or None if healthy."""
    status = step.status.lower()
    err = (step.error or "").strip()
    label = f"'{step.name}'" if step.name else step.type
    is_tool = step.type.lower() == "tool_call"

    # Rule 1: timeouts
    if status == "timeout":
        return "timeout", f"Step {label} has status 'timeout'."
    if step.duration_ms is not None and step.timeout_ms is not None and step.duration_ms > step.timeout_ms:
        return "timeout", (
            f"Step {label} took {step.duration_ms:g} ms, exceeding its limit of {step.timeout_ms:g} ms."
        )
    if err and any(w in err.lower() for w in TIMEOUT_WORDS):
        return "timeout", f"Step {label} reported a timeout: {err}"

    failed = status in FAIL_STATUSES or bool(err)

    # Rule 2: failed tool calls
    if is_tool and failed:
        return "failed_tool_call", f"Tool call {label} failed" + (f": {err}" if err else f" (status '{status}').")

    # Rule 3: explicit errors
    if step.type.lower() == "error" or failed:
        return "explicit_error", f"Step {label} reported an error" + (f": {err}" if err else f" (status '{status}').")

    return None


def analyze(log: AgentLog) -> dict:
    """Return {'status': 'success'|'failed', 'findings': [...]}."""
    findings = []
    for i, step in enumerate(log.steps):
        result = classify_step(step)
        if result:
            category, explanation = result
            findings.append({"step_index": i, "category": category, "explanation": explanation})
    return {"status": "failed" if findings else "success", "findings": findings}

