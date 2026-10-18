# AgentReliability AI — Phase 1 (local MVP)

Upload AI-agent execution logs (JSON), detect failures with deterministic rules, and view timelines and explanations.

## How it works (beginner overview)

1. **Frontend** (React, port 5173) is the web page you see.
2. **Backend** (FastAPI, port 8000) receives the uploaded file, checks its format, runs the detection rules, and stores the result.
3. **SQLite** (`backend/agentreliability.db`) is a single file that holds saved executions.

## Folder structure

```
AgentReliability/
├── README.md
├── sample_logs/          success_log.json, failed_tool_log.json, timeout_log.json
├── backend/
│   ├── requirements.txt
│   ├── app/              main.py (API), schemas.py (format validation),
│   │                     detector.py (rules), database.py (SQLite), seed.py
│   └── tests/            test_detector.py, test_api.py
└── frontend/             Vite + React + Tailwind (src/App.jsx, src/api.js)
```

## Prerequisites (Ubuntu 22.04 / 24.04)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl
# Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

## Run the backend

```bash
cd AgentReliability/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed                 # optional: load the 3 sample logs
uvicorn app.main:app --reload --port 8000
```

Check: <http://127.0.0.1:8000/api/health> returns `{"status":"ok"}`. Interactive API docs: <http://127.0.0.1:8000/docs>.

## Run the frontend (second terminal)

```bash
cd AgentReliability/frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

## Run the tests

```bash
cd AgentReliability/backend
source .venv/bin/activate
python -m pytest -v
```

Tests use a temporary database, so they never touch your real data.

## Log format

```json
{
  "agent_name": "support-bot",
  "run_id": "optional-id",
  "steps": [
    {"type": "tool_call", "name": "search", "status": "failed",
     "duration_ms": 300, "timeout_ms": 5000, "error": "HTTP 503",
     "timestamp": "2026-01-01T10:00:00Z", "input": {}, "output": {}}
  ]
}
```

Required: `agent_name`, and `steps` (at least one, each with `type`). Everything else is optional; `status` defaults to `success`.

## Detection rules (checked in this order, one finding per step)

| Category | Triggers when |
|---|---|
| `timeout` | `status` is `timeout`, OR `duration_ms > timeout_ms`, OR the error text contains "timeout"/"timed out" |
| `failed_tool_call` | `type` is `tool_call` and `status` is error/failed/failure/exception, or `error` is set |
| `explicit_error` | `type` is `error`, or any other step has an error status or `error` message |

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| POST | `/api/executions` | Upload a log (multipart field `file`) |
| GET | `/api/executions` | List saved executions |
| GET | `/api/executions/{id}` | Details with steps and findings |

Quick test without the UI:

```bash
curl -F "file=@sample_logs/failed_tool_log.json" http://127.0.0.1:8000/api/executions
```

## Reset the database (destructive — deletes all saved executions)

```bash
rm backend/agentreliability.db
```

## Phase 2 — Testing and Replay Engine

Dashboard pages: **Overview, Agent Executions, Test Cases, Replay Engine, Failure Analysis, Test History.**

Workflow: upload a log → **Create test case** → edit what you expect (optional) → **Run** → read failures.

### What a test case contains
- `steps`: the recorded steps. Tool-call steps are also the **mocked tool responses**.
- `expected`: `status`, `tool_sequence`, `final_output` (`null` = don't check), `error_conditions` (`[{"step_index":0,"category":"timeout"}]`).
- A freshly generated test reproduces its recording, so it passes. Edit `expected` (or the mocked steps) to see failures.

### Replay is a SIMULATION
Replay does **not** run your real agent or call any language model, and no real tool is called. It plays the recorded steps back through a mock tool registry and compares the result with `expected`. It cannot reproduce live model behavior. Nothing uploaded is ever executed; it is stored and compared as plain data.

### Problems the replay reports
`failed_tool_call`, `timeout`, `unexpected_exception`, `explicit_error`, `missing_expected_error`, `sequence_mismatch`, `missing_output`, `output_mismatch`, `status_mismatch`.

### New API endpoints
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/tests` | Create a test |
| POST | `/api/tests/from-execution/{id}` | Generate a test from an execution |
| GET | `/api/tests`, `/api/tests/{id}` | List / read tests |
| PUT / DELETE | `/api/tests/{id}` | Edit / delete (past runs are kept) |
| POST | `/api/tests/{id}/run`, `/api/tests/run-all` | Run one / all tests |
| GET | `/api/test-runs`, `/api/test-runs/{id}` | History (`?test_id=` filters) |
| GET | `/api/overview`, `/api/failure-analysis` | Dashboard numbers |

Existing databases upgrade automatically (new tables are created on startup).

### Run everything (Ubuntu)
Backend and frontend commands are the same as above. To point the frontend at a backend on another port:
```bash
API_TARGET=http://127.0.0.1:8001 npm run dev
```

## Phase 3 — Python SDK and Real Agent Execution Monitoring

Phase 3 introduces real execution telemetry: instrument your Python agents using the standalone `agentreliability` SDK and stream live execution traces and tool calls to your backend.

### 1. Standalone Python SDK (`sdk/`)
The `agentreliability` package is completely standalone with zero external runtime dependencies (Python standard library only).

Install it into your agent's virtual environment:
```bash
pip install ./sdk
# or pip install -e ./sdk (for development)
```

### 2. Generate a Project API Key
API keys use `ar_...` secure tokens. The backend only stores SHA-256 hashes of the keys.
```bash
cd backend
source .venv/bin/activate
python -m app.create_key my-project
```
This prints your development API key once. Keep it secret and do not commit it to GitHub.

### 3. Connect a Python Agent
```python
from agentreliability import AgentMonitor

# Configure monitor (or set AGENTRELIABILITY_API_KEY environment variable)
monitor = AgentMonitor(
    endpoint="http://localhost:8000",
    api_key="ar_YOUR_KEY_HERE",
    capture_io=False, # default is False to protect privacy; set True to capture payloads
)

@monitor.trace_tool("search_web")
def search_web(query: str):
    return ["result 1", "result 2"]

@monitor.trace_agent("research-agent")
def run_agent(question: str):
    return search_web(question)
```

**Reliability guarantee:** Monitoring failures (e.g. backend offline, network timeout) are handled in the background and will **never crash or alter the behavior** of your agent.

### 4. Run the Deterministic Demo Agent
We include a multi-scenario demo agent in `demo_agent.py`:
```bash
# Export your API key:
export AGENTRELIABILITY_API_KEY="ar_..."
export AGENTRELIABILITY_ENDPOINT="http://localhost:8000"

# Run all 4 deterministic scenarios (success, tool_failure, timeout, exception):
python demo_agent.py all
```

### 5. Live Agent Monitoring Dashboard
Visit the **Live Agent Monitoring** tab in the React dashboard:
- View live streaming executions with auto-polling every 3s.
- Filter by agent, status (`success`, `failed`, `running`), or time range.
- Inspect tool-call history, errors, and redacted inputs/outputs.
- Click **"Create Test Case"** on any recorded real execution to convert it into a Phase 2 replayable test.

### 6. Run Automated Tests
```bash
# Run backend tests (49 tests):
cd backend && source .venv/bin/activate && python -m pytest -v

# Run SDK unit tests (28 tests):
cd sdk && ../backend/.venv/bin/python -m pytest -v
```

## Phase 4 — GitHub Actions Integration & Automated Regression Testing

Phase 4 enables running deterministic agent tests inside your CI/CD pipelines and command line with automated regression detection and dashboard integration.

### 1. Command-Line Test Runner (`agentreliability test`)
Execute test suites offline without needing API keys or cloud credentials:
```bash
# Run tests in a directory or single file
agentreliability test --project ./demo_project/agent-tests/test_pass.json

# Run all tests, write output report, and compare with a baseline
agentreliability test \
  --project ./demo_project/agent-tests \
  --output ./test-results/results.json \
  --baseline ./demo_project/agent-tests/baseline.json
```
- **Exit code 0:** All tests passed.
- **Exit code 1:** Tests failed or regressions detected.

### 2. GitHub Actions Workflow (`.github/workflows/agent-tests.yml`)
Runs on pushes and pull requests to `main`:
1. Checks out repository with least-privilege permissions (`contents: read`).
2. Installs Python and the `agentreliability` SDK.
3. Executes `agentreliability test`.
4. Writes an interactive test summary to `$GITHUB_STEP_SUMMARY`.
5. Uploads `./test-results/results.json` as an artifact (`actions/upload-artifact@v4`).

### 3. Regression Comparison Engine
Compares current test outcomes against `baseline.json`:
- **New failures:** Tests that passed in the baseline and now fail (regressions).
- **Fixed failures:** Tests that failed in the baseline and are now fixed.
- **Unchanged failures:** Tests that continue to fail.

### 4. CI/CD Testing Dashboard
View CI test runs under the **CI/CD Testing** tab in the React dashboard:
- Inspect recent runs, git commit SHAs, branch names, and actors.
- View failure breakdowns and individual test mismatches.
- To upload test runs from your CI pipeline or local machine, add the `--upload` flag:
  ```bash
  export AGENTRELIABILITY_ENDPOINT="http://localhost:8000"
  export AGENTRELIABILITY_API_KEY="ar_..."
  agentreliability test --project ./demo_project/agent-tests --output results.json --upload
  ```

### 5. Automated Tests Summary
- **Backend Tests:** 51 passing tests (`cd backend && python -m pytest -v`)
- **SDK & CLI Tests:** 33 passing tests (`cd sdk && python -m pytest -v`)
- **Total Test Suite:** 84 passing tests across the repository.

## Out of scope so far
Authentication for dashboard UI, billing, external model execution APIs, async python generator tracing.


