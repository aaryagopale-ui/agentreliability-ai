# 🚀 START HERE: AgentReliability AI Quickstart Guide

> **Welcome to the AgentReliability AI Developer Pilot!**  
> This guide is designed so you can get up and running, capture your first AI agent trace, and run an automated regression test in under **5 minutes**—with zero prior knowledge and without needing external assistance.

---

## ⚡ Step 1: The One-Command Launch

Open your terminal in this extracted folder and run the launcher for your operating system:

### 🍎 macOS, 🐧 Linux, or 🪟 Windows WSL2:
```bash
./start.sh
```

### 🪟 Windows (Command Prompt or PowerShell):
```cmd
start.bat
```

### What this command does automatically:
1. **Checks Prerequisites:** Verifies Python (>= 3.9) and Node.js (>= 18).
2. **Creates Isolated Environment:** Sets up an isolated Python virtualenv at `backend/.venv` and installs dependencies.
3. **Collision-Safe Port Detection:** Probes ports `8001` (backend) and `5174` (dashboard). If occupied, selects the next free port without touching other processes.
4. **Initializes Local SQLite:** Sets up your local workspace database and instance identity.
5. **Opens Your Browser:** Automatically launches your web browser to the dashboard (e.g. `http://localhost:5174`).

---

## 💻 Manual Setup (If you prefer running commands manually)

If you prefer not running the automated script, you can execute these standard steps:

```bash
# 1. Create and activate a Python virtual environment
python3 -m venv backend/.venv
source backend/.venv/bin/activate  # On Windows: backend\.venv\Scripts\activate

# 2. Install backend dependencies and SDK
pip install -r backend/requirements.txt
pip install -e sdk

# 3. Install frontend dashboard dependencies
npm --prefix frontend install

# 4. Start backend and dashboard
agentreliability dev
```

---

## 🧭 Step 2: What to Do Once the Dashboard Opens

When the dashboard opens in your browser at `http://localhost:5174`:

### 1. Create an Account or Sign In
- Enter any email address and password (e.g., `developer@company.com`).
- *Note:* All credentials and data are stored in your local SQLite database on your machine (`backend/agentreliability.db`). Nothing is sent to an external server.

### 2. Choose Your Experience (Zero-Code Demo vs. Live Python Agent)

#### 🌟 Option A: One-Click Demo (Instant exploration — No code required)
1. Go to **Getting Started** in the left sidebar.
2. Click the blue button: **"Load Demo Agent & Traces"**.
3. In 2 seconds, synthetic real-world customer support agent data will populate:
   - **Trace 1 (Success):** Multi-step refund workflow with 4 verified tool calls.
   - **Trace 2 (Tool Failure):** Downstream payment timeout with deterministic root-cause analysis.
   - **Trace 3 (Breaking Regression):** Skipped verification check flagged by Golden Baseline comparison.
4. Click **Live Monitoring**, **Failure Analysis**, and **Golden Baselines** to inspect them.

#### 🐍 Option B: Run a Real Python Agent
1. In **Getting Started**, click **Step 3** to generate an active plaintext API key and copy the environment variables:
   ```bash
   export AGENTRELIABILITY_ENDPOINT="http://127.0.0.1:8001"
   export AGENTRELIABILITY_API_KEY="ar_live_your_actual_key"
   ```
2. Activate your project virtual environment in your terminal:
   ```bash
   source backend/.venv/bin/activate  # Windows: backend\Scripts\activate
   ```
3. Run the multi-scenario demo agent:
   ```bash
   # Run standard execution (establishes baseline)
   python demo_agent.py success

   # Run regression scenario (deliberately omits search_docs to trigger regression verdict)
   python demo_agent.py regression
   ```
4. Or run the zero-dependency triage agent:
   ```bash
   python examples/quickstart_agent.py
   ```
5. Watch the live execution waterfall appear immediately in **Live Monitoring**!
6. Run an automated offline regression test:
   ```bash
   agentreliability test --project demo_project --fail-on-regression
   ```

---

## 🩺 System Diagnostics & Troubleshooting

If you ever encounter an issue or want to verify your setup, run the built-in diagnostic doctor:

```bash
agentreliability doctor
```

This tests:
- Python version, virtualenv, and packages (`fastapi`, `uvicorn`, `pydantic`).
- Node.js version, npm, and `frontend/node_modules`.
- SQLite database tables and schema version.
- Port status on `8001` and `5174`.
- Backend health and API key authorization.

### Common Questions & Troubleshooting:

| Symptom | Cause | Solution |
| :--- | :--- | :--- |
| **Safari "Can't Connect to Server" at 127.0.0.1** | Safari requires listening on IPv4 (0.0.0.0) rather than only IPv6 loopback (`::1`). | Resolved: Vite dev server binds to `0.0.0.0`, allowing both `http://localhost:5174` and `http://127.0.0.1:5174` in Safari, Chrome, and Firefox. |
| **Login page shows "Backend Server Unreachable"** | Backend process is stopped or listening on a non-default port. | Run `agentreliability dev` or check `agentreliability doctor` to confirm backend is running on port 8001. |
| **`ModuleNotFoundError: No module named 'agentreliability'`** | Terminal is running outside the virtual environment. | Run `source backend/.venv/bin/activate` or invoke via `backend/.venv/bin/python ...`. |
| **"Invalid email or password" after switching directories** | Local databases are isolated per folder (`backend/agentreliability.db`) to ensure data safety. | Run `agentreliability import-db --source /path/to/other/agentreliability.db` or register a new user in the current workspace. |
| **"Unknown scenario: regression"** | Demo agent script was expecting valid scenarios. | Run `python demo_agent.py regression`. Both `success`, `regression`, `tool_failure`, and `timeout` are fully supported. |
| **"Ollama Offline" in Failure Analysis** | Ollama daemon is not running locally. | **Deterministic root-cause mode is 100% functional without Ollama.** To enable AI hypotheses, run `ollama serve`. |

---

## 📚 In-Depth Documentation

Detailed guides are included right inside the package:
- 📖 **[Developer Pilot Guide](docs/DEVELOPER_PILOT.md):** 15-minute testing plan and feedback template.
- 🔧 **[Troubleshooting Guide](docs/TROUBLESHOOTING.md):** Detailed fixes for port conflicts, SDK errors, and CI/CD pipelines.
- ⌨️ **[CLI Guide](docs/CLI_GUIDE.md):** Full documentation for `agentreliability test`, `compare`, `dev`, `doctor`, and `import-db`.
- 🔌 **Framework Guides:**
  - [LangChain Integration](docs/LANGCHAIN_INTEGRATION.md)
  - [LangGraph Integration](docs/LANGGRAPH_INTEGRATION.md)
  - [CrewAI Integration](docs/CREWAI_INTEGRATION.md)

