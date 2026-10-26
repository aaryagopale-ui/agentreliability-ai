# 🧑‍💻 AgentReliability AI: Private Developer Pilot Guide

Welcome to the **AgentReliability AI Private Developer Pilot**! Thank you for testing AgentReliability. This guide is designed for **3–5 external developers** to evaluate the platform in an isolated, private local environment.

> 🔒 **100% Local & Private:**
> - All telemetry, database records, and trace data remain strictly on your local machine (`http://127.0.0.1:8001` with SQLite).
> - **Zero network egress:** No code, model weights, prompts, or traces are transmitted externally.
> - Any references to `https://api.agentreliability.com` or `https://app.agentreliability.com` in documentation are **illustrative placeholders for future hosted versions and are currently unavailable**.
> - **Zero paid dependencies:** You do not need an OpenAI, Anthropic, or cloud API key.

---

## 1. Tester Prerequisites & Network Requirements

Before starting, ensure your machine has:

- **Operating System:** macOS (Apple Silicon or Intel), Linux (Ubuntu 20.04+, Debian, Fedora, Arch), or Windows (via WSL2 recommended).
- **Python:** `3.9` or higher (`3.10`, `3.11`, or `3.12` recommended). Check with `python3 --version`.
- **Node.js:** `18.0` or higher with `npm`. Check with `node --version`.
- **Estimated Time:** **15 minutes** to complete the entire evaluation.

### 🌐 Network & Internet Access Scope
| Phase | Network Access Needed? | Details |
| :--- | :---: | :--- |
| **Initial Installation** | **Yes (Outbound Only)** | Required to fetch standard open-source dependencies via PyPI (`pip install`) and npm registry (`npm install`). |
| **Runtime Agent Tracing** | **No (100% Offline)** | Traces travel solely over local loopback (`http://127.0.0.1:8001`). No data leaves your machine. |
| **Golden Baseline Comparison** | **No (100% Offline)** | Baseline regression comparison runs completely on the local FastAPI engine. |
| **Offline Test Runner** | **No (100% Offline)** | Replay assertions run in pure Python without starting any network listeners. |

---

## 2. Step-by-Step Local Setup

### Step 2.1: Obtain & Extract the Clean Private Pilot Source Package

If you received the private sanitized distribution package archive (`agentreliability-pilot-v0.1.0.tar.gz`):

```bash
# 1. (Optional) Verify archive checksum against the distributed manifest
shasum -a 256 agentreliability-pilot-v0.1.0.tar.gz
# Compare against the SHA-256 published in agentreliability-pilot-v0.1.0-manifest.txt

# 2. Extract archive
tar -xzf agentreliability-pilot-v0.1.0.tar.gz
cd AgentReliability-pilot-v0.1.0
```

*(Alternatively, if you received direct access to the private repository, clone it and `cd AgentReliability`).*

### Step 2.2: Setup Python Virtual Environment & Install Dependencies
Open a terminal in the extracted directory:

```bash
# Create and activate an isolated virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Windows (cmd): .venv\Scripts\activate.bat
                                # On Windows (PowerShell): .venv\Scripts\Activate.ps1

# Install backend dependencies and the agentreliability SDK (in editable mode)
pip install -r backend/requirements.txt
pip install -e sdk
```

### Step 2.3: Setup the React Dashboard
```bash
# In the project root, install frontend packages (one-time setup)
cd frontend
npm install
cd ..
```

### Step 2.4: Initialize & Start Local Services

You can start the entire stack with minimal commands:

```bash
# 1. Initialize environment and database
agentreliability init

# 2. Start services with automatic port collision resolution
agentreliability dev
```

`agentreliability dev` will:
- Automatically check ports `8001` (backend) and `5174` (dashboard).
- If port `8001` is already in use by a compatible AgentReliability backend, it **reuses it safely**.
- If port `8001` is occupied by an external service, it **automatically selects an available alternative port (e.g. 8002) without terminating any existing process**.
- Sets frontend proxy and SDK endpoints automatically.
- Displays a clean summary with dashboard URL and active ports.

*(Tip: Run `agentreliability doctor` at any time to verify system health, Node, Python, database, and ports).*

#### Alternative: Manual Two-Terminal Setup
If you prefer running separate terminal windows:

**Terminal 1 (Backend Server):**
```bash
source .venv/bin/activate
PYTHONPATH=backend uvicorn app.main:app --port 8001 --reload
```
*Health Check:* Open [http://127.0.0.1:8001/api/health](http://127.0.0.1:8001/api/health). You should see `{"status":"ok"}`.

**Terminal 2 (Frontend Dashboard):**
```bash
cd frontend
npm run dev
```
*Health Check:* Open [http://localhost:5174](http://localhost:5174) in your browser. You should see the AgentReliability dashboard login screen.

---

## 3. The 15-Minute Testing Exercise

### Exercise 1: Register an Account & Create a Project (2 mins)
1. Open [http://localhost:5174](http://localhost:5174).
2. Click **Create an account** and sign up with a test email (e.g. `tester1@example.com`). All passwords are encrypted locally using scrypt.
3. You will be placed into your default project.
4. Click **API Keys & SDK** in the sidebar.
5. Click **+ Generate New API Key**, label it `Pilot Tester Key`, and click **Generate**.
6. **Copy your API key** (`ar_live_...`).

---

### Exercise 2: Configure Environment & Test CLI Status (2 mins)
In a new terminal tab (Terminal 3):

```bash
source .venv/bin/activate

# Set environment variables for the SDK
export AGENTRELIABILITY_ENDPOINT="http://127.0.0.1:8001"
export AGENTRELIABILITY_API_KEY="ar_live_paste_your_copied_key_here"

# Run the health check command
agentreliability status
# (You can also run: python -m agentreliability status)
```

**Success Criteria:**
- Output reports `✅ Backend Server : ONLINE and healthy`.
- Output reports `✅ API Key Auth : VALID and authorized (Project: '...')`.
- Exit code is `0`.

---

### Exercise 3: Run the Simple Support Triage Agent (3 mins)
AgentReliability includes a ready-to-use, zero-dependency customer support triage agent in [`examples/quickstart_agent.py`](file:///Users/aaryagopale/Desktop/AgentReliability/examples/quickstart_agent.py). It uses pure Python functions with simulated latencies:

```bash
python examples/quickstart_agent.py
```

**Terminal Output:**
```text
[Agent] Triaging ticket for cust_99: 'Urgent: unexpected double charge on invoice' (regressed=False)...
  ↳ Classified as billing (urgency: high)
  ↳ Customer tier: enterprise
  ↳ Assigned to: alice@support.example.com (vip-billing)
[Agent] Result: {'status': 'triaged', 'customer_id': 'cust_99', 'category': 'billing', 'assigned_to': 'alice@support.example.com', 'queue': 'vip-billing'}
[Agent] Execution trace delivered to AgentReliability.
```

---

### Exercise 4: Inspect the Visual Execution Waterfall (2 mins)
1. In your browser at [http://localhost:5174](http://localhost:5174), click **Live Monitoring** in the sidebar.
2. Observe your execution of `support_triage_agent` displayed with status `success` and duration (~30–40ms).
3. Click the execution card to expand the **Visual Execution Waterfall**:
   - Verify all 3 tool calls are displayed: `classify_ticket`, `lookup_customer`, and `assign_specialist`.
   - Click each tool call to verify recorded input arguments and output values.

---

### Exercise 5: Create a Golden Baseline & Verify Matching Compare (2 mins)
1. On the expanded execution card in **Live Monitoring**, click **Save as Golden Baseline**.
2. Name it `Support Triage Golden Baseline` and click **Save**.
3. Note the candidate trace ID or query the active baseline via the CLI:
   ```bash
   agentreliability compare --trace <your_trace_id> --agent support_triage_agent
   ```

**Success Criteria:**
- Verdict displays `PASSED`.
- Differences: `0 breaking, 0 performance, 0 informational`.
- Exit code is `0`.

---

### Exercise 6: Introduce a Breaking Regression & Detect via CLI (2 mins)
Run the agent in `regressed` mode. This simulates a broken agent that omits the required `lookup_customer` tool call:

```bash
python examples/quickstart_agent.py regressed
```

Now compare the new regressed trace against your Golden Baseline:
```bash
agentreliability compare --trace <regressed_trace_id> --agent support_triage_agent
```

**Success Criteria:**
- Verdict displays `REGRESSION`.
- The CLI specifically flags the missing tool: `❌ [BREAKING] missing_tool_call: Missing expected tool call(s): ['lookup_customer']`.
- The CLI highlights the sequence mismatch: `❌ [BREAKING] tool_sequence_mismatch`.
- Process exits with **code 1**, effectively blocking broken agent deployments.

---

### Exercise 7: Test Offline CI/CD Assertions (`--fail-on-regression`) (2 mins)
Verify the offline test runner against pre-recorded agent test cases:

```bash
agentreliability test \
  --project ./examples/05_cli_regression_demo/tests \
  --baseline ./examples/05_cli_regression_demo/baseline.json \
  --fail-on-regression
```

**Success Criteria:**
- 2 test cases discovered and executed.
- `Regression Analysis: 0 breaking regression(s)`.
- Exit code is `0`.

---

## 4. Summary of Success Criteria

| Milestone | Expected Behavior | Verify With | Pass? |
| :--- | :--- | :--- | :---: |
| **M1: Installation** | SDK installs cleanly into virtual environment with 0 errors. | `pip list \| grep agentreliability` | [ ] |
| **M2: CLI Diagnostics** | `agentreliability status` reports online backend and valid key. | Exit code `0` | [ ] |
| **M3: Trace Ingestion** | `quickstart_agent.py` sends trace without altering agent behavior. | Console output & Live Monitoring | [ ] |
| **M4: Visual Waterfall** | Waterfall renders timeline with all 3 tool calls and captured inputs/outputs. | Web UI at `http://localhost:5174` | [ ] |
| **M5: Golden Baseline** | Trace is saved as Golden Baseline with active version `1`. | Golden Baselines page / CLI | [ ] |
| **M6: Matching Compare** | Matching trace passes comparison with 0 differences. | Exit code `0` | [ ] |
| **M7: Regression Detection** | Regressed trace flags missing `lookup_customer` tool and exits with code 1. | Exit code `1` | [ ] |
| **M8: Offline Runner** | `agentreliability test --fail-on-regression` executes local test suite. | Exit code `0` | [ ] |

---

## 5. Security & Bug Reporting Guidelines

To protect your privacy and project security:

### How to Report Bugs Safely
- **Never include raw API keys:** Redact keys to `ar_live_••••` before pasting logs.
- **Do not share database files:** Do not send `backend/agentreliability.db` or `.env` files.
- **Use sanitized CLI outputs:** Copy terminal output directly; the AgentReliability CLI automatically masks secret keys and email addresses.
- **Bug Report Template:**
  ```text
  Issue Title: [Component] Brief description of bug
  OS / Platform: (e.g. macOS 14.5 / Ubuntu 22.04 / Windows WSL2)
  Python Version: (e.g. 3.11.8)
  Steps to Reproduce:
    1. ...
    2. ...
  Observed Output:
    ... (redacted)
  Expected Output:
    ...
  ```
- Send bug reports via your designated pilot channel or open an issue on the repository issue tracker.

---

## 6. Pilot Feedback Questionnaire

After completing the exercises, please spend 2 minutes answering these questions:

### Section A: Setup & Onboarding
1. **Total Setup Time:** Approximately how many minutes did it take from `git clone` to running `agentreliability status`?
   - [ ] < 5 minutes
   - [ ] 5–10 minutes
   - [ ] 10–15 minutes
   - [ ] > 15 minutes (please describe where you got stuck)
2. **Setup Friction:** Did you encounter any difficulty with Python virtual environments, Node/npm dependencies, or port availability?
3. **Clarity of Instructions:** Were any steps in the Quickstart or CLI commands ambiguous?

### Section B: Product Experience & Value
4. **Visual Waterfall:** How useful was the execution waterfall timeline in understanding your agent's internal tool calls and timing?
   - [ ] Extremely useful
   - [ ] Somewhat useful
   - [ ] Neutral / Not useful
5. **Golden Baseline Comparison:** Did the regression diffs clearly identify the missing tool call and sequence mismatch without false positives?
   - [ ] Yes, completely clear
   - [ ] Partially clear
   - [ ] Unclear / confusing
6. **CLI Integration:** Would you integrate `agentreliability compare` or `agentreliability test --fail-on-regression` into your GitHub Actions or CI/CD pipelines?
   - [ ] Definitely yes
   - [ ] Probably yes
   - [ ] Unlikely / No

### Section C: Overall Impression & Net Promoter Score (NPS)
7. **Likelihood to Recommend:** On a scale of 0 to 10, how likely are you to recommend AgentReliability AI to another AI agent developer?
   `[ 0  1  2  3  4  5  6  7  8  9  10 ]`
8. **What is the single most valuable feature you tested today?**
9. **What is the #1 missing feature or improvement you would need before using this in production?**

---

## 7. Pilot Results Recording Template (For Pilot Coordinators)

Use this table to record and track results across your 3–5 external developer testers:

| Tester ID | Platform / OS | Python | Setup Time | Tasks Completed (1–7) | Problems Encountered | Willingness to Use Again (0–10) | Notes / Action Items |
| :---: | :--- | :---: | :---: | :---: | :--- | :---: | :--- |
| **Tester #1** | macOS (Apple Silicon) | 3.11 | | | | | |
| **Tester #2** | Ubuntu Linux 22.04 | 3.10 | | | | | |
| **Tester #3** | Windows 11 (WSL2) | 3.11 | | | | | |
| **Tester #4** | macOS (Intel) | 3.12 | | | | | |
| **Tester #5** | Debian Linux 12 | 3.9 | | | | | |

---

*Thank you for participating in the AgentReliability AI Developer Pilot!*

