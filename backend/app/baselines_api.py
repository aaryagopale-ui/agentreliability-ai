"""API endpoints for regression baselines, versioning, and deterministic comparison."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from . import baseline_store, database, trace_store
from .auth_api import check_csrf, get_current_user
from .auth_deps import get_authorized_project, require_api_key_project
from .regression_engine import compare_execution_to_baseline
from .test_schemas import (
    CompareRequestIn,
    CreateBaselineIn,
    UpdateBaselineIn,
)

router = APIRouter()


def _resolve_source_data(source_type: str, source_id: str, project_id: int) -> dict:
    """Safely fetch and normalize execution/trace data within project boundary."""
    if source_type == "trace":
        trace = trace_store.get_execution(source_id, project_id=project_id)
        if not trace:
            raise HTTPException(status_code=404, detail="Source trace execution not found.")
        return {
            "agent_name": trace["agent_name"],
            "status": trace["status"],
            "duration_ms": trace.get("duration_ms"),
            "input": trace.get("input"),
            "output": trace.get("output"),
            "tools": trace.get("tool_calls", []),
            "error_type": trace.get("error_type"),
            "error_message": trace.get("error_message"),
        }
    elif source_type == "execution":
        try:
            exec_int = int(source_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="source_id must be integer for execution source_type.")
        execution = database.get_execution(exec_int, project_id=project_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Source execution not found.")

        steps = execution.get("steps", [])
        tool_steps = [s for s in steps if str(s.get("type", "")).lower() == "tool_call"]
        return {
            "agent_name": execution["agent_name"],
            "status": execution["status"],
            "duration_ms": sum(s.get("duration_ms", 0) for s in steps) if steps else None,
            "input": next((s.get("input") for s in steps if s.get("input") is not None), None),
            "output": next((s.get("output") for s in reversed(steps) if s.get("output") is not None), None),
            "tools": tool_steps,
            "error_type": None,
            "error_message": None,
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported source_type: '{source_type}'.")


@router.post("/api/baselines", status_code=status.HTTP_201_CREATED)
def create_baseline_endpoint(
    body: CreateBaselineIn,
    request: Request,
    project: dict = Depends(get_authorized_project),
    user: dict = Depends(get_current_user),
):
    check_csrf(request)
    pid = project["id"]
    source_data = _resolve_source_data(body.source_type, body.source_id, pid)

    # Derive default expected behavior if not provided
    tools = source_data["tools"]
    tool_seq = [t.get("tool_name") or t.get("name") for t in tools if (t.get("tool_name") or t.get("name"))]
    out = source_data["output"]

    expected_dict = body.expected.model_dump() if body.expected else {
        "status": source_data["status"],
        "tool_sequence": tool_seq,
        "final_output": out,
        "expected_output_fields": list(out.keys()) if isinstance(out, dict) else None,
        "expected_error_type": source_data.get("error_type"),
        "max_duration_ms": round(source_data["duration_ms"] * 1.5, 2) if source_data.get("duration_ms") else None,
        "strict_order": True,
        "allow_additional_tools": False,
        "error_conditions": [],
    }

    baseline = baseline_store.create_baseline(
        project_id=pid,
        agent_name=source_data["agent_name"],
        name=body.name,
        description=body.description,
        source_type=body.source_type,
        source_id=body.source_id,
        status=source_data["status"],
        duration_ms=source_data.get("duration_ms"),
        input_val=source_data.get("input"),
        output_val=source_data.get("output"),
        tools=tools,
        expected=expected_dict,
        user_id=user["id"],
    )
    return baseline


@router.get("/api/baselines")
def list_baselines_endpoint(
    agent_name: Optional[str] = Query(default=None),
    project: dict = Depends(get_authorized_project),
):
    return baseline_store.list_baselines(project["id"], agent_name=agent_name)


@router.get("/api/baselines/{baseline_id}")
def get_baseline_endpoint(
    baseline_id: int,
    project: dict = Depends(get_authorized_project),
):
    baseline = baseline_store.get_baseline(baseline_id, project_id=project["id"])
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found.")
    baseline["history"] = baseline_store.list_baseline_versions(baseline_id, project_id=project["id"])
    return baseline


@router.get("/api/baselines/{baseline_id}/versions")
def list_baseline_versions_endpoint(
    baseline_id: int,
    project: dict = Depends(get_authorized_project),
):
    baseline = baseline_store.get_baseline(baseline_id, project_id=project["id"])
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found.")
    return baseline_store.list_baseline_versions(baseline_id, project_id=project["id"])


@router.get("/api/baselines/{baseline_id}/versions/{version}")
def get_baseline_version_endpoint(
    baseline_id: int,
    version: int,
    project: dict = Depends(get_authorized_project),
):
    v = baseline_store.get_baseline_version(baseline_id, version, project_id=project["id"])
    if not v:
        raise HTTPException(status_code=404, detail="Baseline version not found.")
    return v


@router.post("/api/baselines/{baseline_id}/versions", status_code=status.HTTP_201_CREATED)
def add_baseline_version_endpoint(
    baseline_id: int,
    body: UpdateBaselineIn,
    request: Request,
    project: dict = Depends(get_authorized_project),
    user: dict = Depends(get_current_user),
):
    check_csrf(request)
    pid = project["id"]
    existing = baseline_store.get_baseline(baseline_id, project_id=pid)
    if not existing:
        raise HTTPException(status_code=404, detail="Baseline not found.")

    source_data = _resolve_source_data(body.source_type, body.source_id, pid)
    tools = source_data["tools"]
    tool_seq = [t.get("tool_name") or t.get("name") for t in tools if (t.get("tool_name") or t.get("name"))]
    out = source_data["output"]

    expected_dict = body.expected.model_dump() if body.expected else {
        "status": source_data["status"],
        "tool_sequence": tool_seq,
        "final_output": out,
        "expected_output_fields": list(out.keys()) if isinstance(out, dict) else None,
        "expected_error_type": source_data.get("error_type"),
        "max_duration_ms": round(source_data["duration_ms"] * 1.5, 2) if source_data.get("duration_ms") else None,
        "strict_order": True,
        "allow_additional_tools": False,
        "error_conditions": [],
    }

    updated = baseline_store.create_baseline_version(
        baseline_id=baseline_id,
        project_id=pid,
        source_type=body.source_type,
        source_id=body.source_id,
        status=source_data["status"],
        duration_ms=source_data.get("duration_ms"),
        input_val=source_data.get("input"),
        output_val=source_data.get("output"),
        tools=tools,
        expected=expected_dict,
        user_id=user["id"],
        description=body.description,
    )
    return updated


@router.delete("/api/baselines/{baseline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_baseline_endpoint(
    baseline_id: int,
    request: Request,
    project: dict = Depends(get_authorized_project),
):
    check_csrf(request)
    deleted = baseline_store.delete_baseline(baseline_id, project_id=project["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Baseline not found.")


@router.post("/api/baselines/{baseline_id}/compare")
def compare_with_baseline_endpoint(
    baseline_id: int,
    body: CompareRequestIn,
    request: Request,
    project: dict = Depends(get_authorized_project),
):
    check_csrf(request)
    pid = project["id"]
    baseline = baseline_store.get_baseline(baseline_id, project_id=pid)
    if not baseline or "version_data" not in baseline:
        raise HTTPException(status_code=404, detail="Baseline not found.")

    base_ver = baseline["version_data"]

    # Resolve candidate
    if body.candidate_trace_id:
        cand_trace = trace_store.get_execution(body.candidate_trace_id, project_id=pid)
        if not cand_trace:
            raise HTTPException(status_code=404, detail="Candidate trace not found.")
        candidate_data = cand_trace
    elif body.candidate_execution_id is not None:
        cand_exec = database.get_execution(body.candidate_execution_id, project_id=pid)
        if not cand_exec:
            raise HTTPException(status_code=404, detail="Candidate execution not found.")
        steps = cand_exec.get("steps", [])
        tool_steps = [s for s in steps if str(s.get("type", "")).lower() == "tool_call"]
        candidate_data = {
            "agent_name": cand_exec["agent_name"],
            "status": cand_exec["status"],
            "duration_ms": sum(s.get("duration_ms", 0) for s in steps) if steps else None,
            "input": next((s.get("input") for s in steps if s.get("input") is not None), None),
            "output": next((s.get("output") for s in reversed(steps) if s.get("output") is not None), None),
            "tool_calls": tool_steps,
            "error_type": None,
            "error_message": None,
        }
    else:
        raise HTTPException(status_code=400, detail="Must provide candidate_trace_id or candidate_execution_id.")

    report = compare_execution_to_baseline(
        baseline=base_ver,
        candidate=candidate_data,
        duration_tolerance_pct=body.duration_tolerance_pct,
    )
    report["baseline_id"] = baseline["id"]
    report["baseline_name"] = baseline["name"]
    report["baseline_version"] = base_ver["version"]
    return report


@router.get("/api/v1/baselines")
def list_baselines_v1_endpoint(
    agent_name: Optional[str] = Query(default=None),
    project: dict = Depends(require_api_key_project),
):
    """List Golden Baselines for the project associated with the API key."""
    return baseline_store.list_baselines(project["id"], agent_name=agent_name)


@router.post("/api/v1/baselines/{baseline_id}/compare")
def compare_with_baseline_v1_endpoint(
    baseline_id: int,
    body: CompareRequestIn,
    project: dict = Depends(require_api_key_project),
):
    """Compare a candidate trace against a Golden Baseline using API key auth (for CLI / CI)."""
    pid = project["id"]
    baseline = baseline_store.get_baseline(baseline_id, project_id=pid)
    if not baseline or "version_data" not in baseline:
        raise HTTPException(status_code=404, detail="Baseline not found.")

    base_ver = baseline["version_data"]

    # Resolve candidate
    if body.candidate_trace_id:
        cand_trace = trace_store.get_execution(body.candidate_trace_id, project_id=pid)
        if not cand_trace:
            raise HTTPException(status_code=404, detail="Candidate trace not found.")
        candidate_data = cand_trace
    elif body.candidate_execution_id is not None:
        cand_exec = database.get_execution(body.candidate_execution_id, project_id=pid)
        if not cand_exec:
            raise HTTPException(status_code=404, detail="Candidate execution not found.")
        steps = cand_exec.get("steps", [])
        tool_steps = [s for s in steps if str(s.get("type", "")).lower() == "tool_call"]
        candidate_data = {
            "agent_name": cand_exec["agent_name"],
            "status": cand_exec["status"],
            "duration_ms": sum(s.get("duration_ms", 0) for s in steps) if steps else None,
            "input": next((s.get("input") for s in steps if s.get("input") is not None), None),
            "output": next((s.get("output") for s in reversed(steps) if s.get("output") is not None), None),
            "tool_calls": tool_steps,
            "error_type": None,
            "error_message": None,
        }
    else:
        raise HTTPException(status_code=400, detail="Must provide candidate_trace_id or candidate_execution_id.")

    report = compare_execution_to_baseline(
        baseline=base_ver,
        candidate=candidate_data,
        duration_tolerance_pct=body.duration_tolerance_pct,
    )
    report["baseline_id"] = baseline["id"]
    report["baseline_name"] = baseline["name"]
    report["baseline_version"] = base_ver["version"]
    return report


@router.post("/api/regression/compare-traces")
def compare_two_traces_endpoint(
    request: Request,
    baseline_trace_id: str = Query(...),
    candidate_trace_id: str = Query(...),
    duration_tolerance_pct: float = Query(default=50.0, ge=0.0, le=1000.0),
    project: dict = Depends(get_authorized_project),
):
    check_csrf(request)
    pid = project["id"]
    t1 = trace_store.get_execution(baseline_trace_id, project_id=pid)
    if not t1:
        raise HTTPException(status_code=404, detail="Baseline trace not found.")

    t2 = trace_store.get_execution(candidate_trace_id, project_id=pid)
    if not t2:
        raise HTTPException(status_code=404, detail="Candidate trace not found.")

    # Convert t1 to baseline structure
    tools_1 = t1.get("tool_calls", [])
    seq_1 = [t["tool_name"] for t in tools_1]
    base_dict = {
        "agent_name": t1["agent_name"],
        "status": t1["status"],
        "duration_ms": t1.get("duration_ms"),
        "input": t1.get("input"),
        "output": t1.get("output"),
        "tools": tools_1,
        "expected": {
            "status": t1["status"],
            "tool_sequence": seq_1,
            "final_output": t1.get("output"),
            "strict_order": True,
            "allow_additional_tools": False,
        },
    }

    report = compare_execution_to_baseline(
        baseline=base_dict,
        candidate=t2,
        duration_tolerance_pct=duration_tolerance_pct,
    )
    report["baseline_trace_id"] = baseline_trace_id
    report["candidate_trace_id"] = candidate_trace_id
    return report
