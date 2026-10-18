import { useState } from "react";

export const CATEGORY_LABEL = {
  timeout: "Timeout",
  failed_tool_call: "Failed tool call",
  explicit_error: "Explicit error",
  unexpected_exception: "Unexpected exception",
  missing_expected_error: "Missing expected error",
  sequence_mismatch: "Wrong tool sequence",
  missing_output: "Missing output",
  output_mismatch: "Output differs",
  status_mismatch: "Status differs",
};

const TONES = {
  green: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  red: "bg-red-500/15 text-red-300 ring-red-500/30",
  gray: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
  amber: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
};

export function Badge({ tone = "gray", children }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }) {
  if (status === "success" || status === "passed") return <Badge tone="green">{status === "passed" ? "Passed" : "Success"}</Badge>;
  if (status === "failed") return <Badge tone="red">Failed</Badge>;
  return <Badge>Not run</Badge>;
}

export const Card = ({ className = "", children }) => (
  <div className={`rounded-xl bg-slate-900 p-5 ring-1 ring-slate-800 ${className}`}>{children}</div>
);

export const PageTitle = ({ title, subtitle, children }) => (
  <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 className="text-2xl font-bold text-slate-100">{title}</h1>
      {subtitle && <p className="mt-1 max-w-2xl text-sm text-slate-400">{subtitle}</p>}
    </div>
    <div className="flex flex-wrap gap-2">{children}</div>
  </div>
);

export function Button({ variant = "primary", className = "", ...props }) {
  const styles = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-500",
    ghost: "bg-slate-800 text-slate-200 hover:bg-slate-700",
    danger: "bg-red-600/20 text-red-300 hover:bg-red-600/30",
  };
  return (
    <button
      {...props}
      className={`rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${className}`}
    />
  );
}

export function StatCard({ label, value, tone = "text-slate-100" }) {
  return (
    <Card>
      <p className="text-sm text-slate-400">{label}</p>
      <p className={`mt-1 text-3xl font-bold ${tone}`}>{value}</p>
    </Card>
  );
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div className="rounded-lg bg-red-500/10 p-3 text-sm text-red-300 ring-1 ring-red-500/30">
      <p className="font-semibold">{error.message || String(error)}</p>
      {error.problems?.length > 0 && (
        <ul className="mt-1 list-disc pl-5">{error.problems.map((p) => <li key={p}>{p}</li>)}</ul>
      )}
    </div>
  );
}

export const Empty = ({ children }) => <p className="text-sm text-slate-500">{children}</p>;

export const SimulationBanner = ({ text }) => (
  <div className="rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200 ring-1 ring-amber-500/30">
    <span className="font-semibold">Simulation, not a real agent run. </span>
    {text || "Recorded steps are replayed with mocked tool responses. No model or real tool is executed."}
  </div>
);

/** Vertical timeline. `findings` is a list of {step_index, category, explanation}. */
export function Timeline({ steps, findings = [] }) {
  const byStep = Object.fromEntries(findings.map((f) => [f.step_index, f]));
  return (
    <ol className="relative space-y-4 border-l-2 border-slate-700 pl-6">
      {steps.map((s, i) => {
        const f = byStep[i];
        return (
          <li key={i} className="relative">
            <span className={`absolute -left-[31px] top-1.5 h-3 w-3 rounded-full ring-4 ring-slate-900 ${f ? "bg-red-500" : "bg-emerald-500"}`} />
            <div className={`rounded-lg bg-slate-800/60 p-3 text-sm ring-1 ${f ? "ring-red-500/40" : "ring-slate-700"}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-100">{i + 1}. {s.name || s.type}</span>
                <span className="rounded bg-slate-700 px-1.5 py-0.5 text-xs text-slate-300">{s.type}</span>
                {f && <Badge tone="red">{CATEGORY_LABEL[f.category]}</Badge>}
                {s.duration_ms != null && <span className="ml-auto text-xs text-slate-400">{s.duration_ms} ms</span>}
              </div>
              {s.timestamp && <p className="mt-1 text-xs text-slate-500">{s.timestamp}</p>}
              {f && <p className="mt-1 text-red-300">{f.explanation}</p>}
              {(s.input != null || s.output != null) && (
                <details className="mt-2 text-xs text-slate-400">
                  <summary className="cursor-pointer">Input / output</summary>
                  <pre className="mt-1 overflow-x-auto rounded bg-slate-950 p-2 text-slate-300">{JSON.stringify({ input: s.input, output: s.output }, null, 2)}</pre>
                </details>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Full detail of one test run: banner, mismatches, expected vs observed, timeline. */
export function RunDetail({ run }) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-lg font-semibold text-slate-100">{run.test_name}</h3>
        <StatusBadge status={run.status} />
        <span className="text-xs text-slate-500">{new Date(run.created_at).toLocaleString()} · {run.duration_ms} ms</span>
      </div>
      <SimulationBanner text={run.disclaimer} />
      <section>
        <h4 className="mb-2 font-semibold text-slate-200">Failure explanations</h4>
        {run.mismatches.length === 0 ? (
          <p className="rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-300">Replay matched every expectation.</p>
        ) : (
          <ul className="space-y-2">
            {run.mismatches.map((m, i) => (
              <li key={i} className="rounded-lg bg-red-500/10 p-3 text-sm text-red-200 ring-1 ring-red-500/30">
                <span className="font-semibold">{CATEGORY_LABEL[m.kind] || m.kind}
                  {m.step_index != null && ` · step ${m.step_index + 1}`}:</span> {m.message}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="grid gap-3 text-sm sm:grid-cols-2">
        <Card className="!p-3">
          <p className="text-xs uppercase text-slate-500">Observed tool sequence</p>
          <p className="mt-1 text-slate-200">{run.observed.tool_sequence.join(" → ") || "(no tool calls)"}</p>
        </Card>
        <Card className="!p-3">
          <p className="text-xs uppercase text-slate-500">Observed final output</p>
          <p className="mt-1 break-words text-slate-200">{run.observed.final_output == null ? "(none)" : typeof run.observed.final_output === "string" ? run.observed.final_output : JSON.stringify(run.observed.final_output)}</p>
        </Card>
      </section>
      <section>
        <h4 className="mb-3 font-semibold text-slate-200">Timeline (simulated)</h4>
        <Timeline steps={run.observed.steps} findings={run.observed.findings} />
      </section>
    </div>
  );
}

export function useAsyncAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  async function run(fn) {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run, setError };
}

