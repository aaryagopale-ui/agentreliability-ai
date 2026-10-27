import { useCallback, useEffect, useState } from "react";
import { getOverview, runAllTests } from "../api.js";
import { Button, Card, Empty, ErrorBox, PageTitle, StatCard, StatusBadge, useAsyncAction } from "../ui.jsx";

export default function Overview({ goTo }) {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const action = useAsyncAction();

  const load = useCallback(() => {
    getOverview()
      .then((d) => { setData(d); setLoadError(null); })
      .catch((err) => {
        if (err.status !== 401) {
          setLoadError(err.message || "Unable to load dashboard data.");
        }
      });
  }, []);
  useEffect(load, [load]);

  async function runAll() {
    const res = await action.run(runAllTests);
    if (res) load();
  }

  const t = data?.tests;
  return (
    <>
      <PageTitle title="Overview" subtitle="Live numbers from your local database.">
        <Button onClick={runAll} disabled={action.busy || !t?.total}>{action.busy ? "Running…" : "Run all tests"}</Button>
      </PageTitle>
      {loadError && <p className="mb-4 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">{loadError}</p>}
      <div className="mb-4"><ErrorBox error={action.error} /></div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
        <StatCard label="Live SDK Traces" value={data?.live_traces?.total ?? "–"} tone="text-cyan-400" onClick={() => goTo?.("monitoring")} />
        <StatCard label="Uploaded Logs" value={data?.executions.total ?? "–"} tone="text-indigo-400" onClick={() => goTo?.("executions")} />
        <StatCard label="Test cases" value={t?.total ?? "–"} onClick={() => goTo?.("tests")} />
        <StatCard label="Passed" value={t?.passed ?? "–"} tone="text-emerald-400" onClick={() => goTo?.("history")} />
        <StatCard label="Failed" value={t?.failed ?? "–"} tone="text-red-400" onClick={() => goTo?.("failures")} />
        <StatCard label="Not run yet" value={t?.not_run ?? "–"} tone="text-slate-300" onClick={() => goTo?.("tests")} />
      </div>
      <Card className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-slate-100">Recent test runs</h2>
          <button className="text-sm text-indigo-400 hover:underline" onClick={() => goTo("history")}>View all</button>
        </div>
        {!data || data.recent_runs.length === 0 ? (
          <Empty>No test runs yet. Capture a trace or upload a log, create a test case, then run it.</Empty>
        ) : (
          <ul className="divide-y divide-slate-800">
            {data.recent_runs.map((r) => (
              <li key={r.id} className="flex items-center justify-between py-2 text-sm">
                <span className="text-slate-200">{r.test_name}</span>
                <span className="flex items-center gap-3">
                  <span className="text-xs text-slate-500">{new Date(r.created_at).toLocaleString()}</span>
                  <StatusBadge status={r.status} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card className="mt-6 text-sm text-slate-400 leading-relaxed">
        <p className="font-semibold text-slate-200">How it fits together</p>
        <p className="mt-1">
          1) Ingest real traces via SDK (
          <button
            type="button"
            onClick={() => goTo?.("monitoring")}
            className="font-semibold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
          >
            Live Agent Monitoring
          </button>
          ) or upload JSON logs in{" "}
          <button
            type="button"
            onClick={() => goTo?.("executions")}
            className="font-semibold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
          >
            Agent Executions
          </button>
          . 2) Create a{" "}
          <button
            type="button"
            onClick={() => goTo?.("tests")}
            className="font-semibold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
          >
            Test Case
          </button>{" "}
          or{" "}
          <button
            type="button"
            onClick={() => goTo?.("regression")}
            className="font-semibold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
          >
            Golden Baseline
          </button>{" "}
          from either source. 3) Run tests in the{" "}
          <button
            type="button"
            onClick={() => goTo?.("replay")}
            className="font-semibold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
          >
            Replay Engine
          </button>{" "}
          (deterministic simulation with mocked tools) or run{" "}
          <button
            type="button"
            onClick={() => goTo?.("regression")}
            className="font-semibold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
          >
            Regression Comparisons
          </button>
          . 4) Inspect failures in{" "}
          <button
            type="button"
            onClick={() => goTo?.("failures")}
            className="font-semibold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
          >
            Failure Analysis
          </button>{" "}
          and{" "}
          <button
            type="button"
            onClick={() => goTo?.("history")}
            className="font-semibold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
          >
            Test History
          </button>
          .
        </p>
      </Card>
    </>
  );
}

