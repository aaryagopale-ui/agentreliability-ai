import { useMemo, useState } from "react";
import { Badge, Button, StatusBadge } from "../ui.jsx";
import { createBaseline, createTestFromTrace, diagnoseExecution } from "../api.js";

const FAILURE_LABELS = {
  timeout: "Timeout Error",
  tool_failure: "Tool Call Failure",
  unexpected_exception: "Unexpected Exception",
};

/**
 * Format duration in milliseconds with appropriate units.
 */
function formatDuration(ms) {
  if (ms == null || isNaN(ms)) return "—";
  if (ms < 1) return `${(ms * 1000).toFixed(0)} µs`;
  if (ms < 1000) return `${ms.toFixed(1)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/**
 * Safely format ISO timestamp to time string with milliseconds.
 */
function formatTime(isoString) {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    return isNaN(d.getTime()) ? isoString : d.toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit", fractionalSecondDigits: 3 });
  } catch {
    return isoString;
  }
}

/**
 * Truncating payload viewer with copy support to prevent UI freezing on large payloads.
 */
function SafePayloadViewer({ label, data, defaultExpanded = false }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [copied, setCopied] = useState(false);

  if (data === undefined || data === null) {
    return (
      <div className="rounded bg-slate-950 p-2 text-xs text-slate-500 italic">
        {label}: (None captured or disabled)
      </div>
    );
  }

  const jsonString = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  const isLarge = jsonString.length > 800;
  const displayString = isLarge && !expanded ? jsonString.slice(0, 800) + "\n... [truncated for performance]" : jsonString;

  const handleCopy = () => {
    navigator.clipboard?.writeText(jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded bg-slate-950 p-2.5 ring-1 ring-slate-800 text-xs font-mono">
      <div className="flex items-center justify-between text-slate-400 mb-1 font-sans">
        <span className="font-semibold text-[11px] uppercase tracking-wider">{label}</span>
        <div className="flex items-center gap-2">
          {isLarge && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-indigo-400 hover:text-indigo-300 text-[11px] underline"
            >
              {expanded ? "Collapse" : `Show full (${jsonString.length} chars)`}
            </button>
          )}
          <button
            onClick={handleCopy}
            className="text-slate-400 hover:text-slate-200 text-[11px] px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700"
          >
            {copied ? "Copied!" : "Copy JSON"}
          </button>
        </div>
      </div>
      <pre className="overflow-x-auto max-h-48 text-slate-300 leading-relaxed text-[11px] whitespace-pre-wrap break-all">
        {displayString}
      </pre>
    </div>
  );
}

export default function TraceExecutionTimeline({ detail, onCreateTest, isCreatingTest, testNotice, goTo }) {
  const [viewMode, setViewMode] = useState("both"); // "timeline", "waterfall", "both"
  const [selectedCallId, setSelectedCallId] = useState(null);
  const [expandedSteps, setExpandedSteps] = useState({});
  const [displayLimit, setDisplayLimit] = useState(50); // Large trace windowing limit

  const toggleStep = (id) => {
    setExpandedSteps((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const expandAll = () => {
    const all = {};
    detail?.tool_calls?.forEach((t) => { all[t.call_id] = true; });
    setExpandedSteps(all);
  };

  const collapseAll = () => {
    setExpandedSteps({});
  };

  // Modals for Step 3:
  const [isCustomTestModalOpen, setIsCustomTestModalOpen] = useState(false);
  const [isBaselineModalOpen, setIsBaselineModalOpen] = useState(false);
  const [localTestNotice, setLocalTestNotice] = useState(null);
  const [baselineNotice, setBaselineNotice] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [modalError, setModalError] = useState(null);

  // Custom Test Form State
  const [customTestName, setCustomTestName] = useState("");
  const [customTestDesc, setCustomTestDesc] = useState("");
  const [expectedStatus, setExpectedStatus] = useState("success");
  const [strictOrder, setStrictOrder] = useState(true);
  const [allowAdditional, setAllowAdditional] = useState(false);
  const [outputFields, setOutputFields] = useState("");
  const [expectedErrorType, setExpectedErrorType] = useState("");
  const [maxDurationMs, setMaxDurationMs] = useState("");

  // Baseline Form State
  const [baselineName, setBaselineName] = useState("");
  const [baselineDesc, setBaselineDesc] = useState("");

  // Evidence-Based Failure Diagnosis State (Phase 6 Step 4)
  const [timelineDiagnosis, setTimelineDiagnosis] = useState(null);
  const [isDiagnosing, setIsDiagnosing] = useState(false);
  const [diagnosisErr, setDiagnosisErr] = useState(null);

  const handleRunTimelineDiagnosis = async () => {
    if (!detail?.execution_id) return;
    setIsDiagnosing(true);
    setDiagnosisErr(null);
    try {
      const res = await diagnoseExecution({
        execution_id: String(detail.execution_id),
        source_type: "trace",
        use_ai: true,
      });
      setTimelineDiagnosis(res);
    } catch (err) {
      setDiagnosisErr(err.message || "Failed to run diagnosis.");
    } finally {
      setIsDiagnosing(false);
    }
  };

  const openCustomTestModal = () => {
    setModalError(null);
    setCustomTestName(`${detail.agent_name} / trace ${detail.execution_id.slice(0, 8)}`);
    setCustomTestDesc(`Created from recorded real execution trace ${detail.execution_id}`);
    setExpectedStatus(detail.status || "success");
    setStrictOrder(true);
    setAllowAdditional(false);
    const out = detail.output;
    if (out && typeof out === "object" && !Array.isArray(out)) {
      setOutputFields(Object.keys(out).join(", "));
    } else {
      setOutputFields("");
    }
    setExpectedErrorType(detail.error_type || "");
    setMaxDurationMs(detail.duration_ms ? String(Math.round(detail.duration_ms * 1.5)) : "");
    setIsCustomTestModalOpen(true);
  };

  const openBaselineModal = () => {
    setModalError(null);
    setBaselineName(`${detail.agent_name} Golden Baseline`);
    setBaselineDesc(`Golden baseline captured from trace ${detail.execution_id.slice(0, 8)}`);
    setIsBaselineModalOpen(true);
  };

  const handleCustomTestSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setModalError(null);
    try {
      const toolSeq = (detail.tool_calls || []).map((t) => t.tool_name).filter(Boolean);
      const fields = outputFields.split(",").map((s) => s.trim()).filter(Boolean);
      const payload = {
        name: customTestName.trim(),
        description: customTestDesc.trim() || undefined,
        expected: {
          status: expectedStatus,
          tool_sequence: toolSeq,
          final_output: detail.output,
          expected_output_fields: fields.length > 0 ? fields : undefined,
          expected_error_type: expectedErrorType.trim() || undefined,
          max_duration_ms: maxDurationMs ? Number(maxDurationMs) : undefined,
          strict_order: strictOrder,
          allow_additional_tools: allowAdditional,
        },
      };
      const created = await createTestFromTrace(detail.execution_id, payload);
      setLocalTestNotice(created);
      setIsCustomTestModalOpen(false);
    } catch (err) {
      setModalError(err.message || "Failed to create test case.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBaselineSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setModalError(null);
    try {
      const toolSeq = (detail.tool_calls || []).map((t) => t.tool_name).filter(Boolean);
      const fields = outputFields.split(",").map((s) => s.trim()).filter(Boolean);
      const payload = {
        name: baselineName.trim(),
        description: baselineDesc.trim() || undefined,
        source_type: "trace",
        source_id: detail.execution_id,
        expected: {
          status: detail.status || "success",
          tool_sequence: toolSeq,
          final_output: detail.output,
          expected_output_fields: fields.length > 0 ? fields : undefined,
          expected_error_type: detail.error_type || undefined,
          max_duration_ms: detail.duration_ms ? Math.round(detail.duration_ms * 1.5) : undefined,
          strict_order: true,
          allow_additional_tools: false,
        },
      };
      const created = await createBaseline(payload);
      setBaselineNotice(created);
      setIsBaselineModalOpen(false);
    } catch (err) {
      setModalError(err.message || "Failed to create baseline.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Reconstruct parent-child hierarchy and chronological waterfall spans
  const { toolTree, totalDurationMs, startEpochMs, failedToolCall, precedingTools } = useMemo(() => {
    if (!detail) return { toolTree: [], totalDurationMs: 0, startEpochMs: 0, failedToolCall: null, precedingTools: [] };

    const startEpoch = detail.started_at ? new Date(detail.started_at).getTime() : 0;
    let totalDur = detail.duration_ms;

    const tools = Array.isArray(detail.tool_calls) ? [...detail.tool_calls] : [];

    // Sort chronologically by started_at if available
    tools.sort((a, b) => {
      const ta = a.started_at ? new Date(a.started_at).getTime() : 0;
      const tb = b.started_at ? new Date(b.started_at).getTime() : 0;
      return ta - tb;
    });

    if (!totalDur || totalDur <= 0) {
      if (detail.ended_at && detail.started_at) {
        totalDur = Math.max(1, new Date(detail.ended_at).getTime() - startEpoch);
      } else if (tools.length > 0) {
        totalDur = tools.reduce((acc, t) => acc + (t.duration_ms || 0), 10);
      } else {
        totalDur = 100;
      }
    }

    // Identify first failed tool call and preceding steps for debugging
    let failedTool = null;
    const preceding = [];
    for (const t of tools) {
      if (t.status !== "success" && !failedTool) {
        failedTool = t;
        break;
      }
      preceding.push(t);
    }

    // Build hierarchical tree if parent_call_id is present
    const map = {};
    const roots = [];

    tools.forEach((t) => {
      map[t.call_id] = { ...t, children: [] };
    });

    tools.forEach((t) => {
      if (t.parent_call_id && t.parent_call_id !== t.call_id && map[t.parent_call_id]) {
        map[t.parent_call_id].children.push(map[t.call_id]);
      } else {
        roots.push(map[t.call_id]);
      }
    });

    return {
      toolTree: roots,
      totalDurationMs: totalDur,
      startEpochMs: startEpoch,
      failedToolCall: failedTool,
      precedingTools: preceding,
    };
  }, [detail]);

  if (!detail) return null;

  return (
    <div className="space-y-6">
      {/* Execution Header Card */}
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-5">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 className="text-xl font-bold text-slate-100">{detail.agent_name}</h2>
            <StatusBadge status={detail.status} />
            {detail.metadata?.synthetic_demo || detail.execution_id?.startsWith("demo-") ? (
              <Badge tone="purple">Synthetic Demo Execution</Badge>
            ) : (
              <Badge tone="green">Recorded Real Execution</Badge>
            )}
            {detail.failure_kind && (
              <Badge tone="red">{FAILURE_LABELS[detail.failure_kind] || detail.failure_kind}</Badge>
            )}
          </div>
          <p className="text-xs font-mono text-slate-400">
            Execution ID: <span className="text-slate-300 font-semibold">{detail.execution_id}</span>
          </p>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400 pt-1">
            <span>Started: <strong className="text-slate-200">{formatTime(detail.started_at)}</strong></span>
            {detail.ended_at && (
              <span>Ended: <strong className="text-slate-200">{formatTime(detail.ended_at)}</strong></span>
            )}
            <span>Total Duration: <strong className="text-emerald-400">{formatDuration(detail.duration_ms)}</strong></span>
            <span>Tool Calls: <strong className="text-slate-200">{detail.tool_calls?.length || 0}</strong></span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* View Mode Selector */}
          <div className="inline-flex rounded-lg bg-slate-950 p-1 ring-1 ring-slate-800 text-xs">
            <button
              onClick={() => setViewMode("both")}
              className={`rounded px-2.5 py-1 font-medium transition ${
                viewMode === "both" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Combined View
            </button>
            <button
              onClick={() => setViewMode("waterfall")}
              className={`rounded px-2.5 py-1 font-medium transition ${
                viewMode === "waterfall" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Waterfall
            </button>
            <button
              onClick={() => setViewMode("timeline")}
              className={`rounded px-2.5 py-1 font-medium transition ${
                viewMode === "timeline" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Timeline
            </button>
          </div>

          <Button
            variant="ghost"
            onClick={openCustomTestModal}
            disabled={detail.status === "running"}
            className="flex items-center gap-1.5 text-xs"
          >
            Custom Test Case
          </Button>

          <Button
            variant="secondary"
            onClick={openBaselineModal}
            disabled={detail.status === "running"}
            className="flex items-center gap-1.5 text-xs"
          >
            Set as Golden Baseline
          </Button>

          <Button
            onClick={onCreateTest}
            disabled={isCreatingTest || detail.status === "running"}
            className="flex items-center gap-1.5 text-xs"
          >
            {isCreatingTest ? "Creating..." : "Quick Test"}
          </Button>
        </div>
      </div>

      {baselineNotice && (
        <div className="rounded-lg bg-indigo-500/10 p-3.5 text-sm text-indigo-300 ring-1 ring-indigo-500/30 flex items-center justify-between">
          <span>
            Golden baseline “<strong>{baselineNotice.name}</strong>” (v{baselineNotice.current_version}) saved!
          </span>
          {goTo && (
            <button
              className="text-xs font-semibold underline hover:text-indigo-200"
              onClick={() => goTo("regression")}
            >
              Go to Regression Testing
            </button>
          )}
        </div>
      )}

      {(localTestNotice || testNotice) && (
        <div className="rounded-lg bg-emerald-500/10 p-3.5 text-sm text-emerald-300 ring-1 ring-emerald-500/30 flex items-center justify-between">
          <span>
            Test case “<strong>{(localTestNotice || testNotice).name}</strong>” generated in SQLite test suite!
          </span>
          {goTo && (
            <button
              className="text-xs font-semibold underline hover:text-emerald-200"
              onClick={() => goTo("tests")}
            >
              Go to Test Cases to Replay
            </button>
          )}
        </div>
      )}

      {/* STEP 5: Root Cause & Debugging Inspector (For Failed Runs) */}
      {detail.status === "failed" && (
        <div className="rounded-xl border border-red-500/30 bg-red-950/20 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="flex h-3 w-3 rounded-full bg-red-500 animate-pulse" />
              <h3 className="text-base font-bold text-red-200">
                Debugger & Failure Diagnosis
              </h3>
            </div>
            <span className="rounded bg-red-900/60 px-2.5 py-0.5 text-xs font-mono text-red-200 border border-red-500/40">
              {detail.error_type || failedToolCall?.error_type || "Exception"}
            </span>
          </div>

          {/* Three-Tier Truth Section */}
          <div className="grid gap-3 sm:grid-cols-3">
            {/* 1. Recorded Ground Truth */}
            <div className="rounded-lg bg-slate-950/90 p-3.5 border border-slate-800">
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                1. Recorded Ground Truth
              </span>
              <p className="mt-1 text-xs text-slate-300">
                Exact execution logs and tool responses captured by the Python SDK.
              </p>
              {failedToolCall ? (
                <div className="mt-2 text-xs text-red-300 font-mono">
                  Failing Tool: <strong>{failedToolCall.tool_name}</strong>
                  {failedToolCall.retry_count > 0 && ` (Attempt ${failedToolCall.retry_count + 1})`}
                </div>
              ) : (
                <div className="mt-2 text-xs text-red-300 font-mono">
                  Failed during agent execution level.
                </div>
              )}
            </div>

            {/* 2. Deterministic Heuristic Classification */}
            <div className="rounded-lg bg-slate-950/90 p-3.5 border border-slate-800">
              <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400">
                2. Deterministic Classification
              </span>
              <p className="mt-1 text-xs text-slate-300">
                Rule-based categorization evaluated directly from error kinds without model hallucination.
              </p>
              <div className="mt-2 text-xs font-semibold text-slate-200">
                Category: <span className="text-amber-300 font-mono">{FAILURE_LABELS[detail.failure_kind] || detail.failure_kind || "Unclassified"}</span>
              </div>
            </div>

            {/* 3. AI-Generated Root Cause Explanation */}
            <div className="rounded-lg bg-slate-950/90 p-3.5 border border-slate-800 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400">
                    3. AI Root Cause Analysis
                  </span>
                  {timelineDiagnosis?.ai_diagnosis_available && (
                    <span className="text-[10px] rounded bg-purple-950/80 text-purple-300 px-1.5 py-0.5 border border-purple-800">
                      Ollama Local
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-slate-300">
                  {timelineDiagnosis
                    ? (timelineDiagnosis.ai_diagnosis_available ? "AI-assisted hypothesis & recommendations generated." : "Deterministic evidence report generated.")
                    : "Intelligent root-cause explanation with optional local Ollama."}
                </p>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <Button
                  size="sm"
                  variant={timelineDiagnosis ? "secondary" : "primary"}
                  onClick={handleRunTimelineDiagnosis}
                  disabled={isDiagnosing}
                >
                  {isDiagnosing ? "Analyzing..." : timelineDiagnosis ? "Re-diagnose" : "Analyze Failure"}
                </Button>
                {goTo && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => goTo("failures")}
                  >
                    View All Failures →
                  </Button>
                )}
              </div>
            </div>
          </div>

          {diagnosisErr && (
            <div className="rounded bg-red-950/80 p-2.5 text-xs text-red-300 border border-red-800">
              {diagnosisErr}
            </div>
          )}

          {/* Interactive Failure Diagnosis Report */}
          {timelineDiagnosis && (() => {
            const report = timelineDiagnosis.diagnostic_report || {};
            const ai = timelineDiagnosis.ai_analysis || {};
            const isAiActive = ai.status === "completed" && ai.hypotheses;
            return (
              <div className="rounded-xl border border-indigo-500/30 bg-slate-950 p-4 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-slate-100">Evidence-Based Diagnostic Report</span>
                    <Badge tone={report.evidence_sufficiency === "sufficient" ? "green" : "amber"}>
                      {report.evidence_sufficiency === "sufficient" ? "Evidence Sufficient" : "Inconclusive"}
                    </Badge>
                    {isAiActive && (
                      <Badge tone="indigo">Local AI Powered ({ai.model_used || "ollama"})</Badge>
                    )}
                  </div>
                  <span className="text-xs font-mono text-slate-400">
                    Confidence: <span className="font-semibold text-slate-200">{Math.round((report.confidence_score || 0.8) * 100)}%</span>
                  </span>
                </div>

                {/* Confirmed Observations Checklist */}
                {report.confirmed_observations?.length > 0 && (
                  <div>
                    <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2">
                      Confirmed Trace Evidence
                    </h4>
                    <ul className="space-y-1.5 text-xs text-slate-300">
                      {report.confirmed_observations.map((obs, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className="text-emerald-400 mt-0.5">✓</span>
                          <span>{obs}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Timing Anomalies */}
                {report.timing_anomalies?.length > 0 && (
                  <div className="rounded bg-amber-950/30 p-2.5 border border-amber-500/30">
                    <h4 className="text-[11px] font-bold uppercase tracking-wider text-amber-300 mb-1">
                      Timing Anomalies
                    </h4>
                    <ul className="space-y-1 text-xs text-amber-200">
                      {report.timing_anomalies.map((ano, idx) => (
                        <li key={idx}>⏱ {ano.description || JSON.stringify(ano)}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Deterministic Recommendations */}
                {report.deterministic_recommendations?.length > 0 && (
                  <div>
                    <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2">
                      Recommended Fixes & Mitigations
                    </h4>
                    <ul className="space-y-1 text-xs text-slate-300 list-disc list-inside">
                      {report.deterministic_recommendations.map((rec, idx) => (
                        <li key={idx}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* AI-Generated Hypotheses & Remediation Suggestions */}
                {isAiActive && (
                  <div className="rounded-lg bg-indigo-950/20 p-3.5 border border-indigo-500/30 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                        <span>🤖</span> AI Debugging Hypotheses & Remediation
                      </span>
                      <span className="text-[10px] text-amber-400 bg-amber-950/40 px-2 py-0.5 rounded border border-amber-800">
                        AI Hypothesis — Not Verified Fact
                      </span>
                    </div>
                    <div className="text-xs text-slate-200 leading-relaxed whitespace-pre-wrap">
                      {ai.hypotheses.summary}
                    </div>
                    {ai.hypotheses.potential_fixes?.length > 0 && (
                      <div className="mt-2 space-y-1">
                        <span className="text-[11px] font-semibold text-indigo-300">Suggested Fixes:</span>
                        <ul className="space-y-1 text-xs text-slate-300 list-decimal list-inside">
                          {ai.hypotheses.potential_fixes.map((sug, idx) => (
                            <li key={idx}>{sug}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })()}

          {/* Error Message Monospace Banner */}
          <div className="rounded-lg bg-red-950/60 p-3.5 border border-red-500/20 font-mono text-xs text-red-200">
            <span className="font-bold text-red-300 uppercase tracking-wider text-[10px] block mb-1">
              Captured Error Message:
            </span>
            <div className="break-words select-all">
              {detail.error_message || failedToolCall?.error_message || "No explicit error message string recorded in trace."}
            </div>
          </div>

          {/* Preceding Execution Breadcrumb */}
          {precedingTools.length > 0 && (
            <div className="text-xs text-slate-400">
              <span className="font-semibold text-slate-300">Preceding Steps: </span>
              {precedingTools.map((t, idx) => (
                <span key={t.call_id} className="inline-flex items-center gap-1">
                  <span className="text-emerald-400">{t.tool_name} ({formatDuration(t.duration_ms)})</span>
                  {idx < precedingTools.length - 1 && <span className="text-slate-600">→</span>}
                </span>
              ))}
              <span className="text-slate-600"> → </span>
              <span className="text-red-400 font-semibold">{failedToolCall?.tool_name || "Agent Error"} (Failed)</span>
            </div>
          )}
        </div>
      )}

      {/* STEP 4: Horizontal Execution Waterfall View */}
      {(viewMode === "waterfall" || viewMode === "both") && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-300">
              Execution Waterfall (Relative Timing)
            </h3>
            <span className="text-xs text-slate-400 font-mono">
              Total Span: {formatDuration(totalDurationMs)}
            </span>
          </div>

          <div className="rounded-xl bg-slate-950 p-4 ring-1 ring-slate-800 overflow-x-auto min-w-[500px]">
            {/* Timeline Ruler */}
            <div className="relative mb-3 h-5 border-b border-slate-800 text-[10px] font-mono text-slate-500">
              <span className="absolute left-0">0 ms</span>
              <span className="absolute left-1/4 -translate-x-1/2">{formatDuration(totalDurationMs * 0.25)}</span>
              <span className="absolute left-1/2 -translate-x-1/2">{formatDuration(totalDurationMs * 0.5)}</span>
              <span className="absolute left-3/4 -translate-x-1/2">{formatDuration(totalDurationMs * 0.75)}</span>
              <span className="absolute right-0 text-right">{formatDuration(totalDurationMs)}</span>
            </div>

            {/* Waterfall Rows */}
            <div className="space-y-2">
              {/* Overall Agent Span */}
              <div className="relative flex items-center h-7 text-xs">
                <div className="w-48 truncate pr-2 font-semibold text-slate-200 shrink-0">
                  🤖 {detail.agent_name}
                </div>
                <div className="relative flex-1 h-5 bg-slate-900 rounded overflow-hidden">
                  <div
                    className={`h-full rounded transition-all ${
                      detail.status === "failed" ? "bg-red-500/80" : "bg-indigo-600/80"
                    }`}
                    style={{ left: "0%", width: "100%" }}
                    title={`Agent: ${detail.agent_name} (${formatDuration(totalDurationMs)})`}
                  />
                </div>
                <div className="w-20 text-right text-[11px] font-mono text-slate-400 pl-2 shrink-0">
                  {formatDuration(totalDurationMs)}
                </div>
              </div>

              {/* Tool Call Spans */}
              {detail.tool_calls?.slice(0, displayLimit).map((tool, idx) => {
                const isErr = tool.status !== "success";
                const toolStart = tool.started_at ? new Date(tool.started_at).getTime() : startEpochMs;
                const offsetMs = Math.max(0, toolStart - startEpochMs);
                const leftPct = totalDurationMs > 0 ? Math.min(99, Math.max(0, (offsetMs / totalDurationMs) * 100)) : 0;
                const toolDur = tool.duration_ms || 1;
                const widthPct = totalDurationMs > 0 ? Math.min(100 - leftPct, Math.max(1.5, (toolDur / totalDurationMs) * 100)) : 5;
                const isSelected = selectedCallId === tool.call_id;
                const isNested = Boolean(tool.parent_call_id);

                return (
                  <div
                    key={tool.call_id}
                    onClick={() => {
                      setSelectedCallId(tool.call_id);
                      toggleStep(tool.call_id);
                    }}
                    className={`group relative flex items-center h-7 text-xs cursor-pointer rounded px-1 -mx-1 hover:bg-slate-900/60 ${
                      isSelected ? "bg-indigo-500/10 ring-1 ring-indigo-500/30" : ""
                    }`}
                  >
                    <div className="w-48 truncate pr-2 font-mono text-[11px] text-slate-300 shrink-0 flex items-center gap-1">
                      {isNested && <span className="text-slate-500 pl-2">↳</span>}
                      <span>{idx + 1}. {tool.tool_name}</span>
                      {tool.retry_count > 0 && (
                        <span className="rounded bg-amber-500/20 text-amber-300 px-1 py-0.2 text-[9px]">
                          R{tool.retry_count}
                        </span>
                      )}
                    </div>
                    <div className="relative flex-1 h-5 bg-slate-900/60 rounded overflow-hidden">
                      <div
                        className={`absolute h-full rounded transition-all cursor-pointer ${
                          isErr ? "bg-red-500 hover:bg-red-400 shadow-sm shadow-red-500/50" : "bg-emerald-500 hover:bg-emerald-400 shadow-sm shadow-emerald-500/50"
                        }`}
                        style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                        title={`${tool.tool_name}: ${formatDuration(tool.duration_ms)} (+${formatDuration(offsetMs)} from start)`}
                      />
                    </div>
                    <div className="w-20 text-right text-[11px] font-mono text-slate-400 pl-2 shrink-0">
                      {formatDuration(tool.duration_ms)}
                    </div>
                  </div>
                );
              })}

              {detail.tool_calls?.length > displayLimit && (
                <div className="flex items-center justify-between rounded bg-slate-900/80 px-3 py-2 text-xs text-slate-300 border border-slate-800 mt-2">
                  <span>
                    Showing first <strong>{displayLimit}</strong> of <strong>{detail.tool_calls.length}</strong> spans (Optimized Large Trace Mode)
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setDisplayLimit((prev) => prev + 50)}
                      className="px-2.5 py-1 rounded bg-indigo-600/30 text-indigo-300 hover:bg-indigo-600/50 text-[11px] font-semibold"
                    >
                      Show Next 50
                    </button>
                    <button
                      onClick={() => setDisplayLimit(detail.tool_calls.length)}
                      className="px-2.5 py-1 rounded bg-slate-800 text-slate-200 hover:bg-slate-700 text-[11px]"
                    >
                      Show All ({detail.tool_calls.length})
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* STEP 3: Visual Execution Timeline (Chronological & Hierarchical) */}
      {(viewMode === "timeline" || viewMode === "both") && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-300">
              Execution Timeline ({detail.tool_calls?.length || 0} Steps)
            </h3>
            <div className="flex items-center gap-2 text-xs">
              <button
                onClick={expandAll}
                className="text-slate-400 hover:text-slate-200 underline"
              >
                Expand all
              </button>
              <span className="text-slate-600">·</span>
              <button
                onClick={collapseAll}
                className="text-slate-400 hover:text-slate-200 underline"
              >
                Collapse all
              </button>
            </div>
          </div>

          <div className="relative pl-6 border-l-2 border-slate-700 space-y-5">
            {/* 1. Execution Start Node */}
            <div className="relative">
              <span className="absolute -left-[31px] top-1.5 h-3.5 w-3.5 rounded-full bg-indigo-500 ring-4 ring-slate-900" />
              <div className="rounded-lg bg-slate-900/90 p-3.5 ring-1 ring-slate-800">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-200 text-sm">
                    🚀 Agent Execution Started
                  </span>
                  <span className="text-xs font-mono text-slate-400">
                    {formatTime(detail.started_at)}
                  </span>
                </div>
                {detail.input && (
                  <div className="mt-2.5">
                    <SafePayloadViewer label="Agent Input Arguments" data={detail.input} />
                  </div>
                )}
                {detail.metadata && Object.keys(detail.metadata).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {Object.entries(detail.metadata).map(([k, v]) => (
                      <span key={k} className="rounded bg-slate-950 px-2 py-0.5 text-[10px] font-mono text-slate-400 border border-slate-800">
                        {k}: <strong className="text-slate-300">{String(v)}</strong>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* 2. Tool Calls (Chronological with Hierarchical Nesting Support) */}
            {toolTree.slice(0, displayLimit).map((rootTool, idx) => (
              <ToolNode
                key={rootTool.call_id}
                tool={rootTool}
                index={idx + 1}
                expanded={Boolean(expandedSteps[rootTool.call_id])}
                onToggle={() => toggleStep(rootTool.call_id)}
                isHighlighted={selectedCallId === rootTool.call_id}
                depth={0}
              />
            ))}

            {toolTree.length > displayLimit && (
              <div className="flex items-center justify-between rounded bg-slate-900/80 px-3 py-2 text-xs text-slate-300 border border-slate-800">
                <span>
                  Showing <strong>{displayLimit}</strong> of <strong>{toolTree.length}</strong> top-level steps (Optimized Mode)
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setDisplayLimit((prev) => prev + 50)}
                    className="px-2.5 py-1 rounded bg-indigo-600/30 text-indigo-300 hover:bg-indigo-600/50 text-[11px] font-semibold"
                  >
                    Show Next 50
                  </button>
                  <button
                    onClick={() => setDisplayLimit(toolTree.length)}
                    className="px-2.5 py-1 rounded bg-slate-800 text-slate-200 hover:bg-slate-700 text-[11px]"
                  >
                    Show All ({toolTree.length})
                  </button>
                </div>
              </div>
            )}

            {/* 3. Execution Completion Node */}
            <div className="relative">
              <span
                className={`absolute -left-[31px] top-1.5 h-3.5 w-3.5 rounded-full ring-4 ring-slate-900 ${
                  detail.status === "failed" ? "bg-red-500" : detail.status === "running" ? "bg-amber-500 animate-pulse" : "bg-emerald-500"
                }`}
              />
              <div
                className={`rounded-lg p-3.5 ring-1 ${
                  detail.status === "failed"
                    ? "bg-red-950/20 ring-red-500/30"
                    : "bg-slate-900/90 ring-slate-800"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-200 text-sm">
                    {detail.status === "failed"
                      ? "🛑 Agent Execution Failed"
                      : detail.status === "running"
                      ? "⏳ Agent Execution In Progress..."
                      : "🏁 Agent Execution Completed Successfully"}
                  </span>
                  <span className="text-xs font-mono text-slate-400">
                    {detail.ended_at ? formatTime(detail.ended_at) : "running"}
                  </span>
                </div>

                {detail.output && (
                  <div className="mt-2.5">
                    <SafePayloadViewer label="Final Agent Output" data={detail.output} />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Create Test with Custom Assertions */}
      {isCustomTestModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-slate-900 p-6 border border-slate-700 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-slate-100">Create Test with Custom Assertions</h3>
                <p className="text-xs text-slate-400">Convert real agent trace into a reusable regression test.</p>
              </div>
              <Button variant="ghost" onClick={() => setIsCustomTestModalOpen(false)}>✕</Button>
            </div>

            {modalError && (
              <div className="rounded-lg bg-red-950/80 p-3 text-xs text-red-300 border border-red-500/30">
                {modalError}
              </div>
            )}

            <form onSubmit={handleCustomTestSubmit} className="space-y-3.5 text-xs">
              <div>
                <label className="block uppercase text-slate-400 mb-1 font-semibold">Test Name</label>
                <input
                  type="text"
                  required
                  value={customTestName}
                  onChange={(e) => setCustomTestName(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                />
              </div>

              <div>
                <label className="block uppercase text-slate-400 mb-1 font-semibold">Description</label>
                <textarea
                  rows="2"
                  value={customTestDesc}
                  onChange={(e) => setCustomTestDesc(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block uppercase text-slate-400 mb-1 font-semibold">Expected Status</label>
                  <select
                    value={expectedStatus}
                    onChange={(e) => setExpectedStatus(e.target.value)}
                    className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                  >
                    <option value="success">Success</option>
                    <option value="failed">Failed</option>
                  </select>
                </div>

                <div>
                  <label className="block uppercase text-slate-400 mb-1 font-semibold">Max Duration (ms)</label>
                  <input
                    type="number"
                    placeholder="e.g. 500"
                    value={maxDurationMs}
                    onChange={(e) => setMaxDurationMs(e.target.value)}
                    className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                  />
                </div>
              </div>

              <div>
                <label className="block uppercase text-slate-400 mb-1 font-semibold">
                  Required Output Fields (comma separated)
                </label>
                <input
                  type="text"
                  placeholder="e.g. order_id, status, total"
                  value={outputFields}
                  onChange={(e) => setOutputFields(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                />
                <span className="text-[10px] text-slate-500">Replay fails if candidate output lacks any of these keys.</span>
              </div>

              {expectedStatus === "failed" && (
                <div>
                  <label className="block uppercase text-slate-400 mb-1 font-semibold">Expected Error Type</label>
                  <input
                    type="text"
                    placeholder="e.g. WarehouseError"
                    value={expectedErrorType}
                    onChange={(e) => setExpectedErrorType(e.target.value)}
                    className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                  />
                </div>
              )}

              <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-2">
                <span className="font-semibold text-slate-300 block">Tool Sequence Assertions:</span>
                <div className="flex flex-wrap gap-1">
                  {(detail.tool_calls || []).map((t, idx) => (
                    <span key={idx} className="rounded bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-300 border border-slate-700">
                      {idx + 1}. {t.tool_name}
                    </span>
                  ))}
                </div>
                <div className="pt-2 flex flex-col gap-1.5 text-slate-300">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={strictOrder}
                      onChange={(e) => setStrictOrder(e.target.checked)}
                      className="rounded bg-slate-900 border-slate-700 text-indigo-600"
                    />
                    <span>Strict Tool Order (fail if tools execute in different sequence)</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={allowAdditional}
                      onChange={(e) => setAllowAdditional(e.target.checked)}
                      className="rounded bg-slate-900 border-slate-700 text-indigo-600"
                    />
                    <span>Allow Additional Tools (do not fail if agent invokes extra allowable tools)</span>
                  </label>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <Button variant="ghost" type="button" onClick={() => setIsCustomTestModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Creating..." : "Save Custom Test Case"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Set as Golden Baseline */}
      {isBaselineModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-slate-900 p-6 border border-slate-700 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-slate-100">Set as Golden Baseline</h3>
                <p className="text-xs text-slate-400">Lock down this trace as Version 1 for regression comparison.</p>
              </div>
              <Button variant="ghost" onClick={() => setIsBaselineModalOpen(false)}>✕</Button>
            </div>

            {modalError && (
              <div className="rounded-lg bg-red-950/80 p-3 text-xs text-red-300 border border-red-500/30">
                {modalError}
              </div>
            )}

            <form onSubmit={handleBaselineSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block uppercase text-slate-400 mb-1 font-semibold">Baseline Name</label>
                <input
                  type="text"
                  required
                  value={baselineName}
                  onChange={(e) => setBaselineName(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                />
              </div>

              <div>
                <label className="block uppercase text-slate-400 mb-1 font-semibold">Description</label>
                <textarea
                  rows="2"
                  value={baselineDesc}
                  onChange={(e) => setBaselineDesc(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                />
              </div>

              <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-2">
                <span className="font-semibold text-slate-300 block">Locked Tool Sequence:</span>
                <div className="flex flex-wrap gap-1">
                  {(detail.tool_calls || []).map((t, idx) => (
                    <span key={idx} className="rounded bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-300 border border-slate-700">
                      {idx + 1}. {t.tool_name}
                    </span>
                  ))}
                </div>
                <p className="text-[11px] text-slate-500 pt-1">
                  Baseline duration: {Math.round(detail.duration_ms || 0)} ms · Status: {detail.status}
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <Button variant="ghost" type="button" onClick={() => setIsBaselineModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Saving..." : "Lock as Golden Baseline (v1)"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Recursive Tool Call Node component displaying status, duration, retry badges, and nested children.
 */
function ToolNode({ tool, index, expanded, onToggle, isHighlighted, depth = 0 }) {
  const isErr = tool.status !== "success";

  return (
    <div className={`relative ${depth > 0 ? "ml-5 mt-3 pl-3 border-l-2 border-indigo-500/40" : ""}`}>
      {depth === 0 && (
        <span
          className={`absolute -left-[31px] top-1.5 h-3.5 w-3.5 rounded-full ring-4 ring-slate-900 ${
            isErr ? "bg-red-500" : "bg-emerald-500"
          }`}
        />
      )}

      <div
        className={`rounded-lg p-3.5 transition text-sm ring-1 ${
          isHighlighted
            ? "bg-indigo-500/10 ring-indigo-500"
            : isErr
            ? "bg-red-950/20 ring-red-500/40"
            : "bg-slate-800/60 ring-slate-700/60"
        }`}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={onToggle}
              className="font-semibold text-slate-100 hover:text-indigo-300 text-left flex items-center gap-1.5"
            >
              <span>{depth > 0 ? "↳" : `${index}.`}</span>
              <span>{tool.tool_name}</span>
              <span className="text-slate-500 text-xs font-mono">({expanded ? "▲ hide" : "▼ details"})</span>
            </button>

            <Badge tone={isErr ? "red" : "green"}>{tool.status}</Badge>

            {tool.retry_count > 0 && (
              <span className="rounded bg-amber-500/20 text-amber-300 px-2 py-0.5 text-xs font-semibold ring-1 ring-amber-500/40">
                Attempt {tool.retry_count + 1} (Retry #{tool.retry_count})
              </span>
            )}

            {depth > 0 && (
              <span className="rounded bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 text-[10px] font-mono">
                Nested Sub-Tool
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 text-xs font-mono">
            {tool.started_at && (
              <span className="text-slate-500">{formatTime(tool.started_at)}</span>
            )}
            <span className="font-semibold text-slate-300">{formatDuration(tool.duration_ms)}</span>
          </div>
        </div>

        {/* Error message callout if tool failed */}
        {tool.error_message && (
          <div className="mt-2.5 rounded bg-red-950/80 p-2.5 text-xs font-mono text-red-200 border border-red-500/30">
            <strong className="text-red-300">{tool.error_type ? `[${tool.error_type}] ` : "Error: "}</strong>
            {tool.error_message}
          </div>
        )}

        {/* Expandable Inputs & Outputs */}
        {expanded && (
          <div className="mt-3 pt-3 border-t border-slate-700/60 grid gap-3 sm:grid-cols-2">
            <SafePayloadViewer label="Tool Input Arguments" data={tool.input} defaultExpanded={true} />
            <SafePayloadViewer label="Tool Output Result" data={tool.output} defaultExpanded={true} />
          </div>
        )}

        {/* Render Nested Children if any */}
        {tool.children && tool.children.length > 0 && (
          <div className="mt-2 space-y-2">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-400 mt-2">
              Nested Sub-Calls ({tool.children.length}):
            </div>
            {tool.children.map((child, cIdx) => (
              <ToolNode
                key={child.call_id}
                tool={child}
                index={cIdx + 1}
                expanded={expanded}
                onToggle={onToggle}
                isHighlighted={false}
                depth={depth + 1}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

