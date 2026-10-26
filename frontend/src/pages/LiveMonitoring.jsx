import { useCallback, useEffect, useState } from "react";
import { createTestFromTrace, getTraceExecution, listTraceAgents, listTraceExecutions } from "../api.js";
import { Badge, Button, Card, Empty, ErrorBox, PageTitle, StatusBadge, useAsyncAction } from "../ui.jsx";
import TraceExecutionTimeline from "../components/TraceExecutionTimeline.jsx";

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
    } catch (err) {
      if (err?.status !== 401) {
        setLoadError(err?.message || "Cannot fetch trace executions.");
      }
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
                          {x.metadata?.synthetic_demo || x.execution_id?.startsWith("demo-") ? (
                            <span className="rounded bg-indigo-500/15 px-1.5 py-0.5 text-[9px] font-semibold text-indigo-300 border border-indigo-500/30">
                              Demo
                            </span>
                          ) : (
                            <Badge tone="gray">Live</Badge>
                          )}
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

        {/* Detailed Timeline, Waterfall, & Debugger Inspector */}
        <Card className="lg:col-span-2">
          {!detail ? (
            <Empty>Select an execution from the list to view its real execution timeline, waterfall view, captured inputs/outputs, and tool calls.</Empty>
          ) : (
            <TraceExecutionTimeline
              detail={detail}
              onCreateTest={handleCreateTest}
              isCreatingTest={genTest.busy}
              testNotice={testNotice}
              goTo={goTo}
            />
          )}
        </Card>
      </div>
    </>
  );
}

