"""Trace API: SDK ingestion (needs an API key) and dashboard reads.

Honest scope note: the dashboard READ endpoints have no login (Phase 3 only adds key auth for
SDK writes). Run this locally; add user login before exposing it to a network.
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import ValidationError

from . import test_store, trace_store
from .replay import final_output_of
from .test_schemas import FromExecutionIn
from .testgen import generate_from_execution
from .traces_schemas import MAX_BODY_BYTES, IngestRequest

router = APIRouter()

SOURCE_LABEL = "recorded_real_execution"


# ---------------------------------------------------------------- auth

def require_project(x_api_key: Optional[str] = Header(default=None)) -> dict:
    """Look the key up by its hash. The message is the same whether the key is missing-ish or wrong."""
    if not x_api_key:
        raise HTTPException(401, "Missing API key. Send it in the X-API-Key header.")
    project = trace_store.find_project_by_key(x_api_key)
    if project is None:
        raise HTTPException(401, "Invalid API key.")
    return project


# ---------------------------------------------------------------- ingestion

@router.post("/api/v1/traces/events")
async def ingest_events(request: Request, project: dict = Depends(require_project)):
    # Auth runs first, so unauthenticated callers cannot make us read large bodies.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(413, f"Request body too large (max {MAX_BODY_BYTES} bytes).")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(413, f"Request body too large (max {MAX_BODY_BYTES} bytes).")
    try:
        payload = json.loads(raw)  # data only: nothing in the payload is ever executed
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Body is not valid JSON.")
    try:
        batch = IngestRequest.model_validate(payload)
    except ValidationError as e:
        problems = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:20]]
        raise HTTPException(422, {"message": "Trace events are invalid.", "problems": problems})
    accepted, duplicates = trace_store.ingest(project["id"], batch.events)
    return {"accepted": accepted, "duplicates": duplicates}


# ---------------------------------------------------------------- reads

@router.get("/api/traces/executions")
def list_trace_executions(
    agent: Optional[str] = None,
    status: Optional[str] = Query(default=None, pattern="^(running|success|failed)$"),
    failure_kind: Optional[str] = Query(default=None, pattern="^(timeout|tool_failure|unexpected_exception)$"),
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return trace_store.list_executions(agent, status, failure_kind, since, until, limit, offset)


@router.get("/api/traces/agents")
def list_trace_agents():
    return trace_store.list_agents()


@router.get("/api/traces/errors")
def trace_errors(agent: Optional[str] = None, since: Optional[datetime] = None,
                 limit: int = Query(default=50, ge=1, le=200)):
    """Failed executions plus failed (error/timeout) tool calls."""
    failed = trace_store.list_executions(agent, "failed", None, since, None, limit, 0)["items"]
    tools = [t for t in trace_store.list_tool_calls(agent=agent, since=since, limit=limit * 2)
             if t["status"] != "success"][:limit]
    return {"failed_executions": failed, "failed_tool_calls": tools}


@router.get("/api/traces/tool-calls")
def trace_tool_calls(execution_id: Optional[str] = None,
                     status: Optional[str] = Query(default=None, pattern="^(success|error|timeout)$"),
                     tool_name: Optional[str] = None, agent: Optional[str] = None,
                     since: Optional[datetime] = None, limit: int = Query(default=100, ge=1, le=500)):
    return trace_store.list_tool_calls(execution_id, status, tool_name, agent, since, limit)


@router.get("/api/traces/executions/{execution_id}")
def get_trace_execution(execution_id: str):
    data = trace_store.get_execution(execution_id)
    if data is None:
        raise HTTPException(404, "Execution not found.")
    return data


# ---------------------------------------------------------------- monitoring -> testing

_STEP_STATUS = {"success": "success", "error": "failed", "timeout": "timeout"}


def trace_to_steps(execution: dict) -> list:
    """Convert a captured execution into Phase 2 'steps' (tool calls double as mock responses)."""
    steps = []
    for t in execution["tool_calls"]:
        step = {"type": "tool_call", "name": t["tool_name"], "status": _STEP_STATUS[t["status"]],
                "timestamp": t["started_at"], "duration_ms": t["duration_ms"],
                "input": t["input"], "output": t["output"]}
        if t["error_type"] or t["error_message"]:
            step["error"] = f"{t['error_type'] or 'Error'}: {t['error_message'] or ''}".strip()
        steps.append(step)
    kind = execution["failure_kind"]
    if kind == "unexpected_exception":
        steps.append({"type": "error", "name": execution["agent_name"], "status": "exception",
                      "error": f"{execution['error_type']}: {execution['error_message'] or ''}".strip()})
    elif kind == "timeout" and not any(s["status"] == "timeout" for s in steps):
        steps.append({"type": "error", "name": execution["agent_name"], "status": "timeout",
                      "error": f"{execution['error_type']}: {execution['error_message'] or ''}".strip()})
    elif execution["status"] == "success":
        steps.append({"type": "agent_output", "name": execution["agent_name"], "status": "success",
                      "output": execution["output"]})
    return steps


@router.post("/api/traces/executions/{execution_id}/create-test", status_code=201)
def create_test_from_trace(execution_id: str, body: Optional[FromExecutionIn] = None):
    execution = trace_store.get_execution(execution_id)
    if execution is None:
        raise HTTPException(404, "Execution not found.")
    if execution["status"] == "running":
        raise HTTPException(409, "This execution is still running (no end event yet). Wait for it to finish.")
    steps = trace_to_steps(execution)
    data = generate_from_execution(
        {"id": execution_id[:8], "agent_name": execution["agent_name"], "run_id": execution_id, "steps": steps},
        body.name if body and body.name else f"{execution['agent_name']} / trace {execution_id[:8]}",
    )
    data["input"] = execution["input"]
    data["description"] = (
        f"Created from a RECORDED REAL execution (SDK trace {execution_id}). Running this test is a "
        "deterministic simulation with mocked tools; it is not a live re-execution of your agent."
    )
    case_id = test_store.create_case(data, source_type=SOURCE_LABEL, source_trace_id=execution_id)
    return test_store.get_case(case_id)

