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
def list_ci_runs(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    return ci_store.list_ci_runs(limit=limit, offset=offset)


@router.get("/api/ci/runs/{run_id}")
def get_ci_run(run_id: int):
    run = ci_store.get_ci_run(run_id)
    if not run:
        raise HTTPException(404, "CI test run not found.")
    return run

