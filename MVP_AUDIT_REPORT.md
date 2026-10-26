# AgentReliability AI — MVP Comprehensive System Audit Report

**Date:** October 19, 2026  
**Auditor:** Senior Infrastructure Engineer, Security Architect & Developer Experience Lead  
**Scope:** Frontend (React/Vite), Backend (FastAPI/SQLite), Python SDK (`agentreliability`), CLI, Integrations, and Test Infrastructure.

---

## 1. System Architecture Map

```
AgentReliability AI Stack
├── Frontend (React 19, Vite, Tailwind CSS, Port 5174)
│   ├── Pages: Overview, GettingStarted, LiveMonitoring, RegressionTesting, CITesting,
│   │          Executions, TestCases, Replay, FailureAnalysis, History, ApiKeys
│   ├── Auth: Login, Register, ForgotPassword, ResetPassword
│   ├── Components: ProjectSwitcher, TraceExecutionTimeline, UI primitives
│   └── API Client: frontend/src/api.js (Centralized, Cookie + CSRF + X-Project-Id)
│
├── Backend (FastAPI, SQLite, Port 8001)
│   ├── Core Routers:
│   │   ├── auth_api (/api/auth) - Scrypt, Sessions, Anti-enumeration, CSRF
│   │   ├── projects_api (/api/projects) - Multi-tenant isolation, Project API keys
│   │   ├── traces_api (/api/traces, /api/v1/traces) - Live trace ingestion & query
│   │   ├── baselines_api (/api/baselines, /api/regression) - Baselines & regression diffs
│   │   ├── failure_api (/api/failure-analysis) - Deterministic heuristics + local AI
│   │   ├── ci_api (/api/ci, /api/v1/ci) - Ingestion & reporting for GitHub Actions
│   │   └── main.py (/api/executions, /api/tests, /api/test-runs, /api/overview)
│   ├── Engines & Stores:
│   │   ├── trace_store.py, database.py, test_store.py, baseline_store.py, ci_store.py
│   │   ├── replay.py (Deterministic test runner & simulation)
│   │   ├── regression_engine.py (Trace-to-trace / Baseline comparison)
│   │   ├── failure_engine.py (Root-cause classification & evidence collection)
│   │   ├── local_ai.py (Ollama proxy with fallback)
│   │   └── redaction.py (Regex & key pattern masking)
│   └── Database: backend/agentreliability.db (SQLite with WAL mode)
│
├── Python SDK & CLI (`agentreliability`)
│   ├── SDK Core: monitor.py (AgentMonitor, decorators @trace_agent, @trace_tool)
│   ├── Redaction: redaction.py (client-side secret masking)
│   ├── Transport: transport.py (background thread batching & HTTP ingestion)
│   ├── CLI: cli.py (`agentreliability test`, `agentreliability status`)
│   └── Integrations:
│       ├── langchain.py (`AgentReliabilityCallbackHandler`)
│       ├── langgraph.py (`AgentReliabilityGraphHandler`)
│       └── crewai (experimental / simulated events)
│
└── Test Infrastructure
    ├── backend/tests/ (134 automated unit/integration tests)
    ├── sdk/tests/ (49 unit and framework tests)
    └── demo_project/agent-tests/ (offline test files for CLI and CI/CD)
```

---

## 2. Database Integrity & State Audit

A full database inspection of `backend/agentreliability.db` verified that all tables and existing project data remain intact:

| Table Name | Record Count | Integrity Status |
|---|---|---|
| `users` | 105 | ✅ Intact (Scrypt hashed passwords) |
| `projects` | 149 | ✅ Intact (Multi-tenant workspaces preserved) |
| `api_keys` | 164 | ✅ Intact (SHA-256 hashed keys, prefixes preserved) |
| `sessions` | 95 | ✅ Intact |
| `trace_executions` | 515 | ✅ Intact (All historical agent executions preserved) |
| `trace_tool_calls` | 10,590 | ✅ Intact (All parent/child tool spans preserved) |
| `trace_events` | 11,612 | ✅ Intact (Complete event logs preserved) |
| `executions` | 7 | ✅ Intact (Phase 1 uploaded JSON executions) |
| `test_cases` | 27 | ✅ Intact |
| `test_runs` | 192 | ✅ Intact |
| `baselines` | 5 | ✅ Intact |
| `baseline_versions` | 5 | ✅ Intact |
| `ci_runs` | 0 | ✅ Ready (Schema initialized) |
| `schema_migrations` | 4 | ✅ Intact (Migrations applied: 001 - 004) |

---

## 3. Verified Working Features

1. **Authentication & Multi-Tenant Project Isolation:**
   - User registration, login with HttpOnly session cookies, logout, password reset flow.
   - Project creation, switching, archival, and project-scoped API key lifecycle (creation, prefix display, deletion, rotation).
   - Strict project ownership enforcement (`get_authorized_project`, `require_owned_trace`, `require_owned_execution`, `require_owned_test_case`, `require_owned_test_run`).
2. **Live Agent Monitoring & Tracing:**
   - Ingestion endpoint `/api/v1/traces/events` with API-key verification, body size limits (1MB), and deduplication.
   - Non-blocking Python SDK background transport thread.
   - Capturing agent run metadata, duration, status, and input/output payloads.
   - Flat and nested tool call spans via contextvars (`parent_call_id`).
   - Secret redaction (passwords, tokens, API keys masked with `[REDACTED]`).
   - Live monitoring UI with auto-polling, agent filter, status filter, and time windows.
   - Visual execution timeline with status badges and duration metrics.
3. **Trace-to-Test & Deterministic Replay Engine:**
   - Conversion of real agent executions into reproducible test cases (`POST /api/traces/executions/{id}/create-test`).
   - Deterministic test replay (`run_test`) matching step sequence, tool names, inputs, and outputs against expectations without invoking live models.
   - Prominent disclaimer identifying deterministic simulation vs live agent execution.
4. **Golden Baselines & Behavioral Regression Engine:**
   - Baseline locking from real traces (`POST /api/baselines`) with versioning (`baseline_versions`).
   - Regression diffing engine categorizing status regressions, missing tool calls, tool sequence changes, duration thresholds, and output mismatches.
   - Baseline comparison UI with severity highlighting (`breaking_regression`, `performance_regression`, `informational_change`).
5. **Evidence-Based Failure Analysis:**
   - Deterministic root-cause heuristics classifying timeout, tool failures, network errors, and unexpected exceptions.
   - Preceding events analysis and failure evidence aggregation.
   - Local Ollama status detection with graceful fallback to deterministic diagnosis when offline.
6. **CI/CD Integration & CLI:**
   - CLI execution (`agentreliability test`) discovers JSON test files, runs deterministic assertions, generates GitHub Step Summary markdown, and outputs JSON reports.
   - Correct exit codes (0 for pass, 1 for fail/regression).
7. **Frontend Quality & Build:**
   - Clean production build via Vite (`npm run build` produces 48 modules in <700ms with zero errors).
   - Unified API layer with CSRF token double-submit and `X-Project-Id` headers.

---

## 4. Frontend API Call vs Backend Endpoint Audit

All 37 frontend API client methods in `frontend/src/api.js` were audited against backend route definitions:

| Frontend API Method | HTTP Method & Route | Backend Router / Handler | Status |
|---|---|---|---|
| `register` | `POST /api/auth/register` | `auth_api.py` | ✅ Exact Match |
| `login` | `POST /api/auth/login` | `auth_api.py` | ✅ Exact Match |
| `logout` | `POST /api/auth/logout` | `auth_api.py` | ✅ Exact Match |
| `getMe` | `GET /api/auth/me` | `auth_api.py` | ✅ Exact Match |
| `forgotPassword` | `POST /api/auth/forgot-password` | `auth_api.py` | ✅ Exact Match |
| `resetPassword` | `POST /api/auth/reset-password` | `auth_api.py` | ✅ Exact Match |
| `listProjects` | `GET /api/projects` | `projects_api.py` | ✅ Exact Match |
| `createProject` | `POST /api/projects` | `projects_api.py` | ✅ Exact Match |
| `getProject` | `GET /api/projects/{id}` | `projects_api.py` | ✅ Exact Match |
| `updateProject` | `PATCH /api/projects/{id}` | `projects_api.py` | ✅ Exact Match |
| `archiveProject` | `DELETE /api/projects/{id}` | `projects_api.py` | ✅ Exact Match |
| `claimProject` | `POST /api/projects/{id}/claim` | `projects_api.py` | ✅ Exact Match |
| `listProjectKeys` | `GET /api/projects/{id}/keys` | `projects_api.py` | ✅ Exact Match |
| `createProjectKey` | `POST /api/projects/{id}/keys` | `projects_api.py` | ✅ Exact Match |
| `revokeProjectKey` | `DELETE /api/projects/{id}/keys/{id}` | `projects_api.py` | ✅ Exact Match |
| `rotateProjectKey` | `POST /api/projects/{id}/keys/{id}/rotate` | `projects_api.py` | ✅ Exact Match |
| `listExecutions` | `GET /api/executions` | `main.py` | ✅ Exact Match |
| `getExecution` | `GET /api/executions/{id}` | `main.py` | ✅ Exact Match |
| `uploadLog` | `POST /api/executions` | `main.py` | ✅ Exact Match |
| `getOverview` | `GET /api/overview` | `main.py` | ✅ Exact Match |
| `listTests` | `GET /api/tests` | `main.py` | ✅ Exact Match |
| `getTest` | `GET /api/tests/{id}` | `main.py` | ✅ Exact Match |
| `createTest` | `POST /api/tests` | `main.py` | ✅ Exact Match |
| `updateTest` | `PUT /api/tests/{id}` | `main.py` | ✅ Exact Match |
| `deleteTest` | `DELETE /api/tests/{id}` | `main.py` | ✅ Exact Match |
| `runTest` | `POST /api/tests/{id}/run` | `main.py` | ✅ Exact Match |
| `runAllTests` | `POST /api/tests/run-all` | `main.py` | ✅ Exact Match |
| `listRuns` | `GET /api/test-runs` | `main.py` | ✅ Exact Match |
| `getRun` | `GET /api/test-runs/{id}` | `main.py` | ✅ Exact Match |
| `listTraceExecutions` | `GET /api/traces/executions` | `traces_api.py` | ✅ Exact Match |
| `getTraceExecution` | `GET /api/traces/executions/{id}` | `traces_api.py` | ✅ Exact Match |
| `listTraceAgents` | `GET /api/traces/agents` | `traces_api.py` | ✅ Exact Match |
| `createTestFromTrace`| `POST /api/traces/executions/{id}/create-test` | `traces_api.py` | ✅ Exact Match |
| `listBaselines` | `GET /api/baselines` | `baselines_api.py` | ✅ Exact Match |
| `getBaseline` | `GET /api/baselines/{id}` | `baselines_api.py` | ✅ Exact Match |
| `createBaseline` | `POST /api/baselines` | `baselines_api.py` | ✅ Exact Match |
| `deleteBaseline` | `DELETE /api/baselines/{id}` | `baselines_api.py` | ✅ Exact Match |
| `compareWithBaseline`| `POST /api/baselines/{id}/compare` | `baselines_api.py` | ✅ Exact Match |
| `compareTraces` | `POST /api/regression/compare-traces` | `baselines_api.py` | ✅ Exact Match |
| `getFailureAnalysis` | `GET /api/failure-analysis` | `failure_api.py` | ✅ Exact Match |
| `diagnoseExecution` | `POST /api/failure-analysis/diagnose` | `failure_api.py` | ✅ Exact Match |
| `getOllamaStatus` | `GET /api/failure-analysis/ollama/status` | `failure_api.py` | ✅ Exact Match |
| `listCIRuns` | `GET /api/ci/runs` | `ci_api.py` | ✅ Exact Match |
| `getCIRun` | `GET /api/ci/runs/{id}` | `ci_api.py` | ✅ Exact Match |

**Audit Result:** 100% of frontend API calls match backend endpoints with accurate HTTP verbs and URL paths.

---

## 5. Identified Deficiencies, Gaps & Edge Cases

### Defect 1: Standalone SDK Test Isolation Failure
- **Location:** `sdk/tests/test_framework_integration.py:397`
- **Issue:** `test_backend_schema_validation` imports `from app.traces_schemas import TraceEvent, IngestRequest`.
- **Impact:** Running `pytest` within the SDK directory fails with `ModuleNotFoundError: No module named 'app'` unless the backend root directory is explicitly passed in `PYTHONPATH`.
- **Fix:** Update `sdk/tests/test_framework_integration.py` to defensively import backend schemas if present or validate against self-contained event schema properties.

### Defect 2: SDK Package Link & CLI Entrypoint in Local Environment
- **Location:** `backend/.venv/bin/agentreliability`
- **Issue:** The `agentreliability` CLI command binary is not linked into the virtual environment's `bin/` directory. Running `agentreliability` requires `python3 -m agentreliability.cli` with `PYTHONPATH=sdk/src`.
- **Fix:** Add a `.pth` link in `backend/.venv/lib/python3.14/site-packages/agentreliability.pth` and create the CLI wrapper binary in `backend/.venv/bin/agentreliability`.

### Defect 3: Framework Availability and Status Reporting
- **Location:** Framework integrations (`langchain`, `langgraph`, `crewai`)
- **Issue:**
  - `langchain-core` (1.6.12) and `langgraph` (1.2.16) are installed and verified working.
  - `crewai` is **not installed** in the virtual environment. Any attempt to run real CrewAI workflows raises `ModuleNotFoundError`.
- **Status:** CrewAI integration is synthetic/simulated. This limitation must be explicitly documented and not falsely presented as live.

### Defect 4: Trace Search Edge Case in Baseline Comparison
- **Location:** `backend/app/baselines_api.py:_resolve_source_data`
- **Issue:** When resolving a candidate execution that is supplied as a raw execution ID, if an invalid or cross-tenant ID is passed, the error message should clearly distinguish between not found and unauthorized.

---

## 6. Test Suite Execution Baseline

1. **Backend Automated Tests:**
   - Command: `backend/.venv/bin/pytest backend/tests -v`
   - Result: **134 passed**, 0 failed, 23 Starlette deprecation warnings in 7.41s.
2. **SDK & Framework Automated Tests:**
   - Command: `PYTHONPATH=sdk/src:backend backend/.venv/bin/pytest sdk/tests -v`
   - Result: **49 passed**, 0 failed in 2.26s.
3. **Frontend Production Build:**
   - Command: `npm run build` (in `frontend/`)
   - Result: **48 modules compiled**, 0 errors in 699ms (dist: 374.57 kB JS, 47.25 kB CSS).

---

## 7. Prioritized Action Plan for MVP Completion

1. **Phase 2 — Real Developer Integration Test (`examples/mvp_validation/`):**
   - Implement an order-processing sample agent executing:
     1. Receive order -> 2. Verify customer credentials -> 3. Check inventory -> 4. Retrieve warehouse location -> 5. Calculate total -> 6. Confirm order.
   - Test Scenarios:
     - Scenario A: 100% Successful execution.
     - Scenario B: Tool failure (Inventory lookup exception with error details).
     - Scenario C: Behavioral regression (Skipped tool or modified confirmation schema).
   - Verify SDK live ingestion, API key auth, secret redaction, SQLite persistence, and UI visibility.
2. **Phase 3 — Golden Baseline & Regression Verification:**
   - Create golden baseline from Scenario A.
   - Run candidate comparison against Scenario A (Pass, 0 breaking changes).
   - Run candidate comparison against Scenario C (Detect skipped tool / schema break).
   - Verify baseline versioning and UI status.
3. **Phase 4 — Framework Integration Verification:**
   - Run actual local workflows for `langchain-core` and `langgraph` using installed packages.
   - Clearly document CrewAI package limitation without breaking SDK code.
4. **Phase 5 — Security & Multi-Tenant Verification:**
   - Verify valid, invalid, revoked, and missing API keys.
   - Verify cross-project isolation, CSRF protection, and secret redaction.
5. **Phase 6 — CLI & CI/CD Verification:**
   - Verify CLI runs test suites, generates GitHub summary, outputs JSON, and exits with correct status codes.
6. **Phase 7 — Frontend & Developer Experience:**
   - End-to-end check of all 11 pages in the browser.
7. **Phase 8 — Final Documentation & Deliverables:**
   - Generate `MVP_TEST_RESULTS.md` and `MVP_REMAINING_TASKS.md`.

