import { useEffect, useState } from "react";
import { getRun, getTest, listTests, runTest } from "../api.js";
import { Button, Card, Empty, ErrorBox, PageTitle, RunDetail, SimulationBanner, StatusBadge, useAsyncAction } from "../ui.jsx";

const show = (v) => (v == null ? "(not checked)" : typeof v === "string" ? v : JSON.stringify(v));

export default function Replay({ testId, runId, setSel }) {
  const [tests, setTests] = useState([]);
  const [test, setTest] = useState(null);
  const [run, setRun] = useState(null);
  const act = useAsyncAction();

  useEffect(() => { listTests().then(setTests).catch(() => {}); }, []);
  useEffect(() => {
    if (!testId) { setTest(null); return; }
    getTest(testId).then(setTest).catch(() => setTest(null));
  }, [testId]);
  useEffect(() => {
    if (!runId) { setRun(null); return; }
    getRun(runId).then(setRun).catch(() => setRun(null));
  }, [runId]);

  async function replay() {
    const r = await act.run(() => runTest(testId));
    if (r) setSel(testId, r.id);
  }

  const exp = test?.expected;
  return (
    <>
      <PageTitle title="Replay Engine" subtitle="Replays recorded steps with mocked tool responses and compares the outcome with what you expected." />
      <div className="mb-4"><SimulationBanner text="This is a deterministic simulation. It does not run your real agent or call a language model, so it can't reproduce live model behavior. A real agent runtime is not connected." /></div>
      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <select className="rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-700"
            value={testId || ""} onChange={(e) => setSel(e.target.value ? Number(e.target.value) : null, null)}>
            <option value="">Choose a test case…</option>
            {tests.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <Button onClick={replay} disabled={!testId || act.busy}>{act.busy ? "Replaying…" : "Replay now"}</Button>
        </div>
        <div className="mt-3"><ErrorBox error={act.error} /></div>
      </Card>
      {test && (
        <Card className="mb-6">
          <div className="mb-2 flex items-center gap-3"><h2 className="font-semibold text-slate-100">Expected</h2><StatusBadge status={exp.status} /></div>
          <dl className="grid gap-2 text-sm sm:grid-cols-3">
            <div><dt className="text-xs uppercase text-slate-500">Tool sequence</dt><dd className="text-slate-200">{exp.tool_sequence.join(" → ") || "(none)"}</dd></div>
            <div><dt className="text-xs uppercase text-slate-500">Final output</dt><dd className="break-words text-slate-200">{show(exp.final_output)}</dd></div>
            <div><dt className="text-xs uppercase text-slate-500">Expected error conditions</dt><dd className="text-slate-200">{exp.error_conditions.map((c) => `step ${c.step_index + 1}: ${c.category}`).join(", ") || "(none)"}</dd></div>
          </dl>
        </Card>
      )}
      <Card>{run ? <RunDetail run={run} /> : <Empty>Choose a test and click “Replay now” to see the result.</Empty>}</Card>
    </>
  );
}

