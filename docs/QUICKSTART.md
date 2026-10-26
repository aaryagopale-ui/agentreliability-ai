# ⚡ 10-Minute Developer Quickstart Guide

Welcome to **AgentReliability AI**! This guide is designed for any developer to install the SDK, instrument a simple Python agent with **zero paid API dependencies**, capture execution traces, inspect visual waterfalls, save a Golden Baseline, and detect a breaking regression in **under 10 minutes**.

---

## 🏗️ Architecture & Port Reference

AgentReliability can run entirely on your local machine with zero external network access:

| Component | Default URL / Port | Role |
| :--- | :--- | :--- |
| **FastAPI Backend** | `http://127.0.0.1:8001` | Ingestion API, SQLite database, deterministic replay & regression engine |
| **React Dashboard** | `http://localhost:5174` | Visual execution waterfall, Golden Baselines, failure analysis |
| **Local Ollama LLM** | `http://127.0.0.1:11434` | *(Optional)* Offline diagnostic assistant (deterministic fallback active when offline) |
| **CropBazaar** | `http://localhost:8000` | *Independent external service — completely untouched by AgentReliability* |

> 💡 **Local vs. Hosted Usage:**
> - **Local Development & Private Pilot:** Traces are sent to `http://127.0.0.1:8001` and stored in your local SQLite database (`backend/agentreliability.db`). No telemetry, agent code, or data leaves your computer.
> - **Hosted / Cloud (Future):** References to `https://api.agentreliability.com` or `https://app.agentreliability.com` in documentation are **illustrative placeholders for future hosted versions and are currently unavailable**. The entire developer pilot runs 100% locally on your machine.

---

## 📋 Prerequisites

- **Operating System:** macOS, Linux, or Windows (via WSL2)
- **Python:** 3.9+ (Python 3.10, 3.11, or 3.12 recommended)
- **Node.js:** 18+ (with npm)
- **API Keys Needed:** **Zero.** No OpenAI, Anthropic, or external subscriptions required.

---

## 🚀 Step 1: 1-Click Initialization & Starting Services

AgentReliability features automated environment detection and port conflict resolution.

### Option A: The Recommended 1-Command Workflow

```bash
# 1. Install SDK in editable mode
pip install -e sdk

# 2. Check prerequisites and initialize database
agentreliability init

# 3. Start backend and dashboard with automatic port conflict handling
agentreliability dev
```

`agentreliability dev` automatically:
- Checks if ports `8001` (backend) and `5174` (dashboard) are free.
- If port `8001` is already running a compatible AgentReliability instance, it **safely reuses it**.
- If port `8001` is occupied by an external/unrelated process, it **automatically selects an available port (e.g. 8002) without terminating any existing process**.
- Sets the frontend proxy and SDK endpoints automatically.
- Displays a clean terminal summary with dashboard and API URLs.

*(To diagnose any system or dependency issues at any time, run `agentreliability doctor`).*

### Option B: Manual Two-Terminal Setup (Alternative)

If you prefer to start each service in its own terminal:

#### Terminal 1: Backend Server
```bash
# Activate virtual environment
source backend/.venv/bin/activate       # On Windows: backend\Scripts\activate

# Start the FastAPI backend server on port 8001
PYTHONPATH=backend uvicorn app.main:app --port 8001 --reload
```
*Verify:* Visit [http://127.0.0.1:8001/api/health](http://127.0.0.1:8001/api/health). You should see `{"status":"ok"}`.

#### Terminal 2: Vite React Dashboard
```bash
cd frontend
npm install
npm run dev
```
*Verify:* Open [http://localhost:5174](http://localhost:5174) in your browser.

---

## 🔑 Step 2: Create a Project & API Key

1. Open [http://localhost:5174](http://localhost:5174).
2. If logging in for the first time, click **Create an account** (e.g. `dev@example.com`).
3. Click **API Keys & SDK** (or **Getting Started**) in the sidebar.
4. Click **+ Generate New API Key**, label it `Local Dev`, and click **Generate**.
5. **Copy the secret key** immediately (starts with `ar_live_`).
   *(API keys are hashed with SHA-256 and only displayed once. Never commit keys to Git).*

---

## 📦 Step 3: Install the Python SDK

In your agent's Python environment (e.g. `backend/.venv` or your active venv):

```bash
# In editable/development mode
pip install -e sdk

# Or via standard pip
pip install agentreliability
```

Verify the CLI is installed and importable:
```bash
agentreliability --help
# Or alternatively:
python -m agentreliability --help
```

---

## ⚙️ Step 4: Configure Environment & Verify Status

Export the environment variables in your active terminal:

```bash
export AGENTRELIABILITY_ENDPOINT="http://127.0.0.1:8001"
export AGENTRELIABILITY_API_KEY="ar_live_your_copied_key_here"
```

Run the built-in diagnostic command to confirm your backend and API key:

```bash
agentreliability status
```

**Expected output:**
```text
🔍 AgentReliability Environment Check
--------------------------------------------------
Backend Endpoint : http://127.0.0.1:8001
API Key          : ar_live...8Bs0 (set)
--------------------------------------------------
✅ Backend Server : ONLINE and healthy
✅ API Key Auth   : VALID and authorized (Project: 'My Project')
--------------------------------------------------
Status: Ready to trace and test AI agents!
```

---

## 🤖 Step 5: Instrument Your First Agent (Pure Python)

AgentReliability includes a ready-to-run customer support triage agent in `examples/quickstart_agent.py`. It has zero external dependencies:

```python
import os
import sys
import time
from agentreliability import AgentMonitor

# Initialize monitor using environment variables
monitor = AgentMonitor(
    endpoint=os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001"),
    api_key=os.environ.get("AGENTRELIABILITY_API_KEY", ""),
    capture_io=True,
    metadata={"environment": "quickstart", "version": "1.0.0"}
)

@monitor.trace_tool("classify_ticket")
def classify_ticket(ticket_text: str) -> dict:
    time.sleep(0.01)
    is_urgent = any(w in ticket_text.lower() for w in ["urgent", "down", "error", "charge"])
    category = "billing" if "charge" in ticket_text.lower() else "technical"
    return {"category": category, "urgency": "high" if is_urgent else "normal"}

@monitor.trace_tool("lookup_customer")
def lookup_customer(customer_id: str) -> dict:
    time.sleep(0.01)
    return {"customer_id": customer_id, "tier": "enterprise", "sla_hours": 2}

@monitor.trace_tool("assign_specialist")
def assign_specialist(category: str, tier: str) -> dict:
    time.sleep(0.01)
    queue = "vip-billing" if category == "billing" and tier == "enterprise" else "general-support"
    return {"queue": queue, "assigned_to": "alice@support.example.com"}

@monitor.trace_agent("support_triage_agent")
def triage_ticket(customer_id: str, ticket_text: str, regressed: bool = False) -> dict:
    print(f"\n[Agent] Triaging ticket for {customer_id}: '{ticket_text}'...")

    classification = classify_ticket(ticket_text)

    # In regressed mode, customer lookup is omitted!
    if not regressed:
        customer = lookup_customer(customer_id)
        tier = customer["tier"]
    else:
        print("  ⚠️ [Regression] Skipping lookup_customer tool call!")
        tier = "standard"

    assignment = assign_specialist(classification["category"], tier)
    return {
        "status": "triaged",
        "customer_id": customer_id,
        "category": classification["category"],
        "assigned_to": assignment["assigned_to"],
        "queue": assignment["queue"],
    }

if __name__ == "__main__":
    is_regressed = len(sys.argv) > 1 and sys.argv[1].lower() in ("regressed", "--regressed")
    result = triage_ticket("cust_99", "Urgent: unexpected double charge on invoice", regressed=is_regressed)
    print(f"[Agent] Result: {result}")

    # Crucial: flush background event sender before script termination
    monitor.flush()
```

Run the agent in normal mode to capture your **Golden Execution**:

```bash
python examples/quickstart_agent.py
```

**Console output:**
```text
[Agent] Triaging ticket for cust_99: 'Urgent: unexpected double charge on invoice'...
[Agent] Result: {'status': 'triaged', 'customer_id': 'cust_99', 'category': 'billing', 'assigned_to': 'alice@support.example.com', 'queue': 'vip-billing'}
[Agent] Execution trace delivered to AgentReliability.
```

---

## 🌊 Step 6: Inspect the Execution Waterfall in the Dashboard

1. Open [http://localhost:5174](http://localhost:5174).
2. Click **Live Monitoring** in the sidebar.
3. You will see `support_triage_agent` with status `success` and ~35ms duration.
4. Click on the execution to expand the **Visual Waterfall**:
   - `classify_ticket` span (~10ms)
   - `lookup_customer` span (~10ms)
   - `assign_specialist` span (~10ms)
   - Click any tool call to inspect inputs (`ticket_text`, `customer_id`), outputs, and execution metadata.

---

## 🏆 Step 7: Save a Golden Baseline

A **Golden Baseline** marks a verified trace as the benchmark standard of behavior for future runs.

### Option A: From the Dashboard (1 Click)
1. In **Live Monitoring** (or **Golden Baselines**), select your `support_triage_agent` trace.
2. Click **Save as Golden Baseline**.
3. Name it `Support Triage V1 Baseline` and save.

### Option B: Retrieve Baseline or Trace via CLI
```bash
# Query active baselines for your agent:
agentreliability compare --trace <trace_id> --agent support_triage_agent
```

---

## 🔍 Step 8: Compare a Matching Run (Passing Exit Code 0)

Execute your agent a second time:

```bash
python examples/quickstart_agent.py
```

Now compare the candidate trace against the Golden Baseline using the CLI:

```bash
agentreliability compare --trace <candidate_trace_id> --agent support_triage_agent
```

**Output:**
```text
==================================================
🔍 AgentReliability Golden Baseline Comparison
==================================================
Baseline        : [ID: 21] Support Triage V1 Baseline (v1)
Candidate Trace : d9cb1d430dee4cecbb398d33ba263b9f
Verdict         : PASSED
Summary         : All regression checks passed. Behavior exactly matches baseline.
--------------------------------------------------
Differences     : 0 breaking, 0 performance, 0 informational
--------------------------------------------------
✅ Result: PASSED - Matches Golden Baseline (Exit code 0)
```
*(Exit code is `0` — CI/CD pipelines will pass).*

---

## 🚨 Step 9: Catch a Breaking Regression (Exit Code 1)

Now, simulate an inadvertent code change or broken model tool-selection where the agent forgets to look up the customer:

```bash
python examples/quickstart_agent.py regressed
```

Run `agentreliability compare` on the regressed trace:

```bash
agentreliability compare --trace <regressed_trace_id> --agent support_triage_agent
```

**Output:**
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

The CLI:
- Catches the missing tool call (`lookup_customer`) and sequence mismatch.
- Distinguishes breaking regressions from benign informational changes (`output_value_change`).
- Immediately terminates with **exit code 1**, preventing the regressed code from merging into production.

---

## 🧪 Step 10: Run Offline CLI Regression Testing (`--fail-on-regression`)

AgentReliability can also run offline test discovery and regression assertions without network access:

```bash
agentreliability test \
  --project ./examples/05_cli_regression_demo/tests \
  --baseline ./examples/05_cli_regression_demo/baseline.json \
  --fail-on-regression
```

**Output:**
```text
🔍 AgentReliability Test Runner
Discovered 2 test case(s) in 'examples/05_cli_regression_demo/tests'...

  ✅ PASS: Client Authentication Flow (0.0ms)
  ✅ PASS: Order Fulfillment Flow (0.0ms)

--------------------------------------------------
Results: 2 passed, 0 failed of 2 total.
Regression Analysis: 0 breaking regression(s), 0 fixed, 0 performance warning(s), 0 informational.
--------------------------------------------------
```

---

## 🔧 Troubleshooting Quick Reference

| Issue | Typical Cause | Quick Fix |
| :--- | :--- | :--- |
| `❌ Backend Server : OFFLINE` | Backend not running on `8001` | Start backend with `uvicorn app.main:app --port 8001 --reload`. Note: do not use port `8000` (reserved for CropBazaar). |
| `❌ API Key Auth : INVALID (HTTP 401)` | Unset or mistyped API key | Generate a new key in dashboard -> **API Keys & SDK**, then run `export AGENTRELIABILITY_API_KEY="ar_live_..."`. Verify with `agentreliability status`. |
| `No traces in dashboard` | Script exited before background sender flushed | Add `monitor.flush()` before your Python script exits. |
| `CLI exits with code 1` | Breaking regression detected or test failure | Inspect the formatted diffs in console. Use `--fail-on-regression` to enforce Golden Baseline behavior in CI. |
| `Cross-tenant 404 / 403` | Trace or baseline belongs to another project | Ensure your API key belongs to the active project in the top-left Project Switcher. |

For detailed walkthroughs, see [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

---

## 📋 Developer Feedback Checklist

We value your developer experience! After completing this quickstart, please take 30 seconds to review these 4 questions:

1. **Setup Time:** Did the quickstart take under 10 minutes from `git clone` to baseline comparison?
2. **Clarity:** Were any installation steps, environment variables, or CLI options ambiguous?
3. **Friction:** Did you experience any port collisions, missing dependencies, or unhandled exceptions?
4. **Perceived Value:** Did the Golden Baseline comparison clearly surface actionable breaking diffs vs. false positives?

For conducting structured evaluation with external testers or filling out a pilot evaluation scorecard, see the [**Private Developer Pilot Guide**](DEVELOPER_PILOT.md). Happy testing!
