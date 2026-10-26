import { useEffect, useState, useCallback } from "react";
import { getFailureAnalysis, diagnoseExecution, getOllamaStatus } from "../api.js";
import { Badge, Button, Card, CATEGORY_LABEL, Empty, ErrorBox, PageTitle, StatusBadge, useAsyncAction } from "../ui.jsx";

function Bars({ data, empty, tone = "red" }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return <Empty>{empty}</Empty>;
  const max = Math.max(...entries.map((e) => e[1]));
  const barColor = tone === "amber" ? "bg-amber-500" : tone === "indigo" ? "bg-indigo-500" : "bg-red-500";
  return (
    <ul className="space-y-2.5">
      {entries.map(([k, n]) => (
        <li key={k} className="text-xs">
          <div className="mb-1 flex justify-between text-slate-300 font-mono">
            <span className="capitalize">{CATEGORY_LABEL[k] || k.replace(/_/g, " ")}</span>
            <span className="font-semibold">{n}</span>
          </div>
          <div className="h-2 rounded bg-slate-800 overflow-hidden">
            <div className={`h-2 rounded ${barColor}`} style={{ width: `${(n / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function FailureAnalysis({ openReplay, goTo }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  // Diagnosis Modal / Drawer State
  const [selectedExecution, setSelectedExecution] = useState(null);
  const [diagnosisResult, setDiagnosisResult] = useState(null);
  const [diagnosisError, setDiagnosisError] = useState(null);
  const [useAi, setUseAi] = useState(true);
  const diagAction = useAsyncAction();

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getFailureAnalysis();
      setData(res);
      setError(null);
    } catch (err) {
      if (err.status !== 401) {
        setError(err.message || "Failed to load failure analysis data.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleAnalyze(executionId, sourceType = "trace") {
    setSelectedExecution({ executionId, sourceType });
    setDiagnosisResult(null);
    setDiagnosisError(null);
    try {
      const res = await diagAction.run(() =>
        diagnoseExecution({
          execution_id: String(executionId),
          source_type: sourceType,
          use_ai: useAi,
        })
      );
      if (res) {
        setDiagnosisResult(res);
      }
    } catch (err) {
      setDiagnosisError(err.message || "Failed to diagnose execution.");
    }
  }

  const totalFailures =
    (data?.failed_traces?.length || 0) +
    (data?.failing_runs?.length || 0) +
    Object.values(data?.execution_findings || {}).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-6">
      <PageTitle
        title="Evidence-Based AI Failure Analysis"
        subtitle="Intelligent root-cause diagnostic engine that isolates failing tools, timing anomalies, and schema regressions using ground-truth trace evidence and optional local Ollama AI."
      >
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={useAi}
              onChange={(e) => setUseAi(e.target.checked)}
              className="rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0"
            />
            <span>Enable Local AI Diagnosis</span>
          </label>
          <Button variant="ghost" onClick={loadData}>
            Refresh
          </Button>
        </div>
      </PageTitle>

      {error && <ErrorBox message={error} />}

      {/* Local AI Engine Status Banner */}
      <div
        className={`rounded-xl p-3.5 border text-xs flex flex-wrap items-center justify-between gap-3 ${
          data?.local_ai?.available
            ? "bg-emerald-950/30 border-emerald-500/30 text-emerald-200"
            : "bg-slate-900/90 border-slate-800 text-slate-300"
        }`}
      >
        <div className="flex items-center gap-2.5">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              data?.local_ai?.available ? "bg-emerald-400" : "bg-amber-400"
            }`}
          />
          <div>
            <strong>Local AI Diagnostic Engine:</strong>{" "}
            {data?.local_ai?.available ? (
              <span>
                Ollama Active ({data.local_ai.models?.length || 0} local models available · Selected:{" "}
                <code className="text-emerald-300 font-mono">{data.local_ai.selected_model || "auto"}</code>)
              </span>
            ) : (
              <span>
                Deterministic Mode Active (Local Ollama offline or not detected. Zero cloud transmission; deterministic diagnosis fully functional.)
              </span>
            )}
          </div>
        </div>
        <span className="text-[11px] text-slate-400">
          Endpoint: <code className="font-mono">{data?.local_ai?.base_url || "http://127.0.0.1:11434"}</code>
        </span>
      </div>

      {/* Aggregate Categorization Charts */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Real SDK Traces Failures */}
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-slate-100 text-sm">Real Trace Failures (SDK)</h2>
            <Badge tone="red">{data?.failed_traces?.length || 0}</Badge>
          </div>
          <Bars
            data={data?.trace_failure_kinds}
            empty="No real trace failures captured yet."
            tone="red"
          />
        </Card>

        {/* Uploaded Log Findings */}
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-slate-100 text-sm">Uploaded Log Findings</h2>
            <Badge tone="amber">
              {Object.values(data?.execution_findings || {}).reduce((a, b) => a + b, 0)}
            </Badge>
          </div>
          <Bars
            data={data?.execution_findings}
            empty="No failures in uploaded executions."
            tone="amber"
          />
        </Card>

        {/* Replay Mismatches */}
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-slate-100 text-sm">Replay Test Mismatches</h2>
            <Badge tone="indigo">{data?.failing_runs?.length || 0}</Badge>
          </div>
          <Bars
            data={data?.replay_mismatches}
            empty="No failing replays. All tests passing."
            tone="indigo"
          />
        </Card>
      </div>

      {/* Failed Real Executions (SDK Traces) */}
      <Card>
        <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
          <div>
            <h2 className="font-bold text-slate-100 text-base">
              Failed Real Agent Executions ({data?.failed_traces?.length || 0})
            </h2>
            <p className="text-xs text-slate-400">
              Real executions instrumented with the agentreliability SDK that encountered errors or timeouts.
            </p>
          </div>
        </div>

        {!data || data.failed_traces?.length === 0 ? (
          <Empty>No real agent execution failures recorded. Everything is running reliably!</Empty>
        ) : (
          <div className="space-y-3">
            {data.failed_traces.map((trace) => (
              <div
                key={trace.execution_id}
                className="rounded-xl border border-red-500/20 bg-slate-900/60 p-4 transition hover:border-red-500/40 space-y-3 text-xs"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-100 text-sm">{trace.agent_name}</span>
                      <StatusBadge status="failed" />
                      {trace.failure_kind && (
                        <span className="rounded bg-red-950 px-2 py-0.5 text-[10px] font-mono font-semibold text-red-300 border border-red-800">
                          {trace.failure_kind}
                        </span>
                      )}
                    </div>
                    <p className="font-mono text-slate-400 text-[11px]">
                      ID: <span className="text-slate-300">{trace.execution_id}</span> · Started:{" "}
                      {trace.started_at ? new Date(trace.started_at).toLocaleTimeString() : "—"} · Duration:{" "}
                      <strong className="text-slate-200">
                        {trace.duration_ms ? `${Math.round(trace.duration_ms)} ms` : "—"}
                      </strong>
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      onClick={() => handleAnalyze(trace.execution_id, "trace")}
                      disabled={diagAction.busy}
                      className="text-xs py-1"
                    >
                      {diagAction.busy && selectedExecution?.executionId === trace.execution_id
                        ? "Diagnosing..."
                        : "Analyze Failure"}
                    </Button>
                  </div>
                </div>

                {trace.error_message && (
                  <div className="rounded bg-red-950/60 p-2.5 font-mono text-[11px] text-red-200 border border-red-500/30">
                    <strong className="text-red-300">{trace.error_type ? `[${trace.error_type}] ` : "Error: "}</strong>
                    {trace.error_message}
                  </div>
                )}

                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800">
                  <span>
                    Tools Executed: <strong>{trace.tool_call_count}</strong> ({trace.failed_tool_calls} failed)
                  </span>
                  <span className="text-slate-500">Source: Real SDK Trace</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Currently Failing Test Cases (Replay Engine) */}
      <Card>
        <div className="flex items-center justify-between mb-3 border-b border-slate-800 pb-2">
          <h2 className="font-bold text-slate-100 text-base">Failing Regression Tests</h2>
        </div>
        {!data || data.failing_runs?.length === 0 ? (
          <Empty>No test cases are currently failing.</Empty>
        ) : (
          <ul className="space-y-3">
            {data.failing_runs.map((r) => (
              <li key={r.id} className="rounded-lg bg-slate-900/80 p-3.5 text-xs border border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-100 text-sm">{r.test_name}</span>
                  <button
                    className="text-indigo-400 hover:text-indigo-300 font-semibold underline"
                    onClick={() => openReplay && openReplay(r.test_case_id, r.id)}
                  >
                    Open in Replay Engine
                  </button>
                </div>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-red-300 font-mono text-[11px]">
                  {r.mismatches?.map((m, i) => (
                    <li key={i}>{m.message}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Diagnosis Drawer / Modal */}
      {selectedExecution && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <div className="w-full max-w-3xl rounded-2xl bg-slate-900 p-6 border border-slate-700 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-slate-800 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-slate-100">
                    Evidence-Based Failure Diagnosis
                  </h3>
                  <Badge tone="red">Ground Truth Evidence</Badge>
                </div>
                <p className="text-xs font-mono text-slate-400 mt-0.5">
                  Target: {selectedExecution.executionId} ({selectedExecution.sourceType})
                </p>
              </div>
              <Button variant="ghost" onClick={() => setSelectedExecution(null)}>
                ✕ Close
              </Button>
            </div>

            {diagAction.busy && (
              <div className="flex flex-col items-center justify-center py-12 gap-3 text-slate-400">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                <span className="text-xs font-medium">
                  {useAi ? "Extracting trace evidence & querying local Ollama..." : "Extracting deterministic trace evidence..."}
                </span>
              </div>
            )}

            {diagnosisError && <ErrorBox message={diagnosisError} />}

            {diagnosisResult && (
              <div className="space-y-5 text-xs">
                {/* 1. Diagnostic Summary Card */}
                <div className="rounded-xl bg-slate-950 p-4 border border-slate-800 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-200">Category:</span>
                      <span className="rounded bg-red-950 px-2.5 py-0.5 font-mono text-xs font-bold text-red-300 border border-red-800 uppercase">
                        {diagnosisResult.diagnostic_report?.failure_category}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-slate-400">Evidence Sufficiency:</span>
                      <span className="rounded bg-indigo-950 px-2 py-0.5 font-bold text-indigo-300 uppercase text-[10px] border border-indigo-800">
                        {diagnosisResult.diagnostic_report?.evidence_sufficiency} (
                        {Math.round((diagnosisResult.diagnostic_report?.confidence_score || 0) * 100)}% confidence)
                      </span>
                    </div>
                  </div>

                  {/* Primary Error Box */}
                  {diagnosisResult.diagnostic_report?.primary_error?.error_message && (
                    <div className="rounded-lg bg-red-950/60 p-3 font-mono text-red-200 border border-red-500/30 space-y-1">
                      <div className="font-bold text-red-300 text-[11px]">
                        Failing Component:{" "}
                        {diagnosisResult.diagnostic_report?.primary_error?.failing_tool
                          ? `Tool '${diagnosisResult.diagnostic_report.primary_error.failing_tool}' (Step ${diagnosisResult.diagnostic_report.primary_error.failing_step_index})`
                          : "Agent Unhandled Exception"}
                      </div>
                      <div className="text-[11px] leading-relaxed">
                        [{diagnosisResult.diagnostic_report?.primary_error?.error_type || "Error"}]{" "}
                        {diagnosisResult.diagnostic_report?.primary_error?.error_message}
                      </div>
                    </div>
                  )}

                  {/* Confirmed Observations */}
                  <div className="space-y-1.5 pt-1">
                    <span className="font-semibold text-slate-300 uppercase tracking-wider text-[10px]">
                      Confirmed Ground-Truth Observations:
                    </span>
                    <ul className="list-disc pl-4 space-y-1 text-slate-200">
                      {diagnosisResult.diagnostic_report?.confirmed_observations?.map((obs, idx) => (
                        <li key={idx}>{obs}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* 2. Preceding Events Timeline */}
                {diagnosisResult.diagnostic_report?.preceding_events?.length > 0 && (
                  <div className="rounded-xl bg-slate-950 p-4 border border-slate-800 space-y-2">
                    <span className="font-semibold text-slate-300 uppercase tracking-wider text-[10px] block">
                      Chronological Preceding Events:
                    </span>
                    <div className="space-y-1.5">
                      {diagnosisResult.diagnostic_report.preceding_events.map((ev, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between rounded bg-slate-900 px-3 py-1.5 font-mono text-[11px] border border-slate-800"
                        >
                          <span className="text-slate-200">
                            {ev.step_index}. <strong>{ev.tool_name}</strong>
                          </span>
                          <span className="text-slate-400">
                            Status: <strong className="text-emerald-400">{ev.status}</strong> · Duration:{" "}
                            {ev.duration_ms ? `${Math.round(ev.duration_ms)} ms` : "—"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 3. Timing Anomalies */}
                {diagnosisResult.diagnostic_report?.timing_anomalies?.length > 0 && (
                  <div className="rounded-xl bg-amber-950/30 p-4 border border-amber-500/30 space-y-2 text-amber-200">
                    <span className="font-semibold uppercase tracking-wider text-[10px] block">
                      Timing & Latency Anomalies:
                    </span>
                    <ul className="list-disc pl-4 space-y-1 font-mono text-[11px]">
                      {diagnosisResult.diagnostic_report.timing_anomalies.map((anom, idx) => (
                        <li key={idx}>{anom.description}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 4. Regression Differences */}
                {diagnosisResult.diagnostic_report?.regression_evidence?.length > 0 && (
                  <div className="rounded-xl bg-red-950/30 p-4 border border-red-500/30 space-y-2 text-red-200">
                    <span className="font-semibold uppercase tracking-wider text-[10px] block">
                      Baseline Regression Differences:
                    </span>
                    <ul className="list-disc pl-4 space-y-1 text-[11px]">
                      {diagnosisResult.diagnostic_report.regression_evidence.map((reg, idx) => (
                        <li key={idx}>
                          <strong>[{reg.category}]:</strong> {reg.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 5. Root Cause & Debugging Analysis (AI or Deterministic Rule-Based) */}
                {(() => {
                  const aiStatus = diagnosisResult.ai_analysis?.status;
                  const isAiCompleted = aiStatus === "completed";
                  const analysisData =
                    diagnosisResult.ai_analysis?.deterministic_fallback ||
                    diagnosisResult.ai_analysis?.hypotheses;

                  return (
                    <div className="rounded-xl bg-indigo-950/20 p-4 border border-indigo-500/30 space-y-3">
                      <div className="flex items-center justify-between border-b border-indigo-500/20 pb-2">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-indigo-300 text-sm">
                            {isAiCompleted
                              ? "AI-Assisted Debugging Hypotheses"
                              : "Deterministic Rule-Based Failure Analysis"}
                          </span>
                          <span
                            className={`rounded px-2 py-0.5 text-[10px] font-mono border ${
                              isAiCompleted
                                ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/40"
                                : "bg-amber-500/20 text-amber-300 border-amber-500/40"
                            }`}
                          >
                            {isAiCompleted
                              ? `Local Model: ${diagnosisResult.ai_analysis.model_used}`
                              : "Deterministic Rule-Based (Ollama Offline)"}
                          </span>
                        </div>
                      </div>

                      {!isAiCompleted && (
                        <div className="rounded-lg bg-amber-950/30 border border-amber-500/30 p-2.5 text-xs text-amber-200/90 flex items-start gap-2">
                          <svg className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          <div>
                            <span className="font-semibold text-amber-300">Rule-Based Mode: </span>
                            {diagnosisResult.ai_analysis?.message || "Ollama is unavailable. This analysis was generated deterministically from recorded trace evidence."}
                          </div>
                        </div>
                      )}

                      {analysisData ? (
                        <div className="space-y-3 text-xs">
                          {analysisData.failure_category && (
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-slate-400 uppercase text-[10px]">
                                Failure Classification:
                              </span>
                              <span className="rounded bg-slate-900 px-2 py-0.5 text-amber-300 font-mono text-[11px] border border-slate-700">
                                {analysisData.failure_category}
                              </span>
                            </div>
                          )}

                          <div className="rounded bg-indigo-950/40 p-3 border border-indigo-500/20 text-slate-200 leading-relaxed font-sans">
                            <strong className="text-indigo-300 block mb-1">
                              {isAiCompleted ? "Plain-English Summary:" : "Deterministic Summary:"}
                            </strong>
                            {analysisData.summary}
                          </div>

                          {analysisData.observed_evidence?.length > 0 && (
                            <div>
                              <span className="font-semibold text-slate-300 block mb-1 uppercase text-[10px]">
                                Recorded Trace Evidence:
                              </span>
                              <ul className="list-disc pl-4 space-y-1 text-slate-300 font-mono text-[11px]">
                                {analysisData.observed_evidence.map((ev, i) => (
                                  <li key={i}>{ev}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {analysisData.likely_contributing_factors?.length > 0 && (
                            <div>
                              <span className="font-semibold text-slate-300 block mb-1 uppercase text-[10px]">
                                Likely Contributing Factors:
                              </span>
                              <ul className="list-disc pl-4 space-y-1 text-slate-300">
                                {analysisData.likely_contributing_factors.map((f, i) => (
                                  <li key={i}>{f}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {analysisData.suggested_debugging_steps?.length > 0 && (
                            <div>
                              <span className="font-semibold text-slate-300 block mb-1 uppercase text-[10px]">
                                Suggested Debugging Steps:
                              </span>
                              <ol className="list-decimal pl-4 space-y-1 text-slate-300 font-mono text-[11px]">
                                {analysisData.suggested_debugging_steps.map((s, i) => (
                                  <li key={i}>{s}</li>
                                ))}
                              </ol>
                            </div>
                          )}

                          {analysisData.possible_code_areas_to_inspect?.length > 0 && (
                            <div>
                              <span className="font-semibold text-slate-300 block mb-1 uppercase text-[10px]">
                                Potential Code Areas to Inspect:
                              </span>
                              <div className="flex flex-wrap gap-1.5">
                                {analysisData.possible_code_areas_to_inspect.map((ca, i) => (
                                  <code
                                    key={i}
                                    className="rounded bg-slate-950 px-2 py-0.5 text-indigo-300 font-mono text-[11px] border border-slate-800"
                                  >
                                    {ca}
                                  </code>
                                ))}
                              </div>
                            </div>
                          )}

                          {analysisData.disclaimer && (
                            <p className="text-[10px] text-slate-500 italic pt-1 border-t border-slate-800">
                              {analysisData.disclaimer}
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <p className="text-slate-400 text-xs">
                            {diagnosisResult.ai_analysis?.message || "Operating in deterministic rule-based mode."}
                          </p>
                          <div className="space-y-1 pt-1">
                            <span className="font-semibold text-slate-300 block uppercase text-[10px]">
                              Deterministic Recommendations:
                            </span>
                            <ul className="list-disc pl-4 space-y-1 text-slate-300 font-sans text-xs">
                              {diagnosisResult.diagnostic_report?.deterministic_recommendations?.map((r, i) => (
                                <li key={i}>{r}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
