import { useState } from "react";
import { Badge, Button, Card, PageTitle } from "../ui.jsx";

export default function HelpDocs({ goTo }) {
  const [activeDocTab, setActiveDocTab] = useState("quickstart");
  const [copiedCode, setCopiedCode] = useState(null);

  function copyText(text, id) {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedCode(id);
      setTimeout(() => setCopiedCode(null), 2500);
    }
  }

  const DOC_TABS = [
    { id: "quickstart", label: "🚀 Quickstart & Launcher" },
    { id: "troubleshooting", label: "🔧 Troubleshooting & Ports" },
    { id: "cli", label: "⌨️ CLI Commands Reference" },
    { id: "sdk", label: "🐍 Python SDK & Frameworks" },
    { id: "pilot", label: "🧪 Private Pilot & Feedback" },
  ];

  return (
    <div className="space-y-6">
      <PageTitle
        title="Help & Developer Documentation"
        subtitle="Self-service guides, troubleshooting, CLI reference, and SDK examples for AgentReliability AI."
      >
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => goTo && goTo("getting-started")}>
            ← Back to Getting Started
          </Button>
        </div>
      </PageTitle>

      {/* Navigation Tabs */}
      <div className="flex flex-wrap gap-1 border-b border-slate-800 pb-2">
        {DOC_TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveDocTab(tab.id)}
            className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${
              activeDocTab === tab.id
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 1: Quickstart & Launcher */}
      {activeDocTab === "quickstart" && (
        <div className="space-y-4">
          <Card>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <span>One-Command Setup & Launcher</span>
              <Badge tone="indigo">Recommended</Badge>
            </h3>
            <p className="mt-1 text-xs text-slate-300 leading-relaxed">
              AgentReliability includes a self-healing launcher that verifies Python (3.9+) and Node.js (18+), installs isolated virtual environment dependencies, resolves occupied ports without killing other apps, and opens your browser automatically.
            </p>

            <div className="mt-4 space-y-3">
              <div>
                <span className="text-xs font-semibold text-slate-300">🍎 macOS / 🐧 Linux / 🪟 Windows WSL2:</span>
                <div className="relative mt-1">
                  <pre className="rounded-lg bg-slate-950 p-3 font-mono text-xs text-indigo-300 border border-slate-800 overflow-x-auto">
                    ./start.sh
                  </pre>
                  <button
                    onClick={() => copyText("./start.sh", "start_sh")}
                    className="absolute right-2 top-2 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                  >
                    {copiedCode === "start_sh" ? "Copied!" : "Copy"}
                  </button>
                </div>
              </div>

              <div>
                <span className="text-xs font-semibold text-slate-300">🪟 Windows (Command Prompt / PowerShell):</span>
                <div className="relative mt-1">
                  <pre className="rounded-lg bg-slate-950 p-3 font-mono text-xs text-indigo-300 border border-slate-800 overflow-x-auto">
                    start.bat
                  </pre>
                  <button
                    onClick={() => copyText("start.bat", "start_bat")}
                    className="absolute right-2 top-2 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                  >
                    {copiedCode === "start_bat" ? "Copied!" : "Copy"}
                  </button>
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <h3 className="text-sm font-bold text-slate-100">Manual Command Flow (Optional)</h3>
            <p className="mt-1 text-xs text-slate-400">
              If you prefer executing steps manually without launcher scripts:
            </p>
            <div className="mt-3 relative">
              <pre className="rounded-lg bg-slate-950 p-3 font-mono text-xs text-slate-300 border border-slate-800 overflow-x-auto">
{`# 1. Create and activate Python virtual environment
python3 -m venv backend/.venv
source backend/.venv/bin/activate

# 2. Install backend dependencies and SDK
pip install -r backend/requirements.txt
pip install -e sdk

# 3. Install frontend dependencies & start
npm --prefix frontend install
agentreliability dev`}
              </pre>
              <button
                onClick={() =>
                  copyText(
                    "python3 -m venv backend/.venv && source backend/.venv/bin/activate && pip install -r backend/requirements.txt && pip install -e sdk && npm --prefix frontend install && agentreliability dev",
                    "manual_cmd"
                  )
                }
                className="absolute right-2 top-2 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
              >
                {copiedCode === "manual_cmd" ? "Copied!" : "Copy All"}
              </button>
            </div>
          </Card>
        </div>
      )}

      {/* TAB 2: Troubleshooting */}
      {activeDocTab === "troubleshooting" && (
        <div className="space-y-4">
          <Card>
            <h3 className="text-sm font-bold text-slate-100">Quick Diagnostic Command: `doctor`</h3>
            <p className="mt-1 text-xs text-slate-300">
              Run this anytime you encounter an error to test Python, Node.js, SQLite schema, port availability, and auth health:
            </p>
            <div className="mt-2 relative">
              <pre className="rounded-lg bg-slate-950 p-2.5 font-mono text-xs text-emerald-300 border border-slate-800">
                agentreliability doctor
              </pre>
              <button
                onClick={() => copyText("agentreliability doctor", "doc_cmd")}
                className="absolute right-2 top-2 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
              >
                {copiedCode === "doc_cmd" ? "Copied!" : "Copy"}
              </button>
            </div>
          </Card>

          <Card>
            <h3 className="text-sm font-bold text-slate-100">1. Port Conflicts: "Address already in use" on 8001 or 5174</h3>
            <p className="mt-1 text-xs text-slate-300 leading-relaxed">
              <strong>How AgentReliability handles it:</strong> AgentReliability <em>never terminates external processes</em>. When you start with <code className="text-indigo-300 bg-slate-950 px-1 py-0.5 rounded">agentreliability dev</code>, it detects whether port 8001 is running another process. If occupied, it automatically shifts the backend to port 8002 and dashboard to 5175, synchronizing all SDK connections.
            </p>
            <div className="mt-2 text-xs text-slate-400">
              Manual port override: <code className="text-indigo-300 bg-slate-950 px-1 py-0.5 rounded">agentreliability dev --backend-port 8005 --frontend-port 5180</code>
            </div>
          </Card>

          <Card>
            <h3 className="text-sm font-bold text-slate-100">2. Missing Accounts or Data When Opening Fresh Directory</h3>
            <p className="mt-1 text-xs text-slate-300 leading-relaxed">
              AgentReliability isolates data per folder in an independent SQLite database (<code className="text-indigo-300 bg-slate-950 px-1 py-0.5 rounded">backend/agentreliability.db</code>) to prevent test contamination. To safely copy accounts, projects, baselines, and traces from another workspace:
            </p>
            <div className="mt-2 relative">
              <pre className="rounded-lg bg-slate-950 p-2.5 font-mono text-xs text-slate-300 border border-slate-800 overflow-x-auto">
{`# 1. Preview changes (Dry run, read-only)
agentreliability import-db --source /path/to/other/backend/agentreliability.db --dry-run

# 2. Perform safe import
agentreliability import-db --source /path/to/other/backend/agentreliability.db`}
              </pre>
              <button
                onClick={() => copyText("agentreliability import-db --source ../other/backend/agentreliability.db", "imp_cmd")}
                className="absolute right-2 top-2 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
              >
                {copiedCode === "imp_cmd" ? "Copied!" : "Copy"}
              </button>
            </div>
          </Card>

          <Card>
            <h3 className="text-sm font-bold text-slate-100">3. Failure Analysis: "Ollama Offline"</h3>
            <p className="mt-1 text-xs text-slate-300 leading-relaxed">
              <strong>Deterministic mode is 100% functional without an LLM.</strong> You can view confirmed observations, tool error types, preceding steps, and timing anomalies immediately. To optionally enable AI hypotheses, install and run Ollama locally (<code className="text-indigo-300 bg-slate-950 px-1 py-0.5 rounded">ollama serve</code>).
            </p>
          </Card>

          <Card>
            <h3 className="text-sm font-bold text-slate-100">4. Safari "Can't Connect to Server" or Localhost Binding</h3>
            <p className="mt-1 text-xs text-slate-300 leading-relaxed">
              Apple Safari handles IPv6 loopback (`::1`) differently than Chrome. AgentReliability explicitly binds both backend and Vite dev servers to all network interfaces (<code className="text-indigo-300 bg-slate-950 px-1 py-0.5 rounded">0.0.0.0</code>). You can access the dashboard using either <code className="text-indigo-300 bg-slate-950 px-1 py-0.5 rounded">http://localhost:5174</code> or <code className="text-indigo-300 bg-slate-950 px-1 py-0.5 rounded">http://127.0.0.1:5174</code> with equal reliability.
            </p>
          </Card>

          <Card>
            <h3 className="text-sm font-bold text-slate-100">5. Running Agents: `ModuleNotFoundError: No module named 'agentreliability'`</h3>
            <p className="mt-1 text-xs text-slate-300 leading-relaxed">
              If running <code className="text-indigo-300 bg-slate-950 px-1 py-0.5 rounded">python demo_agent.py</code> in a new terminal window fails to find the SDK, activate the local virtual environment first:
            </p>
            <div className="mt-2 relative">
              <pre className="rounded-lg bg-slate-950 p-2.5 font-mono text-xs text-slate-300 border border-slate-800">
{`# Activate backend virtualenv:
source backend/.venv/bin/activate  # Windows: backend\\Scripts\\activate

# Run demo agent with baseline or regression scenarios:
python demo_agent.py success
python demo_agent.py regression`}
              </pre>
            </div>
          </Card>
        </div>
      )}

      {/* TAB 3: CLI Reference */}
      {activeDocTab === "cli" && (
        <div className="space-y-4">
          <Card>
            <h3 className="text-sm font-bold text-slate-100">CLI Commands Overview</h3>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs border border-slate-800">
                <thead>
                  <tr className="bg-slate-950 text-slate-300 border-b border-slate-800 font-semibold">
                    <th className="p-2.5">Command</th>
                    <th className="p-2.5">Description</th>
                    <th className="p-2.5">Typical Usage</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-[11px] text-slate-300">
                  <tr>
                    <td className="p-2.5 text-indigo-300">agentreliability dev</td>
                    <td className="p-2.5 font-sans">Start backend and dashboard with auto port resolution.</td>
                    <td className="p-2.5">agentreliability dev</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 text-indigo-300">agentreliability test</td>
                    <td className="p-2.5 font-sans">Run regression test cases against baseline or previous runs.</td>
                    <td className="p-2.5">agentreliability test --project ./tests --fail-on-regression</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 text-indigo-300">agentreliability compare</td>
                    <td className="p-2.5 font-sans">Compare a candidate trace against a Golden Baseline on backend.</td>
                    <td className="p-2.5">agentreliability compare --trace tr_123 --agent CustomerBot</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 text-indigo-300">agentreliability doctor</td>
                    <td className="p-2.5 font-sans">Comprehensive environment and dependency diagnostics.</td>
                    <td className="p-2.5">agentreliability doctor</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 text-indigo-300">agentreliability import-db</td>
                    <td className="p-2.5 font-sans">Import accounts, baselines, and traces from another SQLite DB.</td>
                    <td className="p-2.5">agentreliability import-db --source /path/to/db</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 text-indigo-300">agentreliability status</td>
                    <td className="p-2.5 font-sans">Verify backend health and API key validity.</td>
                    <td className="p-2.5">agentreliability status</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* TAB 4: SDK & Frameworks */}
      {activeDocTab === "sdk" && (
        <div className="space-y-4">
          <Card>
            <h3 className="text-sm font-bold text-slate-100">Standard Python Instrumentation</h3>
            <p className="mt-1 text-xs text-slate-300">
              Decorate your agent and tool functions with <code className="text-indigo-300">@monitor.trace_agent</code> and <code className="text-indigo-300">@monitor.trace_tool</code>:
            </p>
            <div className="mt-3 relative">
              <pre className="rounded-lg bg-slate-950 p-3 font-mono text-xs text-slate-300 border border-slate-800 overflow-x-auto">
{`from agentreliability import AgentMonitor

monitor = AgentMonitor()

@monitor.trace_tool("search_database")
def search(query: str):
    return [{"title": "Doc 1", "score": 0.95}]

@monitor.trace_agent("support_agent")
def handle_ticket(ticket_text: str):
    docs = search(ticket_text)
    return {"status": "resolved", "sources": len(docs)}

# Execute agent run
result = handle_ticket("How do I reset my password?")
monitor.flush()  # Ensures traces are sent to local backend`}
              </pre>
              <button
                onClick={() =>
                  copyText(
                    'from agentreliability import AgentMonitor\nmonitor = AgentMonitor()\n\n@monitor.trace_tool("search")\ndef search(q): return ["result"]\n\n@monitor.trace_agent("agent")\ndef run(q): return search(q)\n\nrun("test")\nmonitor.flush()',
                    "sdk_py"
                  )
                }
                className="absolute right-2 top-2 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
              >
                {copiedCode === "sdk_py" ? "Copied!" : "Copy"}
              </button>
            </div>
          </Card>

          <Card>
            <h3 className="text-sm font-bold text-slate-100">Popular AI Framework Integrations</h3>
            <div className="grid gap-3 sm:grid-cols-3 mt-3 text-xs">
              <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-1">
                <span className="font-bold text-indigo-300">🦜 LangChain Callback</span>
                <p className="text-[11px] text-slate-400">
                  Attach <code className="text-slate-300">AgentReliabilityCallbackHandler</code> to any LangChain LLM, tool, or agent runner.
                </p>
              </div>
              <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-1">
                <span className="font-bold text-indigo-300">🕸️ LangGraph Tracer</span>
                <p className="text-[11px] text-slate-400">
                  Record graph state transitions, node executions, and conditional branch evaluations automatically.
                </p>
              </div>
              <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-1">
                <span className="font-bold text-indigo-300">👥 CrewAI Multi-Agent</span>
                <p className="text-[11px] text-slate-400">
                  Monitor multi-agent delegation, task handoffs, and hierarchical crew workflows.
                </p>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* TAB 5: Developer Pilot & Feedback */}
      {activeDocTab === "pilot" && (
        <div className="space-y-4">
          <Card>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <span>Developer Pilot & Testing Plan</span>
              <Badge tone="green">Private Pilot v0.1.0</Badge>
            </h3>
            <p className="mt-1 text-xs text-slate-300 leading-relaxed">
              Thank you for testing AgentReliability AI! Your feedback directly shapes our roadmap, developer experience, and regression detection accuracy.
            </p>

            <div className="mt-4 space-y-3 text-xs">
              <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-2">
                <span className="font-bold text-slate-200">15-Minute Pilot Exercise:</span>
                <ol className="list-decimal list-inside space-y-1 text-slate-400">
                  <li>Run <code className="text-indigo-300">./start.sh</code> and confirm the dashboard opens cleanly.</li>
                  <li>Click <strong>"Load Demo Agent & Traces"</strong> in Getting Started.</li>
                  <li>Inspect the <strong>Execution Waterfall</strong> in Live Monitoring.</li>
                  <li>Diagnose the tool timeout in <strong>Failure Analysis</strong>.</li>
                  <li>Review the <strong>Golden Baseline</strong> and breaking regression difference report.</li>
                  <li>Run <code className="text-indigo-300">python examples/quickstart_agent.py</code> to capture your own trace.</li>
                </ol>
              </div>

              <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-1">
                <span className="font-bold text-slate-200">Privacy & Reporting Bugs Without Secrets:</span>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  AgentReliability never uploads real customer data or private keys. When reporting a defect, simply share the diagnostic summary from <code className="text-indigo-300">agentreliability doctor</code>. Sensitive fields like API keys and passwords are automatically redacted.
                </p>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

