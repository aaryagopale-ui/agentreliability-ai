# 🛠️ AgentReliability AI: CLI & CI/CD Guide

The `agentreliability` command-line tool enables automated test discovery, deterministic replay, baseline regression comparisons, and continuous integration reporting.

---

## 📌 Installation & Quick Check

```bash
pip install -e sdk
python -m agentreliability --help
```

---

## 🚀 Command 1: Setup & Initialization (`init`)

Check prerequisites, verify dependencies, create safe local configuration, and initialize the SQLite database:

```bash
agentreliability init
```

### Options:
- `--install-frontend`: Automatically run `npm install` inside `frontend/` if dependencies are missing.
- `--force`: Overwrite existing `.agentreliability.json`.

---

## 💻 Command 2: Start Development Stack (`dev`)

Starts the local backend and dashboard concurrently with automatic port conflict detection and safe reuse of existing instances:

```bash
agentreliability dev
```

### Key Behaviors:
- Detects if port 8001 (backend) or 5174 (dashboard) is occupied.
- Reuses active compatible AgentReliability instances safely (project-isolated).
- Automatically selects alternative ports (e.g. 8002, 5175) if ports are occupied by external processes.
- **Never terminates external processes automatically.**
- Sets proxy and SDK endpoints automatically via `.agentreliability.json`.

### Options:
- `--backend-port`: Port override for backend (default: 8001).
- `--frontend-port`: Port override for frontend dashboard (default: 5174).
- `--backend-only`: Run only the backend server.
- `--frontend-only`: Run only the frontend dashboard.
- `--host`: Host address to bind (default: 127.0.0.1).
- `--no-banner`: Suppress the startup summary banner.

---

## 🩺 Command 3: System Diagnostics (`doctor`)

Diagnoses Python version, backend dependencies, Node.js, npm, SQLite database tables, and port conflicts with clear, actionable recommendations:

```bash
agentreliability doctor
```

---

## 🔍 Command 4: Environment & Health Check (`status`)

Verify connectivity to the backend and validate your project API key before running test suites:

```bash
agentreliability status
```

### Options:
- `--endpoint, -e`: Backend URL (defaults to `$AGENTRELIABILITY_ENDPOINT` or `http://127.0.0.1:8001`)
- `--api-key, -k`: Project API key (defaults to `$AGENTRELIABILITY_API_KEY`)

### Sample Output:
```
🔍 AgentReliability Environment Check
--------------------------------------------------
Backend Endpoint : http://127.0.0.1:8001
API Key          : ar_live...39a1 (set)
--------------------------------------------------
✅ Backend Server : ONLINE and healthy
✅ API Key Auth   : VALID and authorized for project
--------------------------------------------------
Status: Ready to trace and test AI agents!
```

---

## 🧪 Command 2: Execute Test Suite (`test`)

Discovers all `.json` test cases in a directory and executes deterministic replay assertions:

```bash
agentreliability test --project ./agent-tests
```

### Command Options:
| Flag | Description |
| :--- | :--- |
| `--project, -p` | Directory of `.json` test cases or path to a single test file (default: `./agent-tests`). |
| `--output, -o` | Path to save the resulting JSON test report. |
| `--baseline, -b` | Path to a previous JSON test report to perform regression comparison. |
| `--fail-on-regression` | Exit with code 1 if a breaking regression is detected against the baseline. Preserves backward compatibility when omitted. Informational differences and performance warnings do not trigger exit code 1 unless explicitly classified as breaking. |
| `--upload` | Uploads the test report to the AgentReliability backend for dashboard tracking. |
| `--commit` | Git commit SHA to associate with this CI run. |

### Exit Codes:
- `0`: All tests passed (or backward compatibility preserved when `--fail-on-regression` is omitted and candidate tests pass).
- `1`: One or more tests failed, upload failed, or breaking regressions detected (when `--fail-on-regression` is set).
- `2`: Test path or JSON syntax error.

---

## 📈 Baseline Regression Testing

To catch behavior regressions before merging pull requests:

```bash
agentreliability test \
  --project ./agent-tests \
  --baseline ./baselines/v1.0.json \
  --fail-on-regression \
  --output ./reports/latest.json
```

### Output:
```text
🔍 AgentReliability Test Runner
Discovered 3 test case(s) in './agent-tests'...

  ✅ PASS: Client Authentication Flow (12.0ms)
  ❌ FAIL: Order Fulfillment Flow (28.4ms)
       ↳ sequence_mismatch: Tool-call sequence differs at position 2: expected calculate_tax, observed create_shipment.

--------------------------------------------------
Results: 1 passed, 1 failed of 2 total.
Regression Analysis: 1 breaking regression(s), 0 fixed, 0 performance warning(s), 0 informational.
--------------------------------------------------
```

---

## 🔍 Command 3: Compare Trace Against Golden Baseline (`compare`)

Compare any live or captured trace directly against a saved Golden Baseline using the backend's deterministic regression engine:

```bash
agentreliability compare --trace <trace_id> --agent <agent_name>
```

### Command Options:
| Flag | Description |
| :--- | :--- |
| `--trace, -t` | **(Required)** Candidate trace execution ID to compare. |
| `--baseline-id, -b` | Backend Golden Baseline ID to compare against. |
| `--agent, -a` | Agent name to automatically locate the latest active Golden Baseline (used if `--baseline-id` is omitted). |
| `--tolerance` | Latency increase tolerance percentage before flagging a performance regression (default: `50.0`%). |
| `--endpoint, -e` | Backend URL (defaults to `$AGENTRELIABILITY_ENDPOINT` or `http://127.0.0.1:8001`). |
| `--api-key, -k` | Project API key (defaults to `$AGENTRELIABILITY_API_KEY`). |
| `--output, -o` | Optional file path to save the full JSON regression report. |

### Sample Output (Breaking Regression):
```text
==================================================
🔍 AgentReliability Golden Baseline Comparison
==================================================
Baseline        : [ID: 21] Support Triage V1 Baseline (v1)
Candidate Trace : f9c6c33d08d940aa92e73ad67414efb1
Verdict         : REGRESSION
Summary         : Regressions detected (2 breaking differences).
--------------------------------------------------
Differences     : 2 breaking, 0 performance, 1 informational

Details:
  ❌ [BREAKING] missing_tool_call: Missing expected tool call(s): ['lookup_customer'].
  ❌ [BREAKING] tool_sequence_mismatch: Tool call sequence differs at step 2: expected 'lookup_customer', observed 'assign_specialist'.
  ℹ️ [INFO]     output_value_change: Output field 'queue' value differs from baseline.
--------------------------------------------------
❌ Result: REGRESSION DETECTED (Exit code 1)
```

### Exit Codes:
- `0`: Execution matched Golden Baseline (or only benign performance warnings occurred).
- `1`: Breaking regression detected (missing tool calls, unexpected errors, output schema breaks) or API error.
- `2`: Missing required arguments (e.g. neither `--baseline-id` nor `--agent` specified).

---

## 🤖 GitHub Actions Integration

Create `.github/workflows/agent-tests.yml`:

```yaml
name: AI Agent Regression Tests

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test-agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Dependencies & SDK
        run: |
          pip install -e sdk

      - name: Run Agent Regression Tests
        env:
          AGENTRELIABILITY_ENDPOINT: "https://your-agentreliability-server.com"
          AGENTRELIABILITY_API_KEY: ${{ secrets.AGENTRELIABILITY_API_KEY }}
        run: |
          agentreliability test \
            --project ./examples/05_cli_regression_demo/tests \
            --baseline ./examples/05_cli_regression_demo/baseline.json \
            --output results.json \
            --commit ${{ github.sha }} \
            --upload
```

The CLI automatically detects `$GITHUB_STEP_SUMMARY` and renders a clean markdown report inside your GitHub Action run summary!

