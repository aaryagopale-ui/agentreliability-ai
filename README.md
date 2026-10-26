# 🤖 AgentReliability AI

> **Developer Infrastructure Platform for AI Agent Tracing, Testing, Regression Detection, and Continuous Reliability.**

AgentReliability AI gives engineering teams enterprise-grade observability and automated regression testing for AI agents. Turn production traces into deterministic regression tests in one click, catch behavioral changes before deploying, and analyze agent failures with ground-truth execution evidence.

---

## 🌟 Key Platform Capabilities

1. **Python Tracing SDK (`agentreliability`)**:
   - Zero-overhead decorators (`@monitor.trace_agent`, `@monitor.trace_tool`).
   - Automatic parent-child nested tool tracking.
   - Built-in PII and credential sanitization (OpenAI keys, AWS keys, Bearer tokens, emails).
   - Defensive architecture: monitoring never alters or breaks the developer's agent.

2. **Visual Execution Waterfall**:
   - Real-time latency tracking and timeline inspection.
   - Chronological tool call waterfall with relative timing ruler.
   - Expandable argument and output inspection with payload size limiting.

3. **Trace-to-Test Regression Engine**:
   - Convert live execution traces into reusable regression test cases in one click.
   - Deterministic replay simulation without paid LLM or external API costs.
   - Automatic sequence mismatch, schema drift, and latency regression detection.

4. **Evidence-Based AI Failure Analysis**:
   - Three-Tier Truth Model separating immutable trace facts, deterministic heuristics, and AI hypotheses.
   - Automated root-cause isolation identifying the failing step, tool, and preceding sequence.
   - Optional local Ollama LLM integration (`http://127.0.0.1:11434`) with strict prompt injection defenses.

5. **Multi-Tenant Security & API Key Management**:
   - Project-scoped data isolation across all endpoints.
   - Scrypt password hashing with constant-time verification.
   - Double-submit CSRF protection and SHA-256 hashed API keys.

6. **CLI & GitHub Actions CI/CD**:
   - Automated test runner: `agentreliability test --project ./tests --baseline baseline.json --upload`.
   - Rich Markdown reporting directly in `$GITHUB_STEP_SUMMARY`.

---

## 📌 Ports & Local Development Setup

| Service | Port | Description |
| :--- | :---: | :--- |
| **FastAPI Backend** | `8001` | Ingestion, replay engine, and REST APIs |
| **React Frontend** | `5174` | Dashboard and execution timelines |
| **Local Ollama LLM** | `11434` | (Optional) Local offline model diagnostics |
| **CropBazaar** | `8000` | *Independent service — completely untouched by AgentReliability* |

---

## ⚡ Five-Minute Quickstart

### Recommended: 1-Command Startup with Auto Port Management
```bash
# 1. Install SDK in editable mode
pip install -e sdk

# 2. Initialize environment & database
agentreliability init

# 3. Start services (handles port conflicts & reuses existing instances automatically)
agentreliability dev
```
*(Run `agentreliability doctor` at any time to diagnose Python, Node, database, or port issues).*

### Alternative: Manual Two-Terminal Setup

#### 1. Start the FastAPI Backend (Port 8001)
```bash
cd AgentReliability
source backend/.venv/bin/activate
PYTHONPATH=backend uvicorn app.main:app --port 8001 --reload
```
Check health: [http://127.0.0.1:8001/api/health](http://127.0.0.1:8001/api/health)

#### 2. Start the React Frontend (Port 5174)
```bash
cd AgentReliability/frontend
npm run dev
```
Open [http://localhost:5174](http://localhost:5174) in your browser.

### 3. Run the Automated Five-Minute Demo
To see the full end-to-end lifecycle (project creation, API keys, trace capture, test generation, replay, and failure diagnosis) executed in under 1 second:
```bash
python scripts/five_minute_demo.py
```

---

## 📦 Python SDK Quick Example

Install the SDK:
```bash
pip install -e sdk
```

Instrument your Python agent:
```python
import os
from agentreliability import AgentMonitor

# Initialize monitor pointing to port 8001
monitor = AgentMonitor(
    endpoint=os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001"),
    api_key=os.environ.get("AGENTRELIABILITY_API_KEY"),
    capture_io=True,
)

@monitor.trace_tool("search_kb")
def search_kb(query: str) -> list[str]:
    return [f"Article for {query}"]

@monitor.trace_agent("support_agent")
def run_agent(query: str):
    return search_kb(query)

if __name__ == "__main__":
    result = run_agent("pricing inquiry")
    print(result)
    monitor.flush()
```

---

## 📚 Technical Documentation

Explore our comprehensive documentation:
- ⚡ [**10-Minute Developer Quickstart Guide**](docs/QUICKSTART.md) — From installation to Golden Baseline comparison.
- 🧑‍💻 [**Private Developer Pilot Guide**](docs/DEVELOPER_PILOT.md) — 15-minute evaluation exercise, success criteria, and results template for 3–5 external testers.
- 🐍 [**Python SDK Guide**](docs/SDK_GUIDE.md) — Deep dive into decorators, nested calls, and redaction.
- 🛠️ [**CLI & CI/CD Guide**](docs/CLI_GUIDE.md) — Command reference and GitHub Actions workflows.
- 🔄 [**Trace-to-Test Guide**](docs/TRACE_TO_TEST.md) — Turning production traces into deterministic tests.
- 🔧 [**Troubleshooting Guide**](docs/TROUBLESHOOTING.md) — Step-by-step solutions for all common error states.

---

## 📁 Repository Structure

```
AgentReliability/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app setup and middleware
│   │   ├── traces_api.py        # Live trace ingestion endpoints
│   │   ├── replay.py            # Deterministic simulation replay engine
│   │   ├── failure_engine.py    # Evidence-based diagnostic engine
│   │   ├── local_ai.py          # Local Ollama LLM integration
│   │   ├── redaction.py         # PII & secret redactor
│   │   ├── security.py          # Scrypt password hashing & session auth
│   │   ├── database.py          # SQLite database connection manager
│   │   └── migrations/          # Versioned schema migrations
│   └── tests/                   # 124+ automated backend tests
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main dashboard routing & sidebar
│   │   ├── pages/
│   │   │   ├── GettingStarted.jsx  # Interactive 10-step onboarding flow
│   │   │   ├── LiveMonitoring.jsx  # Execution waterfall timeline
│   │   │   ├── RegressionTesting.jsx # Baseline comparison diffs
│   │   │   ├── FailureAnalysis.jsx   # Root cause evidence drawer
│   │   │   ├── TestCases.jsx       # Generated test case management
│   │   │   └── ApiKeys.jsx         # Project API key management
│   │   └── components/
│   │       ├── TraceExecutionTimeline.jsx # Visual timeline & waterfall
│   │       └── ProjectSwitcher.jsx # Multi-tenant project selector
├── sdk/
│   ├── src/agentreliability/
│   │   ├── monitor.py           # Public AgentMonitor & decorators
│   │   ├── cli.py               # agentreliability CLI runner
│   │   ├── redaction.py         # Local client-side secret scrubbing
│   │   ├── transport.py         # Defensive background event sender
│   │   └── engine.py            # Client-side deterministic test replay
│   └── tests/                   # 37+ automated SDK & CLI tests
├── examples/                    # 5 runnable, tested integration examples
├── scripts/
│   └── five_minute_demo.py      # Automated reproducible 5-minute demo
└── docs/                        # Complete technical guides
```

---

## 🧪 Running the Test Suites

### Backend Tests
```bash
backend/.venv/bin/pytest backend/tests/ -v
```

### SDK and CLI Tests
```bash
PYTHONPATH=sdk/src backend/.venv/bin/pytest sdk/tests/ -v
```

### Frontend Build
```bash
cd frontend && npm run build
```
