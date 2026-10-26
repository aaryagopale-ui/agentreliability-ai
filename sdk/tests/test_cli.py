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


def test_cli_status_offline_backend(capsys):
    # Unreachable port -> should gracefully report offline and exit with 1
    code = main(["status", "--endpoint", "http://127.0.0.1:54321"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Backend Server : OFFLINE" in captured.out
    assert "uvicorn app.main:app --port 8001" in captured.out


def test_cli_help_no_command(capsys):
    code = main([])
    assert code == 1
    captured = capsys.readouterr()
    assert "AgentReliability CLI" in captured.out or "usage:" in captured.out


def test_cli_status_valid_key(monkeypatch, capsys):
    from unittest.mock import MagicMock
    import urllib.request

    def mock_urlopen(req, timeout=3.0):
        url = req.full_url if hasattr(req, "full_url") else req
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        if "/api/health" in url:
            cm.read.return_value = b'{"status": "ok"}'
        elif "/api/v1/auth/verify" in url:
            assert req.headers.get("X-api-key") == "ar_valid_key_123"
            cm.read.return_value = b'{"status": "ok", "authenticated": true, "project": {"id": 1, "name": "Production Agents"}}'
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    code = main(["status", "--endpoint", "http://127.0.0.1:8001", "--api-key", "ar_valid_key_123"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Backend Server : ONLINE and healthy" in captured.out
    assert "VALID and authorized (Project: 'Production Agents')" in captured.out


def test_cli_status_invalid_or_revoked_key(monkeypatch, capsys):
    import urllib.error
    import urllib.request
    from unittest.mock import MagicMock

    def mock_urlopen(req, timeout=3.0):
        url = req.full_url if hasattr(req, "full_url") else req
        if "/api/health" in url:
            cm = MagicMock()
            cm.__enter__.return_value = cm
            cm.__exit__.return_value = False
            cm.status = 200
            cm.read.return_value = b'{"status": "ok"}'
            return cm
        elif "/api/v1/auth/verify" in url:
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
        raise ValueError(f"Unexpected url {url}")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    code = main(["status", "--endpoint", "http://127.0.0.1:8001", "--api-key", "ar_revoked_key"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Backend Server : ONLINE and healthy" in captured.out
    assert "INVALID or revoked (HTTP 401 Unauthorized)" in captured.out


def test_cli_status_missing_key(monkeypatch, capsys):
    from unittest.mock import MagicMock
    import urllib.request

    def mock_urlopen(req, timeout=3.0):
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        cm.read.return_value = b'{"status": "ok"}'
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.delenv("AGENTRELIABILITY_API_KEY", raising=False)
    code = main(["status", "--endpoint", "http://127.0.0.1:8001"])
    assert code == 0
    captured = capsys.readouterr()
    assert "API Key          : Not set" in captured.out
    assert "SKIPPED (No API key provided)" in captured.out


def test_cli_upload_localhost_in_ci_success(tmp_path, monkeypatch, capsys):
    """Verify Issue #2: CLI does not skip upload when CI=true or GITHUB_ACTIONS=true with localhost endpoint."""
    from unittest.mock import MagicMock
    import urllib.request

    uploaded_requests = []

    def mock_urlopen(req, timeout=5.0):
        uploaded_requests.append(req)
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        cm.read.return_value = b'{"status": "ok", "run_id": 1}'
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001")
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_ci_test_key_123")

    test_case = {
        "name": "ci_pass_test",
        "steps": [{"type": "tool_call", "name": "db_lookup", "status": "success"}],
        "expected": {"status": "success", "tool_sequence": ["db_lookup"]}
    }
    (tmp_path / "ci_test.json").write_text(json.dumps(test_case))

    code = main(["test", "--project", str(tmp_path), "--upload"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Uploaded test results successfully to AgentReliability backend." in captured.out
    assert len(uploaded_requests) == 1
    req = uploaded_requests[0]
    assert req.full_url == "http://127.0.0.1:8001/api/v1/ci/runs"
    assert req.headers.get("X-api-key") == "ar_ci_test_key_123"


def test_cli_upload_remote_success(tmp_path, monkeypatch, capsys):
    from unittest.mock import MagicMock
    import urllib.request

    uploaded_requests = []

    def mock_urlopen(req, timeout=5.0):
        uploaded_requests.append(req)
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_ENDPOINT", "https://api.agentreliability.com")
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_prod_key_abc")

    test_case = {
        "name": "remote_test",
        "steps": [{"type": "tool_call", "name": "calc", "status": "success"}],
        "expected": {"status": "success", "tool_sequence": ["calc"]}
    }
    (tmp_path / "remote.json").write_text(json.dumps(test_case))

    code = main(["test", "--project", str(tmp_path), "--upload", "--commit", "sha12345"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Uploaded test results successfully to AgentReliability backend." in captured.out
    assert len(uploaded_requests) == 1
    assert uploaded_requests[0].full_url == "https://api.agentreliability.com/api/v1/ci/runs"


def test_cli_upload_unreachable_backend(tmp_path, monkeypatch, capsys):
    import urllib.error
    import urllib.request

    def mock_urlopen(req, timeout=5.0):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:54321")
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_key_xyz")

    test_case = {
        "name": "unreachable_test",
        "steps": [{"type": "tool_call", "name": "calc", "status": "success"}],
        "expected": {"status": "success", "tool_sequence": ["calc"]}
    }
    (tmp_path / "unreach.json").write_text(json.dumps(test_case))

    code = main(["test", "--project", str(tmp_path), "--upload"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Could not connect to backend at http://127.0.0.1:54321" in captured.err
    assert "Remote upload failed." in captured.err


def test_cli_upload_auth_failure_401(tmp_path, monkeypatch, capsys):
    import urllib.error
    import urllib.request

    def mock_urlopen(req, timeout=5.0):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001")
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_revoked_key")

    test_case = {
        "name": "auth_fail_test",
        "steps": [{"type": "tool_call", "name": "calc", "status": "success"}],
        "expected": {"status": "success", "tool_sequence": ["calc"]}
    }
    (tmp_path / "auth_fail.json").write_text(json.dumps(test_case))

    code = main(["test", "--project", str(tmp_path), "--upload"])
    assert code == 1
    captured = capsys.readouterr()
    assert "API key authentication failed for backend upload (HTTP 401 Unauthorized)." in captured.err
    assert "Remote upload failed." in captured.err


def test_cli_upload_missing_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("AGENTRELIABILITY_API_KEY", raising=False)

    test_case = {
        "name": "missing_key_test",
        "steps": [{"type": "tool_call", "name": "calc", "status": "success"}],
        "expected": {"status": "success", "tool_sequence": ["calc"]}
    }
    (tmp_path / "missing_key.json").write_text(json.dumps(test_case))

    code = main(["test", "--project", str(tmp_path), "--upload"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Error: --upload specified but AGENTRELIABILITY_API_KEY is not configured." in captured.err


def test_cli_upload_failed_test_still_exits_nonzero(tmp_path, monkeypatch, capsys):
    from unittest.mock import MagicMock
    import urllib.request

    def mock_urlopen(req, timeout=5.0):
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_valid_key")

    test_case = {
        "name": "failing_test",
        "steps": [{"type": "tool_call", "name": "calc", "status": "failed", "error": "Crash"}],
        "expected": {"status": "success", "tool_sequence": ["calc"]}
    }
    (tmp_path / "fail.json").write_text(json.dumps(test_case))

    code = main(["test", "--project", str(tmp_path), "--upload"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Uploaded test results successfully to AgentReliability backend." in captured.out


def test_cli_compare_missing_api_key(capsys, monkeypatch):
    monkeypatch.delenv("AGENTRELIABILITY_API_KEY", raising=False)
    code = main(["compare", "--trace", "tr_123", "--baseline-id", "1"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Error: API key is required." in captured.err


def test_cli_compare_missing_baseline_and_agent(capsys, monkeypatch):
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_test_key")
    code = main(["compare", "--trace", "tr_123"])
    assert code == 2
    captured = capsys.readouterr()
    assert "Error: Must specify either --baseline-id or --agent" in captured.err


def test_cli_compare_success_matching(capsys, monkeypatch, tmp_path):
    import io
    import urllib.request
    from unittest.mock import MagicMock

    mock_report = {
        "baseline_id": 42,
        "baseline_name": "Weather Baseline",
        "baseline_version": 1,
        "is_regression": False,
        "verdict": "passed",
        "summary": "Candidate matches baseline perfectly across all checks.",
        "counts": {"breaking": 0, "performance": 0, "informational": 0, "total": 0},
        "differences": []
    }

    def mock_urlopen(req, timeout=10.0):
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        cm.read.return_value = json.dumps(mock_report).encode("utf-8")
        assert req.headers.get("X-api-key") == "ar_valid_key"
        assert req.full_url.endswith("/api/v1/baselines/42/compare")
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_valid_key")

    out_file = tmp_path / "comp_out.json"
    code = main(["compare", "--trace", "tr_candidate_999", "--baseline-id", "42", "--output", str(out_file)])
    assert code == 0
    captured = capsys.readouterr()
    assert "PASSED - Matches Golden Baseline" in captured.out
    assert "Weather Baseline" in captured.out
    assert out_file.exists()
    saved = json.loads(out_file.read_text())
    assert saved["is_regression"] is False


def test_cli_compare_breaking_regression(capsys, monkeypatch):
    import urllib.request
    from unittest.mock import MagicMock

    mock_report = {
        "baseline_id": 42,
        "baseline_name": "Weather Baseline",
        "baseline_version": 1,
        "is_regression": True,
        "verdict": "breaking_regression",
        "summary": "1 breaking regression(s) detected.",
        "counts": {"breaking": 1, "performance": 0, "informational": 0, "total": 1},
        "differences": [
            {
                "category": "tool_sequence",
                "severity": "breaking_regression",
                "message": "Tool sequence diverged. Missing required tool call: 'lookup_forecast'."
            }
        ]
    }

    def mock_urlopen(req, timeout=10.0):
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        cm.read.return_value = json.dumps(mock_report).encode("utf-8")
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_valid_key")

    code = main(["compare", "--trace", "tr_regressed", "--baseline-id", "42"])
    assert code == 1
    captured = capsys.readouterr()
    assert "REGRESSION DETECTED" in captured.out
    assert "❌ [BREAKING] tool_sequence: Tool sequence diverged" in captured.out


def test_cli_compare_perf_warning_only(capsys, monkeypatch):
    import urllib.request
    from unittest.mock import MagicMock

    mock_report = {
        "baseline_id": 42,
        "baseline_name": "Weather Baseline",
        "baseline_version": 2,
        "is_regression": False,
        "verdict": "performance_regression",
        "summary": "1 performance regression(s) detected.",
        "counts": {"breaking": 0, "performance": 1, "informational": 0, "total": 1},
        "differences": [
            {
                "category": "duration",
                "severity": "performance_regression",
                "message": "Latency 2500ms exceeded baseline threshold 1500ms."
            }
        ]
    }

    def mock_urlopen(req, timeout=10.0):
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        cm.read.return_value = json.dumps(mock_report).encode("utf-8")
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_valid_key")

    code = main(["compare", "--trace", "tr_slow", "--baseline-id", "42"])
    assert code == 0
    captured = capsys.readouterr()
    assert "PASSED WITH PERFORMANCE WARNING" in captured.out
    assert "[PERF]" in captured.out
    assert "Latency 2500ms exceeded" in captured.out


def test_cli_compare_agent_lookup_flow(capsys, monkeypatch):
    import urllib.request
    from unittest.mock import MagicMock

    call_history = []

    def mock_urlopen(req, timeout=10.0):
        call_history.append(req.full_url)
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200

        if "/api/v1/baselines?agent_name=weather_agent" in req.full_url:
            cm.read.return_value = json.dumps([{"id": 77, "name": "Weather Gold", "agent_name": "weather_agent"}]).encode("utf-8")
        elif "/api/v1/baselines/77/compare" in req.full_url:
            cm.read.return_value = json.dumps({
                "baseline_id": 77,
                "baseline_name": "Weather Gold",
                "baseline_version": 1,
                "is_regression": False,
                "verdict": "passed",
                "summary": "Passed",
                "counts": {"breaking": 0, "performance": 0, "informational": 0, "total": 0},
                "differences": []
            }).encode("utf-8")
        else:
            raise ValueError(f"Unexpected url {req.full_url}")
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_valid_key")

    code = main(["compare", "--trace", "tr_lookup_trace", "--agent", "weather_agent"])
    assert code == 0
    assert len(call_history) == 2
    assert any("/api/v1/baselines?agent_name=weather_agent" in u for u in call_history)
    assert any("/api/v1/baselines/77/compare" in u for u in call_history)


def test_cli_compare_agent_not_found(capsys, monkeypatch):
    import urllib.request
    from unittest.mock import MagicMock

    def mock_urlopen(req, timeout=5.0):
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        cm.read.return_value = json.dumps([]).encode("utf-8")
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_valid_key")

    code = main(["compare", "--trace", "tr_lookup_trace", "--agent", "nonexistent_agent"])
    assert code == 1
    captured = capsys.readouterr()
    assert "No Golden Baseline found for agent 'nonexistent_agent'" in captured.err


def test_cli_compare_http_401(capsys, monkeypatch):
    import urllib.error
    import urllib.request

    def mock_urlopen(req, timeout=10.0):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_invalid_key")

    code = main(["compare", "--trace", "tr_1", "--baseline-id", "10"])
    assert code == 1
    captured = capsys.readouterr()
    assert "API key authentication failed (HTTP 401 Unauthorized)." in captured.err


def test_cli_compare_http_404_with_detail(capsys, monkeypatch):
    import io
    import urllib.error
    import urllib.request

    def mock_urlopen(req, timeout=10.0):
        body = io.BytesIO(b'{"detail":"Candidate trace not found."}')
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, body)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_valid_key")

    code = main(["compare", "--trace", "tr_missing", "--baseline-id", "10"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Candidate trace not found." in captured.err


def test_cli_compare_network_error(capsys, monkeypatch):
    import urllib.error
    import urllib.request

    def mock_urlopen(req, timeout=10.0):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_valid_key")

    code = main(["compare", "--trace", "tr_1", "--baseline-id", "10"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Could not connect to backend" in captured.err


# ==============================================================================
# Issue #12: --fail-on-regression automated tests
# ==============================================================================

def test_cli_test_fail_on_regression_breaking(tmp_path, capsys):
    """When --fail-on-regression is enabled and a breaking regression occurs, exit code is 1."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    # Test case passes on its own
    current_case = {
        "name": "lookup_flow",
        "steps": [
            {"type": "tool_call", "name": "lookup", "status": "success", "output": {"val": 1}}
        ],
        "expected": {
            "status": "success",
            "tool_sequence": ["lookup"]
        }
    }
    case_path = tests_dir / "test_lookup.json"
    case_path.write_text(json.dumps(current_case))

    # Baseline required both lookup and verify
    baseline_report = {
        "results": [
            {
                "name": "lookup_flow",
                "status": "passed",
                "observed": {
                    "tool_sequence": ["lookup", "verify"],
                    "status": "success"
                }
            }
        ]
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline_report))

    code = main([
        "test",
        "--project", str(tests_dir),
        "--baseline", str(baseline_path),
        "--fail-on-regression"
    ])
    assert code == 1
    captured = capsys.readouterr()
    assert "BREAKING REGRESSION DETECTED" in captured.err or "BREAKING REGRESSION DETECTED" in captured.out
    assert "missing tool call" in captured.out
    assert "verify" in captured.out


def test_cli_test_fail_on_regression_omitted_backward_compat(tmp_path, capsys):
    """When --fail-on-regression is omitted, breaking regressions do not fail passing tests."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    current_case = {
        "name": "lookup_flow",
        "steps": [
            {"type": "tool_call", "name": "lookup", "status": "success", "output": {"val": 1}}
        ],
        "expected": {
            "status": "success",
            "tool_sequence": ["lookup"]
        }
    }
    case_path = tests_dir / "test_lookup.json"
    case_path.write_text(json.dumps(current_case))

    baseline_report = {
        "results": [
            {
                "name": "lookup_flow",
                "status": "passed",
                "observed": {
                    "tool_sequence": ["lookup", "verify"],
                    "status": "success"
                }
            }
        ]
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline_report))

    # Omit --fail-on-regression
    code = main([
        "test",
        "--project", str(tests_dir),
        "--baseline", str(baseline_path)
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "Results: 1 passed, 0 failed" in captured.out
    assert "missing tool call" in captured.out


def test_cli_test_fail_on_regression_passing_comparison(tmp_path, capsys):
    """When --fail-on-regression is enabled and comparison passes, exit code is 0."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    current_case = {
        "name": "lookup_flow",
        "steps": [
            {"type": "tool_call", "name": "lookup", "status": "success", "output": {"val": 1}}
        ],
        "expected": {
            "status": "success",
            "tool_sequence": ["lookup"]
        }
    }
    case_path = tests_dir / "test_lookup.json"
    case_path.write_text(json.dumps(current_case))

    baseline_report = {
        "results": [
            {
                "name": "lookup_flow",
                "status": "passed",
                "observed": {
                    "tool_sequence": ["lookup"],
                    "final_output": {"val": 1},
                    "status": "success"
                }
            }
        ]
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline_report))

    code = main([
        "test",
        "--project", str(tests_dir),
        "--baseline", str(baseline_path),
        "--fail-on-regression"
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "Results: 1 passed, 0 failed" in captured.out
    assert "0 breaking regression(s)" in captured.out


def test_cli_test_fail_on_regression_performance_only_warning(tmp_path, capsys, monkeypatch):
    """When only performance warnings occur, --fail-on-regression does NOT exit with 1."""
    import agentreliability.engine as engine

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    # Mock run_test to simulate a candidate that took 1500ms
    orig_run_test = engine.run_test
    def mock_run_test(test):
        res = orig_run_test(test)
        res["duration_ms"] = 1500.0  # Increased latency (> 50% tolerance)
        return res

    monkeypatch.setattr("agentreliability.cli.run_test", mock_run_test)

    current_case = {
        "name": "latency_test",
        "steps": [
            {"type": "tool_call", "name": "quick_fetch", "status": "success"}
        ],
        "expected": {
            "status": "success",
            "tool_sequence": ["quick_fetch"]
        }
    }
    case_path = tests_dir / "test_latency.json"
    case_path.write_text(json.dumps(current_case))

    baseline_report = {
        "results": [
            {
                "name": "latency_test",
                "status": "passed",
                "duration_ms": 200.0,  # Baseline was 200ms
                "observed": {
                    "tool_sequence": ["quick_fetch"],
                    "status": "success"
                }
            }
        ]
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline_report))

    code = main([
        "test",
        "--project", str(tests_dir),
        "--baseline", str(baseline_path),
        "--fail-on-regression"
    ])
    # Must exit 0 because performance warnings do not fail tests unless classified as breaking
    assert code == 0
    captured = capsys.readouterr()
    assert "Results: 1 passed, 0 failed" in captured.out
    assert "1 performance warning(s)" in captured.out
    assert "[PERF]" in captured.out
    assert "latency_regression" in captured.out


def test_cli_test_fail_on_regression_explicit_threshold_breaking(tmp_path, capsys, monkeypatch):
    """When a test rule explicitly sets max_duration_ms and it's exceeded, it is a breaking regression."""
    import agentreliability.engine as engine

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    def mock_run_test(test):
        res = engine.run_test(test)
        res["duration_ms"] = 2500.0
        return res

    monkeypatch.setattr("agentreliability.cli.run_test", mock_run_test)

    current_case = {
        "name": "sla_test",
        "steps": [
            {"type": "tool_call", "name": "sla_fetch", "status": "success"}
        ],
        "expected": {
            "status": "success",
            "tool_sequence": ["sla_fetch"],
            "max_duration_ms": 1000.0  # Explicit limit
        }
    }
    case_path = tests_dir / "test_sla.json"
    case_path.write_text(json.dumps(current_case))

    baseline_report = {
        "results": [
            {
                "name": "sla_test",
                "status": "passed",
                "duration_ms": 500.0,
                "observed": {
                    "tool_sequence": ["sla_fetch"],
                    "status": "success"
                }
            }
        ]
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline_report))

    code = main([
        "test",
        "--project", str(tests_dir),
        "--baseline", str(baseline_path),
        "--fail-on-regression"
    ])
    assert code == 1
    captured = capsys.readouterr()
    assert "BREAKING REGRESSION DETECTED" in captured.err or "BREAKING REGRESSION DETECTED" in captured.out
    assert "duration_threshold_exceeded" in captured.out


def test_cli_test_preserves_exit_code_on_test_failure_without_baseline(tmp_path, capsys):
    """Failed tests still exit with code 1 when --fail-on-regression is used without a baseline."""
    fail_case = {
        "name": "fail_case",
        "steps": [
            {"type": "tool_call", "name": "db", "status": "failed", "error": "Disk full"}
        ],
        "expected": {
            "status": "success"
        }
    }
    (tmp_path / "test_fail.json").write_text(json.dumps(fail_case))

    code = main([
        "test",
        "--project", str(tmp_path),
        "--fail-on-regression"
    ])
    assert code == 1
    captured = capsys.readouterr()
    assert "Results: 0 passed, 1 failed" in captured.out


def test_cli_test_preserves_exit_code_on_invalid_path(capsys):
    """Invalid project path returns exit code 2."""
    code = main([
        "test",
        "--project", "/tmp/definitely_nonexistent_test_path_12345",
        "--fail-on-regression"
    ])
    assert code == 2


def test_cli_test_help_includes_fail_on_regression(capsys):
    """Help message documents --fail-on-regression."""
    with pytest.raises(SystemExit) as exc_info:
        main(["test", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--fail-on-regression" in captured.out
    assert "Exit with code 1 if a breaking regression is detected" in captured.out


def test_cli_module_execution_entrypoint():
    """Verify python -m agentreliability executes successfully without error."""
    import subprocess
    import sys

    res = subprocess.run(
        [sys.executable, "-m", "agentreliability", "--help"],
        capture_output=True,
        text=True,
        timeout=5.0,
    )
    assert res.returncode == 0
    assert "usage: agentreliability" in res.stdout
    assert "status,test,compare" in res.stdout






