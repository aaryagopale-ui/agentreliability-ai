import { useEffect, useState } from "react";
import { getFailureAnalysis } from "../api.js";
import { Card, CATEGORY_LABEL, Empty, PageTitle } from "../ui.jsx";

function Bars({ data, empty }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return <Empty>{empty}</Empty>;
  const max = Math.max(...entries.map((e) => e[1]));
  return (
    <ul className="space-y-2">
      {entries.map(([k, n]) => (
        <li key={k} className="text-sm">
          <div className="mb-1 flex justify-between text-slate-300"><span>{CATEGORY_LABEL[k] || k}</span><span>{n}</span></div>
          <div className="h-2 rounded bg-slate-800"><div className="h-2 rounded bg-red-500" style={{ width: `${(n / max) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}

export default function FailureAnalysis({ openReplay }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { getFailureAnalysis().then(setData).catch(() => setError("Cannot reach the backend. Is it running on port 8000?")); }, []);

  return (
    <>
      <PageTitle title="Failure Analysis" subtitle="Which kinds of failures happen most, based on stored data." />
      {error && <p className="mb-4 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">{error}</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 font-semibold text-slate-100">Failures found in uploaded executions</h2>
          <Bars data={data?.execution_findings} empty="No failures in uploaded executions." />
        </Card>
        <Card>
          <h2 className="mb-3 font-semibold text-slate-100">Replay mismatches (latest run per test)</h2>
          <Bars data={data?.replay_mismatches} empty="No failing replays. Run your tests first if you haven't." />
        </Card>
      </div>
      <Card className="mt-6">
        <h2 className="mb-3 font-semibold text-slate-100">Currently failing tests</h2>
        {!data || data.failing_runs.length === 0 ? <Empty>No tests are failing.</Empty> : (
          <ul className="space-y-3">
            {data.failing_runs.map((r) => (
              <li key={r.id} className="rounded-lg bg-slate-800/60 p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-100">{r.test_name}</span>
                  <button className="text-indigo-400 hover:underline" onClick={() => openReplay(r.test_case_id, r.id)}>Open in Replay Engine</button>
                </div>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-red-300">
                  {r.mismatches.map((m, i) => <li key={i}>{m.message}</li>)}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

