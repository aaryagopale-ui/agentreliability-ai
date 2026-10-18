import { useCallback, useEffect, useState } from "react";
import { getOverview, runAllTests } from "../api.js";
import { Button, Card, Empty, ErrorBox, PageTitle, StatCard, StatusBadge, useAsyncAction } from "../ui.jsx";

export default function Overview({ goTo }) {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const action = useAsyncAction();

  const load = useCallback(() => {
    getOverview().then((d) => { setData(d); setLoadError(null); })
      .catch(() => setLoadError("Cannot reach the backend. Is it running on port 8000?"));
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
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Executions" value={data?.executions.total ?? "–"} />
        <StatCard label="Test cases" value={t?.total ?? "–"} />
        <StatCard label="Passed" value={t?.passed ?? "–"} tone="text-emerald-400" />
        <StatCard label="Failed" value={t?.failed ?? "–"} tone="text-red-400" />
        <StatCard label="Not run yet" value={t?.not_run ?? "–"} tone="text-slate-300" />
      </div>
      <Card className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-slate-100">Recent test runs</h2>
          <button className="text-sm text-indigo-400 hover:underline" onClick={() => goTo("history")}>View all</button>
        </div>
        {!data || data.recent_runs.length === 0 ? (
          <Empty>No test runs yet. Upload a log, create a test case, then run it.</Empty>
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
      <Card className="mt-6 text-sm text-slate-400">
        <p className="font-semibold text-slate-200">How it fits together</p>
        <p className="mt-1">1) Upload a log in <b>Agent Executions</b>. 2) Create a <b>Test Case</b> from it. 3) Run it in the <b>Replay Engine</b> (a deterministic simulation with mocked tools). 4) Study failures in <b>Failure Analysis</b> and <b>Test History</b>.</p>
      </Card>
    </>
  );
}

