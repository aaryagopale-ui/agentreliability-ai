# 🔧 AgentReliability AI: Troubleshooting & Error Resolution Guide

This guide provides simple, step-by-step instructions to resolve common errors and setup issues.

---

## Quick Diagnostic Check

Run the comprehensive system doctor command to inspect Python, Node, database, and ports:
```bash
agentreliability doctor
```
*(You can also run `agentreliability status` to verify backend connectivity and API key authorization).*

---

## 1. Port Conflicts: "Address already in use" on Port 8001 or 5174

### Symptoms:
- `OSError: [Errno 48] error while attempting to bind on address ('127.0.0.1', 8001): address already in use`
- Vite dev server port collision on `5174`
- Trace upload or dashboard proxy failures

### How AgentReliability Automatically Handles This:
Run the stack using `agentreliability dev`:
```bash
agentreliability dev
```
1. **Compatible Instance Reuse:** If port 8001 is already running an active, compatible AgentReliability backend, `agentreliability dev` will automatically reuse it (safely isolated by project API keys and headers) instead of crashing.
2. **Safe Fallback Selection:** If port 8001 or 5174 is in use by another external application (e.g. Docker, other web servers), AgentReliability **never terminates external processes**. Instead, it automatically selects the next available port (e.g. `8002` or `5175`).
3. **Automatic Synchronization:** When ports change, `agentreliability dev` automatically configures Vite's proxy target (`API_TARGET`) and writes `.agentreliability.json` so the Python SDK and CLI connect to the right port with zero manual environment variable export needed.

### Manual Port Override:
If you want to manually assign custom ports:
```bash
agentreliability dev --backend-port 8005 --frontend-port 5180
```

---

## 2. Backend Server Offline or Unreachable

### Symptoms:
- CLI outputs: `❌ Backend Server : OFFLINE or unreachable`
- Agent log: `agentreliability: could not reach the backend; traces were dropped`
- Web browser says `Unable to connect to 127.0.0.1:8001`

### Root Cause:
The FastAPI backend server is not running on port `8001` (or your configured port).

### Resolution:
1. Run `agentreliability dev` to start all services automatically.
2. Or start backend manually:
   ```bash
   cd AgentReliability
   source backend/.venv/bin/activate
   PYTHONPATH=backend uvicorn app.main:app --port 8001 --reload
   ```
3. Test health: Visit [http://127.0.0.1:8001/api/health](http://127.0.0.1:8001/api/health). You should see `{"status":"ok"}`.
   > ⚠️ **Port Note:** Do not use port `8000`. Port `8000` is reserved for CropBazaar. AgentReliability runs on `8001`.

---

## 3. Invalid or Unrecognized API Key

### Symptoms:
- CLI outputs: `❌ API Key Auth : INVALID (HTTP 401 Unauthorized)`
- Agent log: `backend rejected the traces (HTTP 401)`

### Root Cause:
The string in `AGENTRELIABILITY_API_KEY` does not match any active key in the database, or contains typos/trailing spaces.

### Resolution:
1. Log into the dashboard at [http://localhost:5174](http://localhost:5174).
2. Go to **API Keys & SDK** (or **Getting Started**).
3. Click **+ Generate New API Key**.
4. Copy the complete key (starts with `ar_live_`).
5. Re-export in your terminal:
   ```bash
   export AGENTRELIABILITY_API_KEY="ar_live_your_new_key_here"
   ```

---

## 3. Revoked API Key

### Symptoms:
- Traces stop appearing in the dashboard.
- CLI outputs: `HTTP 401 Unauthorized`.

### Root Cause:
The key was explicitly revoked or rotated in the dashboard.

### Resolution:
Once an API key is revoked, it cannot be un-revoked. Generate a new key in **API Keys & SDK** and update your environment variables or CI/CD secrets.

---

## 4. Missing Environment Variables

### Symptoms:
- SDK logs: `agentreliability: no API key (set AGENTRELIABILITY_API_KEY); monitoring is disabled`
- Agent code executes normally, but no traces appear in the dashboard.

### Root Cause:
The required environment variables are not set in the shell running your agent script.

### Resolution:
Run the following in the same terminal before running your agent:
```bash
export AGENTRELIABILITY_ENDPOINT="http://127.0.0.1:8001"
export AGENTRELIABILITY_API_KEY="ar_live_your_copied_key"
```

To persist these between terminal sessions, add them to your `~/.zshrc` or `~/.bashrc`.

---

## 5. Python SDK Not Installed

### Symptoms:
- Python error: `ModuleNotFoundError: No module named 'agentreliability'`

### Root Cause:
The `agentreliability` package is not installed in the currently active Python environment.

### Resolution:
Run pip install in editable mode:
```bash
cd AgentReliability
pip install -e sdk
```
Verify:
```bash
python -c "import agentreliability; print(agentreliability.__version__)"
```

---

## 6. Unauthorized Project Access (Cross-Tenant 403/404)

### Symptoms:
- API response: `HTTP 403 Forbidden` or `HTTP 404 Not Found` when requesting traces or tests.

### Root Cause:
You are trying to access an execution, test, or baseline that belongs to another project. AgentReliability strictly enforces project tenant isolation.

### Resolution:
1. Check your active project in the top-left **Project Switcher** in the sidebar.
2. Switch to the project that owns the resource.
3. Ensure the API key you are using belongs to that specific project.

---

## 7. Trace Ingestion Failure (Payload Too Large or Malformed)

### Symptoms:
- Agent log: `backend rejected the traces (HTTP 413)` or `(HTTP 422)`

### Root Cause:
- **HTTP 413 (Payload Too Large):** Captured tool arguments or output exceeded the 16KB limit.
- **HTTP 422 (Validation Error):** The trace event is missing required fields (`event_id`, `timestamp`, `agent_name`).

### Resolution:
1. If sending large objects, the SDK automatically truncates inputs to 2,000 characters. To lower this limit:
   ```python
   monitor = AgentMonitor(max_payload_chars=1000)
   ```
2. Disable full I/O capturing if inputs contain binary data or large datasets:
   ```python
   monitor = AgentMonitor(capture_io=False)
   ```

---

## 8. No Traces Recorded in Dashboard

### Symptoms:
- "0 executions", "0 live traces" shown in **Live Agent Monitoring**.

### Root Cause:
1. The script exited before the background transport thread sent the events.
2. Monitoring was disabled because no API key was present.

### Resolution:
1. Always call `monitor.flush()` before your Python script exits:
   ```python
   run_my_agent()
   monitor.flush(timeout=3.0)
   ```
2. Verify that `AGENTRELIABILITY_API_KEY` is not empty.

---

## 9. Local LLM / Ollama Unavailable

### Symptoms:
- Failure Analysis page shows: `Deterministic Mode (Ollama Offline)`
- AI Diagnosis reports: `Local Ollama daemon is not reachable at http://127.0.0.1:11434`

### Root Cause:
The Ollama local daemon is not running or not installed.

### Resolution:
1. **Deterministic mode is 100% functional without an LLM.** You can still view confirmed observations, failing tools, preceding steps, and timing anomalies.
2. If you wish to enable AI hypotheses:
   - Install Ollama from [https://ollama.com](https://ollama.com).
   - Start Ollama:
     ```bash
     ollama serve
     ```
   - Pull a lightweight model (e.g. `ollama pull llama3:8b` or `mistral`).
   - Refresh the Failure Analysis page. The badge will switch to **Ollama Ready**.

---

## 10. Regression Comparison Inconclusive

### Symptoms:
- Regression analysis reports: `Inconclusive Evidence` or `Insufficient Step Data`

### Root Cause:
The candidate trace was captured without tool calls, or the baseline test case was missing expected output criteria.

### Resolution:
1. Ensure your agent is instrumented with at least one `@monitor.trace_tool` decorator so execution steps are recorded.
2. In **Test Cases**, click **Edit Test Case** and specify expected tool sequence or expected output fields.

---

## 11. Common CLI Errors & Exit Codes Matrix

### CLI Exit Codes Reference:
| Exit Code | Command | Reason | Resolution |
| :---: | :--- | :--- | :--- |
| `0` | `test` / `compare` | All tests / comparisons passed (or only non-breaking performance warnings). | Expected passing state. CI/CD checks will pass. |
| `1` | `test` | One or more tests failed individual assertions. | Review mismatch details in terminal output. |
| `1` | `test --fail-on-regression` | Breaking regression detected against baseline. | Inspect breaking difference details. Fix code or update baseline. |
| `1` | `test --upload` | Remote upload to backend failed (network/auth error). | Verify `$AGENTRELIABILITY_ENDPOINT` and `$AGENTRELIABILITY_API_KEY`. |
| `1` | `compare` | Breaking regression detected against Golden Baseline. | Inspect the `❌ [BREAKING]` diffs in output. |
| `1` | `status` | Backend offline or API key invalid/revoked. | Start backend on port `8001` or generate a new key. |
| `2` | `test` | Test file/directory does not exist or invalid JSON. | Check `--project` path argument. |
| `2` | `compare` | Neither `--baseline-id` nor `--agent` specified. | Pass `--baseline-id <id>` or `--agent <name>`. |

---

## 12. Local Development vs. Hosted Usage

AgentReliability is built to function identically in local offline environments and hosted deployments:

| Setting | Local Development & Private Pilot | Hosted / Cloud (Future Roadmap) |
| :--- | :--- | :--- |
| **Endpoint URL** | `http://127.0.0.1:8001` | `https://api.agentreliability.com` *(Illustrative placeholder for future hosted versions — currently unavailable)* |
| **Database** | Local SQLite (`backend/agentreliability.db`) | Hosted PostgreSQL or multi-tenant database |
| **API Keys** | Generated in local dashboard | Generated in hosted organization settings |
| **TLS / SSL** | Plain HTTP over loopback | Enforced HTTPS / TLS 1.3 |
| **Ollama Diagnostics** | Local daemon on `127.0.0.1:11434` | Hosted model gateway or deterministic fallback mode |
| **Dashboard** | `http://localhost:5174` (Vite) | Cloud domain (e.g. `app.agentreliability.com` — *illustrative placeholder*) |

> ⚠️ **Pilot Clarification:** All testing in the private developer pilot runs **100% locally**. Do not attempt to route traces to `agentreliability.com` as external domains are illustrative placeholders for future commercial offerings.

---

## 13. Account or Projects Missing Across Different Folders / Ports

### Symptoms:
- Registered on one installation, but opening a fresh installation on another port or folder says `Invalid email or password`.
- Re-registering works, but previous projects, Golden Baselines, or test runs are absent.

### Root Cause:
AgentReliability isolates each local installation directory with its own independent SQLite database (`backend/agentreliability.db`). Changing ports *within the same directory* preserves the database, but a separate directory uses its own isolated database file to prevent accidental cross-project interference.

### Resolution:
1. **To copy accounts and projects into your current workspace:**
   Use the safe `import-db` command:
   ```bash
   # Test in dry-run mode first (read-only verification)
   agentreliability import-db --source /path/to/original/backend/agentreliability.db --dry-run

   # Perform actual import
   agentreliability import-db --source /path/to/original/backend/agentreliability.db
   ```
2. The source database is opened in **read-only mode** (`mode=ro`) and never altered.
3. Target records are imported inside an atomic transaction with conflict protection (`INSERT OR IGNORE`).



