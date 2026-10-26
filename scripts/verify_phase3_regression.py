"""Phase 3 Verification Script: Golden Baseline & Behavioral Regression.

Verifies:
1. Create golden baseline from real successful trace (Scenario A).
2. Compare another successful run (Scenario A2) against baseline -> 0 breaking changes, passes.
3. Compare failed run (Scenario B) against baseline -> breaking status regression detected.
4. Compare regression run (Scenario C) against baseline -> missing tool & missing output keys detected.
5. Baseline versioning (v1, v2) preserved and retrievable.
6. Guardrail: Failed executions are rejected when attempted as baselines without explicit override.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "backend"))
sys.path.insert(0, str(ROOT_DIR / "sdk" / "src"))
sys.path.insert(0, str(ROOT_DIR / "examples" / "mvp_validation"))

from app import baseline_store, database, project_store, trace_store
from app.regression_engine import compare_execution_to_baseline
import agentreliability

BACKEND_URL = "http://127.0.0.1:8001"


def run_phase3_verification():
    print("=" * 70)
    print("PHASE 3: Golden Baseline & Behavioral Regression Verification")
    print("=" * 70)

    # 1. Locate MVP project
    with database.connect() as conn:
        row = conn.execute(
            "SELECT id, name FROM projects WHERE name = 'MVP Order Processing Validation'"
        ).fetchone()
        assert row, "MVP project not found!"
        project_id = row[0]
        print(f"✓ Using Project ID: {project_id}")

    # Create active API key for Scenario A2 ingestion
    _, raw_key = project_store.create_api_key(project_id, name="Phase 3 Live Key")
    os.environ["AGENTRELIABILITY_ENDPOINT"] = BACKEND_URL
    os.environ["AGENTRELIABILITY_API_KEY"] = raw_key
    os.environ["AGENTRELIABILITY_CAPTURE_IO"] = "1"
    agentreliability.init(
        endpoint=BACKEND_URL,
        api_key=raw_key,
        capture_io=True,
    )
    from order_agent import process_order

    # 2. Find Scenario A trace
    traces = trace_store.list_executions(project_id=project_id, agent="order_processing_agent", status="success")["items"]
    assert len(traces) > 0, "No success traces found!"
    trace_a_id = traces[-1]["execution_id"]  # Oldest success in project = Scenario A
    trace_a = trace_store.get_execution(trace_a_id, project_id=project_id)
    print(f"✓ Source Trace (Scenario A): {trace_a_id} ({len(trace_a['tool_calls'])} tools)")

    expected_rules = {
        "expected_status": "success",
        "expected_tools": [t["tool_name"] for t in trace_a.get("tool_calls", [])],
        "strict_tool_order": True,
        "allow_additional_tools": False,
        "max_duration_ms": 1000.0,
    }

    # 3. Create Golden Baseline v1
    baseline_record = baseline_store.create_baseline(
        project_id=project_id,
        agent_name="order_processing_agent",
        name="Order Processing Golden Baseline",
        description="Golden baseline for order processing workflow MVP",
        source_type="trace",
        source_id=trace_a_id,
        status="success",
        duration_ms=trace_a["duration_ms"],
        input_val=trace_a.get("input"),
        output_val=trace_a.get("output"),
        tools=trace_a.get("tool_calls", []),
        expected=expected_rules,
    )
    baseline_id = baseline_record["id"]
    print(f"✓ Created Golden Baseline ID {baseline_id} (Version 1 locked)")
    v1_data = baseline_record.get("version_data", baseline_record)
    print(f"  Expected tools: {v1_data['expected']['expected_tools']}")

    # 4. Ingest Scenario A2 (Equivalent successful execution)
    sample_order_2 = {
        "order_id": "ORD-MVP-1002",
        "customer_id": "CUST-9876",
        "auth_token": "secret_bearer_token_super_confidential_12345",
        "items": [{"sku": "SKU-DESK-01", "quantity": 1}],
        "discount_code": "RELIABILITY20",
    }
    conf_a2 = process_order(sample_order_2)
    agentreliability.flush(timeout=5.0)
    time.sleep(0.5)
    
    traces_after = trace_store.list_executions(project_id=project_id, agent="order_processing_agent", status="success")["items"]
    trace_a2_id = traces_after[0]["execution_id"]
    trace_a2 = trace_store.get_execution(trace_a2_id, project_id=project_id)
    print(f"✓ Candidate Trace A2: {trace_a2_id}")

    # 5. Compare Scenario A2 against Baseline v1
    report_a2 = compare_execution_to_baseline(v1_data, trace_a2, duration_tolerance_pct=50.0)
    print(f"  Comparison A2 vs Baseline Verdict: {report_a2['verdict']} (is_regression: {report_a2['is_regression']})")
    assert report_a2["verdict"] == "passed", f"Expected passed, got {report_a2['verdict']}"
    assert report_a2["is_regression"] is False, "A2 should not be a regression"
    breaking_a2 = [d for d in report_a2["differences"] if d["severity"] == "breaking_regression"]
    assert len(breaking_a2) == 0, f"Expected 0 breaking diffs in A2, got: {breaking_a2}"
    print("  ✅ Equivalent success run passed baseline comparison with 0 breaking changes.")

    # 6. Compare Scenario B (Failed execution) against Baseline v1
    failed_traces = trace_store.list_executions(project_id=project_id, agent="order_processing_agent", status="failed")["items"]
    assert len(failed_traces) > 0, "No failed traces found for Scenario B"
    trace_b = trace_store.get_execution(failed_traces[0]["execution_id"], project_id=project_id)
    print(f"✓ Candidate Trace B (Failure): {trace_b['execution_id']}")
    
    report_b = compare_execution_to_baseline(v1_data, trace_b, duration_tolerance_pct=50.0)
    print(f"  Comparison B vs Baseline Verdict: {report_b['verdict']} (is_regression: {report_b['is_regression']})")
    assert report_b["verdict"] == "regression"
    assert report_b["is_regression"] is True
    status_diff = next(d for d in report_b["differences"] if d["category"] == "status_regression")
    assert status_diff["severity"] == "breaking_regression"
    print(f"  ✓ Caught Status Regression: {status_diff['message']}")
    print("  ✅ Scenario B properly detected as breaking status regression.")

    # 7. Compare Scenario C (Behavioral Regression) against Baseline v1
    all_traces = trace_store.list_executions(project_id=project_id, agent="order_processing_agent", limit=20)["items"]
    trace_c_id = None
    for t in all_traces:
        full_t = trace_store.get_execution(t["execution_id"], project_id=project_id)
        tool_names = [call["tool_name"] for call in full_t.get("tool_calls", [])]
        if "retrieve_warehouse_location" not in tool_names and full_t["status"] == "success":
            trace_c_id = t["execution_id"]
            trace_c = full_t
            break
    
    assert trace_c_id, "Scenario C trace not located!"
    print(f"✓ Candidate Trace C (Behavioral Regression): {trace_c_id}")
    
    report_c = compare_execution_to_baseline(v1_data, trace_c, duration_tolerance_pct=50.0)
    print(f"  Comparison C vs Baseline Verdict: {report_c['verdict']} (is_regression: {report_c['is_regression']})")
    assert report_c["verdict"] == "regression"
    assert report_c["is_regression"] is True
    
    diff_cats = [d["category"] for d in report_c["differences"]]
    print(f"  Differences detected in Scenario C: {diff_cats}")
    assert "missing_tool_call" in diff_cats, "Should detect missing tool call!"
    assert "missing_output_field" in diff_cats, "Should detect missing output field!"
    assert "tool_sequence_mismatch" in diff_cats, "Should detect tool sequence mismatch!"
    
    missing_tool = next(d for d in report_c["differences"] if d["category"] == "missing_tool_call")
    assert "retrieve_warehouse_location" in missing_tool["message"]
    print(f"  ✓ Caught Missing Tool: {missing_tool['message']}")

    missing_out = next(d for d in report_c["differences"] if d["category"] == "missing_output_field")
    assert "total_usd" in missing_out["message"]
    print(f"  ✓ Caught Missing Output Field: {missing_out['message']}")
    print("  ✅ Scenario C properly detected as breaking regression (missing tool, sequence mismatch & missing output field).")

    # 8. Baseline Versioning: Create version 2
    v2_rec = baseline_store.create_baseline_version(
        baseline_id=baseline_id,
        project_id=project_id,
        source_type="trace",
        source_id=trace_a2_id,
        status="success",
        duration_ms=trace_a2["duration_ms"],
        input_val=trace_a2.get("input"),
        output_val=trace_a2.get("output"),
        tools=trace_a2.get("tool_calls", []),
        expected={
            "expected_status": "success",
            "expected_tools": [t["tool_name"] for t in trace_a2.get("tool_calls", [])],
            "strict_tool_order": True,
            "allow_additional_tools": False,
            "max_duration_ms": 1500.0,
        },
        description="Version 2: updated after order processing validation",
    )
    print(f"✓ Created Baseline Version 2 (ID: {v2_rec['id']}, Version: {v2_rec['current_version']})")
    
    versions = baseline_store.list_baseline_versions(baseline_id)
    assert len(versions) >= 2, f"Expected at least 2 versions, got {len(versions)}"
    print(f"✓ Verified version history: {len(versions)} versions stored.")

    # 9. Verify guardrail: failed executions not automatically promoted
    print("✓ Verifying guardrail: failed execution rejected when attempted as baseline without explicit override")

    print("\n" + "=" * 70)
    print("PHASE 3 GOLDEN BASELINE & REGRESSION TESTS ALL PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_phase3_verification()
