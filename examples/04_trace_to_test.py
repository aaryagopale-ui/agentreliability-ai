#!/usr/bin/env python3
"""Example 4: Trace-to-Test Regression Workflow.

Demonstrates:
- How a recorded trace from the Python SDK is converted into a regression test case
- How deterministic assertions (tool sequence, output structure, error type) are generated
- How replaying the test detects behavior regressions when tool sequences change

Usage:
  python examples/04_trace_to_test.py
"""
import json
import os
import sys
from pathlib import Path

# Add sdk/src to sys.path
sdk_path = str(Path(__file__).resolve().parent.parent / "sdk" / "src")
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from agentreliability.engine import run_test
from agentreliability.regression import compare_runs


def main():
    print("=== AgentReliability Example 4: Trace-to-Test Workflow ===")

    # 1. Simulated recorded trace payload captured by the SDK in production
    recorded_trace = {
        "execution_id": "exec-checkout-sample-42",
        "agent_name": "checkout_workflow_agent",
        "status": "success",
        "tool_sequence": ["verify_token", "calculate_taxes", "process_order"],
        "duration_ms": 128.5,
        "output": {
            "order_id": "ORD-991",
            "total_with_tax": 108.50,
            "status": "confirmed",
        },
    }

    print("\n1. Original Production Trace Captured:")
    print(json.dumps(recorded_trace, indent=2))

    # 2. Convert recorded trace into an automated regression test specification
    generated_test_case = {
        "name": f"Regression: {recorded_trace['agent_name']}",
        "description": f"Auto-generated regression test from trace {recorded_trace['execution_id']}",
        "steps": [
            {"type": "tool_call", "name": "verify_token", "status": "success", "duration_ms": 15},
            {"type": "tool_call", "name": "calculate_taxes", "status": "success", "duration_ms": 22},
            {"type": "tool_call", "name": "process_order", "status": "success", "duration_ms": 91, "output": recorded_trace["output"]},
        ],
        "expected": {
            "status": "success",
            "tool_sequence": recorded_trace["tool_sequence"],
            "final_output": recorded_trace["output"],
            "expected_output_fields": ["order_id", "total_with_tax", "status"],
            "strict_order": True,
            "allow_additional_tools": False,
        },
    }

    print("\n2. Converted Test Case Specification:")
    print(f"  Name           : {generated_test_case['name']}")
    print(f"  Expected Tools : {' -> '.join(generated_test_case['expected']['tool_sequence'])}")
    print(f"  Output Fields  : {generated_test_case['expected']['expected_output_fields']}")

    # 3. Baseline Replay Run (Matches expected behavior)
    print("\n3. Executing Baseline Replay Run...")
    baseline_result = run_test(generated_test_case)
    print(f"  Result : {'✅ PASSED' if baseline_result['status'] == 'passed' else '❌ FAILED'}")
    print(f"  Mismatches: {len(baseline_result.get('mismatches', []))}")

    # 4. Introduce a subtle regression (developer accidentally dropped the tax calculation step)
    print("\n4. Simulating Code Regression (tax calculation step omitted by accident)...")
    regressed_test_case = dict(generated_test_case)
    regressed_test_case["steps"] = [
        {"type": "tool_call", "name": "verify_token", "status": "success"},
        # calculate_taxes was deleted!
        {"type": "tool_call", "name": "process_order", "status": "success", "output": {"order_id": "ORD-991"}},
    ]

    regressed_result = run_test(regressed_test_case)
    print(f"  Result : {'✅ PASSED' if regressed_result['status'] == 'passed' else '❌ FAILED'}")
    for m in regressed_result.get("mismatches", []):
        print(f"  ↳ Detected Mismatch: [{m['kind']}] {m['message']}")

    # 5. Regression Comparison Analysis
    print("\n5. Running Regression Comparison (Current vs Baseline):")
    current_runs = [{"name": "checkout_test", "status": regressed_result["status"]}]
    baseline_runs = [{"name": "checkout_test", "status": baseline_result["status"]}]
    comparison = compare_runs(current_runs, baseline_runs)
    print(f"  New Failures (Regressions): {comparison['counts']['new_failures']}")
    print(f"  Has Regressions           : {comparison['counts']['new_failures'] > 0}")


if __name__ == "__main__":
    main()

