import json
import pytest
from pathlib import Path
from agentreliability.cli import main, discover_test_files, load_test_case
from agentreliability.regression import compare_runs

def test_discover_test_files(tmp_path):
    f1 = tmp_path / "test1.json"
    f2 = tmp_path / "test2.json"
    f3 = tmp_path / "ignore.txt"
    f1.write_text("{}")
    f2.write_text("{}")
    f3.write_text("hello")

    found = discover_test_files(tmp_path)
    assert len(found) == 2
    assert f1 in found and f2 in found

def test_cli_execution_all_pass(tmp_path, capsys):
    test_case = {
        "name": "pass_case",
        "steps": [
            {"type": "tool_call", "name": "lookup", "status": "success", "output": {"data": 123}}
        ],
        "expected": {
            "status": "success",
            "tool_sequence": ["lookup"],
            "final_output": {"data": 123}
        }
    }
    case_path = tmp_path / "test_pass.json"
    case_path.write_text(json.dumps(test_case))
    out_report = tmp_path / "report.json"

    code = main(["test", "--project", str(tmp_path), "--output", str(out_report)])
    assert code == 0
    assert out_report.exists()
    
    report = json.loads(out_report.read_text())
    assert report["total"] == 1
    assert report["passed"] == 1
    assert report["failed"] == 0

def test_cli_execution_failure_exit_code(tmp_path, capsys):
    test_case = {
        "name": "fail_case",
        "steps": [
            {"type": "tool_call", "name": "lookup", "status": "failed", "error": "500 Internal Error"}
        ],
        "expected": {
            "status": "success",  # Expected success, but got failure -> mismatch
            "tool_sequence": ["lookup"]
        }
    }
    case_path = tmp_path / "test_fail.json"
    case_path.write_text(json.dumps(test_case))
    out_report = tmp_path / "report.json"

    code = main(["test", "--project", str(tmp_path), "--output", str(out_report)])
    assert code == 1  # Exits with nonzero on failure
    
    report = json.loads(out_report.read_text())
    assert report["total"] == 1
    assert report["passed"] == 0
    assert report["failed"] == 1
    assert len(report["results"][0]["mismatches"]) > 0

def test_regression_comparison_detection():
    baseline = [
        {"name": "test_1", "status": "passed"},
        {"name": "test_2", "status": "failed"},
        {"name": "test_3", "status": "passed"}
    ]
    current = [
        {"name": "test_1", "status": "failed"},  # regression: passed -> failed
        {"name": "test_2", "status": "passed"},  # fixed: failed -> passed
        {"name": "test_3", "status": "passed"}   # passed in both -> passed
    ]
    res = compare_runs(current, baseline)
    assert res["has_baseline"] is True
    assert res["counts"]["new_failures"] == 1
    assert res["counts"]["fixed_failures"] == 1
    assert res["counts"]["passed"] == 1

def test_github_step_summary_generation(tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    test_case = {
        "name": "summary_test",
        "steps": [{"type": "tool_call", "name": "tool_a", "status": "success"}],
        "expected": {"status": "success", "tool_sequence": ["tool_a"]}
    }
    (tmp_path / "test.json").write_text(json.dumps(test_case))
    
    code = main(["test", "--project", str(tmp_path)])
    assert code == 0
    assert summary_file.exists()
    content = summary_file.read_text()
    assert "AgentReliability AI Test Results" in content
    assert "✅ All Passed" in content
