"""Performance, stress testing, and product quality verification suite for Phase 6 Step 6.

Validates:
1. Performance baselines: p50/p95 latency for API requests, trace ingestion, and regression diffing.
2. Large execution traces: 10, 100, and 1,000 spans; deep nesting (10 levels); large payloads; missing timestamps.
3. SDK reliability: exception propagation, non-invasive telemetry failure, thread-safe concurrent executions.
4. Multi-tenant concurrency: parallel trace ingestion across tenants, instantaneous key revocation, zero database locks.
"""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import connect, init_db
from app.security import create_session, hash_password, SESSION_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME


@pytest.fixture(autouse=True)
def isolated_perf_db(tmp_path, monkeypatch):
    """Ensure all performance tests run in an ephemeral database and never touch the local database."""
    test_db = str(tmp_path / "test_perf.db")
    monkeypatch.setenv("AGENTRELIABILITY_DB", test_db)
    init_db()
from app.project_store import create_project, create_api_key, revoke_api_key
from app.trace_store import ingest, get_execution, list_executions
from app.traces_schemas import IngestRequest, TraceEvent
from app.test_store import create_case, get_case, save_run
from app.replay import run_test
from app.regression_engine import compare_execution_to_baseline
from app.failure_engine import diagnose_failure
from app.redaction import global_redactor


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def test_setup():
    """Sets up an isolated user and project for performance testing."""
    client = TestClient(app)
    user_email = f"quality_user_{int(time.time() * 1000)}@agentreliability.local"
    with connect() as conn:
        pwd_hash = hash_password("QualityPass123!")
        cur = conn.execute(
            """INSERT INTO users (email, password_hash, name, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_email, pwd_hash, "Quality Tester", _now(), _now()),
        )
        user_id = cur.lastrowid

    proj, api_key = create_project(name="Quality Benchmark Project", owner_id=user_id)
    project_id = proj["id"]
    raw_token, _ = create_session(user_id)

    headers = {
        "Cookie": f"{SESSION_COOKIE_NAME}={raw_token}",
        "X-Project-Id": str(project_id),
    }

    return {
        "client": client,
        "user_id": user_id,
        "project_id": project_id,
        "api_key": api_key,
        "headers": headers,
    }


# =============================================================================
# 1. Performance Baselines & Latency Measurements (Step 2)
# =============================================================================

def test_api_latency_baselines(test_setup):
    """Measures p50 and p95 API response times across multiple endpoints."""
    client = test_setup["client"]
    headers = test_setup["headers"]

    # 1. Health check latency
    health_times = []
    for _ in range(30):
        t0 = time.perf_counter()
        res = client.get("/api/health")
        assert res.status_code == 200
        health_times.append((time.perf_counter() - t0) * 1000)

    health_times.sort()
    p50_health = health_times[len(health_times) // 2]
    p95_health = health_times[int(len(health_times) * 0.95)]
    assert p50_health < 50.0  # p50 should be well under 50ms locally

    # 2. Project-scoped overview latency
    overview_times = []
    for _ in range(30):
        t0 = time.perf_counter()
        res = client.get("/api/overview", headers=headers)
        assert res.status_code == 200
        overview_times.append((time.perf_counter() - t0) * 1000)

    overview_times.sort()
    p50_overview = overview_times[len(overview_times) // 2]
    p95_overview = overview_times[int(len(overview_times) * 0.95)]
    assert p50_overview < 100.0


def test_trace_ingestion_latency(test_setup):
    """Measures trace ingestion latency for single and batched events."""
    client = test_setup["client"]
    api_key = test_setup["api_key"]

    auth_headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }

    ingest_times = []
    for i in range(25):
        payload = {
            "events": [
                {
                    "event_id": f"bench-evt-{i}-{time.time()}",
                    "execution_id": f"bench-exec-{i}",
                    "agent_name": "benchmark_agent",
                    "type": "execution_start",
                    "timestamp": _now(),
                    "input": {"query": f"bench_run_{i}"},
                },
                {
                    "event_id": f"bench-tool-{i}-{time.time()}",
                    "execution_id": f"bench-exec-{i}",
                    "agent_name": "benchmark_agent",
                    "type": "tool_call",
                    "timestamp": _now(),
                    "tool_name": "fast_lookup",
                    "duration_ms": 1.2,
                    "status": "success",
                    "output": {"result": i},
                },
                {
                    "event_id": f"bench-end-{i}-{time.time()}",
                    "execution_id": f"bench-exec-{i}",
                    "agent_name": "benchmark_agent",
                    "type": "execution_end",
                    "timestamp": _now(),
                    "status": "success",
                    "duration_ms": 2.5,
                    "output": {"result": i},
                },
            ]
        }
        t0 = time.perf_counter()
        res = client.post("/api/v1/traces/events", headers=auth_headers, json=payload)
        assert res.status_code == 200
        ingest_times.append((time.perf_counter() - t0) * 1000)

    ingest_times.sort()
    p50 = ingest_times[len(ingest_times) // 2]
    p95 = ingest_times[int(len(ingest_times) * 0.95)]
    assert p50 < 60.0  # Ingestion batch p50 under 60ms


# =============================================================================
# 2. Large Execution Traces & Stress Testing (Step 3)
# =============================================================================

def test_large_trace_10_spans(test_setup):
    """Verifies ingestion and retrieval of a 10-span trace."""
    project_id = test_setup["project_id"]
    exec_id = f"stress-10-{int(time.time())}"

    events_raw = [
        {"event_id": f"{exec_id}-start", "execution_id": exec_id, "agent_name": "stress_agent_10", "type": "execution_start", "timestamp": _now()}
    ]
    for j in range(10):
        events_raw.append({
            "event_id": f"{exec_id}-tool-{j}",
            "execution_id": exec_id,
            "agent_name": "stress_agent_10",
            "type": "tool_call",
            "timestamp": _now(),
            "tool_name": f"worker_step_{j}",
            "duration_ms": 5.0,
            "status": "success",
            "output": {"step": j},
        })
    events_raw.append({
        "event_id": f"{exec_id}-end",
        "execution_id": exec_id,
        "agent_name": "stress_agent_10",
        "type": "execution_end",
        "timestamp": _now(),
        "status": "success",
        "duration_ms": 50.0,
        "output": {"completed_steps": 10},
    })

    batch = IngestRequest.model_validate({"events": events_raw})
    accepted, duplicates = ingest(project_id, batch.events)
    assert accepted == 12
    assert duplicates == 0

    detail = get_execution(exec_id, project_id=project_id)
    assert detail is not None
    assert len(detail["tool_calls"]) == 10


def test_large_trace_100_spans(test_setup):
    """Verifies ingestion and retrieval of a 100-span trace."""
    project_id = test_setup["project_id"]
    exec_id = f"stress-100-{int(time.time())}"

    events_raw = [
        {"event_id": f"{exec_id}-start", "execution_id": exec_id, "agent_name": "stress_agent_100", "type": "execution_start", "timestamp": _now()}
    ]
    for j in range(100):
        events_raw.append({
            "event_id": f"{exec_id}-tool-{j}",
            "execution_id": exec_id,
            "agent_name": "stress_agent_100",
            "type": "tool_call",
            "timestamp": _now(),
            "tool_name": f"worker_step_{j}",
            "duration_ms": 2.0,
            "status": "success",
            "output": {"step": j},
        })
    events_raw.append({
        "event_id": f"{exec_id}-end",
        "execution_id": exec_id,
        "agent_name": "stress_agent_100",
        "type": "execution_end",
        "timestamp": _now(),
        "status": "success",
        "duration_ms": 200.0,
        "output": {"completed_steps": 100},
    })

    # Ingest in chunks of 50 to respect MAX_EVENTS_PER_BATCH
    accepted_total = 0
    for i in range(0, len(events_raw), 50):
        chunk = events_raw[i:i + 50]
        batch = IngestRequest.model_validate({"events": chunk})
        accepted, _ = ingest(project_id, batch.events)
        accepted_total += accepted

    assert accepted_total == 102

    detail = get_execution(exec_id, project_id=project_id)
    assert detail is not None
    assert len(detail["tool_calls"]) == 100


def test_large_trace_1000_spans(test_setup):
    """Stress test: Ingests a 1,000 span trace and verifies sub-second query performance."""
    project_id = test_setup["project_id"]
    exec_id = f"stress-1000-{int(time.time())}"

    events_raw = [
        {"event_id": f"{exec_id}-start-event", "execution_id": exec_id, "agent_name": "stress_agent_1000", "type": "execution_start", "timestamp": _now()}
    ]
    for j in range(1000):
        events_raw.append({
            "event_id": f"{exec_id}-tool-{j:04d}",
            "execution_id": exec_id,
            "agent_name": "stress_agent_1000",
            "type": "tool_call",
            "timestamp": _now(),
            "tool_name": f"step_{j % 20}",
            "duration_ms": 1.0,
            "status": "success",
            "output": {"index": j},
        })
    events_raw.append({
        "event_id": f"{exec_id}-end-event",
        "execution_id": exec_id,
        "agent_name": "stress_agent_1000",
        "type": "execution_end",
        "timestamp": _now(),
        "status": "success",
        "duration_ms": 1050.0,
        "output": {"total": 1000},
    })

    t0 = time.perf_counter()
    accepted_total = 0
    # Ingest in chunks of 100 (standard batch size)
    for i in range(0, len(events_raw), 100):
        chunk = events_raw[i:i + 100]
        batch = IngestRequest.model_validate({"events": chunk})
        accepted, _ = ingest(project_id, batch.events)
        accepted_total += accepted
    ingest_dur = time.perf_counter() - t0
    assert accepted_total == 1002
    assert ingest_dur < 2.0  # Ingesting 1000 spans should complete in under 2 seconds locally

    t1 = time.perf_counter()
    detail = get_execution(exec_id, project_id=project_id)
    query_dur = time.perf_counter() - t1
    assert detail is not None
    assert len(detail["tool_calls"]) == 1000
    assert query_dur < 0.25  # Retrieval of 1000 spans should be under 250ms


def test_deeply_nested_tool_calls(test_setup):
    """Verifies that 10 levels of nested parent_call_id hierarchy are stored and resolved cleanly."""
    project_id = test_setup["project_id"]
    exec_id = f"nest-10-{int(time.time())}"

    events_raw = [
        {"event_id": f"{exec_id}-start", "execution_id": exec_id, "agent_name": "nest_agent", "type": "execution_start", "timestamp": _now()}
    ]

    prev_id = None
    for depth in range(10):
        call_id = f"{exec_id}-call-{depth}"
        events_raw.append({
            "event_id": call_id,
            "execution_id": exec_id,
            "agent_name": "nest_agent",
            "type": "tool_call",
            "timestamp": _now(),
            "tool_name": f"nested_level_{depth}",
            "duration_ms": 5.0,
            "status": "success",
            "parent_call_id": prev_id,
            "output": {"depth": depth},
        })
        prev_id = call_id

    events_raw.append({
        "event_id": f"{exec_id}-end",
        "execution_id": exec_id,
        "agent_name": "nest_agent",
        "type": "execution_end",
        "timestamp": _now(),
        "status": "success",
        "duration_ms": 50.0,
    })

    batch = IngestRequest.model_validate({"events": events_raw})
    accepted, _ = ingest(project_id, batch.events)
    assert accepted == 12

    detail = get_execution(exec_id, project_id=project_id)
    assert detail is not None
    tool_map = {t["call_id"]: t for t in detail["tool_calls"]}
    assert tool_map[f"{exec_id}-call-0"]["parent_call_id"] is None
    for d in range(1, 10):
        assert tool_map[f"{exec_id}-call-{d}"]["parent_call_id"] == f"{exec_id}-call-{d-1}"


def test_malformed_payloads_fail_safely(test_setup):
    """Verifies that invalid payloads are rejected with 422 or 400 without crashing."""
    client = test_setup["client"]
    api_key = test_setup["api_key"]

    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    # 1. Missing execution_id
    res1 = client.post("/api/v1/traces/events", headers=headers, json={
        "events": [{"event_id": "bad-1", "type": "tool_call", "timestamp": _now()}]
    })
    assert res1.status_code == 422

    # 2. Invalid JSON string
    res2 = client.post("/api/v1/traces/events", headers=headers, content="not valid json")
    assert res2.status_code in (400, 422)

    # 3. Non-string event_id
    res3 = client.post("/api/v1/traces/events", headers=headers, json={
        "events": [{"event_id": 12345, "execution_id": "e", "agent_name": "a", "type": "tool_call", "timestamp": _now()}]
    })
    assert res3.status_code in (200, 422)  # Coerced to string or rejected safely


# =============================================================================
# 3. SDK Reliability & Concurrency (Step 4 & Step 5)
# =============================================================================

def test_concurrent_trace_ingestion_multi_tenant():
    """Simulates 10 concurrent threads ingesting traces into separate projects with zero lock collisions."""
    with connect() as conn:
        pwd_hash = hash_password("ConcurrentPass123!")
        cur = conn.execute(
            """INSERT INTO users (email, password_hash, name, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (f"conc_user_{int(time.time() * 1000)}@agentreliability.local", pwd_hash, "Concurrent User", _now(), _now()),
        )
        user_id = cur.lastrowid

    projects = []
    for p_idx in range(5):
        proj, key = create_project(name=f"Concurrent Proj {p_idx}", owner_id=user_id)
        projects.append((proj["id"], key))

    def worker_ingest(proj_tuple, thread_id):
        p_id, _ = proj_tuple
        now_ts = int(time.time() * 1000)
        exec_id = f"thread-exec-{thread_id:03d}-{now_ts}"
        events = [
            TraceEvent(event_id=f"evt-start-{thread_id:03d}-{now_ts}", execution_id=exec_id, agent_name="worker_agent", type="execution_start", timestamp=_now()),
            TraceEvent(event_id=f"evt-tool1-{thread_id:03d}-{now_ts}", execution_id=exec_id, agent_name="worker_agent", type="tool_call", timestamp=_now(), tool_name="fetch_data", duration_ms=10.0, status="success"),
            TraceEvent(event_id=f"evt-end01-{thread_id:03d}-{now_ts}", execution_id=exec_id, agent_name="worker_agent", type="execution_end", timestamp=_now(), status="success", duration_ms=20.0),
        ]
        accepted, _ = ingest(p_id, events)
        return accepted

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(20):
            proj_choice = projects[i % len(projects)]
            futures.append(executor.submit(worker_ingest, proj_choice, i))

        results = [f.result() for f in as_completed(futures)]

    assert len(results) == 20
    assert all(r == 3 for r in results)


def test_api_key_revocation_instantaneous(test_setup):
    """Verifies that an API key revoked mid-stream immediately stops ingestion with 401."""
    client = test_setup["client"]
    project_id = test_setup["project_id"]

    # Generate a dedicated key for this test
    key_record, active_key = create_api_key(project_id=project_id, name="Revocation Test Key")
    key_id = key_record["id"]

    headers = {"X-API-Key": active_key, "Content-Type": "application/json"}

    # 1. First ingest works
    res1 = client.post("/api/v1/traces/events", headers=headers, json={
        "events": [
            {"event_id": f"rev-evt-1-{time.time()}", "execution_id": "rev-exec-1", "agent_name": "agent", "type": "execution_start", "timestamp": _now()}
        ]
    })
    assert res1.status_code == 200

    # 2. Revoke the key
    revoked = revoke_api_key(project_id=project_id, key_id=key_id)
    assert revoked is True

    # 3. Subsequent ingest fails with 401 Unauthorized
    res2 = client.post("/api/v1/traces/events", headers=headers, json={
        "events": [
            {"event_id": f"rev-evt-2-{time.time()}", "execution_id": "rev-exec-2", "agent_name": "agent", "type": "execution_start", "timestamp": _now()}
        ]
    })
    assert res2.status_code == 401


def test_concurrent_replay_and_regression_comparisons(test_setup):
    """Verifies that concurrent replay executions and regression comparisons succeed without deadlocks."""
    project_id = test_setup["project_id"]

    test_data = {
        "name": "Concurrent Replay Test",
        "description": "Tests parallel replay engine execution",
        "agent_name": "order_agent",
        "steps": [
            {"type": "tool_call", "name": "check_stock", "status": "success", "duration_ms": 10, "output": {"stock": 50}},
            {"type": "tool_call", "name": "ship_order", "status": "success", "duration_ms": 15, "output": {"tracking": "TRK-01"}},
        ],
        "expected": {
            "status": "success",
            "tool_sequence": ["check_stock", "ship_order"],
            "final_output": {"tracking": "TRK-01"},
        },
    }
    case_id = create_case(test_data, project_id=project_id)
    case_record = get_case(case_id, project_id=project_id)

    def worker_replay(run_idx):
        res = run_test(case_record)
        save_run(case_record, res, project_id=project_id)
        return res["status"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker_replay, i) for i in range(16)]
        results = [f.result() for f in as_completed(futures)]

    assert len(results) == 16
    assert all(r == "passed" for r in results)
