"""CI/CD Results API router.

Endpoints:
  POST /api/v1/ci/runs  - Authenticated ingestion from GitHub Actions
  GET  /api/ci/runs     - List CI runs for dashboard
  GET  /api/ci/runs/{id} - Get detailed test report for a CI run
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from . import ci_store
from .auth_deps import get_authorized_project, require_owned_ci_run
from .traces_api import require_project

router = APIRouter()


class CIRunPayload(BaseModel):
    commit_sha: str = Field(default="local", max_length=64)
    branch: str = Field(default="main", max_length=128)
    actor: str = Field(default="user", max_length=128)
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    duration_ms: float = Field(ge=0.0)
    report: dict = Field(default_factory=dict)


@router.post("/api/v1/ci/runs", status_code=201)
def ingest_ci_run(payload: CIRunPayload, project: dict = Depends(require_project)):
    run_id = ci_store.save_ci_run(project["id"], payload.model_dump())
    return {"id": run_id, "status": "recorded"}


@router.get("/api/ci/runs")
def list_ci_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    project: dict = Depends(get_authorized_project),
):
    return ci_store.list_ci_runs(project_id=project["id"], limit=limit, offset=offset)


@router.get("/api/ci/runs/{run_id}")
def get_ci_run(run: dict = Depends(require_owned_ci_run)):
    return run


@router.get("/api/ci/regression")
def compare_ci_runs(
    base_id: int = Query(...),
    head_id: int = Query(...),
    project: dict = Depends(get_authorized_project),
):
    """Compare two CI runs belonging to the authorized project."""
    base_run = ci_store.get_ci_run(base_id, project_id=project["id"])
    head_run = ci_store.get_ci_run(head_id, project_id=project["id"])
    if not base_run or not head_run:
        raise HTTPException(404, "CI test run not found.")

    base_results = base_run.get("report", {}).get("results", [])
    head_results = head_run.get("report", {}).get("results", [])

    base_map = {b.get("name") or b.get("test_name"): b for b in base_results}
    new_failures, fixed_failures, unchanged_failures, passed = [], [], [], []

    for curr in head_results:
        name = curr.get("name") or curr.get("test_name")
        curr_status = curr.get("status")
        base = base_map.get(name)

        if base is None:
            if curr_status == "failed":
                new_failures.append(curr)
            else:
                passed.append(curr)
        else:
            base_status = base.get("status")
            if curr_status == "failed" and base_status == "passed":
                new_failures.append({**curr, "regression_note": "Regression: passed in baseline, failed in current run"})
            elif curr_status == "passed" and base_status == "failed":
                fixed_failures.append({**curr, "regression_note": "Fixed: failed in baseline, passed in current run"})
            elif curr_status == "failed" and base_status == "failed":
                unchanged_failures.append(curr)
            else:
                passed.append(curr)

    return {
        "has_baseline": True,
        "base_run_id": base_id,
        "head_run_id": head_id,
        "counts": {
            "total": len(head_results),
            "new_failures": len(new_failures),
            "fixed_failures": len(fixed_failures),
            "unchanged_failures": len(unchanged_failures),
            "passed": len(passed),
        },
        "summary": {
            "new_failures": new_failures,
            "fixed_failures": fixed_failures,
            "unchanged_failures": unchanged_failures,
            "passed": passed,
        },
    }

