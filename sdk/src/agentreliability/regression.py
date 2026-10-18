"""Deterministic regression comparison engine.

Compares current test execution runs against previously saved baseline runs.
Classifies tests into:
  - new_failures: passed (or absent) in baseline, now failed
  - fixed_failures: failed in baseline, now passed
  - unchanged_failures: failed in both baseline and current
  - passed: passed in both (or new passing test)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def compare_runs(current_runs: List[dict], baseline_runs: Optional[List[dict]]) -> dict:
    """Compare a current list of test results against an optional baseline."""
    if not baseline_runs:
        return {
            "has_baseline": False,
            "summary": {
                "new_failures": [r for r in current_runs if r["status"] == "failed"],
                "fixed_failures": [],
                "unchanged_failures": [],
                "passed": [r for r in current_runs if r["status"] == "passed"]
            },
            "counts": {
                "total": len(current_runs),
                "new_failures": sum(1 for r in current_runs if r["status"] == "failed"),
                "fixed_failures": 0,
                "unchanged_failures": 0,
                "passed": sum(1 for r in current_runs if r["status"] == "passed")
            }
        }

    baseline_map = {b.get("name") or b.get("test_name"): b for b in baseline_runs}

    new_failures = []
    fixed_failures = []
    unchanged_failures = []
    passed = []

    for curr in current_runs:
        name = curr.get("name") or curr.get("test_name")
        curr_status = curr.get("status")
        base = baseline_map.get(name)

        if base is None:
            # Not in baseline
            if curr_status == "failed":
                new_failures.append(curr)
            else:
                passed.append(curr)
        else:
            base_status = base.get("status")
            if curr_status == "failed" and base_status == "passed":
                new_failures.append({
                    **curr,
                    "regression_note": "Regression: passed in baseline, failed in current run"
                })
            elif curr_status == "passed" and base_status == "failed":
                fixed_failures.append({
                    **curr,
                    "regression_note": "Fixed: failed in baseline, now passing"
                })
            elif curr_status == "failed" and base_status == "failed":
                unchanged_failures.append({
                    **curr,
                    "regression_note": "Unchanged failure: failed in baseline and still failing"
                })
            else:
                passed.append(curr)

    return {
        "has_baseline": True,
        "summary": {
            "new_failures": new_failures,
            "fixed_failures": fixed_failures,
            "unchanged_failures": unchanged_failures,
            "passed": passed
        },
        "counts": {
            "total": len(current_runs),
            "new_failures": len(new_failures),
            "fixed_failures": len(fixed_failures),
            "unchanged_failures": len(unchanged_failures),
            "passed": len(passed)
        }
    }

