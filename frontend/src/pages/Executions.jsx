import { useCallback, useEffect, useState } from "react";
import { createTestFromExecution, getExecution, listExecutions, uploadLog } from "../api.js";
import { Badge, Button, Card, Empty, ErrorBox, PageTitle, StatusBadge, Timeline, CATEGORY_LABEL, useAsyncAction } from "../ui.jsx";

// This page is the Phase 1 feature set (upload, list, timeline) plus "Create test case".
export default function Executions({ goTo }) {
  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const up = useAsyncAction();
  const gen = useAsyncAction();
  const [notice, setNotice] = useState(null);

  const refresh = useCallback(async () => {
    try {
      setItems(await listExecutions());
      setLoadError(null);
    } catch {
      setLoadError("Cannot reach the backend. Is it running on port 8000?");
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (selectedId == null) { setDetail(null); return; }
    getExecution(selectedId).then(setDetail).catch(() => setDetail(null));
  }, [selectedId]);

  async function handleFile(e) {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setNotice(null);
    const created = await up.run(() => uploadLog(file));
    if (created) { await refresh(); setSelectedId(created.id); }
  }

  async function makeTest() {
    const t = await gen.run(() => createTestFromExecution(detail.id));
    if (t) setNotice(t);
  }

  return (
    <>
      <PageTitle title="Agent Executions" subtitle="Upload JSON agent logs. Failures are detected with fixed rules (no AI).">
        <label className="cursor-pointer rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500">
          {up.busy ? "Uploading…" : "Upload log (.json)"}
          <input type="file" accept=".json,application/json" className="hidden" onChange={handleFile} disabled={up.busy} />
        </label>
      </PageTitle>
      {loadError && <p className="mb-4 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">{loadError}</p>}
      <div className="mb-4"><ErrorBox error={up.error} /></div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          {items.length === 0 ? (
            <Card><Empty>No executions yet. Upload a log to get started.</Empty></Card>
          ) : (
            <Card className="!p-0 overflow-hidden">
              <ul className="divide-y divide-slate-800">
                {items.map((x) => (
                  <li key={x.id}>
                    <button onClick={() => { setSelectedId(x.id); setNotice(null); }}
                      className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-800/60 ${selectedId === x.id ? "bg-indigo-500/10" : ""}`}>
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-100">{x.agent_name}</p>
                        <p className="truncate text-xs text-slate-500">{x.run_id || `#${x.id}`} · {x.step_count} steps · {new Date(x.created_at).toLocaleString()}</p>
                      </div>
                      <StatusBadge status={x.status} />
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
        <Card className="lg:col-span-2">
          {!detail ? <Empty>Select an execution to see its timeline and failure explanations.</Empty> : (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold text-slate-100">{detail.agent_name}</h2>
                    <StatusBadge status={detail.status} />
                  </div>
                  <p className="text-sm text-slate-500">{detail.run_id || `Execution #${detail.id}`}</p>
                </div>
                <Button onClick={makeTest} disabled={gen.busy}>{gen.busy ? "Creating…" : "Create test case"}</Button>
              </div>
              <ErrorBox error={gen.error} />
              {notice && (
                <div className="rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-300">
                  Test case “{notice.name}” created.{" "}
                  <button className="underline" onClick={() => goTo("tests")}>Go to Test Cases</button>
                </div>
              )}
              <section>
                <h3 className="mb-2 font-semibold text-slate-200">Failure explanations</h3>
                {detail.findings.length === 0 ? (
                  <p className="rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-300">No failures detected. All steps look healthy.</p>
                ) : (
                  <ul className="space-y-2">
                    {detail.findings.map((f) => (
                      <li key={f.step_index} className="rounded-lg bg-red-500/10 p-3 text-sm text-red-200 ring-1 ring-red-500/30">
                        <span className="font-semibold">Step {f.step_index + 1} · {CATEGORY_LABEL[f.category]}:</span> {f.explanation}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
              <section>
                <h3 className="mb-3 font-semibold text-slate-200">Timeline</h3>
                <Timeline steps={detail.steps} findings={detail.findings} />
              </section>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

