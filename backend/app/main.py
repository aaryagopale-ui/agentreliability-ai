"""FastAPI app. Run: uvicorn app.main:app --reload --port 8000"""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from . import ci_store, database, test_store, trace_store
from .ci_api import router as ci_router
from .detector import analyze
from .replay import run_test
from .schemas import AgentLog
from .test_schemas import FromExecutionIn, TestCaseIn
from .testgen import generate_from_execution
from .traces_api import router as traces_router

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    test_store.init_tables()
    trace_store.init_tables()
    ci_store.init_tables()
    yield


app = FastAPI(title="AgentReliability AI", lifespan=lifespan)

# Allow the Vite dev server to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(traces_router)
app.include_router(ci_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/executions", status_code=201)
async def upload_execution(file: UploadFile = File(...)):
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
    exec_id = database.save_execution(log.model_dump(), analysis)
    return database.get_execution(exec_id)


@app.get("/api/executions")
def list_executions():
    return database.list_executions()


@app.get("/api/executions/{exec_id}")
def get_execution(exec_id: int):
    data = database.get_execution(exec_id)
    if data is None:
        raise HTTPException(404, "Execution not found.")
    return data



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
def create_test(body: TestCaseIn):
    case_id = test_store.create_case(body.model_dump())
    return test_store.get_case(case_id)


@app.post("/api/tests/from-execution/{exec_id}", status_code=201)
def create_test_from_execution(exec_id: int, body: FromExecutionIn | None = None):
    execution = database.get_execution(exec_id)
    if execution is None:
        raise HTTPException(404, "Execution not found.")
    data = generate_from_execution(execution, body.name if body else None)
    case_id = test_store.create_case(data, source_execution_id=exec_id)
    return test_store.get_case(case_id)


@app.get("/api/tests")
def list_tests():
    return test_store.list_cases()


@app.post("/api/tests/run-all")
def run_all_tests():
    runs = [_run_and_save(test_store.get_case(c["id"])) for c in test_store.list_cases()]
    passed = sum(1 for r in runs if r["status"] == "passed")
    return {"total": len(runs), "passed": passed, "failed": len(runs) - passed, "runs": runs}


@app.get("/api/tests/{case_id}")
def get_test(case_id: int):
    return _require_case(case_id)


@app.put("/api/tests/{case_id}")
def update_test(case_id: int, body: TestCaseIn):
    _require_case(case_id)
    test_store.update_case(case_id, body.model_dump())
    return test_store.get_case(case_id)


@app.delete("/api/tests/{case_id}", status_code=204)
def delete_test(case_id: int):
    _require_case(case_id)
    test_store.delete_case(case_id)


@app.post("/api/tests/{case_id}/run", status_code=201)
def run_one_test(case_id: int):
    return _run_and_save(_require_case(case_id))


@app.get("/api/test-runs")
def list_test_runs(test_id: int | None = None):
    return test_store.list_runs(test_id)


@app.get("/api/test-runs/{run_id}")
def get_test_run(run_id: int):
    run = test_store.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Test run not found.")
    return run


@app.get("/api/overview")
def overview():
    cases = test_store.list_cases()
    passed = sum(1 for c in cases if c["last_run_status"] == "passed")
    failed = sum(1 for c in cases if c["last_run_status"] == "failed")
    executions = database.list_executions()
    return {
        "executions": {
            "total": len(executions),
            "failed": sum(1 for e in executions if e["status"] == "failed"),
        },
        "tests": {"total": len(cases), "passed": passed, "failed": failed,
                  "not_run": len(cases) - passed - failed},
        "recent_runs": test_store.list_runs(limit=5),
    }


@app.get("/api/failure-analysis")
def failure_analysis():
    latest = test_store.latest_runs_per_test()
    kinds: dict[str, int] = {}
    failing = []
    for run in latest:
        if run["status"] == "failed":
            failing.append(run)
            for m in run["mismatches"]:
                kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    return {
        "execution_findings": test_store.execution_finding_counts(),
        "replay_mismatches": kinds,
        "failing_runs": failing,
    }
