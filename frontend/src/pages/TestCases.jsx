import { useCallback, useEffect, useState } from "react";
import { createTest, deleteTest, getTest, listTests, runAllTests, runTest, updateTest } from "../api.js";
import { Button, Card, Empty, ErrorBox, PageTitle, StatusBadge, useAsyncAction } from "../ui.jsx";

const TEMPLATE = {
  name: "My new test",
  description: "",
  agent_name: "my-agent",
  input: "What is the weather in Paris?",
  steps: [
    { type: "tool_call", name: "get_weather", status: "success", duration_ms: 120, timeout_ms: 5000, output: { temp_c: 18 } },
    { type: "llm_call", name: "respond", status: "success", output: "It is 18°C in Paris." },
  ],
  expected: { status: "success", tool_sequence: ["get_weather"], final_output: "It is 18°C in Paris.", error_conditions: [] },
};

const pretty = (v) => JSON.stringify(v, null, 2);

function TestForm({ initial, onSaved, onCancel }) {
  const editing = initial.id != null;
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description || "");
  const [agentName, setAgentName] = useState(initial.agent_name);
  const [input, setInput] = useState(pretty(initial.input ?? null));
  const [steps, setSteps] = useState(pretty(initial.steps));
  const [expected, setExpected] = useState(pretty(initial.expected));
  const save = useAsyncAction();
  const [parseError, setParseError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    let body;
    try {
      body = {
        name, description: description || null, agent_name: agentName,
        input: JSON.parse(input), steps: JSON.parse(steps), expected: JSON.parse(expected),
      };
      setParseError(null);
    } catch (err) {
      setParseError({ message: `One of the JSON boxes is not valid JSON: ${err.message}` });
      return;
    }
    const saved = await save.run(() => (editing ? updateTest(initial.id, body) : createTest(body)));
    if (saved) onSaved();
  }

  const field = "w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-700 focus:outline-none focus:ring-indigo-500";
  const mono = `${field} font-mono text-xs`;
  return (
    <div className="fixed inset-0 z-20 flex items-start justify-center overflow-y-auto bg-black/70 p-4">
      <form onSubmit={submit} className="my-8 w-full max-w-3xl space-y-4 rounded-xl bg-slate-900 p-6 ring-1 ring-slate-700">
        <h2 className="text-lg font-semibold text-slate-100">{editing ? `Edit test #${initial.id}` : "Create test case"}</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm text-slate-300">Name<input className={field} value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} /></label>
          <label className="text-sm text-slate-300">Agent name<input className={field} value={agentName} onChange={(e) => setAgentName(e.target.value)} required maxLength={120} /></label>
        </div>
        <label className="block text-sm text-slate-300">Description<input className={field} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} /></label>
        <label className="block text-sm text-slate-300">Input (JSON)<textarea className={mono} rows={2} value={input} onChange={(e) => setInput(e.target.value)} /></label>
        <label className="block text-sm text-slate-300">
          Expected results (JSON): status, tool_sequence, final_output (null = don't check), error_conditions
          <textarea className={mono} rows={9} value={expected} onChange={(e) => setExpected(e.target.value)} />
        </label>
        <label className="block text-sm text-slate-300">
          Recorded steps / mocked tool responses (JSON)
          <textarea className={mono} rows={12} value={steps} onChange={(e) => setSteps(e.target.value)} />
        </label>
        <ErrorBox error={parseError || save.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button type="submit" disabled={save.busy}>{save.busy ? "Saving…" : "Save"}</Button>
        </div>
      </form>
    </div>
  );
}

export default function TestCases({ goTo, openReplay }) {
  const [tests, setTests] = useState([]);
  const [form, setForm] = useState(null); // null | initial object
  const [loadError, setLoadError] = useState(null);
  const [summary, setSummary] = useState(null);
  const act = useAsyncAction();

  const load = useCallback(() => {
    listTests().then((d) => { setTests(d); setLoadError(null); })
      .catch(() => setLoadError("Cannot reach the backend. Is it running on port 8000?"));
  }, []);
  useEffect(load, [load]);

  async function edit(id) {
    const t = await act.run(() => getTest(id));
    if (t) setForm(t);
  }
  async function remove(t) {
    if (!window.confirm(`Delete test "${t.name}"? Its past results stay in Test History.`)) return;
    await act.run(() => deleteTest(t.id));
    load();
  }
  async function runOne(t) {
    const run = await act.run(() => runTest(t.id));
    if (run) { load(); openReplay(t.id, run.id); }
  }
  async function runAll() {
    const res = await act.run(runAllTests);
    if (res) { setSummary(res); load(); }
  }

  return (
    <>
      <PageTitle title="Test Cases" subtitle="Reusable tests created from logs. Edit what you expect, then replay.">
        <Button variant="ghost" onClick={() => setForm(TEMPLATE)}>New test</Button>
        <Button onClick={runAll} disabled={act.busy || tests.length === 0}>Run all</Button>
      </PageTitle>
      {loadError && <p className="mb-4 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">{loadError}</p>}
      <div className="mb-4"><ErrorBox error={act.error} /></div>
      {summary && (
        <p className="mb-4 rounded-lg bg-slate-800 p-3 text-sm text-slate-200">
          Run all finished: {summary.total} tests, <span className="text-emerald-400">{summary.passed} passed</span>, <span className="text-red-400">{summary.failed} failed</span>.{" "}
          <button className="text-indigo-400 underline" onClick={() => goTo("history")}>See history</button>
        </p>
      )}
      <Card className="!p-0 overflow-x-auto">
        {tests.length === 0 ? (
          <div className="p-5"><Empty>No test cases yet. Open <button className="text-indigo-400 underline" onClick={() => goTo("executions")}>Agent Executions</button>, pick a log, and click “Create test case”, or use “New test”.</Empty></div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-800 text-xs uppercase text-slate-500">
              <tr><th className="px-4 py-3">Name</th><th className="px-4 py-3">Agent</th><th className="px-4 py-3">Steps</th><th className="px-4 py-3">Last result</th><th className="px-4 py-3 text-right">Actions</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {tests.map((t) => (
                <tr key={t.id} className="hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-medium text-slate-100">{t.name}</td>
                  <td className="px-4 py-3 text-slate-400">{t.agent_name}</td>
                  <td className="px-4 py-3 text-slate-400">{t.step_count}</td>
                  <td className="px-4 py-3"><StatusBadge status={t.last_run_status} /></td>
                  <td className="space-x-2 whitespace-nowrap px-4 py-3 text-right">
                    <Button onClick={() => runOne(t)} disabled={act.busy}>Run</Button>
                    <Button variant="ghost" onClick={() => edit(t.id)}>Edit</Button>
                    <Button variant="danger" onClick={() => remove(t)}>Delete</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {form && <TestForm initial={form} onCancel={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}
    </>
  );
}

