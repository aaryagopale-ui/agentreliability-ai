import { useState, useEffect, useCallback } from "react";
import {
  listProjects,
  listProjectKeys,
  listTraceExecutions,
  listTests,
  listRuns,
  listBaselines,
  createBaseline,
  createProjectKey,
  createProject,
  seedDemoData,
  getDemoStatus,
} from "../api.js";
import { Badge, Button, Card, PageTitle } from "../ui.jsx";

export default function GettingStarted({ currentProject, user, systemInfo, goTo }) {
  const [loading, setLoading] = useState(true);
  const [keys, setKeys] = useState([]);
  const [traces, setTraces] = useState([]);
  const [tests, setTests] = useState([]);
  const [runs, setRuns] = useState([]);
  const [baselines, setBaselines] = useState([]);
  const [newKey, setNewKey] = useState(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedSnippet, setCopiedSnippet] = useState(null);
  const [generatingKey, setGeneratingKey] = useState(false);
  const [creatingBaseline, setCreatingBaseline] = useState(false);
  const [baselineCreatedMsg, setBaselineCreatedMsg] = useState(null);

  // One-click demo state
  const [seedingDemo, setSeedingDemo] = useState(false);
  const [demoFeedback, setDemoFeedback] = useState(null);
  const [demoError, setDemoError] = useState(null);
  const [demoStatus, setDemoStatus] = useState(null);

  // Active step in interactive wizard (1 to 7)
  const [activeStep, setActiveStep] = useState(1);

  const loadProjectState = useCallback(async () => {
    if (!currentProject?.id) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [keysRes, tracesRes, testsRes, runsRes, demoStatusRes, baselinesRes] =
        await Promise.all([
          listProjectKeys(currentProject.id).catch(() => []),
          listTraceExecutions({ limit: 10 }).catch(() => ({ items: [] })),
          listTests().catch(() => []),
          listRuns().catch(() => []),
          getDemoStatus().catch(() => null),
          listBaselines().catch(() => []),
        ]);
      setKeys(keysRes || []);
      const trList = tracesRes?.items || (Array.isArray(tracesRes) ? tracesRes : []);
      setTraces(trList);
      setTests(testsRes || []);
      setRuns(runsRes || []);
      setDemoStatus(demoStatusRes);
      setBaselines(baselinesRes || []);
    } finally {
      setLoading(false);
    }
  }, [currentProject?.id]);

  useEffect(() => {
    loadProjectState();
  }, [loadProjectState]);

  async function handleLoadDemo() {
    if (!currentProject?.id) return;
    setSeedingDemo(true);
    setDemoError(null);
    setDemoFeedback(null);
    try {
      const res = await seedDemoData();
      setDemoFeedback(res);
      await loadProjectState();
      // Jump to step 5 or 6 in wizard to highlight demo traces
      setActiveStep(5);
    } catch (err) {
      setDemoError(
        err?.message ||
          "Failed to load synthetic demo data. Please verify your project selection and connection."
      );
    } finally {
      setSeedingDemo(false);
    }
  }

  const activeKeys = keys.filter((k) => !k.revoked_at);
  const hasActiveKey = activeKeys.length > 0;
  const activeKeySample = newKey?.api_key || (activeKeys[0]?.prefix ? `${activeKeys[0].prefix}••••••••` : null);

  const backendEndpoint =
    systemInfo?.backend_url ||
    (typeof window !== "undefined"
      ? `${window.location.protocol}//${window.location.hostname}:8001`
      : "http://127.0.0.1:8001");

  async function handleQuickGenerateKey() {
    if (!currentProject?.id) return;
    setGeneratingKey(true);
    try {
      const res = await createProjectKey(currentProject.id, { name: "Quickstart Key" });
      setNewKey(res);
      await loadProjectState();
      return res;
    } catch {
      return null;
    } finally {
      setGeneratingKey(false);
    }
  }

  async function handleCopyEnvVars() {
    let keyToUse = newKey?.api_key;
    if (!keyToUse && currentProject?.id) {
      setGeneratingKey(true);
      try {
        const res = await createProjectKey(currentProject.id, { name: "Quickstart Key" });
        setNewKey(res);
        await loadProjectState();
        keyToUse = res?.api_key;
      } catch {
        // Ignored
      } finally {
        setGeneratingKey(false);
      }
    }
    if (keyToUse) {
      copyText(
        `export AGENTRELIABILITY_ENDPOINT="${backendEndpoint}"\nexport AGENTRELIABILITY_API_KEY="${keyToUse}"`,
        "env_vars"
      );
    }
  }

  async function handleCreateBaselineFromTrace(traceId, agentName) {
    if (!currentProject?.id || !traceId) return;
    setCreatingBaseline(true);
    setBaselineCreatedMsg(null);
    try {
      await createBaseline({
        name: `${agentName || "Agent"} Golden Baseline`,
        source_type: "trace",
        source_id: traceId,
        description: `Promoted from trace ${traceId} during onboarding wizard.`,
      });
      setBaselineCreatedMsg(`Golden Baseline created successfully from trace ${traceId}!`);
      await loadProjectState();
    } catch (err) {
      setBaselineCreatedMsg(`Error: ${err?.message || "Failed to create baseline"}`);
    } finally {
      setCreatingBaseline(false);
    }
  }

  function copyText(text, id) {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      if (id === "key") {
        setCopiedKey(true);
        setTimeout(() => setCopiedKey(false), 2500);
      } else {
        setCopiedSnippet(id);
        setTimeout(() => setCopiedSnippet(null), 2500);
      }
    }
  }

  // 7 Explicit Onboarding Wizard Steps
  const wizardSteps = [
    {
      id: 1,
      name: "1. Account & Sign In",
      isDone: Boolean(user?.email),
      statusLabel: user?.email ? "Authenticated" : "Sign In Required",
    },
    {
      id: 2,
      name: "2. Select Project",
      isDone: Boolean(currentProject?.id),
      statusLabel: currentProject?.name ? "Active" : "No Project",
    },
    {
      id: 3,
      name: "3. Generate API Key",
      isDone: hasActiveKey,
      statusLabel: hasActiveKey ? "Key Provisioned" : "Action Needed",
    },
    {
      id: 4,
      name: "4. Connect Agent",
      isDone: traces.length > 0,
      statusLabel: traces.length > 0 ? "Agent Connected" : "Ready to Run",
    },
    {
      id: 5,
      name: "5. Capture Trace",
      isDone: traces.length > 0,
      statusLabel: traces.length > 0 ? `${traces.length} Traces` : "Awaiting Traces",
    },
    {
      id: 6,
      name: "6. Golden Baseline",
      isDone: baselines.length > 0,
      statusLabel: baselines.length > 0 ? "Baseline Active" : "Action Needed",
    },
    {
      id: 7,
      name: "7. Regression Test",
      isDone: runs.length > 0,
      statusLabel: runs.length > 0 ? "Comparison Done" : "Ready to Compare",
    },
  ];

  const completedStepsCount = wizardSteps.filter((s) => s.isDone).length;
  const progressPercent = Math.round((completedStepsCount / wizardSteps.length) * 100);

  // Auto-advance activeStep to first uncompleted step on first load
  useEffect(() => {
    if (!loading) {
      const firstIncomplete = wizardSteps.find((s) => !s.isDone);
      if (firstIncomplete && activeStep === 1 && !user) {
        setActiveStep(1);
      } else if (firstIncomplete && activeStep === 1) {
        setActiveStep(firstIncomplete.id);
      }
    }
  }, [loading]);

  return (
    <div className="space-y-6">
      <PageTitle
        title="Developer Onboarding Wizard"
        subtitle="Complete self-service onboarding: connect your agent, capture visual traces, establish Golden Baselines, and detect regressions."
      >
        <div className="flex items-center gap-2">
          <Button
            onClick={handleLoadDemo}
            disabled={seedingDemo || !currentProject?.id}
            className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold shadow-md shadow-indigo-600/30"
          >
            {seedingDemo ? "Loading Demo Data…" : "Load Demo Agent & Traces"}
          </Button>
          <Button variant="ghost" onClick={loadProjectState} disabled={loading}>
            {loading ? "Checking..." : "Refresh"}
          </Button>
        </div>
      </PageTitle>

      {/* Demo Error Notification */}
      {demoError && (
        <div className="rounded-xl border border-red-500/40 bg-red-950/20 p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-red-300">⚠️ Demo Loading Error</span>
            <Button size="sm" variant="secondary" onClick={handleLoadDemo} disabled={seedingDemo}>
              Retry
            </Button>
          </div>
          <p className="text-xs text-red-200/90">{demoError}</p>
        </div>
      )}

      {/* One-Click Synthetic Demo Hero Card */}
      <div className="rounded-xl border border-indigo-500/30 bg-gradient-to-r from-indigo-950/30 via-slate-900 to-slate-900 p-5 shadow-xl space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-indigo-600 text-xs font-bold text-white">
                🚀
              </span>
              <h3 className="text-sm font-bold text-slate-100">
                Want to explore the product before writing code?
              </h3>
              <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-[10px] font-semibold text-indigo-300 border border-indigo-500/30">
                One-Click Demo
              </span>
            </div>
            <p className="text-xs text-slate-300 max-w-2xl leading-relaxed">
              Click <strong>"Load Demo Agent & Traces"</strong> to populate synthetic customer support agent traces, a tool timeout failure, and a breaking regression comparison instantly.
            </p>
          </div>
          <div className="shrink-0 flex items-center gap-2">
            <Button
              onClick={handleLoadDemo}
              disabled={seedingDemo || !currentProject?.id}
              className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold shadow-lg shadow-indigo-600/30"
            >
              {seedingDemo
                ? "Loading Demo Data…"
                : demoStatus?.demo_loaded
                ? "Reload Demo Traces"
                : "Load Demo Agent & Traces"}
            </Button>
          </div>
        </div>

        {demoFeedback && (
          <div className="rounded-lg bg-indigo-950/50 border border-indigo-500/30 p-3 space-y-2 mt-2">
            <div className="flex items-center justify-between text-xs font-bold text-indigo-300">
              <span>{demoFeedback.already_existed ? "ℹ️ Demo Active" : "✓ Synthetic Demo Ready"}</span>
              <span className="font-mono text-slate-400">Agent: {demoFeedback.agent_name}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
              <Button size="sm" onClick={() => goTo && goTo("monitoring")}>
                View Live Monitoring →
              </Button>
              <Button size="sm" variant="secondary" onClick={() => goTo && goTo("failures")}>
                Failure Analysis →
              </Button>
              <Button size="sm" variant="secondary" onClick={() => goTo && goTo("regression")}>
                Golden Baselines →
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Onboarding Wizard Stepper Bar */}
      <Card>
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-800 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-slate-100">Interactive Setup Progress</h3>
                <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-xs font-semibold text-indigo-300 border border-indigo-500/30">
                  {completedStepsCount} of {wizardSteps.length} Steps Complete ({progressPercent}%)
                </span>
              </div>
              <p className="mt-0.5 text-xs text-slate-400">
                Follow each step in order or jump to any step below. Commands dynamically use your active project and port.
              </p>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-mono">
              <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
              <span>
                {systemInfo?.database_engine === "demo"
                  ? "Public Demo Store (Synthetic Sandbox)"
                  : systemInfo?.database_engine === "postgres"
                  ? "Neon PostgreSQL"
                  : `Local SQLite: ${systemInfo?.database_name || "agentreliability.db"}`}
              </span>
            </div>
          </div>

          {/* Stepper Tabs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-1.5">
            {wizardSteps.map((s) => {
              const isCurrent = activeStep === s.id;
              return (
                <button
                  key={s.id}
                  onClick={() => setActiveStep(s.id)}
                  className={`flex flex-col p-2.5 rounded-lg text-left transition border ${
                    isCurrent
                      ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 ring-1 ring-indigo-500/40"
                      : s.isDone
                      ? "bg-slate-900 border-emerald-500/30 text-slate-300 hover:bg-slate-800"
                      : "bg-slate-950 border-slate-800 text-slate-500 hover:text-slate-300"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold">Step {s.id}</span>
                    {s.isDone ? (
                      <span className="text-emerald-400 font-bold text-xs">✓</span>
                    ) : (
                      <span className="h-1.5 w-1.5 rounded-full bg-slate-600"></span>
                    )}
                  </div>
                  <span className="truncate text-xs font-medium mt-1 text-slate-200">{s.name.split(". ")[1]}</span>
                  <span className="text-[9px] text-slate-400 mt-0.5">{s.statusLabel}</span>
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      {/* WIZARD STEP CARD (Displays the content for activeStep) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-xl space-y-5">
        {/* STEP 1: Account & Sign In */}
        {activeStep === 1 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">Step 1 of 7</span>
                <h3 className="text-base font-bold text-slate-100 mt-0.5">Register & Sign In to Workspace</h3>
              </div>
              <Badge tone="green">Completed ✓</Badge>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              You are signed in as <strong className="text-slate-100">{user?.name || "Developer"}</strong> (<code className="text-indigo-300">{user?.email}</code>).
            </p>
            <div className="rounded-lg bg-slate-950 p-3.5 border border-slate-800 text-xs space-y-2">
              <div className="flex items-center gap-2 font-semibold text-slate-200">
                <span>🔒 Privacy & Data Isolation Notice</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                {systemInfo?.database_engine === "demo"
                  ? <>You are exploring the public interactive demo. All projects, test cases, and Golden Baselines are served from an isolated in-memory synthetic data store. No production credentials or external services are accessed.</>
                  : systemInfo?.database_engine === "postgres"
                  ? <>Your account, projects, baselines, and traces are securely stored in Neon PostgreSQL (<code className="text-slate-300">{systemInfo?.database_path || "Neon Cloud Database"}</code>). All passwords use memory-hard scrypt hashing.</>
                  : <>Your account, projects, baselines, and traces are stored in this workspace's local SQLite database (<code className="text-slate-300">{systemInfo?.database_path || "backend/agentreliability.db"}</code>). All passwords use memory-hard scrypt hashing. Data is never sent to an external cloud or third-party server.</>}
              </p>
            </div>
            <div className="flex justify-end pt-2">
              <Button onClick={() => setActiveStep(2)}>
                Next: Select Project →
              </Button>
            </div>
          </div>
        )}

        {/* STEP 2: Create Project */}
        {activeStep === 2 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">Step 2 of 7</span>
                <h3 className="text-base font-bold text-slate-100 mt-0.5">Select or Create a Project</h3>
              </div>
              <Badge tone={currentProject?.id ? "green" : "amber"}>
                {currentProject?.id ? "Active Project Selected" : "Action Needed"}
              </Badge>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Projects provide multi-tenant isolation for traces, Golden Baselines, and test suites.
            </p>
            <div className="rounded-lg bg-slate-950 p-4 border border-slate-800 space-y-2">
              <div className="text-xs text-slate-400">Currently Active Project:</div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-bold text-indigo-300">"{currentProject?.name}"</span>
                <span className="rounded bg-slate-800 px-2 py-0.5 text-xs font-mono text-slate-300">
                  Project ID: {currentProject?.id}
                </span>
              </div>
            </div>
            <div className="flex items-center justify-between pt-2">
              <Button variant="secondary" onClick={() => setActiveStep(1)}>
                ← Previous
              </Button>
              <div className="flex items-center gap-2">
                <Button variant="ghost" onClick={() => goTo && goTo("apikeys")}>
                  Manage Projects in Settings
                </Button>
                <Button onClick={() => setActiveStep(3)}>
                  Next: Generate API Key →
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* STEP 3: Generate API Key */}
        {activeStep === 3 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">Step 3 of 7</span>
                <h3 className="text-base font-bold text-slate-100 mt-0.5">Provision a Project API Key</h3>
              </div>
              <Badge tone={newKey ? "green" : hasActiveKey ? "indigo" : "amber"}>
                {newKey ? "Live Key Ready" : hasActiveKey ? "Key Active" : "Generate Key"}
              </Badge>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              The AgentReliability Python SDK authenticates trace ingestion using a high-entropy secret key starting with <code className="text-indigo-300">ar_live_</code>.
            </p>

            {/* If newly generated key exists */}
            {newKey ? (
              <div className="rounded-lg bg-emerald-950/30 border border-emerald-500/40 p-4 space-y-2">
                <span className="text-xs font-bold text-emerald-400">✓ Active Live Key (Plaintext):</span>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={newKey.api_key}
                    className="flex-1 rounded-lg border border-emerald-500/40 bg-slate-950 px-3 py-1.5 font-mono text-xs text-emerald-300 select-all"
                  />
                  <Button size="sm" onClick={() => copyText(newKey.api_key, "key")}>
                    {copiedKey ? "Copied!" : "Copy Key"}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="rounded-lg bg-indigo-950/30 border border-indigo-500/30 p-4 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div className="space-y-0.5">
                    <span className="text-xs font-bold text-indigo-300">
                      {hasActiveKey ? "Active Key Already Registered in Database" : "No API Keys Found"}
                    </span>
                    <p className="text-[11px] text-slate-400 max-w-xl">
                      {hasActiveKey
                        ? "API keys are hashed (SHA-256) in the SQLite database for security and cannot be displayed in plaintext. Generate a fresh key to copy into your shell."
                        : "Generate an API key to allow your Python agent to transmit traces to this project."}
                    </p>
                  </div>
                  <Button onClick={handleQuickGenerateKey} disabled={generatingKey} className="shrink-0">
                    {generatingKey ? "Generating..." : "+ Generate Plaintext Key"}
                  </Button>
                </div>
              </div>
            )}

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-300">Copy Shell Environment Variables:</span>
                {!newKey && (
                  <span className="text-[10px] text-indigo-300">
                    (Clicking Copy will auto-provision an active key if needed)
                  </span>
                )}
              </div>
              <div className="relative">
                <pre className="rounded-lg bg-slate-950 p-3 font-mono text-xs text-slate-300 border border-slate-800 overflow-x-auto">
{`export AGENTRELIABILITY_ENDPOINT="${backendEndpoint}"
export AGENTRELIABILITY_API_KEY="${newKey?.api_key || "<Click 'Copy Env Vars' or '+ Generate Plaintext Key' to reveal>"}"`}
                </pre>
                <button
                  onClick={handleCopyEnvVars}
                  disabled={generatingKey}
                  className="absolute right-2 top-2 rounded bg-indigo-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-indigo-500"
                >
                  {copiedSnippet === "env_vars" ? "Copied Real Key!" : generatingKey ? "Generating..." : "Copy Env Vars"}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <Button variant="secondary" onClick={() => setActiveStep(2)}>
                ← Previous
              </Button>
              <Button onClick={() => setActiveStep(4)}>
                Next: Connect Sample Agent →
              </Button>
            </div>
          </div>
        )}

        {/* STEP 4: Connect Sample Agent */}
        {activeStep === 4 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">Step 4 of 7</span>
                <h3 className="text-base font-bold text-slate-100 mt-0.5">Instrument & Run Sample Python Agent</h3>
              </div>
              <Badge tone="indigo">Python SDK</Badge>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Run the included zero-dependency quickstart agent in your terminal. It exercises search and customer support tools and transmits execution traces directly to your local backend.
            </p>

            <div className="space-y-2">
              <span className="text-xs font-semibold text-slate-300">Run Command in Terminal:</span>
              <div className="relative">
                <pre className="rounded-lg bg-slate-950 p-3 font-mono text-xs text-indigo-300 border border-slate-800 overflow-x-auto">
{`# Run the included quickstart agent
python examples/quickstart_agent.py

# Or run the multi-step customer support demo agent
python demo_agent.py success`}
                </pre>
                <button
                  onClick={() => copyText("python examples/quickstart_agent.py", "cmd_step4")}
                  className="absolute right-2 top-2 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                >
                  {copiedSnippet === "cmd_step4" ? "Copied!" : "Copy Command"}
                </button>
              </div>
            </div>

            <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 text-xs space-y-1">
              <span className="font-semibold text-slate-200">How Instrumentation Works (2 lines of code):</span>
              <pre className="text-[11px] font-mono text-slate-400 overflow-x-auto">
{`from agentreliability import AgentMonitor
monitor = AgentMonitor()

@monitor.trace_tool("search_db")
def search(query): return ["doc1", "doc2"]

@monitor.trace_agent("support_agent")
def handle_ticket(t): return search(t)

handle_ticket("reset password")
monitor.flush()`}
              </pre>
            </div>

            <div className="flex items-center justify-between pt-2">
              <Button variant="secondary" onClick={() => setActiveStep(3)}>
                ← Previous
              </Button>
              <Button onClick={() => setActiveStep(5)}>
                Next: Verify Captured Trace →
              </Button>
            </div>
          </div>
        )}

        {/* STEP 5: Capture Trace */}
        {activeStep === 5 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">Step 5 of 7</span>
                <h3 className="text-base font-bold text-slate-100 mt-0.5">Inspect Visual Trace Waterfall</h3>
              </div>
              <Badge tone={traces.length > 0 ? "green" : "amber"}>
                {traces.length > 0 ? `${traces.length} Traces Recorded` : "Waiting for Traces"}
              </Badge>
            </div>

            {traces.length > 0 ? (
              <div className="rounded-lg bg-emerald-950/20 border border-emerald-500/30 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-emerald-400">✓ First Trace Ingested Successfully!</span>
                  <span className="text-[11px] font-mono text-slate-400">Latest ID: {traces[0].execution_id}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="rounded bg-slate-950 p-2 border border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Agent</span>
                    <strong className="text-slate-200">{traces[0].agent_name}</strong>
                  </div>
                  <div className="rounded bg-slate-950 p-2 border border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Status</span>
                    <strong className={traces[0].status === "success" ? "text-emerald-400" : "text-red-400"}>
                      {traces[0].status}
                    </strong>
                  </div>
                  <div className="rounded bg-slate-950 p-2 border border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Duration</span>
                    <strong className="text-slate-200">
                      {traces[0].duration_ms ? `${traces[0].duration_ms.toFixed(1)}ms` : "N/A"}
                    </strong>
                  </div>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <Button size="sm" onClick={() => goTo && goTo("monitoring")}>
                    Open Visual Waterfall in Live Monitoring →
                  </Button>
                </div>
              </div>
            ) : (
              <div className="rounded-lg bg-slate-950 p-4 border border-slate-800 space-y-3">
                <p className="text-xs text-slate-300">
                  No traces recorded in project "{currentProject?.name}" yet. Run <code className="text-indigo-300">python demo_agent.py success</code> or click below:
                </p>
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={handleLoadDemo} disabled={seedingDemo}>
                    {seedingDemo ? "Loading Demo..." : "Load Demo Traces Instead"}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={loadProjectState}>
                    Refresh Trace List
                  </Button>
                </div>
              </div>
            )}

            <div className="flex items-center justify-between pt-2">
              <Button variant="secondary" onClick={() => setActiveStep(4)}>
                ← Previous
              </Button>
              <Button onClick={() => setActiveStep(6)}>
                Next: Establish Golden Baseline →
              </Button>
            </div>
          </div>
        )}

        {/* STEP 6: Golden Baseline */}
        {activeStep === 6 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">Step 6 of 7</span>
                <h3 className="text-base font-bold text-slate-100 mt-0.5">Establish a Golden Baseline</h3>
              </div>
              <Badge tone={baselines.length > 0 ? "green" : "amber"}>
                {baselines.length > 0 ? `${baselines.length} Baseline(s) Active` : "Baseline Needed"}
              </Badge>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              A Golden Baseline records the trusted sequence of tool calls, latencies, and output schema. Future candidate executions are compared against this standard to detect regressions.
            </p>

            {baselineCreatedMsg && (
              <div className="rounded-lg bg-indigo-950/40 border border-indigo-500/30 p-3 text-xs text-indigo-300">
                {baselineCreatedMsg}
              </div>
            )}

            {baselines.length > 0 ? (
              <div className="rounded-lg bg-emerald-950/20 border border-emerald-500/30 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-emerald-400">✓ Active Golden Baseline:</span>
                  <span className="text-[11px] font-mono text-slate-400">Version: {baselines[0].current_version || 1}</span>
                </div>
                <div className="text-xs space-y-1">
                  <div className="text-slate-200 font-semibold">{baselines[0].name}</div>
                  <div className="text-slate-400">Target Agent: <code className="text-slate-300">{baselines[0].agent_name}</code></div>
                </div>
                <Button size="sm" onClick={() => goTo && goTo("regression")}>
                  Inspect Golden Baseline in Regression Suite →
                </Button>
              </div>
            ) : traces.length > 0 ? (
              <div className="rounded-lg bg-slate-950 p-4 border border-slate-800 space-y-3">
                <p className="text-xs text-slate-300">
                  Promote your latest captured trace (<code className="text-indigo-300">{traces[0].execution_id}</code>) to a Golden Baseline:
                </p>
                <Button
                  onClick={() => handleCreateBaselineFromTrace(traces[0].execution_id, traces[0].agent_name)}
                  disabled={creatingBaseline}
                >
                  {creatingBaseline ? "Creating Baseline..." : "★ Promote Trace to Golden Baseline"}
                </Button>
              </div>
            ) : (
              <div className="rounded-lg bg-slate-950 p-4 border border-slate-800 space-y-2">
                <p className="text-xs text-slate-400">
                  Capture a trace or click "Load Demo Agent & Traces" to establish a Golden Baseline.
                </p>
              </div>
            )}

            <div className="flex items-center justify-between pt-2">
              <Button variant="secondary" onClick={() => setActiveStep(5)}>
                ← Previous
              </Button>
              <Button onClick={() => setActiveStep(7)}>
                Next: Run Regression Test →
              </Button>
            </div>
          </div>
        )}

        {/* STEP 7: Run Regression Test */}
        {activeStep === 7 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">Step 7 of 7</span>
                <h3 className="text-base font-bold text-slate-100 mt-0.5">Run Automated Regression Comparison</h3>
              </div>
              <Badge tone="indigo">CI/CD & CLI</Badge>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Run offline regression tests directly from your terminal or CI/CD pipeline using the AgentReliability CLI. It detects missing tool calls, unauthorized tool invocations, and timing regressions.
            </p>

            <div className="space-y-2">
              <span className="text-xs font-semibold text-slate-300">Run CLI Regression Test:</span>
              <div className="relative">
                <pre className="rounded-lg bg-slate-950 p-3 font-mono text-xs text-indigo-300 border border-slate-800 overflow-x-auto">
{`# 1. Trigger simulated breaking change in demo agent
python demo_agent.py regression

# 2. Run offline regression suite against baseline
agentreliability test --project demo_project --fail-on-regression

# 3. Or compare candidate trace against backend Golden Baseline
agentreliability compare --trace ${traces[0]?.execution_id || "tr_candidate_001"} --agent "${baselines[0]?.agent_name || "CustomerSupportAgent"}"`}
                </pre>
                <button
                  onClick={() => copyText("agentreliability test --project demo_project --fail-on-regression", "cmd_step7")}
                  className="absolute right-2 top-2 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                >
                  {copiedSnippet === "cmd_step7" ? "Copied!" : "Copy"}
                </button>
              </div>
            </div>

            <div className="rounded-lg bg-emerald-950/20 border border-emerald-500/30 p-4 space-y-2">
              <span className="text-xs font-bold text-emerald-400">🎉 Congratulations!</span>
              <p className="text-xs text-slate-300 leading-relaxed">
                You have completed the full self-service lifecycle of AgentReliability AI! You can now instrument any AI agent framework (LangChain, LangGraph, CrewAI) and automate regression testing in your CI/CD pipeline.
              </p>
            </div>

            <div className="flex items-center justify-between pt-2">
              <Button variant="secondary" onClick={() => setActiveStep(6)}>
                ← Previous
              </Button>
              <div className="flex items-center gap-2">
                <Button variant="secondary" onClick={() => goTo && goTo("docs")}>
                  Open Documentation & Guides →
                </Button>
                <Button onClick={() => goTo && goTo("overview")}>
                  Go to Overview Dashboard →
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
