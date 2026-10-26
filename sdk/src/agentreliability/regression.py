"""Deterministic regression comparison engine.

Compares current test execution runs against previously saved baseline runs.
Classifies tests into:
  - new_failures: passed (or absent) in baseline, now failed
  - fixed_failures: failed in baseline, now passed
  - unchanged_failures: failed in both baseline and current
  - passed: passed in both (or new passing test)
Categorizes regression differences into:
  - breaking_regression (status regression, missing tool, missing output keys, duration limit exceeded)
  - performance_regression (latency increase beyond tolerance threshold)
  - informational_change (benign output value change, extra tools)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def compare_runs(
    current_runs: List[dict],
    baseline_runs: Optional[List[dict]],
    duration_tolerance_pct: float = 50.0,
) -> dict:
    """Compare a current list of test results against an optional baseline."""
    if not baseline_runs:
        has_failed = any(r.get("status") == "failed" for r in current_runs)
        return {
            "has_baseline": False,
            "verdict": "failed" if has_failed else "passed",
            "is_regression": False,
            "summary": {
                "new_failures": [r for r in current_runs if r.get("status") == "failed"],
                "fixed_failures": [],
                "unchanged_failures": [],
                "passed": [r for r in current_runs if r.get("status") == "passed"],
                "performance_warnings": [],
                "informational": [],
            },
            "counts": {
                "total": len(current_runs),
                "new_failures": sum(1 for r in current_runs if r.get("status") == "failed"),
                "breaking": 0,
                "performance": 0,
                "informational": 0,
                "fixed_failures": 0,
                "unchanged_failures": 0,
                "passed": sum(1 for r in current_runs if r.get("status") == "passed"),
            },
            "differences": [],
        }

    baseline_map = {b.get("name") or b.get("test_name"): b for b in baseline_runs}

    new_failures = []
    fixed_failures = []
    unchanged_failures = []
    passed = []
    diffs = []
    breaking_count = 0
    perf_count = 0
    info_count = 0

    for curr in current_runs:
        name = curr.get("name") or curr.get("test_name")
        curr_status = curr.get("status")
        base = baseline_map.get(name)

        if base is None:
            # Not in baseline
            if curr_status == "failed":
                new_failures.append(curr)
                breaking_count += 1
                diffs.append({
                    "test_name": name,
                    "category": "status_regression",
                    "severity": "breaking_regression",
                    "message": f"Test '{name}' failed in current run (absent from baseline).",
                })
            else:
                passed.append(curr)
            continue

        base_status = base.get("status")

        # 1. Status classification
        if curr_status == "failed" and base_status == "passed":
            item = {
                **curr,
                "regression_note": "Regression: passed in baseline, failed in current run",
            }
            new_failures.append(item)
            breaking_count += 1
            diffs.append({
                "test_name": name,
                "category": "status_regression",
                "severity": "breaking_regression",
                "message": f"Regression: test '{name}' passed in baseline, failed in current run.",
            })
        elif curr_status == "passed" and base_status == "failed":
            fixed_failures.append({
                **curr,
                "regression_note": "Fixed: failed in baseline, now passing",
            })
        elif curr_status == "failed" and base_status == "failed":
            unchanged_failures.append({
                **curr,
                "regression_note": "Unchanged failure: failed in baseline and still failing",
            })
        else:
            passed.append(curr)

        # 2. Timing and duration comparison
        curr_dur = curr.get("duration_ms")
        base_dur = base.get("duration_ms")
        expected = curr.get("expected") or base.get("expected") or {}
        max_allowed_dur = (
            expected.get("max_duration_ms")
            or curr.get("max_duration_ms")
            or base.get("max_duration_ms")
        )
        tol = expected.get("duration_tolerance_pct", duration_tolerance_pct)

        if max_allowed_dur is not None and curr_dur is not None and curr_dur > max_allowed_dur:
            diffs.append({
                "test_name": name,
                "category": "duration_threshold_exceeded",
                "severity": "breaking_regression",
                "message": f"Test '{name}' duration ({curr_dur:.1f} ms) exceeded maximum allowed limit ({max_allowed_dur:.1f} ms).",
            })
            breaking_count += 1
        elif base_dur is not None and curr_dur is not None and base_dur > 0:
            pct_change = ((curr_dur - base_dur) / base_dur) * 100.0
            if pct_change > tol:
                diffs.append({
                    "test_name": name,
                    "category": "latency_regression",
                    "severity": "performance_regression",
                    "message": f"Test '{name}' execution latency increased by {pct_change:.1f}% ({curr_dur:.1f} ms vs baseline {base_dur:.1f} ms, tolerance {tol}%).",
                })
                perf_count += 1

        # 3. Tool sequence comparison
        curr_tools = curr.get("observed", {}).get("tool_sequence") or curr.get("tool_sequence")
        base_tools = base.get("observed", {}).get("tool_sequence") or base.get("tool_sequence")
        if (
            curr_tools is not None
            and base_tools is not None
            and curr_status == "passed"
            and base_status == "passed"
        ):
            missing_tools = [t for t in base_tools if t not in curr_tools]
            if missing_tools:
                diffs.append({
                    "test_name": name,
                    "category": "missing_tool_call",
                    "severity": "breaking_regression",
                    "message": f"Test '{name}' missing tool call(s) present in baseline: {', '.join(missing_tools)}.",
                })
                breaking_count += 1
            elif len(curr_tools) > len(base_tools):
                diffs.append({
                    "test_name": name,
                    "category": "additional_tools",
                    "severity": "informational_change",
                    "message": f"Test '{name}' executed additional tool calls compared to baseline.",
                })
                info_count += 1

        # 4. Final output comparison
        curr_out = curr.get("observed", {}).get("final_output") or curr.get("final_output")
        base_out = base.get("observed", {}).get("final_output") or base.get("final_output")
        if (
            curr_out is not None
            and base_out is not None
            and curr_status == "passed"
            and base_status == "passed"
        ):
            if isinstance(base_out, dict) and isinstance(curr_out, dict):
                missing_keys = [k for k in base_out.keys() if k not in curr_out]
                if missing_keys:
                    diffs.append({
                        "test_name": name,
                        "category": "missing_output_keys",
                        "severity": "breaking_regression",
                        "message": f"Test '{name}' missing output key(s) present in baseline: {', '.join(missing_keys)}.",
                    })
                    breaking_count += 1
                elif curr_out != base_out:
                    diffs.append({
                        "test_name": name,
                        "category": "output_value_change",
                        "severity": "informational_change",
                        "message": f"Test '{name}' output value differs from baseline.",
                    })
                    info_count += 1
            elif curr_out != base_out:
                diffs.append({
                    "test_name": name,
                    "category": "output_value_change",
                    "severity": "informational_change",
                    "message": f"Test '{name}' output value differs from baseline.",
                })
                info_count += 1

    if breaking_count > 0:
        verdict = "breaking_regression"
    elif perf_count > 0:
        verdict = "performance_regression"
    elif info_count > 0:
        verdict = "informational_change"
    else:
        verdict = "passed"

    return {
        "has_baseline": True,
        "verdict": verdict,
        "is_regression": breaking_count > 0,
        "summary": {
            "new_failures": new_failures,
            "fixed_failures": fixed_failures,
            "unchanged_failures": unchanged_failures,
            "passed": passed,
            "performance_warnings": [
                d for d in diffs if d.get("severity") == "performance_regression"
            ],
            "informational": [
                d for d in diffs if d.get("severity") == "informational_change"
            ],
        },
        "counts": {
            "total": len(current_runs),
            "new_failures": len(new_failures),
            "breaking": breaking_count,
            "performance": perf_count,
            "informational": info_count,
            "fixed_failures": len(fixed_failures),
            "unchanged_failures": len(unchanged_failures),
            "passed": len(passed),
        },
        "differences": diffs,
    }

