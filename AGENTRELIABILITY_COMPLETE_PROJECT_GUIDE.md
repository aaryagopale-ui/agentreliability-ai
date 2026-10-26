# AgentReliability AI — Complete Project Guide & Technical Manual

> **Document Version:** 1.0.0  
> **Target Audience:** Developers, AI Engineers, QA Automation Specialists, and Architects  
> **Scope:** Full-stack architecture, SDK instrumentation, deterministic replay, regression testing, and security model.

---

## Table of Contents
1. [What is AgentReliability AI and the Problem It Solves](#1-what-is-agentreliability-ai-and-the-problem-it-solves)
2. [Complete Architecture and Technology Stack](#2-complete-architecture-and-technology-stack)
3. [Every Dashboard Feature and How It Works](#3-every-dashboard-feature-and-how-it-works)
4. [AI Agents, Tools, Traces, Spans, SDK Instrumentation & Frameworks](#4-ai-agents-tools-traces-spans-sdk-instrumentation--frameworks)
5. [Golden Baselines and Regression Testing](#5-golden-baselines-and-regression-testing)
6. [Deterministic Replay Engine and Evidence-Based Failure Analysis](#6-deterministic-replay-engine-and-evidence-based-failure-analysis)
7. [Backend APIs, Database Tables, Authentication & Security](#7-backend-apis-database-tables-authentication--security)
8. [CI/CD and GitHub Actions](#8-cicd-and-github-actions)
9. [Real CrewAI Execution Example and Complete Data Flow](#9-real-crewai-execution-example-and-complete-data-flow)
10. [Important Project Folders and Files Guide](#10-important-project-folders-and-files-guide)
11. [Current Implementation Status, Limitations & Remaining Work](#11-current-implementation-status-limitations--remaining-work)
12. [Glossary of Concepts](#12-glossary-of-concepts)

---

## 1. What is AgentReliability AI and the Problem It Solves

### The Real-World Problem
Autonomous AI agents are not simple stateless functions. They are **stateful, non-deterministic decision machines** that iteratively think, select tools, observe tool outputs, and decide on next steps.

When teams deploy agents to production, they face four fundamental reliability problems:
1. **Silent Failures and Hallucinations:** An LLM might fail to call a required tool, call the tool with invalid arguments, or misinterpret a tool's error output while continuing its execution loop. The agent returns a polite answer that looks plausible but is factually invalid.
2. **Behavioral and Latency Regressions:** When an engineer tweaks a prompt, modifies a tool description, or updates model weights (e.g. migrating from GPT-4o-mini to GPT-4o, or updating a local Llama model), previously working agent workflows often break silently.
3. **Flaky and Prohibitively Expensive Testing:** Re-running autonomous agents against live cloud APIs for unit or regression testing takes minutes, costs real money for every test suite run, and produces non-deterministic results due to stochastic model sampling.
4. **Lack of Hierarchical Observability:** In multi-agent frameworks like CrewAI or LangGraph, where one agent delegates tasks to another agent who calls three sequential tools, standard APM tools (like Datadog or Sentry) fail to present the parent-child relationship between agent delegations and tool invocations.

### The Solution: AgentReliability AI
**AgentReliability AI** is an open-source, developer-first observability, regression testing, deterministic replay, and debugging platform designed specifically for AI agents.

Key capabilities:
- **Zero-Crash SDK Tracing:** Non-blocking, client-side sanitized telemetry hooks for standard Python code, CrewAI, LangChain, and LangGraph.
- **Hierarchical Timelines and Waterfalls:** High-resolution interactive visual timelines displaying exact parent-child links (Crew $\to$ Task $\to$ Tool Call) and execution durations.
- **Golden Baseline Regression Testing:** Capture a known good execution trace, save it as a "Golden Baseline", and automatically detect missing tools, tool ordering shifts, schema changes, and latency slowdowns in future runs.
- **Offline Deterministic Replay:** Replays recorded agent step sequences against mocked tool responses in milliseconds, with zero cloud API costs.
- **Evidence-Based Failure Analysis:** Rule-based diagnostic engine that categorizes failures into hard facts and confirmed observations, with optional local AI explanation via an offline Ollama instance.
- **CI/CD Integration:** A native Python CLI (`agentreliability test`) and GitHub Actions workflow that gates PRs and prevents regressions before code reaches production.

---

## 2. Complete Architecture and Technology Stack

### High-Level Architecture Diagram

```text
                  +────────────────────────────────────────────────────────+
                  │                   AGENT ENVIRONMENT                    │
                  │   CrewAI / LangChain / LangGraph / Custom Python       │
                  +────────────────────────────────────────────────────────+
                                              │
                         @tool decorators / event listeners
                                              │
                                              ▼
                  +────────────────────────────────────────────────────────+
                  │           AgentReliability Python SDK Tracing          │
                  │   - Redaction & PII Scrubbing                          │
                  │   - Non-blocking Asynchronous Background Transport     │
                  +────────────────────────────────────────────────────────+
                                              │
                                 HTTP POST (Header: X-API-Key)
                                 Port 8001
                                              ▼
+──────────────────────────────────────────────────────────────────────────────────────────+
│                                 FastAPI BACKEND SERVER                                   │
│                                                                                          │
│  [Auth & Security]              [Core Engines]                  [API Routers]            │
│  - Session Cookies              - Regression Comparison Engine  - /api/v1/traces         │
│  - CSRF Token Guard             - Deterministic Replay Engine   - /api/baselines         │
│  - API Key Verification (SHA256)- Failure Diagnosis Rules       - /api/tests             │
│  - Project Workspace Isolation  - Optional Local Ollama Bridge  - /api/v1/ci             │
+──────────────────────────────────────────────────────────────────────────────────────────+
                                              │
                                              ▼
                  +────────────────────────────────────────────────────────+
                  │               SQLite Database (WAL Mode)               │
                  │   - agentreliability.db                                │
                  │   - 15 relational tables with strict foreign keys      │
                  │   - Transactional schema migrations                    │
                  +────────────────────────────────────────────────────────+
                                              │
                                 HTTP REST / Active Project ID
                                              ▼
                  +────────────────────────────────────────────────────────+
                  │                React 19 Frontend Dashboard             │
                  │   - Vite 6 + Tailwind CSS (Dark Mode)                  │
                  │   - Waterfall & Timeline Visualizers                   │
                  │   - Port 5174                                          │
                  +────────────────────────────────────────────────────────+
```

### Technology Breakdown

#### Frontend (`frontend/`)
- **React 19:** Single-page application using modern hooks (`useState`, `useEffect`, `useCallback`).
- **Vite 6:** Fast development server and build tool configured with reverse proxy to backend port `8001`.
- **Tailwind CSS 3.4:** Custom responsive dark slate palette (`bg-slate-950`, `border-slate-800`).
- **Lucide React:** Semantic icon set for agent states, tools, and actions.
- **Zero Heavy Graph Dependencies:** Custom lightweight SVG and CSS-based timeline and waterfall visualizations in `TraceExecutionTimeline.jsx`.

#### Backend (`backend/app/`)
- **FastAPI:** High-performance asynchronous Python web framework running on Uvicorn ASGI server.
- **Pydantic v2:** Strict input validation and serialization for agent logs, trace schemas, and authentication payloads.
- **SQLite 3 (WAL Mode):** Embedded database configured with `PRAGMA journal_mode = WAL`, `PRAGMA busy_timeout = 30000`, and `PRAGMA foreign_keys = ON`.
- **PBKDF2-HMAC-SHA256:** Password hashing with 100,000 iterations and per-user 16-byte random salt.

#### Python SDK & CLI (`sdk/`)
- **Package Name:** `agentreliability`
- **Core Monitor:** `AgentMonitor` provides execution decorators and tool context managers.
- **Transport:** Asynchronous background thread queue with automatic batching, exponential backoff, and flush timeouts.
- **CLI:** `agentreliability` command-line utility with `status` and `test` subcommands.

#### External Services & Paid APIs
- **Zero Paid APIs:** The entire platform runs 100% locally and offline without external API keys (no OpenAI, Anthropic, or Pinecone accounts required).
- **Optional Local AI:** Connects only to a local Ollama daemon (`http://127.0.0.1:11434`) if installed; otherwise falls back automatically to deterministic rules.

---

## 3. Every Dashboard Feature and How It Works

The web frontend operates on **Port 5174** and organizes functionality into 11 main tabs:

### 1. Overview (`frontend/src/pages/Overview.jsx`)
- **What it does:** Displays high-level health cards for the currently selected project workspace.
- **Metrics shown:** Total live traces captured, total failed traces, regression test coverage, and a list of the 5 most recent test executions.
- **Backend route:** `GET /api/overview`

### 2. Getting Started (`frontend/src/pages/GettingStarted.jsx`)
- **What it does:** A 10-milestone developer onboarding checklist that tracks progress (e.g. "8/10 Milestones Completed").
- **Features:** One-click "Generate Quickstart API Key" button and copy-pasteable code snippets for Python SDK, CrewAI, LangChain, and CLI testing.
- **Backend routes:** `GET /api/projects/{id}/keys`, `POST /api/projects/{id}/keys`

### 3. Live Agent Monitoring (`frontend/src/pages/LiveMonitoring.jsx`)
- **What it does:** Real-time stream of agent executions and nested tool calls captured live via the SDK.
- **Controls & Filters:** Filter by agent name, execution status (`success`, `failed`, `running`), and time window (`1h`, `24h`, `7d`, `all`). Auto-poll switch.
- **Visualization:** Interactive detail drawer with **Timeline** and **Waterfall** charts (`TraceExecutionTimeline.jsx`) showing start offsets, execution durations, input/output JSON payloads, and exact parent task linkages.
- **Actions:** One-click **"Generate Test Case"** button to convert a live trace directly into an offline test case.
- **Backend routes:** `GET /api/v1/traces/executions`, `GET /api/v1/traces/executions/{id}`, `GET /api/v1/traces/agents`

### 4. Regression Testing (`frontend/src/pages/RegressionTesting.jsx`)
- **What it does:** Compares candidate agent executions against saved "Golden Baselines" to detect breaking changes.
- **Controls:** Select Baseline, select Candidate Execution Trace, and set Duration Tolerance slider (default: $\pm 50\%$).
- **Output:** Categorized diff list (`breaking_regression`, `performance_regression`, `informational_change`), baseline version history, and baseline version rollback/promotion.
- **Backend routes:** `GET /api/baselines`, `POST /api/baselines`, `POST /api/baselines/{id}/compare`, `GET /api/baselines/{id}/versions`

### 5. CI/CD Testing (`frontend/src/pages/CITesting.jsx`)
- **What it does:** Displays regression test suites executed and uploaded automatically from GitHub Actions or local CLI runs.
- **Displays:** Git commit SHA, branch name, execution duration, total passed, and total failed tests.
- **Backend routes:** `GET /api/v1/ci/runs`, `GET /api/v1/ci/runs/{id}`

### 6. Agent Executions (`frontend/src/pages/Executions.jsx`)
- **What it does:** Legacy log ingestion for recorded execution JSON files.
- **Features:** Drag-and-drop JSON file upload (up to 5 MB), step counts, error counts, and static rule analysis.
- **Backend routes:** `GET /api/executions`, `POST /api/executions`

### 7. Test Cases (`frontend/src/pages/TestCases.jsx`)
- **What it does:** Management of reusable offline test definitions.
- **Features:** Displays agent initial state, recorded step sequence, and expected assertions (e.g. expected tools, expected outputs). Includes "Run Test" and "Run All Tests" buttons.
- **Backend routes:** `GET /api/tests`, `POST /api/tests`, `PUT /api/tests/{id}`, `DELETE /api/tests/{id}`

### 8. Replay Engine (`frontend/src/pages/Replay.jsx`)
- **What it does:** Interactive simulator that plays recorded test cases against mocked tool registries.
- **Prominent Banner:** Clearly informs the user: *"Deterministic simulation: recorded steps were replayed with mocked tool responses. No real agent, model or external tool was executed."*
- **Displays:** Chronological step execution cards, mock tool outputs, duration, and pass/fail assertion checks.
- **Backend routes:** `POST /api/tests/{id}/run`, `GET /api/test-runs/{id}`

### 9. Failure Analysis (`frontend/src/pages/FailureAnalysis.jsx`)
- **What it does:** Centralized diagnostic triage across all failed traces in the project.
- **Displays:** Failure distribution bar charts by category (`tool_failure`, `timeout`, `unexpected_exception`), failing agent ranking, and a diagnostic modal detailing confirmed facts, preceding events, timing anomalies, and local AI recommendations.
- **Backend routes:** `GET /api/v1/failures/dashboard`, `POST /api/v1/failures/diagnose`, `GET /api/v1/failures/ollama-status`

### 10. Test History (`frontend/src/pages/History.jsx`)
- **What it does:** Historical log of all test case replay runs.
- **Displays:** Run ID, test case name, run timestamp, status badge, duration in milliseconds, and failure reasons.
- **Backend routes:** `GET /api/test-runs`

### 11. API Keys & SDK (`frontend/src/pages/ApiKeys.jsx`)
- **What it does:** Self-service API key management for the active project.
- **Features:** Create key (displays full plaintext token once with copy button), rotate key (creates new key and revokes old key atomically), and revoke key. Plaintext keys are never stored or displayed again.
- **Backend routes:** `GET /api/projects/{id}/keys`, `POST /api/projects/{id}/keys`, `DELETE /api/projects/{id}/keys/{key_id}`, `POST /api/projects/{id}/keys/{key_id}/rotate`

---

## 4. AI Agents, Tools, Traces, Spans, SDK Instrumentation & Frameworks

### Core Observability Concepts
- **Agent Name:** The logical identity of the agent or multi-agent crew (e.g. `crewai_financial_audit_crew`).
- **Trace Execution:** The top-level record representing a single end-to-end execution from start to finish (`execution_id`).
- **Span:** A timed segment representing an operation within a trace.
- **Task Span:** A high-level sub-goal assigned to an agent.
- **Tool Call Span:** An invocation of an individual tool (e.g. `check_database`).
- **Hierarchy (`parent_call_id`):** Spans reference the ID of the task or agent step that invoked them, allowing multi-agent delegation trees to be faithfully reconstructed.

### SDK Instrumentation

#### Direct Python Instrumentation
```python
from agentreliability.monitor import AgentMonitor

monitor = AgentMonitor(
    agent_name="financial_analyst",
    endpoint="http://127.0.0.1:8001",
    api_key="ar_live_...",
)

with monitor.trace_execution(input_data={"account_id": "ACC-101"}) as exec_span:
    with monitor.trace_tool("fetch_account", input_data={"id": "ACC-101"}) as tool_span:
        data = db.query(...)
        tool_span.set_output(data)
    exec_span.set_output({"status": "verified"})
```

#### CrewAI Event Bus Integration (`sdk/src/agentreliability/integrations/crewai.py`)
CrewAI emits events via `crewai.events.crewai_event_bus`. AgentReliability hooks directly into this bus using `AgentReliabilityCrewListener`:
1. `CrewKickoffStartedEvent` $\to$ Automatically starts the root trace execution.
2. `TaskStartedEvent` $\to$ Creates a task span with description and assigned agent role.
3. `ToolUsageStartedEvent` $\to$ Creates a child tool call span linked to the current task via `parent_call_id`.
4. `ToolUsageFinishedEvent` / `ToolUsageErrorEvent` $\to$ Records output, error message, and computes tool duration.
5. `TaskCompletedEvent` / `TaskFailedEvent` $\to$ Finalizes task duration and task output.
6. `CrewKickoffCompletedEvent` $\to$ Finalizes the root execution and triggers background asynchronous transport flush.

#### LangChain & LangGraph Integration (`sdk/src/agentreliability/integrations/langchain.py`)
Implements `BaseCallbackHandler` to capture:
- `on_chain_start` / `on_chain_end` $\to$ Root chain or sub-graph boundaries.
- `on_tool_start` / `on_tool_end` / `on_tool_error` $\to$ Tool inputs, outputs, errors, and timing.
- `on_llm_start` / `on_llm_end` $\to$ Model invocation latency and token usage metadata.

### Client-Side Sensitive Data Redaction
Before any telemetry leaves the developer's process, [`Redactor`](file:///Users/aaryagopale/Desktop/AgentReliability/sdk/src/agentreliability/redaction.py) sanitizes all payloads:
- **Regex Pattern Masking:** Automatically detects and replaces OpenAI keys (`sk-...`), AgentReliability keys (`ar_live_...`), JWT tokens, private keys, and passwords with `[REDACTED]`.
- **Key-Name Scrubbing:** In JSON dictionaries, keys such as `password`, `secret`, `api_key`, `access_token`, or `authorization` have their values scrubbed.
- **Payload Bounding:** Strings exceeding 5,000 characters are safely truncated to protect database memory.

---

## 5. Golden Baselines and Regression Testing

### Baseline Creation & Storage
A Golden Baseline represents a verified, production-grade agent execution that serves as the benchmark for future runs.
1. When a user clicks **"Set as Golden Baseline"**, the backend calls `POST /api/baselines`.
2. A record is inserted into `baselines` with `agent_name` and `active_version = 1`.
3. A detailed snapshot is saved in `baseline_versions` containing:
   - `expected_tools_json`: Ordered list of expected tool calls and arguments.
   - `expected_status`: Expected final status (`success`).
   - `latency_budget_ms`: Baseline execution duration plus a tolerance threshold.
   - `output_schema_json`: JSON Schema of the final output.

### The Regression Comparison Engine (`backend/app/regression_engine.py`)
When comparing a candidate trace against a baseline, the engine executes four deterministic comparison checks:

```text
                                [ Candidate Execution ]
                                          │
                  ┌───────────────────────┼───────────────────────┐
                  ▼                       ▼                       ▼
         [ Status Check ]          [ Tool Sequence ]       [ Latency Check ]
          Baseline: success         Expected: [A, B]        Baseline: 70ms
          Candidate: failed         Candidate: [A]          Candidate: 180ms
                  │                       │                       │
                  ▼                       ▼                       ▼
           status_regression        missing_tool             high_latency
         (breaking_regression)   (breaking_regression)   (performance_regression)
```

1. **Status Regression (`breaking_regression`):** Baseline succeeded, but candidate failed.
2. **Missing Tool Regression (`breaking_regression`):** An expected tool from the baseline was omitted by the candidate agent.
3. **Tool Order Mismatch (`breaking_regression`):** Tools were called out of sequence when `strict_order=True`.
4. **Output Schema Regression (`breaking_regression`):** Required keys from the baseline output schema are missing in the candidate output.
5. **Latency Budget Regression (`performance_regression`):** Candidate runtime exceeds baseline duration by more than the configured tolerance percentage (default: $50\%$).
6. **Informational Change (`informational_change`):** Safe differences, such as additional permitted tools or benign output value updates.

---

## 6. Deterministic Replay Engine and Evidence-Based Failure Analysis

### Deterministic Replay Engine (`backend/app/replay.py`)
> **Core Principle:** The Replay Engine is a **simulation**, not a re-execution of live agent code.
- **No LLM API Calls:** Zero tokens are consumed during replay.
- **Mock Tool Registry:** The [`MockToolRegistry`](file:///Users/aaryagopale/Desktop/AgentReliability/backend/app/replay.py#L28) inspects recorded tool steps in the test case and feeds those exact responses back to the test runner.
- **Speed & Reproducibility:** Executes in under 10 milliseconds. The exact same test case input produces the exact same output every single time.

### Failure Analysis Engine (`backend/app/failure_engine.py`)
The failure analysis engine processes failed traces using deterministic diagnostic extraction:
- **Confirmed Observations:** Extracts exact recorded facts (e.g. *"Tool 'check_database' returned HTTP 500"*).
- **Preceding Events:** Assembles all successful tool calls and steps leading up to the failure point.
- **Timing Anomalies:** Flags steps taking $>10,000\text{ ms}$ (high latency) or $<1.0\text{ ms}$ (immediate connection refusal).
- **Evidence Sufficiency Scoring:** Grades evidence as `sufficient`, `partial`, or `insufficient`.

### Optional Local AI Assistance (`backend/app/local_ai.py`)
- **Zero Cloud Leakage:** Communicates exclusively with an offline Ollama daemon (`http://127.0.0.1:11434`).
- **Prompt Injection Defense:** Trace evidence is wrapped inside `<untrusted_trace_evidence>` tags with explicit instructions forbidding the LLM from executing commands found within traces.
- **Separation of Facts vs. Hypotheses:** AI recommendations are strictly labeled as *"Suggested Hypotheses"*, ensuring they are never confused with confirmed execution facts.

---

## 7. Backend APIs, Database Tables, Authentication & Security

### Database Schema (15 Tables in `agentreliability.db`)

| Table Name | Primary Purpose | Key Columns |
| :--- | :--- | :--- |
| `users` | User accounts | `id`, `email`, `password_hash`, `name`, `created_at` |
| `sessions` | Active web sessions | `session_token`, `csrf_token`, `user_id`, `expires_at` |
| `password_resets` | Password recovery tokens | `id`, `user_id`, `reset_token`, `expires_at`, `used_at` |
| `projects` | Multi-tenant workspaces | `id`, `name`, `owner_id`, `is_archived`, `created_at` |
| `api_keys` | Hashed ingestion credentials | `id`, `project_id`, `name`, `key_hash`, `key_prefix`, `revoked_at` |
| `trace_executions` | Root live agent traces | `execution_id`, `project_id`, `agent_name`, `status`, `duration_ms`, `input_json`, `output_json` |
| `trace_tool_calls` | Child tasks and tool calls | `call_id`, `execution_id`, `tool_name`, `duration_ms`, `status`, `parent_call_id` |
| `trace_events` | Granular event stream | `event_id`, `execution_id`, `event_name`, `payload_json`, `timestamp` |
| `baselines` | Golden Baseline definitions | `id`, `project_id`, `agent_name`, `active_version` |
| `baseline_versions` | Versioned baseline snapshots | `baseline_id`, `version`, `execution_id`, `expected_tools_json`, `latency_budget_ms` |
| `test_cases` | Offline test definitions | `id`, `project_id`, `name`, `steps_json`, `assertions_json` |
| `test_runs` | Replay execution results | `id`, `test_case_id`, `status`, `duration_ms`, `failure_reason` |
| `ci_runs` | Uploaded CI/CD test runs | `id`, `project_id`, `commit_sha`, `branch`, `passed`, `failed` |
| `executions` | Legacy uploaded JSON logs | `id`, `project_id`, `agent_name`, `steps_json`, `findings_json` |
| `schema_migrations` | Transactional migration log | `version`, `name`, `applied_at` |

### Authentication & Authorization Flow
1. **Web Sessions:** When logging in via `POST /api/auth/login`, the server generates a 32-byte session token and a CSRF token. The session token is set as an `HttpOnly`, `SameSite=Lax` cookie (`ar_session`).
2. **CSRF Protection:** State-mutating requests (`POST`, `PUT`, `DELETE`) require the `X-CSRF-Token` header, validated by `check_csrf` in `backend/app/auth_api.py`.
3. **Workspace Isolation:** Every request resolves the active project using `X-Project-Id` via `get_authorized_project`. Users cannot view or modify data belonging to projects they do not own.
4. **API Key Verification:** The SDK authenticates via `X-API-Key: ar_live_...`. The backend hashes the incoming key using SHA-256 and matches it against `api_keys.key_hash`. Plaintext keys are never stored in the database.

---

## 8. CI/CD and GitHub Actions

### GitHub Actions Workflow (`.github/workflows/agent-tests.yml`)
The workflow automatically executes on every pull request and push to `main`:
1. Checks out the repository.
2. Sets up Python 3.11.
3. Installs the local SDK: `pip install ./sdk`.
4. Runs deterministic regression tests using the CLI:
   ```bash
   agentreliability test \
     --project ./demo_project/agent-tests \
     --output ./test-results/results.json \
     --baseline ./demo_project/agent-tests/baseline.json \
     $UPLOAD_FLAG
   ```
5. If `AGENTRELIABILITY_ENDPOINT` and `AGENTRELIABILITY_API_KEY` are provided as repository secrets, test results are automatically uploaded to the dashboard's **CI/CD Testing** tab.
6. Generates a Markdown test summary in GitHub Actions (`GITHUB_STEP_SUMMARY`).

---

## 9. Real CrewAI Execution Example and Complete Data Flow

The project includes an authentic, executable CrewAI example in [`examples/crewai_live_example.py`](file:///Users/aaryagopale/Desktop/AgentReliability/examples/crewai_live_example.py):

### The Workflow
- **Crew Name:** `crewai_financial_audit_crew`
- **Agent 1:** `Database Auditor` (Tools: `check_database`)
- **Agent 2:** `Risk Analyst` (Tools: `calculate_risk`)
- **LLM Configuration:** Deterministic local completion client conforming to the OpenAI spec (zero paid API calls or cloud dependencies).

### Complete Telemetry Lifecycle
```text
1. crew.kickoff() executed
   │
   ├── Database Auditor executes Task 1
   │   └── check_database(account_id="ACC-AUDIT-901") is called
   │       └── Output: balance_usd = 12500.0 (Duration: 0.037 ms)
   │
   └── Risk Analyst executes Task 2
       └── calculate_risk(account_id="ACC-AUDIT-901", balance_usd=12500.0) is called
           └── Output: risk_score = 15, rating = "low_risk" (Duration: 0.021 ms)
   │
2. Event Bus flushes telemetry to AgentReliability backend (Port 8001)
   │
3. Database stores trace under execution_id "exec-crew-9affd0195d2c483b88b2":
   ├── trace_executions: status="success", duration_ms=72.509
   └── trace_tool_calls:
       ├── Task 1: [Database Auditor] Verify account status... (Duration: 24.44 ms)
       │   └── Tool Call: check_database (parent: Task 1, Duration: 0.037 ms)
       └── Task 2: [Risk Analyst] Calculate risk score... (Duration: 12.318 ms)
           └── Tool Call: calculate_risk (parent: Task 2, Duration: 0.021 ms)
   │
4. Dashboard Live Monitoring displays hierarchical waterfall with 4 nested spans.
```

---

## 10. Important Project Folders and Files Guide

```text
AgentReliability/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI application entry point
│   │   ├── database.py              # SQLite connection & WAL mode config
│   │   ├── auth_api.py              # User authentication, sessions & CSRF
│   │   ├── auth_deps.py             # Dependency injection for project authorization
│   │   ├── traces_api.py            # Live trace ingestion endpoints
│   │   ├── baselines_api.py         # Golden Baseline management & comparison
│   │   ├── regression_engine.py     # Deterministic regression diffing engine
│   │   ├── failure_engine.py        # Rule-based diagnostic extractor
│   │   ├── local_ai.py              # Local Ollama AI integration bridge
│   │   ├── replay.py                # Deterministic replay simulation engine
│   │   ├── redaction.py             # Server-side credential sanitizer
│   │   └── migrations/              # Versioned SQLite schema migrations
│   ├── tests/                       # 193 automated backend pytest test cases
│   └── agentreliability.db         # SQLite database file
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # Main React dashboard layout & routing
│   │   ├── api.js                   # Centralized API client with CSRF handling
│   │   ├── ui.jsx                   # Reusable dark-mode UI components
│   │   ├── pages/                   # 11 dashboard pages (LiveMonitoring, Regression, etc.)
│   │   └── components/
│   │       └── TraceExecutionTimeline.jsx # Timeline & Waterfall chart renderer
│   ├── package.json                 # React 19 dependencies
│   └── vite.config.js               # Dev server & reverse-proxy config
├── sdk/
│   ├── src/agentreliability/
│   │   ├── monitor.py               # Core AgentMonitor tracing class
│   │   ├── transport.py             # Asynchronous HTTP background sender
│   │   ├── redaction.py             # Client-side PII/credential scrubber
│   │   ├── cli.py                   # agentreliability CLI utility
│   │   └── integrations/
│   │       ├── crewai.py            # CrewAI event bus listener
│   │       ├── langchain.py         # LangChain callback handler
│   │       └── langgraph.py         # LangGraph graph execution handler
│   └── tests/                       # 58 automated SDK pytest test cases
├── examples/
│   └── crewai_live_example.py       # Verified live CrewAI 2-agent example
└── .github/workflows/
    └── agent-tests.yml              # CI/CD regression testing workflow
```

---

## 11. Current Implementation Status, Limitations & Remaining Work

### Implemented & Fully Verified
- Complete React 19 frontend with 11 responsive dashboard tabs.
- FastAPI backend on port 8001 with WAL SQLite storage and 4 database migrations.
- User authentication, multi-tenant project isolation, CSRF defense, and hashed API keys.
- Real-time live trace ingestion with parent-child task and tool nesting.
- Golden Baseline creation, multi-version snapshots, and promotion.
- Deterministic regression comparison engine.
- Deterministic replay simulator with explicit simulation disclaimer banner.
- Rule-based evidence failure analysis.
- Python SDK with native CrewAI and LangChain integrations.
- Command-line interface (`agentreliability status` and `agentreliability test`).
- GitHub Actions CI workflow.
- **Test Suite:** 193 backend tests and 58 SDK tests passing cleanly.

### Incomplete, Mocked, or Planned Features
- **Local AI Debugger:** Fully implemented, but requires an external Ollama instance running at `http://127.0.0.1:11434`; otherwise operates in deterministic fallback mode.
- **PostgreSQL Adapter:** A migration architecture document exists (`docs/postgres_migration_plan.md`), but the active backend currently runs on SQLite.
- **WebSocket Streaming:** Telemetry updates are currently fetched via responsive HTTP polling; live WebSocket push is planned for future phases.

---

## 12. Glossary of Concepts

- **Agent:** An autonomous program powered by an LLM that iteratively decides which tools to execute to achieve a specific objective.
- **Trace:** A complete recorded history of an agent execution from initial input to final output.
- **Span:** A timed interval representing a single discrete unit of work (e.g. an agent task or a tool call) within a trace.
- **Parent-Child Hierarchy:** Tree structure where child tool calls are linked to the specific agent task that invoked them via `parent_call_id`.
- **Golden Baseline:** A known-good reference execution saved by developers against which future runs are compared.
- **Regression:** A defect where an agent capability fails, slows down, changes its tool call sequence, or produces invalid schemas following an update.
- **Deterministic Replay:** Replaying recorded agent steps using mocked tool outputs without invoking real LLMs or external APIs.
- **Multi-Tenancy:** Architecture ensuring each user's workspaces and data are strictly isolated from all other users.
- **Redaction:** Automatic client-side and server-side masking of sensitive credentials (tokens, passwords, keys) before telemetry is stored or analyzed.

---

## How to Run the Project Locally

### 1. Start the Backend (Port 8001)
```bash
cd ~/Desktop/AgentReliability
PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --port 8001 --host 127.0.0.1 --reload
```

### 2. Start the Frontend (Port 5174)
```bash
cd ~/Desktop/AgentReliability/frontend
npm run dev
```

### 3. Run the Verified CrewAI Example
```bash
cd ~/Desktop/AgentReliability
AGENTRELIABILITY_ENDPOINT="http://127.0.0.1:8001" \
AGENTRELIABILITY_API_KEY="<your_api_key_from_dashboard>" \
venv-crewai312/bin/python examples/crewai_live_example.py
```

