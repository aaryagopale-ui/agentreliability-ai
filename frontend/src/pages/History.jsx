import { useEffect, useState } from "react";
import { getRun, listRuns } from "../api.js";
import { Card, Empty, PageTitle, RunDetail, StatusBadge } from "../ui.jsx";

export default function History() {
  const [runs, setRuns] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch((err) => {
        if (err?.status !== 401) {
          setError(err?.message || "Unable to load test history.");
        }
      });
  }, []);
  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    getRun(selected).then(setDetail).catch(() => setDetail(null));
  }, [selected]);

  return (
    <>
      <PageTitle title="Test History" subtitle="Every test run, newest first. Results of deleted tests are kept." />
      {error && <p className="mb-4 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">{error}</p>}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="!p-0 overflow-hidden lg:col-span-1">
          {runs.length === 0 ? <div className="p-5"><Empty>No runs yet.</Empty></div> : (
            <ul className="max-h-[70vh] divide-y divide-slate-800 overflow-y-auto">
              {runs.map((r) => (
                <li key={r.id}>
                  <button onClick={() => setSelected(r.id)} className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-800/60 ${selected === r.id ? "bg-indigo-500/10" : ""}`}>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-100">{r.test_name}</p>
                      <p className="text-xs text-slate-500">Run #{r.id} · {new Date(r.created_at).toLocaleString()}{r.mismatch_count > 0 && ` · ${r.mismatch_count} issue(s)`}</p>
                    </div>
                    <StatusBadge status={r.status} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="lg:col-span-2">
          {detail ? <RunDetail run={detail} /> : <Empty>Select a run to see its failure explanations and timeline.</Empty>}
        </Card>
      </div>
    </>
  );
}

