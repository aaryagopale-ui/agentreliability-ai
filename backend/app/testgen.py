"""Turn a saved execution into a reusable test case."""
from .replay import analyze_steps, final_output_of, tool_sequence_of


def generate_from_execution(execution: dict, name: str | None = None) -> dict:
    steps = execution["steps"]
    findings = analyze_steps(steps)
    first_input = next((s["input"] for s in steps if s.get("input") is not None), None)
    label = execution.get("run_id") or f"execution #{execution['id']}"
    return {
        "name": name or f"{execution['agent_name']} / {label}",
        "description": f"Generated from execution #{execution['id']}. Expected results are the recorded behavior; edit them as needed.",
        "agent_name": execution["agent_name"],
        "input": first_input,
        "steps": steps,
        "expected": {
            "status": "failed" if findings else "success",
            "tool_sequence": tool_sequence_of(steps),
            "final_output": final_output_of(steps),
            "error_conditions": [{"step_index": f["step_index"], "category": f["category"]} for f in findings],
        },
    }

