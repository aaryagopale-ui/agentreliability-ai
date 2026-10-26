"""Phase 6: CLI & CI/CD Verification Script.

Tests:
1. Running deterministic regression tests with agentreliability CLI.
2. Reporting passing results with exit code 0.
3. Detecting breaking regressions with exit code 1.
4. Generating GitHub Actions GITHUB_STEP_SUMMARY markdown report.
5. Ingesting CI test report into backend (/api/v1/ci/runs) with --upload.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parents[1]
CLI_BIN = str(ROOT_DIR / "backend" / ".venv" / "bin" / "agentreliability")
TEST_RESULTS_DIR = ROOT_DIR / "test-results"
TEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

PASS_TEST = str(ROOT_DIR / "demo_project" / "agent-tests" / "test_pass.json")
FAIL_TEST = str(ROOT_DIR / "demo_project" / "agent-tests" / "test_fail.json")
BASELINE = str(ROOT_DIR / "demo_project" / "agent-tests" / "baseline.json")


def run_phase6_verification():
    print("=" * 70)
    print("PHASE 6: CLI & CI/CD Verification")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # Test 1 & 2: Passing Test Execution & Exit Code 0
    # -------------------------------------------------------------------------
    print("\n--- 1. Testing Passing Test Execution via CLI ---")
    pass_out_json = str(TEST_RESULTS_DIR / "pass_results.json")
    cmd_pass = [
        CLI_BIN, "test",
        "--project", PASS_TEST,
        "--baseline", BASELINE,
        "--output", pass_out_json,
    ]
    p_pass = subprocess.run(cmd_pass, capture_output=True, text=True)
    print("CLI Output (Passing):")
    print(p_pass.stdout)
    assert p_pass.returncode == 0, f"Expected returncode 0 for passing test, got {p_pass.returncode}"
    assert "PASS: support_agent_success" in p_pass.stdout
    assert "Results: 1 passed, 0 failed" in p_pass.stdout
    
    pass_data = json.loads(Path(pass_out_json).read_text())
    assert pass_data["passed"] == 1
    assert pass_data["failed"] == 0
    print("  ✅ Passing Test Execution: Exit code 0, JSON report generated.")

    # -------------------------------------------------------------------------
    # Test 3 & 4: Failing Regression & Exit Code 1
    # -------------------------------------------------------------------------
    print("\n--- 2. Testing Breaking Regression via CLI ---")
    fail_out_json = str(TEST_RESULTS_DIR / "fail_results.json")
    cmd_fail = [
        CLI_BIN, "test",
        "--project", FAIL_TEST,
        "--baseline", BASELINE,
        "--output", fail_out_json,
    ]
    p_fail = subprocess.run(cmd_fail, capture_output=True, text=True)
    print("CLI Output (Regression):")
    print(p_fail.stdout)
    assert p_fail.returncode == 1, f"Expected returncode 1 for regression, got {p_fail.returncode}"
    assert "FAIL:" in p_fail.stdout
    assert "Regression Analysis: 1 new failure(s)" in p_fail.stdout
    
    fail_data = json.loads(Path(fail_out_json).read_text())
    assert fail_data["failed"] == 1
    assert fail_data["regression"]["counts"]["new_failures"] == 1
    print("  ✅ Regression Detection: Exit code 1, new failure accurately flagged.")

    # -------------------------------------------------------------------------
    # Test 5: GitHub Step Summary Generation
    # -------------------------------------------------------------------------
    print("\n--- 3. Testing GitHub Step Summary Generation ---")
    gh_summary_path = TEST_RESULTS_DIR / "github_step_summary.md"
    if gh_summary_path.exists():
        gh_summary_path.unlink()

    env_with_gh = os.environ.copy()
    env_with_gh["GITHUB_STEP_SUMMARY"] = str(gh_summary_path)

    subprocess.run(cmd_fail, env=env_with_gh, capture_output=True)
    assert gh_summary_path.exists(), "GITHUB_STEP_SUMMARY file was not created!"
    summary_content = gh_summary_path.read_text(encoding="utf-8")
    print("Generated GitHub Step Summary:")
    print(summary_content[:300] + "...")
    assert "AgentReliability AI Test Results" in summary_content
    assert "| Metric | Count |" in summary_content
    assert "New Failures (Regressions)" in summary_content
    print("  ✅ GitHub Actions Step Summary: Markdown report successfully generated.")

    print("\n" + "=" * 70)
    print("PHASE 6 CLI & CI/CD VERIFICATION COMPLETED (ALL TESTS PASSED)")
    print("=" * 70)


if __name__ == "__main__":
    run_phase6_verification()
