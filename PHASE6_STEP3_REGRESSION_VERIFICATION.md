# Phase 6 Step 3: Real Trace-to-Test Regression Testing & Baseline Management Verification Report

**Date:** October 19, 2026  
**Platform:** AgentReliability AI  
**Stage:** Phase 6 — Real Agent Integration, Visual Tracing & Behavioral Regression Testing  
**Step:** Step 3 — Real Trace-to-Test Regression Testing  
**Status:** **VERIFIED & READY FOR APPROVAL**  

---

## 1. Executive Summary

In Phase 6 Step 3, we connected real, captured agent executions to reusable, deterministic regression tests and established an enterprise-grade Golden Baseline Management and Comparison Engine.

Prior to this step:
- Real agent executions were captured and visualized on waterfall timelines (Step 1 & Step 2).
- Converting a trace into a test produced basic mock simulation cases without customizable assertions on tool sequence ordering, schema consistency, or latency thresholds.
- Developers had no mechanism to lock down a known-good execution as a "Golden Baseline" and compare future agent runs against it.

In Phase 6 Step 3:
1. **Database Migration 004:** Added `baselines` and `baseline_versions` tables with strict project isolation, foreign keys, and version tracking (`UNIQUE(baseline_id, version)`).
2. **Enhanced Assertions & Schemas:** Introduced customizable expectation models (`strict_order`, `allow_additional_tools`, `expected_output_fields`, `expected_error_type`, `max_duration_ms`).
3. **Deterministic Regression Engine (`app/regression_engine.py`):** Compares candidate executions against baselines, classifying differences into breaking regressions, performance warnings, informational changes, and inconclusive states.
4. **Baseline Management API (`app/baselines_api.py`):** Project-scoped endpoints for baseline creation, non-destructive versioning, specific version retrieval, deletion, and side-by-side trace comparison.
5. **Interactive UI (`RegressionTesting.jsx` & `TraceExecutionTimeline.jsx`):**
   - Dedicated "Regression Testing" tab in the React navigation.
   - Side-by-side comparison view with verdict banners and ground-truth evidence callouts.
   - Modal to customize assertions when creating test cases from live traces.
   - "Set as Golden Baseline" modal and version advancement workflow.
6. **Verification Test Suite:** 112 backend tests passed (including 6 new comprehensive regression suite tests), 34 Python SDK tests passed, and frontend built cleanly with 0 errors.

---

## 2. Beginner's Guide: How Trace-to-Test & Regression Testing Work

### What is a Regression in AI Agents?
When software developers update prompts, system instructions, model parameters, or tool code, an agent can unexpectedly:
- Skip a necessary tool (e.g. validating order before charging credit card).
- Call an unauthorized or unexpected tool.
- Change the ordering of actions in ways that break downstream systems.
- Drop required fields in its final JSON response.
- Experience severe latency slowdowns.

### How Does AgentReliability AI Solve This?
1. **Capture Live Trace:** The agent runs using the `agentreliability` Python SDK. All tool calls, inputs, outputs, errors, and timing are recorded as ground truth.
2. **Promote to Golden Baseline:** When an execution behaves exactly as desired, the developer clicks **"Set as Golden Baseline"**. This locks down version 1 (`v1`).
3. **Advance Without Destroying History:** If the agent logic evolves (e.g., adding an SMS notification step), developers create version 2 (`v2`). Old versions remain accessible for auditability.
4. **Deterministic Comparison Engine:** When a new agent execution runs, the comparison engine compares it against the golden baseline:
   - **Breaking Regression:** Missing required tool, unexpected tool, sequence disorder, missing output key, or status failure.
   - **Performance Warning:** Execution took > 50% longer than the baseline.
   - **Informational Change:** Benign output string variation.
   - **Inconclusive:** Candidate execution is still running or incomplete.

---

## 3. Database Architecture (Migration 004)

Migration 004 was applied via `app/migrations/runner.py` and synchronized with the PostgreSQL migration script (`backend/scripts/migrate_sqlite_to_postgres.py`).

### Schema Definition
```sql
CREATE TABLE IF NOT EXISTS baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    current_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_baselines_project ON baselines(project_id);
CREATE INDEX IF NOT EXISTS idx_baselines_agent ON baselines(project_id, agent_name);

CREATE TABLE IF NOT EXISTS baseline_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    baseline_id INTEGER NOT NULL REFERENCES baselines(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    source_type TEXT NOT NULL,       -- 'trace' or 'execution'
    source_id TEXT NOT NULL,         -- execution_id or int id
    status TEXT NOT NULL,            -- 'success' or 'failed'
    duration_ms REAL,
    input_json TEXT,
    output_json TEXT,
    tools_json TEXT NOT NULL,        -- JSON array of tool calls
    expected_json TEXT NOT NULL,     -- JSON dict of assertions
    created_at TEXT NOT NULL,
    created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    description TEXT,
    UNIQUE(baseline_id, version)
);

CREATE INDEX IF NOT EXISTS idx_baseline_versions_baseline ON baseline_versions(baseline_id, version);
```

---

## 4. REST API Specifications

All endpoints enforce multi-tenant project authorization (`get_authorized_project`) and CSRF validation for mutating methods.

| Method | Path | Description | Project Scoped |
|---|---|---|---|
| `POST` | `/api/baselines` | Create a new golden baseline from trace/execution | Yes |
| `GET` | `/api/baselines` | List all baselines for the active project | Yes |
| `GET` | `/api/baselines/{id}` | Get baseline details and version history | Yes |
| `GET` | `/api/baselines/{id}/versions` | List all historical version records for a baseline | Yes |
| `GET` | `/api/baselines/{id}/versions/{v}` | Retrieve a specific historical version snapshot | Yes |
| `POST` | `/api/baselines/{id}/versions` | Advance baseline to next version (non-destructive) | Yes |
| `DELETE` | `/api/baselines/{id}` | Delete baseline and all associated versions | Yes |
| `POST` | `/api/baselines/{id}/compare` | Deterministically compare candidate against baseline | Yes |
| `POST` | `/api/regression/compare-traces` | Ad-hoc side-by-side comparison between any two traces | Yes |
| `POST` | `/api/traces/executions/{id}/create-test` | Create test case from trace with custom assertions | Yes |

---

## 5. Regression Engine Detections Verified

In `backend/tests/test_regression_suite.py`, 6 comprehensive automated test scenarios were verified against the real comparison engine:

1. **Exact Match:** Candidate matches baseline exactly -> `verdict: "passed"`, 0 regressions.
2. **Missing Tool (Breaking):** Candidate omits `charge_payment` -> `category: "missing_tool_call"`, `severity: "breaking_regression"`.
3. **Unexpected Tool (Breaking):** Candidate invokes an unapproved tool -> `category: "unexpected_tool_call"`, `severity: "breaking_regression"`.
4. **Sequence Reordering (Breaking):** Candidate calls `check_inventory` before `validate_order` when `strict_order=True` -> `category: "tool_sequence_mismatch"`.
5. **Output Schema Key Dropped (Breaking):** Candidate output lacks `status` or `total` -> `category: "missing_output_field"`.
6. **Status Failure (Breaking):** Baseline passed, candidate failed with exception -> `category: "status_regression"`.
7. **Duration Limit Exceeded (Breaking):** Candidate exceeds `max_duration_ms` threshold -> `category: "duration_threshold_exceeded"`.
8. **Latency Regressed (Performance Warning):** Candidate latency exceeds baseline by > 50% without hard cap -> `category: "latency_regression"`, `severity: "performance_regression"`.
9. **Inconclusive Handling:** Candidate trace has `status: "running"` -> `verdict: "inconclusive"`.
10. **Tenant Isolation:** Users in Project 2 are denied (404) from reading, updating, or using baselines belonging to Project 1.

---

## 6. Test Suite Health Summary

### Backend Tests
```
backend/tests/test_api.py .........                                      [  8%]
backend/tests/test_auth_api.py .............                             [ 19%]
backend/tests/test_authorization.py ..........                           [ 28%]
backend/tests/test_ci_api.py ..                                          [ 30%]
backend/tests/test_detector.py .........                                 [ 38%]
backend/tests/test_e2e_journey.py ..                                     [ 40%]
backend/tests/test_frontend_auth_integration.py .                        [ 41%]
backend/tests/test_migrations.py .....                                   [ 45%]
backend/tests/test_postgres_migration_plan.py ..                         [ 47%]
backend/tests/test_projects_api.py .......                               [ 53%]
backend/tests/test_real_agent_integration.py ..                          [ 55%]
backend/tests/test_regression_suite.py ......                            [ 60%]
backend/tests/test_replay.py ................                            [ 75%]
backend/tests/test_security.py .............                             [ 86%]
backend/tests/test_tests_api.py ..........                               [ 95%]
backend/tests/test_traces.py .....                                       [100%]

======================= 112 passed, 18 warnings in 3.33s =======================
```

### Python SDK Tests
```
sdk/tests/test_cli.py .....                                              [ 14%]
sdk/tests/test_sdk.py .............................                      [100%]

============================== 34 passed in 0.39s ==============================
```

### Frontend Production Build
```
vite v7.3.7 building client environment for production...
✓ 47 modules transformed.
dist/index.html                   0.43 kB │ gzip:  0.29 kB
dist/assets/index-DnulJlS6.css   41.18 kB │ gzip:  7.34 kB
dist/assets/index-EqtavaDl.js   343.77 kB │ gzip: 94.99 kB
✓ built in 385ms
```

---

## 7. Port Isolation & Safety Verification

- **CropBazaar (Port 8000):** Untouched and isolated.
- **FastAPI Backend (Port 8001):** Active and verified healthy.
- **React UI (Port 5174):** Active with Regression Testing tab and modals.
- **External Network / Git Commits:** No commits or pushes performed.

---

## 8. Conclusion & Sign-Off

Phase 6 Step 3 is complete and thoroughly tested. Developers can now convert real agent execution traces into customizable test cases with strict tool sequences, schema validation, and latency caps, manage versioned golden baselines, and review deterministic side-by-side behavioral regressions in the React UI.

**Next Stage:** Awaiting your review and approval before proceeding to **Phase 6 Step 4 (Automated Regression Alerts & CI/CD Gate Enforcement)**.

