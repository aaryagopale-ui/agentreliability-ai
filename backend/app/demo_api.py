"""Demo Agent & Traces Seeding API router.

Provides a safe, zero-dependency one-click demo experience so developers can explore
AgentReliability's monitoring, Golden Baselines, regression detection, and failure analysis
without configuring external models or installing the SDK.
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status

from .auth_api import check_csrf
from .auth_deps import get_authorized_project
from . import baseline_store, test_store, trace_store
from .regression_engine import compare_execution_to_baseline
from .traces_schemas import TraceEvent

router = APIRouter(prefix="/api/demo", tags=["Demo"])

DEMO_AGENT_NAME = "support_triage_agent"
DEMO_BASELINE_NAME = "Support Triage Golden Baseline (Demo)"
DEMO_TEST_NAME = "Support Triage Refund Flow (Demo)"


def _get_demo_ids(project_id: int) -> dict:
    return {
        "success": f"demo-trace-support-success-{project_id}",
        "timeout": f"demo-trace-support-timeout-{project_id}",
        "regressed": f"demo-trace-support-regressed-{project_id}",
    }


@router.get("/status")
def get_demo_status(
    project: dict = Depends(get_authorized_project),
) -> dict:
    """Check if synthetic demo data is already seeded in this project."""
    pid = project["id"]
    ids = _get_demo_ids(pid)

    success_trace = trace_store.get_execution(ids["success"], project_id=pid)
    timeout_trace = trace_store.get_execution(ids["timeout"], project_id=pid)
    regressed_trace = trace_store.get_execution(ids["regressed"], project_id=pid)

    traces_count = sum(1 for t in (success_trace, timeout_trace, regressed_trace) if t is not None)

    baselines = baseline_store.list_baselines(pid, agent_name=DEMO_AGENT_NAME)
    demo_baseline = next((b for b in baselines if b["name"] == DEMO_BASELINE_NAME), None)

    cases = test_store.list_cases(project_id=pid)
    demo_case = next((c for c in cases if c["name"] == DEMO_TEST_NAME), None)

    is_loaded = traces_count == 3 and demo_baseline is not None and demo_case is not None

    return {
        "demo_loaded": is_loaded,
        "traces_count": traces_count,
        "baseline_id": demo_baseline["id"] if demo_baseline else None,
        "test_case_id": demo_case["id"] if demo_case else None,
        "agent_name": DEMO_AGENT_NAME,
        "trace_ids": ids,
    }


@router.post("/seed", status_code=status.HTTP_201_CREATED)
def seed_demo_data(
    request: Request,
    project: dict = Depends(get_authorized_project),
) -> dict:
    """Seed realistic, synthetic demo agent traces, a Golden Baseline, and comparisons.

    Safe & idempotent: repeated clicks do not create duplicate records.
    Never modifies or deletes existing user data.
    """
    check_csrf(request)
    pid = project["id"]
    ids = _get_demo_ids(pid)

    # 1. Check existing records for idempotency
    success_trace = trace_store.get_execution(ids["success"], project_id=pid)
    timeout_trace = trace_store.get_execution(ids["timeout"], project_id=pid)
    regressed_trace = trace_store.get_execution(ids["regressed"], project_id=pid)

    baselines = baseline_store.list_baselines(pid, agent_name=DEMO_AGENT_NAME)
    demo_baseline = next((b for b in baselines if b["name"] == DEMO_BASELINE_NAME), None)

    cases = test_store.list_cases(project_id=pid)
    demo_case = next((c for c in cases if c["name"] == DEMO_TEST_NAME), None)

    already_existed = (
        success_trace is not None
        and timeout_trace is not None
        and regressed_trace is not None
        and demo_baseline is not None
        and demo_case is not None
    )

    now = datetime.now(timezone.utc)
    t0 = now - timedelta(minutes=14)
    t1 = now - timedelta(minutes=9)
    t2 = now - timedelta(minutes=4)

    # 2. Ingest Trace 1: Successful multi-step execution
    if success_trace is None:
        events_success = [
            TraceEvent(
                event_id=f"demo-ev-{pid}-start-1",
                execution_id=ids["success"],
                agent_name=DEMO_AGENT_NAME,
                type="execution_start",
                timestamp=t0,
                input={"customer_id": "cust_9021", "query": "Requesting status of refund for damaged order #54321", "priority": "high"},
                metadata={"synthetic_demo": True, "is_demo": True, "demo_type": "success", "scenario": "Customer refund resolution with full verification and email dispatch."},
            ),
            TraceEvent(
                event_id=f"demo-ev-{pid}-tool-1-1",
                execution_id=ids["success"],
                agent_name=DEMO_AGENT_NAME,
                type="tool_call",
                timestamp=t0 + timedelta(milliseconds=15),
                tool_name="lookup_customer",
                duration_ms=125.0,
                status="success",
                input={"customer_id": "cust_9021"},
                output={"name": "Alice Johnson", "tier": "gold", "account_age_days": 420},
                metadata={"synthetic_demo": True},
            ),
            TraceEvent(
                event_id=f"demo-ev-{pid}-tool-1-2",
                execution_id=ids["success"],
                agent_name=DEMO_AGENT_NAME,
                type="tool_call",
                timestamp=t0 + timedelta(milliseconds=150),
                tool_name="fetch_order_status",
                duration_ms=210.0,
                status="success",
                input={"order_id": "54321"},
                output={"order_id": "54321", "item": "Ergonomic Keyboard", "delivered": True, "eligible_for_refund": True},
                metadata={"synthetic_demo": True},
            ),
            TraceEvent(
                event_id=f"demo-ev-{pid}-tool-1-3",
                execution_id=ids["success"],
                agent_name=DEMO_AGENT_NAME,
                type="tool_call",
                timestamp=t0 + timedelta(milliseconds=370),
                tool_name="issue_refund",
                duration_ms=345.0,
                status="success",
                input={"order_id": "54321", "amount": 49.99, "reason": "damaged_goods"},
                output={"refund_id": "ref_88291", "status": "approved", "processed_at": "2026-10-22T18:00:00Z"},
                metadata={"synthetic_demo": True},
            ),
            TraceEvent(
                event_id=f"demo-ev-{pid}-tool-1-4",
                execution_id=ids["success"],
                agent_name=DEMO_AGENT_NAME,
                type="tool_call",
                timestamp=t0 + timedelta(milliseconds=725),
                tool_name="send_customer_email",
                duration_ms=95.0,
                status="success",
                input={"to": "alice@example.com", "subject": "Refund Approved", "body": "Your refund of $49.99 for order 54321 has been processed."},
                output={"sent": True, "message_id": "msg_001"},
                metadata={"synthetic_demo": True},
            ),
            TraceEvent(
                event_id=f"demo-ev-{pid}-end-1",
                execution_id=ids["success"],
                agent_name=DEMO_AGENT_NAME,
                type="execution_end",
                timestamp=t0 + timedelta(milliseconds=825),
                duration_ms=825.0,
                status="success",
                output={"status": "resolved", "refund_id": "ref_88291", "amount": 49.99, "action": "processed_refund", "message": "Refund processed successfully for damaged item."},
                metadata={"synthetic_demo": True},
            ),
        ]
        trace_store.ingest(pid, events_success)

    # 3. Ingest Trace 2: Tool timeout failure
    if timeout_trace is None:
        events_timeout = [
            TraceEvent(
                event_id=f"demo-ev-{pid}-start-2",
                execution_id=ids["timeout"],
                agent_name=DEMO_AGENT_NAME,
                type="execution_start",
                timestamp=t1,
                input={"customer_id": "cust_4412", "query": "Process warranty replacement for order #12345", "priority": "urgent"},
                metadata={"synthetic_demo": True, "is_demo": True, "demo_type": "tool_failure", "scenario": "Downstream payment gateway timeout during refund dispatch."},
            ),
            TraceEvent(
                event_id=f"demo-ev-{pid}-tool-2-1",
                execution_id=ids["timeout"],
                agent_name=DEMO_AGENT_NAME,
                type="tool_call",
                timestamp=t1 + timedelta(milliseconds=12),
                tool_name="lookup_customer",
                duration_ms=110.0,
                status="success",
                input={"customer_id": "cust_4412"},
                output={"name": "Bob Smith", "tier": "standard"},
                metadata={"synthetic_demo": True},
            ),
            TraceEvent(
                event_id=f"demo-ev-{pid}-tool-2-2",
                execution_id=ids["timeout"],
                agent_name=DEMO_AGENT_NAME,
                type="tool_call",
                timestamp=t1 + timedelta(milliseconds=130),
                tool_name="fetch_order_status",
                duration_ms=180.0,
                status="success",
                input={"order_id": "12345"},
                output={"order_id": "12345", "item": "USB-C Hub", "delivered": True},
                metadata={"synthetic_demo": True},
            ),
            TraceEvent(
                event_id=f"demo-ev-{pid}-tool-2-3",
                execution_id=ids["timeout"],
                agent_name=DEMO_AGENT_NAME,
                type="tool_call",
                timestamp=t1 + timedelta(milliseconds=320),
                tool_name="issue_refund",
                duration_ms=12000.0,
                status="timeout",
                error_type="GatewayTimeoutError",
                error_message="PaymentGatewayTimeout: Connection to payment gateway service at 10.0.4.12:443 timed out after 12000ms",
                input={"order_id": "12345", "amount": 29.99},
                metadata={"synthetic_demo": True},
            ),
            TraceEvent(
                event_id=f"demo-ev-{pid}-end-2",
                execution_id=ids["timeout"],
                agent_name=DEMO_AGENT_NAME,
                type="execution_end",
                timestamp=t1 + timedelta(milliseconds=12330),
                duration_ms=12330.0,
                status="failed",
                error_type="GatewayTimeoutError",
                error_message="PaymentGatewayTimeout: Downstream refund service timed out after 12000ms",
                metadata={"synthetic_demo": True},
            ),
        ]
        trace_store.ingest(pid, events_timeout)

    # 4. Ingest Trace 3: Regressed execution missing required tools & fields
    if regressed_trace is None:
        events_regressed = [
            TraceEvent(
                event_id=f"demo-ev-{pid}-start-3",
                execution_id=ids["regressed"],
                agent_name=DEMO_AGENT_NAME,
                type="execution_start",
                timestamp=t2,
                input={"customer_id": "cust_9021", "query": "Requesting status of refund for damaged order #54321", "priority": "high"},
                metadata={"synthetic_demo": True, "is_demo": True, "demo_type": "regression_missing_tool", "scenario": "Skipped order verification and confirmation email."},
            ),
            TraceEvent(
                event_id=f"demo-ev-{pid}-tool-3-1",
                execution_id=ids["regressed"],
                agent_name=DEMO_AGENT_NAME,
                type="tool_call",
                timestamp=t2 + timedelta(milliseconds=10),
                tool_name="lookup_customer",
                duration_ms=98.0,
                status="success",
                input={"customer_id": "cust_9021"},
                output={"name": "Alice Johnson", "tier": "gold"},
                metadata={"synthetic_demo": True},
            ),
            # Notice: fetch_order_status is missing
            TraceEvent(
                event_id=f"demo-ev-{pid}-tool-3-2",
                execution_id=ids["regressed"],
                agent_name=DEMO_AGENT_NAME,
                type="tool_call",
                timestamp=t2 + timedelta(milliseconds=115),
                tool_name="issue_refund",
                duration_ms=310.0,
                status="success",
                input={"order_id": "54321", "amount": 49.99},
                output={"refund_id": "ref_88291", "status": "approved"},
                metadata={"synthetic_demo": True},
            ),
            # Notice: send_customer_email is missing
            TraceEvent(
                event_id=f"demo-ev-{pid}-end-3",
                execution_id=ids["regressed"],
                agent_name=DEMO_AGENT_NAME,
                type="execution_end",
                timestamp=t2 + timedelta(milliseconds=430),
                duration_ms=430.0,
                status="success",
                output={"status": "resolved", "action": "processed_refund", "message": "Refund processed without verification."},
                metadata={"synthetic_demo": True},
            ),
        ]
        trace_store.ingest(pid, events_regressed)

    # 5. Create Golden Baseline
    if demo_baseline is None:
        demo_baseline = baseline_store.create_baseline(
            project_id=pid,
            agent_name=DEMO_AGENT_NAME,
            name=DEMO_BASELINE_NAME,
            description="Synthetic golden baseline for customer support triage: requires customer lookup, order verification, refund issuance, and confirmation email.",
            source_type="trace",
            source_id=ids["success"],
            status="completed",
            duration_ms=825.0,
            input_val={"customer_id": "cust_9021", "query": "Requesting status of refund for damaged order #54321", "priority": "high"},
            output_val={"status": "resolved", "refund_id": "ref_88291", "amount": 49.99, "action": "processed_refund", "message": "Refund processed successfully for damaged item."},
            tools=[
                {"tool_name": "lookup_customer", "status": "success", "duration_ms": 125.0},
                {"tool_name": "fetch_order_status", "status": "success", "duration_ms": 210.0},
                {"tool_name": "issue_refund", "status": "success", "duration_ms": 345.0},
                {"tool_name": "send_customer_email", "status": "success", "duration_ms": 95.0},
            ],
            expected={
                "tools": ["lookup_customer", "fetch_order_status", "issue_refund", "send_customer_email"],
                "strict_order": True,
                "output_fields": ["status", "refund_id", "amount", "action"],
            },
        )

    # 6. Create Test Case and Simulated Runs
    case_id = demo_case["id"] if demo_case else None
    if demo_case is None:
        case_id = test_store.create_case(
            data={
                "name": DEMO_TEST_NAME,
                "description": "Synthetic regression test for customer support refund triage with tool verification.",
                "agent_name": DEMO_AGENT_NAME,
                "input": {"customer_id": "cust_9021", "query": "Requesting status of refund for damaged order #54321", "priority": "high"},
                "steps": [
                    {"tool": "lookup_customer", "input": {"customer_id": "cust_9021"}, "output": {"name": "Alice Johnson", "tier": "gold"}},
                    {"tool": "fetch_order_status", "input": {"order_id": "54321"}, "output": {"order_id": "54321", "eligible_for_refund": True}},
                    {"tool": "issue_refund", "input": {"order_id": "54321", "amount": 49.99}, "output": {"refund_id": "ref_88291", "status": "approved"}},
                    {"tool": "send_customer_email", "input": {"to": "alice@example.com"}, "output": {"sent": True}},
                ],
                "expected": {
                    "status": "completed",
                    "output": {"status": "resolved", "refund_id": "ref_88291"},
                    "required_tools": ["lookup_customer", "fetch_order_status", "issue_refund", "send_customer_email"],
                },
            },
            source_type="trace",
            source_trace_id=ids["success"],
            project_id=pid,
        )

        # Passing run
        test_store.save_run(
            case={"id": case_id, "name": DEMO_TEST_NAME},
            result={
                "status": "passed",
                "mode": "replay",
                "mismatches": [],
                "observed": {"status": "completed", "output": {"status": "resolved", "refund_id": "ref_88291"}},
                "duration_ms": 775.0,
            },
            project_id=pid,
        )

        # Regressed run
        test_store.save_run(
            case={"id": case_id, "name": DEMO_TEST_NAME},
            result={
                "status": "failed",
                "mode": "replay",
                "mismatches": [
                    {"field": "steps", "reason": "Missing expected tool call 'send_customer_email'"},
                    {"field": "output.refund_id", "reason": "Expected 'ref_88291' but field was missing"},
                ],
                "observed": {"status": "completed", "output": {"status": "resolved"}},
                "duration_ms": 408.0,
            },
            project_id=pid,
        )

    # 7. Generate comparison reports using existing regression engine
    base_ver = demo_baseline.get("version_data") if demo_baseline else None
    if not base_ver and demo_baseline:
        fresh_b = baseline_store.get_baseline(demo_baseline["id"], project_id=pid)
        base_ver = fresh_b.get("version_data") if fresh_b else None

    passing_comp = None
    regressed_comp = None

    if base_ver:
        cand_s = trace_store.get_execution(ids["success"], project_id=pid)
        cand_r = trace_store.get_execution(ids["regressed"], project_id=pid)
        if cand_s:
            passing_comp = compare_execution_to_baseline(baseline=base_ver, candidate=cand_s)
        if cand_r:
            regressed_comp = compare_execution_to_baseline(baseline=base_ver, candidate=cand_r)

    return {
        "status": "success",
        "already_existed": already_existed,
        "message": (
            "Demo agent & traces are already loaded in this project."
            if already_existed
            else "Synthetic customer-support demo agent, traces, baseline, and regressions loaded successfully."
        ),
        "agent_name": DEMO_AGENT_NAME,
        "traces": {
            "success": ids["success"],
            "timeout": ids["timeout"],
            "regressed": ids["regressed"],
        },
        "baseline": {
            "id": demo_baseline["id"] if demo_baseline else None,
            "name": demo_baseline["name"] if demo_baseline else None,
        },
        "comparisons": {
            "passing": {
                "candidate_trace_id": ids["success"],
                "verdict": passing_comp["verdict"] if passing_comp else "passed",
                "is_regression": passing_comp["is_regression"] if passing_comp else False,
            },
            "breaking_regression": {
                "candidate_trace_id": ids["regressed"],
                "verdict": regressed_comp["verdict"] if regressed_comp else "regression",
                "is_regression": regressed_comp["is_regression"] if regressed_comp else True,
                "differences_count": len(regressed_comp.get("differences", [])) if regressed_comp else 2,
            },
        },
        "test_case_id": case_id,
        "failure_analysis_trace_id": ids["timeout"],
    }
