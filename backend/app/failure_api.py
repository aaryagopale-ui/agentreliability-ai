"""API router for Evidence-Based Failure Analysis and Local AI Debugging."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from . import baseline_store, database, test_store, trace_store
from .auth_api import check_csrf
from .auth_deps import get_authorized_project
from .failure_engine import diagnose_failure
from .local_ai import check_ollama_status, run_local_ai_diagnosis
from .regression_engine import compare_execution_to_baseline

router = APIRouter()


class DiagnoseRequestIn(BaseModel):
    execution_id: str = Field(min_length=1, max_length=255)
    source_type: str = Field(default="trace")  # 'trace' or 'execution'
    use_ai: bool = True
    model: Optional[str] = None


@router.get("/api/failure-analysis/ollama/status")
def get_ollama_status_endpoint():
    """Probe local Ollama daemon status without requiring auth (read-only health info)."""
    return check_ollama_status()


@router.get("/api/failure-analysis")
def failure_analysis_overview(project: dict = Depends(get_authorized_project)):
    """Comprehensive failure analysis overview for the active project."""
    pid = project["id"]

    # 1. Test Replay Mismatches (Phase 2)
    latest = test_store.latest_runs_per_test(project_id=pid)
    replay_kinds: dict[str, int] = {}
    failing_test_runs = []
    for run in latest:
        if run["status"] == "failed":
            failing_test_runs.append(run)
            for m in run.get("mismatches", []):
                k = m.get("kind", "unknown")
                replay_kinds[k] = replay_kinds.get(k, 0) + 1

    # 2. Phase 1 Uploaded Execution Findings
    exec_findings = test_store.execution_finding_counts(project_id=pid)

    # 3. Real Trace Execution Failures (Phase 6)
    failed_traces_res = trace_store.list_executions(project_id=pid, status="failed", limit=50)
    failed_traces = failed_traces_res.get("items", []) if isinstance(failed_traces_res, dict) else (failed_traces_res or [])
    trace_failure_kinds: dict[str, int] = {}
    for t in failed_traces:
        fk = t.get("failure_kind") or t.get("error_type") or "unspecified_failure"
        trace_failure_kinds[fk] = trace_failure_kinds.get(fk, 0) + 1

    # Check local AI readiness
    ollama_info = check_ollama_status()

    return {
        "execution_findings": exec_findings,
        "replay_mismatches": replay_kinds,
        "trace_failure_kinds": trace_failure_kinds,
        "failing_runs": failing_test_runs,
        "failed_traces": [
            {
                "execution_id": t["execution_id"],
                "agent_name": t["agent_name"],
                "status": t["status"],
                "failure_kind": t.get("failure_kind"),
                "error_type": t.get("error_type"),
                "error_message": t.get("error_message"),
                "started_at": t.get("started_at"),
                "duration_ms": t.get("duration_ms"),
                "tool_call_count": t.get("tool_call_count", 0),
                "failed_tool_calls": t.get("failed_tool_calls", 0),
            }
            for t in failed_traces
        ],
        "local_ai": ollama_info,
    }


@router.post("/api/failure-analysis/diagnose")
def diagnose_execution_endpoint(
    body: DiagnoseRequestIn,
    request: Request,
    project: dict = Depends(get_authorized_project),
):
    """Run evidence-based diagnostic extraction and optional local AI failure analysis."""
    check_csrf(request)
    pid = project["id"]

    exec_dict: Optional[dict] = None
    tools: List[dict] = []
    agent_name = ""

    if body.source_type == "trace":
        trace = trace_store.get_execution(body.execution_id, project_id=pid)
        if not trace:
            raise HTTPException(status_code=404, detail="Trace execution not found in this project.")
        exec_dict = trace
        tools = trace.get("tool_calls", [])
        agent_name = trace["agent_name"]
    elif body.source_type == "execution":
        try:
            exec_int = int(body.execution_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="execution_id must be integer for 'execution' source_type.")
        execution = database.get_execution(exec_int, project_id=pid)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found in this project.")
        exec_dict = {
            "execution_id": str(execution["id"]),
            "agent_name": execution["agent_name"],
            "status": execution["status"],
            "failure_kind": execution.get("findings", [{}])[0].get("category") if execution.get("findings") else None,
            "error_type": None,
            "error_message": execution.get("findings", [{}])[0].get("explanation") if execution.get("findings") else None,
            "duration_ms": sum(s.get("duration_ms", 0) for s in execution.get("steps", [])),
            "input": next((s.get("input") for s in execution.get("steps", []) if s.get("input") is not None), None),
            "output": next((s.get("output") for s in reversed(execution.get("steps", [])) if s.get("output") is not None), None),
        }
        agent_name = execution["agent_name"]
        tools = [
            {
                "call_id": f"step_{idx}",
                "tool_name": s.get("name") or "tool",
                "status": s.get("status"),
                "duration_ms": s.get("duration_ms"),
                "error_type": None,
                "error_message": s.get("error"),
                "retry_count": 0,
            }
            for idx, s in enumerate(execution.get("steps", []))
            if str(s.get("type", "")).lower() == "tool_call"
        ]
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported source_type: '{body.source_type}'.")

    # Check if a golden baseline exists for this agent to provide regression evidence
    regression_comparison = None
    try:
        baselines = baseline_store.list_baselines(project_id=pid, agent_name=agent_name)
        if baselines:
            # Use most recent baseline
            base_full = baseline_store.get_baseline(baselines[0]["id"], project_id=pid)
            if base_full and "version_data" in base_full:
                candidate_data = {
                    "agent_name": agent_name,
                    "status": exec_dict["status"],
                    "duration_ms": exec_dict.get("duration_ms"),
                    "output": exec_dict.get("output"),
                    "tool_calls": tools,
                    "error_type": exec_dict.get("error_type"),
                    "error_message": exec_dict.get("error_message"),
                }
                regression_comparison = compare_execution_to_baseline(
                    baseline=base_full["version_data"],
                    candidate=candidate_data,
                )
    except Exception as exc:
        # Graceful fallback: diagnosis proceeds even if regression comparison fails
        pass

    # Run Deterministic Diagnosis
    deterministic_report = diagnose_failure(
        execution=exec_dict,
        tool_calls=tools,
        regression_comparison=regression_comparison,
    )

    # Run Optional Local AI Analysis (Ollama)
    ai_report = None
    if body.use_ai:
        ai_report = run_local_ai_diagnosis(
            diagnostic_report=deterministic_report,
            model=body.model,
        )

    return {
        "project_id": pid,
        "source_type": body.source_type,
        "diagnostic_report": deterministic_report,
        "ai_analysis": ai_report,
    }
