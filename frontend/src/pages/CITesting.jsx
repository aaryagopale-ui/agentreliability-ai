import { useEffect, useState } from "react";
import { getCIRun, listCIRuns } from "../api.js";
import { Badge, Button, Card, Empty, PageTitle, StatusBadge } from "../ui.jsx";

export default function CITesting() {
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    listCIRuns()
      .then((data) => {
        setRuns(data);
        setError(null);
      })
      .catch((err) => {
        if (err?.status !== 401) {
          setError(err?.message || "Cannot connect to backend to fetch CI runs.");
        }
      });
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    getCIRun(selectedId)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [selectedId]);

  return (
    <>
      <PageTitle
        title="CI/CD Testing & Regressions"
        subtitle="Automated agent regression test results received from GitHub Actions or CLI runs."
      >
        <Button variant="ghost" onClick={load}>Refresh</Button>
      </PageTitle>

      {error && (
        <div className="mb-4 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">
          {error}
        </div>
      )}

      {/* Guide note on how to trigger */}
      <Card className="mb-6 !p-4 text-xs text-slate-400">
        <p className="font-semibold text-slate-200 text-sm mb-1">GitHub Actions & CLI Integration</p>
        <p>
          Tests run offline with zero cloud API keys using deterministic mocked tools. To ingest runs into this dashboard from CI, run:
        </p>
        <pre className="mt-2 rounded bg-slate-950 p-2 font-mono text-indigo-300 overflow-x-auto">
          agentreliability test --project ./agent-tests --output results.json --baseline baseline.json --upload
        </pre>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Runs List */}
        <div className="lg:col-span-1">
          {runs.length === 0 ? (
            <Card>
              <Empty>
                No CI/CD test runs recorded yet. Upload test reports from GitHub Actions or local CLI using <code className="text-slate-300">--upload</code>.
              </Empty>
            </Card>
          ) : (
            <Card className="!p-0 overflow-hidden">
              <ul className="divide-y divide-slate-800 max-h-[75vh] overflow-y-auto">
                {runs.map((r) => (
                  <li key={r.id}>
                    <button
                      onClick={() => setSelectedId(r.id)}
                      className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-800/60 ${
                        selectedId === r.id ? "bg-indigo-500/10" : ""
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="truncate font-medium text-slate-100">
                            Run #{r.id}
                          </p>
                          <Badge tone="gray">{r.branch}</Badge>
                        </div>
                        <p className="truncate text-xs font-mono text-slate-500 mt-0.5">
                          commit {r.commit_sha.slice(0, 8)}
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {r.passed}/{r.total} passed · {r.actor}
                        </p>
                      </div>
                      <StatusBadge status={r.status} />
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        {/* Detailed Report View */}
        <Card className="lg:col-span-2">
          {!detail ? (
            <Empty>Select a CI run on the left to inspect its test cases, regression breakdown, and failure explanations.</Empty>
          ) : (
            <div className="space-y-6">
              {/* Header */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold text-slate-100">CI Run #{detail.id}</h2>
                    <StatusBadge status={detail.status} />
                  </div>
                  <p className="mt-1 text-xs font-mono text-slate-400">
                    Git Commit: {detail.commit_sha} · Branch: {detail.branch} · Triggered by: {detail.actor}
                  </p>
                  <p className="text-xs text-slate-500">
                    Recorded at: {new Date(detail.created_at).toLocaleString()} · Duration: {detail.duration_ms.toFixed(1)} ms
                  </p>
                </div>
              </div>

              {/* Regression Summary Badge Row */}
              {detail.report?.regression && (
                <div className="grid gap-3 sm:grid-cols-4">
                  <div className="rounded-lg bg-slate-950 p-3 ring-1 ring-slate-800 text-center">
                    <span className="text-[10px] uppercase text-slate-500 font-semibold block">Total Tests</span>
                    <span className="text-xl font-bold text-slate-100">{detail.total}</span>
                  </div>
                  <div className="rounded-lg bg-slate-950 p-3 ring-1 ring-slate-800 text-center">
                    <span className="text-[10px] uppercase text-slate-500 font-semibold block">Passed</span>
                    <span className="text-xl font-bold text-emerald-400">{detail.passed}</span>
                  </div>
                  <div className="rounded-lg bg-slate-950 p-3 ring-1 ring-slate-800 text-center">
                    <span className="text-[10px] uppercase text-slate-500 font-semibold block">New Regressions</span>
                    <span className="text-xl font-bold text-red-400">
                      {detail.report.regression.counts?.new_failures ?? detail.failed}
                    </span>
                  </div>
                  <div className="rounded-lg bg-slate-950 p-3 ring-1 ring-slate-800 text-center">
                    <span className="text-[10px] uppercase text-slate-500 font-semibold block">Fixed Tests</span>
                    <span className="text-xl font-bold text-indigo-400">
                      {detail.report.regression.counts?.fixed_failures ?? 0}
                    </span>
                  </div>
                </div>
              )}

              {/* Individual Test Results */}
              <div>
                <h3 className="mb-3 font-semibold text-slate-200">
                  Executed Regression Tests ({detail.report?.results?.length ?? 0})
                </h3>
                {!detail.report?.results || detail.report.results.length === 0 ? (
                  <p className="text-xs text-slate-500 italic">No individual test details attached.</p>
                ) : (
                  <ul className="space-y-3">
                    {detail.report.results.map((res, i) => {
                      const isFail = res.status === "failed";
                      return (
                        <li
                          key={i}
                          className={`rounded-lg p-3 text-sm ring-1 ${
                            isFail ? "bg-red-500/10 ring-red-500/30" : "bg-slate-800/60 ring-slate-700"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-slate-100">{res.name}</span>
                            <StatusBadge status={res.status} />
                          </div>
                          {res.file && (
                            <p className="text-[11px] font-mono text-slate-500 mt-0.5">{res.file}</p>
                          )}
                          {isFail && res.mismatches?.length > 0 && (
                            <div className="mt-2 space-y-1">
                              {res.mismatches.map((m, idx) => (
                                <p key={idx} className="text-xs text-red-300 font-mono">
                                  ↳ <strong>{m.kind}:</strong> {m.message}
                                </p>
                              ))}
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

