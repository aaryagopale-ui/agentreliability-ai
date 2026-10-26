"""FastAPI app. Run: uvicorn app.main:app --reload --port 8000"""
import json
import logging
import os
import re
from urllib.parse import urlparse
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from . import ci_store, database, test_store, trace_store
from .auth_api import check_csrf, router as auth_router
from .auth_deps import (
    get_authorized_project,
    require_owned_execution,
    require_owned_test_case,
    require_owned_test_run,
)
from .ci_api import router as ci_router
from .detector import analyze
from .projects_api import router as projects_router
from .replay import run_test
from .schemas import AgentLog
from .test_schemas import FromExecutionIn, TestCaseIn
from .testgen import generate_from_execution
from .traces_api import router as traces_router
from .baselines_api import router as baselines_router
from .failure_api import router as failure_router
from .demo_api import router as demo_router

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    test_store.init_tables()
    trace_store.init_tables()
    ci_store.init_tables()
    yield


logger = logging.getLogger("agentreliability.main")

app = FastAPI(title="AgentReliability AI", lifespan=lifespan)

# Configurable CORS for multi-environment support (dev, staging, production)
DEFAULT_DEV_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5174", "http://127.0.0.1:5174",
    "http://localhost:5175", "http://127.0.0.1:5175",
]

PRODUCTION_FRONTEND_ORIGINS = [
    "https://agentreliability-ai.vercel.app",
]


def resolve_allowed_origins() -> list[str]:
    """Resolve and sanitize allowed CORS origins without wildcards for credentials support."""
    allowed = set()
    # Always allow local dev origins
    allowed.update(DEFAULT_DEV_ORIGINS)
    # Always allow production Vercel frontend
    allowed.update(PRODUCTION_FRONTEND_ORIGINS)

    # Environment overrides (AGENTRELIABILITY_ALLOWED_ORIGINS, FRONTEND_URL, etc.)
    env_origins_str = os.environ.get("AGENTRELIABILITY_ALLOWED_ORIGINS", "")
    for env_val in [env_origins_str, os.environ.get("FRONTEND_URL"), os.environ.get("AGENTRELIABILITY_FRONTEND_URL")]:
        if env_val:
            for item in env_val.split(","):
                cleaned = item.strip().rstrip("/")
                if cleaned:
                    allowed.add(cleaned)

    return sorted(list(allowed))


@app.middleware("http")
async def preserve_cors_on_error_middleware(request: Request, call_next):
    """Ensure that even unhandled exceptions (HTTP 500) return a structured response
    that passes through CORSMiddleware, preserving Access-Control-Allow-Origin headers
    so frontend clients receive clear diagnostic errors rather than misleading browser CORS blocks.
    Also ensures redirect responses (3xx) do not leak absolute backend URLs that would
    bypass same-origin proxies (e.g. Vercel /api rewrite)."""
    try:
        response = await call_next(request)
        if response.status_code in (301, 302, 307, 308) and "location" in response.headers:
            loc = response.headers["location"]
            parsed = urlparse(loc)
            if parsed.netloc:
                response.headers["location"] = f"{parsed.path}{'?' + parsed.query if parsed.query else ''}"
        return response
    except Exception as exc:
        logger.exception("Unhandled server exception processing %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Please check server logs or retry."},
        )


raw_regex = os.environ.get("AGENTRELIABILITY_ALLOWED_ORIGIN_REGEX")
if raw_regex is not None:
    origin_regex = raw_regex.strip() or None
elif os.environ.get("AGENTRELIABILITY_ENV") == "production":
    origin_regex = None
else:
    origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=resolve_allowed_origins(),
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-CSRF-Token", "X-Instance-ID", "X-Service", "X-Service-Version"],
)


app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(traces_router)
app.include_router(ci_router)
app.include_router(baselines_router)
app.include_router(failure_router)
app.include_router(demo_router)


def get_instance_identity() -> dict:
    if database.is_postgres():
        db_url = database.get_database_url() or ""
        masked_url = re.sub(r":([^:@]+)@", ":****@", db_url)
        db_name = "Neon PostgreSQL"
        if "@" in masked_url:
            host_part = masked_url.split("@")[-1].split("?")[0]
            db_name = f"PostgreSQL ({host_part})"
        inst_id = os.environ.get("AGENTRELIABILITY_INSTANCE_ID", "cloud_neon_prod")
        return {
            "instance_id": inst_id,
            "database_engine": "postgres",
            "database_name": db_name,
            "database_path": masked_url,
            "workspace_root": "cloud-hosted",
            "environment": os.environ.get("AGENTRELIABILITY_ENV", "production"),
        }
    else:
        db = database.db_path()
        backend_dir = os.path.dirname(db)
        root = os.path.dirname(backend_dir)
        inst_id = os.environ.get("AGENTRELIABILITY_INSTANCE_ID")
        if not inst_id:
            import hashlib
            inst_id = f"ar_inst_{hashlib.sha256(root.encode('utf-8')).hexdigest()[:12]}"
        return {
            "instance_id": inst_id,
            "database_engine": "sqlite",
            "database_name": os.path.basename(db),
            "database_path": db,
            "workspace_root": root,
            "environment": os.environ.get("AGENTRELIABILITY_ENV", "development"),
        }


@app.get("/api/health")
def health():
    """Health & readiness probe verifying database connectivity and instance identity."""
    identity = get_instance_identity()
    headers = {
        "X-Service": "agentreliability-backend",
        "X-Service-Version": "0.1.0",
        "X-Instance-ID": identity["instance_id"],
    }
    try:
        with database.connect() as conn:
            conn.execute("SELECT 1")
        return JSONResponse(
            content={"status": "ok"},
            headers=headers,
        )
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": str(exc)},
            headers=headers,
        )


@app.get("/api/v1/system/info")
def system_info():
    """Return backend service metadata, version, instance identity, and multi-tenant capabilities."""
    identity = get_instance_identity()
    return {
        "service": "agentreliability-backend",
        "version": "0.1.0",
        "status": "ok",
        "instance_id": identity["instance_id"],
        "database_engine": identity["database_engine"],
        "database_name": identity["database_name"],
        "database_path": identity["database_path"],
        "workspace_root": identity["workspace_root"],
        "environment": identity["environment"],
        "multi_tenant": True,
        "auth_methods": ["api_key", "session_cookie"],
    }


@app.post("/api/executions", status_code=201)
async def upload_execution(
    request: Request,
    file: UploadFile = File(...),
    project: dict = Depends(get_authorized_project),
):
    check_csrf(request)
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 5 MB).")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "File is not valid JSON.")
    try:
        log = AgentLog.model_validate(payload)
    except ValidationError as e:
        problems = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
        raise HTTPException(422, {"message": "Log format is invalid.", "problems": problems})

    analysis = analyze(log)
    exec_id = database.save_execution(log.model_dump(), analysis, project_id=project["id"])
    return database.get_execution(exec_id, project_id=project["id"])


@app.get("/api/executions")
def list_executions(project: dict = Depends(get_authorized_project)):
    return database.list_executions(project_id=project["id"])


@app.get("/api/executions/{exec_id}")
def get_execution(execution: dict = Depends(require_owned_execution)):
    return execution


@app.get("/api/executions/{exec_id}/analysis")
def get_execution_analysis(execution: dict = Depends(require_owned_execution)):
    return {
        "id": execution["id"],
        "agent_name": execution["agent_name"],
        "status": execution["status"],
        "findings": execution.get("findings", []),
    }


@app.delete("/api/executions/{exec_id}", status_code=204)
def delete_execution(request: Request, execution: dict = Depends(require_owned_execution)):
    check_csrf(request)
    with database.connect() as conn:
        conn.execute("DELETE FROM executions WHERE id = ?", (execution["id"],))



# ---------------------------------------------------------------------------
# Phase 2: test cases, replay, results
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Turn Pydantic errors into the same friendly shape the frontend already understands."""
    problems = [
        f"{'.'.join(str(p) for p in err['loc'] if p != 'body')}: {err['msg']}" for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": {"message": "Request is invalid.", "problems": problems}})


def _require_case(case_id: int) -> dict:
    case = test_store.get_case(case_id)
    if case is None:
        raise HTTPException(404, "Test case not found.")
    return case


def _run_and_save(case: dict) -> dict:
    result = run_test(case)
    run_id = test_store.save_run(case, result)
    return test_store.get_run(run_id)


@app.post("/api/tests", status_code=201)
def create_test(
    body: TestCaseIn,
    request: Request,
    project: dict = Depends(get_authorized_project),
):
    check_csrf(request)
    case_id = test_store.create_case(body.model_dump(), project_id=project["id"])
    return test_store.get_case(case_id, project_id=project["id"])


@app.post("/api/tests/from-execution/{exec_id}", status_code=201)
def create_test_from_execution(
    request: Request,
    execution: dict = Depends(require_owned_execution),
    body: FromExecutionIn | None = None,
):
    check_csrf(request)
    data = generate_from_execution(execution, body.name if body else None)
    proj_id = execution.get("project_id", 1)
    case_id = test_store.create_case(data, source_execution_id=execution["id"], project_id=proj_id)
    return test_store.get_case(case_id, project_id=proj_id)


@app.get("/api/tests")
def list_tests(project: dict = Depends(get_authorized_project)):
    return test_store.list_cases(project_id=project["id"])


@app.post("/api/tests/run-all")
def run_all_tests(
    request: Request,
    project: dict = Depends(get_authorized_project),
):
    check_csrf(request)
    pid = project["id"]
    cases = test_store.list_cases(project_id=pid)
    runs = []
    for c in cases:
        full_case = test_store.get_case(c["id"], project_id=pid)
        if full_case:
            res = run_test(full_case)
            run_id = test_store.save_run(full_case, res, project_id=pid)
            runs.append(test_store.get_run(run_id, project_id=pid))
    passed = sum(1 for r in runs if r["status"] == "passed")
    return {"total": len(runs), "passed": passed, "failed": len(runs) - passed, "runs": runs}


@app.get("/api/tests/{case_id}")
def get_test(case: dict = Depends(require_owned_test_case)):
    return case


@app.put("/api/tests/{case_id}")
def update_test(
    request: Request,
    body: TestCaseIn,
    case: dict = Depends(require_owned_test_case),
):
    check_csrf(request)
    test_store.update_case(case["id"], body.model_dump(), project_id=case["project_id"])
    return test_store.get_case(case["id"], project_id=case["project_id"])


@app.delete("/api/tests/{case_id}", status_code=204)
def delete_test(
    request: Request,
    case: dict = Depends(require_owned_test_case),
):
    check_csrf(request)
    test_store.delete_case(case["id"], project_id=case["project_id"])


@app.post("/api/tests/{case_id}/run", status_code=201)
def run_one_test(
    request: Request,
    case: dict = Depends(require_owned_test_case),
):
    check_csrf(request)
    res = run_test(case)
    proj_id = case.get("project_id", 1)
    run_id = test_store.save_run(case, res, project_id=proj_id)
    return test_store.get_run(run_id, project_id=proj_id)


@app.get("/api/test-runs")
def list_test_runs(
    test_id: int | None = None,
    project: dict = Depends(get_authorized_project),
):
    if test_id is not None:
        case = test_store.get_case(test_id, project_id=project["id"])
        if not case:
            raise HTTPException(404, "Test case not found.")
    return test_store.list_runs(test_id=test_id, project_id=project["id"])


@app.get("/api/test-runs/{run_id}")
def get_test_run(run: dict = Depends(require_owned_test_run)):
    return run


@app.get("/api/overview")
def overview(project: dict = Depends(get_authorized_project)):
    pid = project["id"]
    cases = test_store.list_cases(project_id=pid)
    passed = sum(1 for c in cases if c["last_run_status"] == "passed")
    failed = sum(1 for c in cases if c["last_run_status"] == "failed")
    json_executions = database.list_executions(project_id=pid)
    live_traces_res = trace_store.list_executions(project_id=pid, limit=1)
    live_traces_total = live_traces_res.get("total", 0) if isinstance(live_traces_res, dict) else len(live_traces_res)
    live_traces_failed_res = trace_store.list_executions(project_id=pid, status="failed", limit=1)
    live_traces_failed = live_traces_failed_res.get("total", 0) if isinstance(live_traces_failed_res, dict) else len(live_traces_failed_res)

    return {
        "executions": {
            "total": len(json_executions),
            "failed": sum(1 for e in json_executions if e["status"] == "failed"),
            "uploaded_logs": len(json_executions),
            "live_traces": live_traces_total,
        },
        "live_traces": {
            "total": live_traces_total,
            "failed": live_traces_failed,
        },
        "tests": {"total": len(cases), "passed": passed, "failed": failed,
                  "not_run": len(cases) - passed - failed},
        "recent_runs": test_store.list_runs(project_id=pid, limit=5),
    }

