import { useCallback, useEffect, useState } from "react";
import { createTestFromTrace, getTraceExecution, listTraceAgents, listTraceExecutions } from "../api.js";
import { Badge, Button, Card, Empty, ErrorBox, PageTitle, StatusBadge, useAsyncAction } from "../ui.jsx";

const FAILURE_LABELS = {
  timeout: "Timeout",
  tool_failure: "Tool Call Failure",
  unexpected_exception: "Unexpected Exception",
};

export default function LiveMonitoring({ goTo }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [agents, setAgents] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  
  // Filters
  const [agentFilter, setAgentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [timeFilter, setTimeFilter] = useState("all"); // all, 1h, 24h, 7d
  const [autoPoll, setAutoPoll] = useState(true);

  const genTest = useAsyncAction();
  const [testNotice, setTestNotice] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const getSinceIso = () => {
    if (timeFilter === "1h") return new Date(Date.now() - 3600 * 1000).toISOString();
    if (timeFilter === "24h") return new Date(Date.now() - 24 * 3600 * 1000).toISOString();
    if (timeFilter === "7d") return new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString();
    return null;
  };

  const refresh = useCallback(async () => {
    try {
      const since = getSinceIso();
      const res = await listTraceExecutions({
        agent: agentFilter || undefined,
        status: statusFilter || undefined,
        since: since || undefined,
        limit: 50,
      });
      setItems(res.items);
      setTotal(res.total);
      setLastRefreshed(new Date());
      setLoadError(null);
    } catch {
      setLoadError("Cannot reach the backend or fetch trace executions. Is backend running on port 8000?");
    }
  }, [agentFilter, statusFilter, timeFilter]);

  // Load agents list once or periodically
  useEffect(() => {
    listTraceAgents().then(setAgents).catch(() => {});
  }, []);

  // Poll every 3 seconds if autoPoll is true
  useEffect(() => {
    refresh();
    if (!autoPoll) return;
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [refresh, autoPoll]);

  // Load execution detail when selected
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    getTraceExecution(selectedId)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [selectedId]);

  async function handleCreateTest() {
    if (!detail) return;
    const t = await genTest.run(() => createTestFromTrace(detail.execution_id));
    if (t) setTestNotice(t);
  }

  return (
    <>
      <PageTitle
        title="Live Agent Monitoring"
        subtitle="Real-time live traces sent from agents instrumented with the agentreliability Python SDK."
      >
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={autoPoll}
              onChange={(e) => setAutoPoll(e.target.checked)}
              className="rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0"
            />
            Auto-refresh (3s)
          </label>
          <Button variant="ghost" onClick={refresh}>Refresh</Button>
        </div>
      </PageTitle>

      {lastRefreshed && (
        <div className="mb-4 flex items-center justify-between text-xs text-slate-400">
          <span>
            Last refreshed: <strong className="text-slate-200">{lastRefreshed.toLocaleTimeString()}</strong>
          </span>
          <span>Total matches: {total}</span>
        </div>
      )}

      {loadError && (
        <div className="mb-4 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">
          {loadError}
        </div>
      )}

      {/* Filters bar */}
      <Card className="mb-6 !p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label className="block text-xs uppercase text-slate-400 mb-1">Filter by Agent</label>
            <select
              className="w-full rounded-lg bg-slate-950 px-3 py-1.5 text-sm text-slate-100 ring-1 ring-slate-800"
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
            >
              <option value="">All agents</option>
              {agents.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs uppercase text-slate-400 mb-1">Filter by Status</label>
            <select
              className="w-full rounded-lg bg-slate-950 px-3 py-1.5 text-sm text-slate-100 ring-1 ring-slate-800"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All statuses</option>
              <option value="success">Success</option>
              <option value="failed">Failed</option>
              <option value="running">Running</option>
            </select>
          </div>
          <div>
            <label className="block text-xs uppercase text-slate-400 mb-1">Time Range</label>
            <select
              className="w-full rounded-lg bg-slate-950 px-3 py-1.5 text-sm text-slate-100 ring-1 ring-slate-800"
              value={timeFilter}
              onChange={(e) => setTimeFilter(e.target.value)}
            >
              <option value="all">All time</option>
              <option value="1h">Last 1 hour</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Main split view */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Executions List */}
        <div className="lg:col-span-1">
          {items.length === 0 ? (
            <Card>
              <Empty>No real executions recorded yet. Run `python demo_agent.py all` with an API key to stream live traces!</Empty>
            </Card>
          ) : (
            <Card className="!p-0 overflow-hidden">
              <ul className="divide-y divide-slate-800 max-h-[75vh] overflow-y-auto">
                {items.map((x) => (
                  <li key={x.execution_id}>
                    <button
                      onClick={() => {
                        setSelectedId(x.execution_id);
                        setTestNotice(null);
                      }}
                      className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-800/60 ${
                        selectedId === x.execution_id ? "bg-indigo-500/10" : ""
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="truncate font-medium text-slate-100">{x.agent_name}</p>
                          <Badge tone="gray">Live</Badge>
                        </div>
                        <p className="truncate text-xs font-mono text-slate-500 mt-0.5">
                          {x.execution_id.slice(0, 12)}…
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {x.duration_ms != null ? `${Math.round(x.duration_ms)}ms` : "in progress"} · {x.tool_call_count} tools
                          {x.failed_tool_calls > 0 && <span className="text-red-400"> ({x.failed_tool_calls} failed)</span>}
                        </p>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <StatusBadge status={x.status} />
                        {x.failure_kind && (
                          <span className="text-[10px] font-semibold text-red-400">
                            {FAILURE_LABELS[x.failure_kind] || x.failure_kind}
                          </span>
                        )}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        {/* Detailed Timeline & Inspector */}
        <Card className="lg:col-span-2">
          {!detail ? (
            <Empty>Select an execution from the list to view its real execution timeline, captured inputs/outputs, and tool calls.</Empty>
          ) : (
            <div className="space-y-6">
              {/* Header */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold text-slate-100">{detail.agent_name}</h2>
                    <StatusBadge status={detail.status} />
                    <Badge tone="green">Recorded Real Execution</Badge>
                  </div>
                  <p className="mt-1 text-xs font-mono text-slate-400">
                    Execution ID: {detail.execution_id}
                  </p>
                  <p className="text-xs text-slate-500">
                    Started: {new Date(detail.started_at).toLocaleString()}
                    {detail.duration_ms != null && ` · Total: ${detail.duration_ms.toFixed(1)} ms`}
                  </p>
                </div>
                <Button
                  onClick={handleCreateTest}
                  disabled={genTest.busy || detail.status === "running"}
                >
                  {genTest.busy ? "Creating…" : "Create Test Case"}
                </Button>
              </div>

              <ErrorBox error={genTest.error} />

              {testNotice && (
                <div className="rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-300 ring-1 ring-emerald-500/30">
                  Test case “<strong>{testNotice.name}</strong>” created in SQLite!{" "}
                  <button className="underline font-semibold" onClick={() => goTo("tests")}>
                    Go to Test Cases to Replay
                  </button>
                </div>
              )}

              {/* Error Callout if execution failed */}
              {detail.status === "failed" && (
                <div className="rounded-lg bg-red-500/10 p-4 ring-1 ring-red-500/30 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-red-300">
                      {FAILURE_LABELS[detail.failure_kind] || "Failure Detected"}
                    </span>
                    {detail.error_type && (
                      <span className="rounded bg-red-900/50 px-2 py-0.5 text-xs font-mono text-red-200">
                        {detail.error_type}
                      </span>
                    )}
                  </div>
                  {detail.error_message && (
                    <p className="text-sm text-red-200 mt-1 font-mono break-words">
                      {detail.error_message}
                    </p>
                  )}
                </div>
              )}

              {/* Input / Output overview */}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-lg bg-slate-950 p-3 ring-1 ring-slate-800">
                  <span className="text-xs font-semibold uppercase text-slate-400">Captured Agent Input</span>
                  <pre className="mt-2 text-xs text-slate-300 max-h-40 overflow-auto">
                    {detail.input ? JSON.stringify(detail.input, null, 2) : "(Input capture disabled or None)"}
                  </pre>
                </div>
                <div className="rounded-lg bg-slate-950 p-3 ring-1 ring-slate-800">
                  <span className="text-xs font-semibold uppercase text-slate-400">Captured Agent Output</span>
                  <pre className="mt-2 text-xs text-slate-300 max-h-40 overflow-auto">
                    {detail.output ? JSON.stringify(detail.output, null, 2) : "(Output capture disabled or None)"}
                  </pre>
                </div>
              </div>

              {/* Tool Calls & Execution Timeline */}
              <div>
                <h3 className="mb-3 font-semibold text-slate-200">
                  Tool-Call History ({detail.tool_calls.length})
                </h3>
                {detail.tool_calls.length === 0 ? (
                  <p className="text-xs text-slate-500 italic">No tool calls recorded for this execution.</p>
                ) : (
                  <ol className="relative space-y-4 border-l-2 border-slate-700 pl-6">
                    {detail.tool_calls.map((t, idx) => {
                      const isErr = t.status !== "success";
                      return (
                        <li key={t.call_id} className="relative">
                          <span
                            className={`absolute -left-[31px] top-1.5 h-3 w-3 rounded-full ring-4 ring-slate-900 ${
                              isErr ? "bg-red-500" : "bg-emerald-500"
                            }`}
                          />
                          <div
                            className={`rounded-lg bg-slate-800/60 p-3 text-sm ring-1 ${
                              isErr ? "ring-red-500/40" : "ring-slate-700"
                            }`}
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-semibold text-slate-100">
                                {idx + 1}. {t.tool_name}
                              </span>
                              <Badge tone={isErr ? "red" : "green"}>{t.status}</Badge>
                              {t.duration_ms != null && (
                                <span className="ml-auto text-xs text-slate-400">
                                  {t.duration_ms.toFixed(1)} ms
                                </span>
                              )}
                            </div>
                            {t.started_at && (
                              <p className="mt-1 text-xs text-slate-500">
                                {new Date(t.started_at).toLocaleTimeString()}
                              </p>
                            )}
                            {t.error_message && (
                              <p className="mt-1 text-xs text-red-300 font-mono">
                                {t.error_type ? `[${t.error_type}] ` : ""}{t.error_message}
                              </p>
                            )}
                            {(t.input != null || t.output != null) && (
                              <details className="mt-2 text-xs text-slate-400">
                                <summary className="cursor-pointer text-slate-400 hover:text-slate-200">
                                  Inspect Tool Payload
                                </summary>
                                <pre className="mt-1 overflow-x-auto rounded bg-slate-950 p-2 text-slate-300">
                                  {JSON.stringify({ input: t.input, output: t.output }, null, 2)}
                                </pre>
                              </details>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </div>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

