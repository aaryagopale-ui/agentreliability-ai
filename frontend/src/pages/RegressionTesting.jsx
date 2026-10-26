import { useCallback, useEffect, useState } from "react";
import {
  listBaselines,
  getBaseline,
  createBaseline,
  createBaselineVersion,
  deleteBaseline,
  compareWithBaseline,
  listTraceExecutions,
  listBaselineVersions,
} from "../api.js";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorBox,
  PageTitle,
  StatusBadge,
  useAsyncAction,
} from "../ui.jsx";

const SEVERITY_COLORS = {
  breaking_regression: "bg-red-500/10 text-red-300 ring-red-500/30",
  performance_regression: "bg-amber-500/10 text-amber-300 ring-amber-500/30",
  informational_change: "bg-sky-500/10 text-sky-300 ring-sky-500/30",
  inconclusive: "bg-slate-500/10 text-slate-300 ring-slate-500/30",
};

export default function RegressionTesting({ goTo }) {
  const [baselines, setBaselines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Selected baseline & candidate for comparison
  const [selectedBaselineId, setSelectedBaselineId] = useState(null);
  const [selectedBaseline, setSelectedBaseline] = useState(null);
  const [candidateTraces, setCandidateTraces] = useState([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [durationTolerance, setDurationTolerance] = useState(50.0);

  // Comparison Results
  const [comparisonResult, setComparisonResult] = useState(null);
  const compareAction = useAsyncAction();

  // Version History Modal
  const [historyBaseline, setHistoryBaseline] = useState(null);
  const [versionsList, setVersionsList] = useState([]);

  // New Baseline / New Version Modal
  const [isUpdateModalOpen, setIsUpdateModalOpen] = useState(false);
  const [targetBaselineForUpdate, setTargetBaselineForUpdate] = useState(null);
  const [newVersionTraceId, setNewVersionTraceId] = useState("");
  const [newVersionDescription, setNewVersionDescription] = useState("");
  const updateAction = useAsyncAction();

  const loadBaselines = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listBaselines();
      setBaselines(data);
      if (data.length > 0 && !selectedBaselineId) {
        setSelectedBaselineId(data[0].id);
      }
      setError(null);
    } catch (err) {
      setError(err?.message || "Failed to load baselines.");
    } finally {
      setLoading(false);
    }
  }, [selectedBaselineId]);

  useEffect(() => {
    loadBaselines();
  }, [loadBaselines]);

  // Load candidate traces
  useEffect(() => {
    listTraceExecutions({ limit: 50 })
      .then((res) => {
        setCandidateTraces(res.items || []);
        if (res.items?.length > 0 && !selectedCandidateId) {
          setSelectedCandidateId(res.items[0].execution_id);
        }
      })
      .catch(() => {});
  }, [selectedCandidateId]);

  // Load selected baseline detail
  useEffect(() => {
    if (!selectedBaselineId) {
      setSelectedBaseline(null);
      return;
    }
    getBaseline(selectedBaselineId)
      .then((b) => {
        setSelectedBaseline(b);
        setComparisonResult(null); // reset report when changing baseline
      })
      .catch(() => setSelectedBaseline(null));
  }, [selectedBaselineId]);

  async function handleRunComparison() {
    if (!selectedBaselineId || !selectedCandidateId) return;
    const report = await compareAction.run(() =>
      compareWithBaseline(selectedBaselineId, {
        candidate_trace_id: selectedCandidateId,
        duration_tolerance_pct: Number(durationTolerance),
      })
    );
    if (report) {
      setComparisonResult(report);
    }
  }

  async function handleOpenHistory(b) {
    setHistoryBaseline(b);
    try {
      const vers = await listBaselineVersions(b.id);
      setVersionsList(vers);
    } catch {
      setVersionsList([]);
    }
  }

  async function handleDeleteBaseline(id) {
    if (!confirm("Are you sure you want to delete this baseline and its version history?")) return;
    try {
      await deleteBaseline(id);
      if (selectedBaselineId === id) setSelectedBaselineId(null);
      loadBaselines();
    } catch (err) {
      alert(err.message || "Failed to delete baseline");
    }
  }

  async function handlePromoteCandidateAsVersion() {
    if (!selectedBaselineId || !selectedCandidateId) return;
    const ok = await updateAction.run(async () => {
      await createBaselineVersion(selectedBaselineId, {
        source_type: "trace",
        source_id: selectedCandidateId,
        description: `Promoted candidate trace ${selectedCandidateId.slice(0, 8)} to next version`,
      });
      // reload
      const updated = await getBaseline(selectedBaselineId);
      setSelectedBaseline(updated);
      setComparisonResult(null);
      loadBaselines();
    });
  }

  async function handleCreateNewVersionSubmit(e) {
    e.preventDefault();
    if (!targetBaselineForUpdate || !newVersionTraceId) return;
    await updateAction.run(async () => {
      await createBaselineVersion(targetBaselineForUpdate.id, {
        source_type: "trace",
        source_id: newVersionTraceId,
        description: newVersionDescription.trim() || undefined,
      });
      setIsUpdateModalOpen(false);
      setNewVersionDescription("");
      loadBaselines();
      if (selectedBaselineId === targetBaselineForUpdate.id) {
        const refreshed = await getBaseline(selectedBaselineId);
        setSelectedBaseline(refreshed);
      }
    });
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Deterministic Regression Testing"
        subtitle="Lock down golden behavior baselines from verified agent traces and perform deterministic comparisons to detect breaking changes, missing tools, output schema violations, and latency regressions."
      >
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={loadBaselines}>
            Refresh
          </Button>
          <Button onClick={() => goTo && goTo("monitoring")} variant="secondary">
            Select Trace from Monitoring
          </Button>
        </div>
      </PageTitle>

      {error && <ErrorBox message={error} />}

      {baselines.length === 0 && !loading ? (
        <Card className="text-center py-12">
          <div className="mx-auto max-w-md space-y-3">
            <h3 className="text-lg font-semibold text-slate-100">No Golden Baselines Saved Yet</h3>
            <p className="text-sm text-slate-400">
              Golden baselines lock down verified tool sequences, output schemas, and maximum runtime limits.
              Go to <strong>Live Agent Monitoring</strong>, select an execution trace, and click <strong>"Save as Golden Baseline"</strong> to create your first baseline.
            </p>
            <div className="pt-2">
              <Button onClick={() => goTo && goTo("monitoring")}>
                Go to Live Agent Monitoring
              </Button>
            </div>
          </div>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-12">
          {/* Left Column: Baselines List (4 cols) */}
          <div className="lg:col-span-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
                Golden Baselines ({baselines.length})
              </h3>
            </div>

            <div className="space-y-3 max-h-[80vh] overflow-y-auto pr-1">
              {baselines.map((b) => (
                <div
                  key={b.id}
                  onClick={() => setSelectedBaselineId(b.id)}
                  className={`cursor-pointer rounded-xl p-4 transition border ${
                    selectedBaselineId === b.id
                      ? "border-indigo-500 bg-indigo-500/10 ring-1 ring-indigo-500"
                      : "border-slate-800 bg-slate-900/60 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h4 className="font-semibold text-slate-100">{b.name}</h4>
                      <p className="text-xs font-mono text-indigo-400 mt-0.5">{b.agent_name}</p>
                    </div>
                    <span className="rounded bg-indigo-600/20 text-indigo-300 px-2 py-0.5 text-xs font-mono font-bold border border-indigo-500/30">
                      v{b.current_version}
                    </span>
                  </div>

                  {b.description && (
                    <p className="text-xs text-slate-400 mt-2 line-clamp-2">{b.description}</p>
                  )}

                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800 text-[11px] text-slate-400">
                    <span>
                      Tools: <strong>{b.version_data?.tools?.length || 0}</strong>
                    </span>
                    <span>
                      Duration: <strong>{b.version_data?.duration_ms ? `${Math.round(b.version_data.duration_ms)}ms` : "—"}</strong>
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenHistory(b);
                      }}
                      className="text-xs text-indigo-400 hover:text-indigo-300 underline font-sans"
                    >
                      History
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right Column: Baseline Details & Regression Comparison (8 cols) */}
          <div className="lg:col-span-8 space-y-6">
            {selectedBaseline ? (
              <>
                {/* Active Baseline Card */}
                <Card>
                  <div className="flex flex-wrap items-start justify-between gap-4 pb-4 border-b border-slate-800">
                    <div>
                      <div className="flex items-center gap-3">
                        <h2 className="text-xl font-bold text-slate-100">{selectedBaseline.name}</h2>
                        <span className="rounded bg-indigo-500/20 text-indigo-300 px-2.5 py-0.5 text-xs font-mono font-bold ring-1 ring-indigo-500/40">
                          Active Version: v{selectedBaseline.current_version}
                        </span>
                        <StatusBadge status={selectedBaseline.version_data?.status || "success"} />
                      </div>
                      <p className="text-xs text-slate-400 mt-1">
                        Agent: <strong className="text-slate-200">{selectedBaseline.agent_name}</strong> · Source:{" "}
                        <span className="font-mono text-slate-300">{selectedBaseline.version_data?.source_id}</span>
                      </p>
                      {selectedBaseline.description && (
                        <p className="text-xs text-slate-300 mt-2">{selectedBaseline.description}</p>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setTargetBaselineForUpdate(selectedBaseline);
                          setIsUpdateModalOpen(true);
                        }}
                      >
                        + New Version
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => handleDeleteBaseline(selectedBaseline.id)}
                        className="text-red-400 hover:text-red-300"
                      >
                        Delete
                      </Button>
                    </div>
                  </div>

                  {/* Golden Invariant Assertions */}
                  <div className="mt-4 grid gap-3 sm:grid-cols-3 text-xs">
                    <div className="rounded-lg bg-slate-950 p-3 border border-slate-800">
                      <span className="text-slate-400 font-medium">Expected Tool Sequence</span>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {selectedBaseline.version_data?.expected?.tool_sequence?.map((t, idx) => (
                          <span
                            key={idx}
                            className="rounded bg-slate-900 text-slate-200 px-1.5 py-0.5 font-mono text-[11px] border border-slate-700"
                          >
                            {idx + 1}. {t}
                          </span>
                        )) || <span className="text-slate-500 italic">None specified</span>}
                      </div>
                      <div className="mt-2 text-[10px] text-slate-500">
                        Strict Order:{" "}
                        <strong className="text-slate-300">
                          {selectedBaseline.version_data?.expected?.strict_order ? "YES" : "NO"}
                        </strong>
                      </div>
                    </div>

                    <div className="rounded-lg bg-slate-950 p-3 border border-slate-800">
                      <span className="text-slate-400 font-medium">Output Schema Keys</span>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {selectedBaseline.version_data?.expected?.expected_output_fields?.map((k) => (
                          <span
                            key={k}
                            className="rounded bg-emerald-950/60 text-emerald-300 px-1.5 py-0.5 font-mono text-[11px] border border-emerald-800/40"
                          >
                            {k}
                          </span>
                        )) || <span className="text-slate-500 italic">Any output accepted</span>}
                      </div>
                      <div className="mt-2 text-[10px] text-slate-500">
                        Status Invariant:{" "}
                        <strong className="text-slate-300">
                          {selectedBaseline.version_data?.expected?.status || "success"}
                        </strong>
                      </div>
                    </div>

                    <div className="rounded-lg bg-slate-950 p-3 border border-slate-800">
                      <span className="text-slate-400 font-medium">Duration & Latency Budget</span>
                      <div className="mt-1 text-sm font-bold text-emerald-400 font-mono">
                        {selectedBaseline.version_data?.expected?.max_duration_ms
                          ? `< ${Math.round(selectedBaseline.version_data.expected.max_duration_ms)} ms`
                          : "No hard cap"}
                      </div>
                      <p className="mt-1 text-[11px] text-slate-500">
                        Baseline latency: {Math.round(selectedBaseline.version_data?.duration_ms || 0)} ms
                      </p>
                    </div>
                  </div>
                </Card>

                {/* Candidate Comparison Runner */}
                <Card>
                  <h3 className="text-base font-semibold text-slate-100 mb-3">
                    Run Deterministic Regression Comparison
                  </h3>
                  <div className="grid gap-4 sm:grid-cols-12 items-end">
                    <div className="sm:col-span-6">
                      <label className="block text-xs uppercase text-slate-400 mb-1">
                        Candidate Trace Execution
                      </label>
                      <select
                        value={selectedCandidateId}
                        onChange={(e) => setSelectedCandidateId(e.target.value)}
                        className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                      >
                        {candidateTraces.map((t) => (
                          <option key={t.execution_id} value={t.execution_id}>
                            {t.agent_name} ({t.execution_id.slice(0, 8)}) — {t.status} (
                            {t.duration_ms ? `${Math.round(t.duration_ms)}ms` : "in progress"})
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="sm:col-span-3">
                      <label className="block text-xs uppercase text-slate-400 mb-1">
                        Latency Tolerance ({durationTolerance}%)
                      </label>
                      <input
                        type="range"
                        min="10"
                        max="200"
                        step="10"
                        value={durationTolerance}
                        onChange={(e) => setDurationTolerance(e.target.value)}
                        className="w-full accent-indigo-500"
                      />
                    </div>

                    <div className="sm:col-span-3">
                      <Button
                        onClick={handleRunComparison}
                        disabled={compareAction.busy || !selectedCandidateId}
                        className="w-full"
                      >
                        {compareAction.busy ? "Analyzing..." : "Compare Behavior"}
                      </Button>
                    </div>
                  </div>
                </Card>

                {/* Regression Comparison Report */}
                {comparisonResult && (
                  <Card className="space-y-4">
                    {/* Verdict Banner */}
                    <div
                      className={`rounded-xl p-4 border flex flex-wrap items-center justify-between gap-3 ${
                        comparisonResult.verdict === "passed"
                          ? "bg-emerald-950/40 border-emerald-500/50 text-emerald-200"
                          : comparisonResult.verdict === "regression"
                          ? "bg-red-950/40 border-red-500/50 text-red-200"
                          : comparisonResult.verdict === "performance_warning"
                          ? "bg-amber-950/40 border-amber-500/50 text-amber-200"
                          : "bg-slate-900 border-slate-700 text-slate-300"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span
                          className={`h-3 w-3 rounded-full ${
                            comparisonResult.verdict === "passed"
                              ? "bg-emerald-400"
                              : comparisonResult.verdict === "regression"
                              ? "bg-red-500 animate-pulse"
                              : comparisonResult.verdict === "performance_warning"
                              ? "bg-amber-400"
                              : "bg-slate-500"
                          }`}
                        />
                        <div>
                          <h4 className="font-bold text-base uppercase tracking-wider">
                            Verdict: {comparisonResult.verdict.replace("_", " ")}
                          </h4>
                          <p className="text-xs opacity-90 mt-0.5">{comparisonResult.summary}</p>
                        </div>
                      </div>

                      {/* Quick Summary Counts */}
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-red-950 px-2 py-0.5 text-xs font-semibold text-red-300 border border-red-800">
                          {comparisonResult.counts?.breaking || 0} Breaking
                        </span>
                        <span className="rounded bg-amber-950 px-2 py-0.5 text-xs font-semibold text-amber-300 border border-amber-800">
                          {comparisonResult.counts?.performance || 0} Latency
                        </span>
                        <span className="rounded bg-sky-950 px-2 py-0.5 text-xs font-semibold text-sky-300 border border-sky-800">
                          {comparisonResult.counts?.informational || 0} Info
                        </span>
                      </div>
                    </div>

                    {/* Side-by-Side Summary Comparison Cards */}
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="rounded-lg bg-slate-950 p-4 border border-slate-800 space-y-2">
                        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                          <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                            Baseline (v{comparisonResult.baseline_version || selectedBaseline.current_version})
                          </span>
                          <StatusBadge status={comparisonResult.baseline?.status || "success"} />
                        </div>
                        <div className="text-xs space-y-1 text-slate-300 font-mono">
                          <div>
                            Duration:{" "}
                            <strong>
                              {comparisonResult.baseline?.duration_ms
                                ? `${Math.round(comparisonResult.baseline.duration_ms)} ms`
                                : "—"}
                            </strong>
                          </div>
                          <div>
                            Tool Calls:{" "}
                            <strong>{comparisonResult.baseline?.tool_count ?? comparisonResult.baseline?.tool_sequence?.length}</strong>
                          </div>
                          <div className="pt-1 flex flex-wrap gap-1">
                            {comparisonResult.baseline?.tool_sequence?.map((t, i) => (
                              <span key={i} className="rounded bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-300 border border-slate-800">
                                {t}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>

                      <div className="rounded-lg bg-slate-950 p-4 border border-slate-800 space-y-2">
                        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                          <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                            Candidate Execution
                          </span>
                          <StatusBadge status={comparisonResult.candidate?.status || "unknown"} />
                        </div>
                        <div className="text-xs space-y-1 text-slate-300 font-mono">
                          <div>
                            Duration:{" "}
                            <strong>
                              {comparisonResult.candidate?.duration_ms
                                ? `${Math.round(comparisonResult.candidate.duration_ms)} ms`
                                : "—"}
                            </strong>
                          </div>
                          <div>
                            Tool Calls:{" "}
                            <strong>{comparisonResult.candidate?.tool_count ?? comparisonResult.candidate?.tool_sequence?.length}</strong>
                          </div>
                          <div className="pt-1 flex flex-wrap gap-1">
                            {comparisonResult.candidate?.tool_sequence?.map((t, i) => (
                              <span key={i} className="rounded bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-300 border border-slate-800">
                                {t}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Detailed Differences List */}
                    {comparisonResult.differences?.length > 0 ? (
                      <div className="space-y-2">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 pt-2">
                          Detected Differences & Ground Truth Evidence ({comparisonResult.differences.length})
                        </h4>
                        <div className="space-y-2">
                          {comparisonResult.differences.map((diff, idx) => (
                            <div
                              key={idx}
                              className={`rounded-lg p-3 text-xs border ${
                                SEVERITY_COLORS[diff.severity] || "bg-slate-900 border-slate-800"
                              }`}
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <span className="font-semibold uppercase tracking-wider text-[11px]">
                                  {diff.category.replace(/_/g, " ")}
                                </span>
                                <span className="rounded px-2 py-0.5 text-[10px] font-mono font-bold uppercase">
                                  {diff.severity.replace(/_/g, " ")}
                                </span>
                              </div>
                              <p className="mt-1 font-sans text-sm text-slate-100">{diff.message}</p>
                              {diff.evidence && (
                                <pre className="mt-2 rounded bg-slate-950 p-2 font-mono text-[11px] text-slate-300 overflow-x-auto">
                                  {JSON.stringify(diff.evidence, null, 2)}
                                </pre>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-lg bg-emerald-500/10 p-3 text-xs text-emerald-300 border border-emerald-500/20 text-center">
                        ✓ Exact behavior match. All tool sequences, output schema fields, and duration limits satisfied.
                      </div>
                    )}

                    {/* Promotion Action */}
                    <div className="pt-3 border-t border-slate-800 flex items-center justify-between">
                      <span className="text-xs text-slate-400">
                        Accept these changes and make candidate trace the new golden standard?
                      </span>
                      <Button
                        onClick={handlePromoteCandidateAsVersion}
                        disabled={updateAction.busy}
                        variant="secondary"
                      >
                        {updateAction.busy ? "Promoting..." : `Promote to v${selectedBaseline.current_version + 1}`}
                      </Button>
                    </div>
                  </Card>
                )}
              </>
            ) : (
              <Card>
                <Empty>Select a golden baseline from the list to review its assertions and run regression comparisons.</Empty>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* Baseline History Modal */}
      {historyBaseline && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-2xl rounded-2xl bg-slate-900 p-6 border border-slate-700 shadow-2xl space-y-4 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-slate-100">
                  Version History: {historyBaseline.name}
                </h3>
                <p className="text-xs text-slate-400">{historyBaseline.agent_name}</p>
              </div>
              <Button variant="ghost" onClick={() => setHistoryBaseline(null)}>
                ✕ Close
              </Button>
            </div>

            <div className="space-y-3">
              {versionsList.map((ver) => (
                <div
                  key={ver.version}
                  className="rounded-lg bg-slate-950 p-4 border border-slate-800 space-y-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-indigo-400 text-sm">
                      Version {ver.version} {ver.version === historyBaseline.current_version && "(Current Active)"}
                    </span>
                    <span className="text-slate-500 font-mono">
                      {new Date(ver.created_at).toLocaleString()}
                    </span>
                  </div>

                  {ver.description && (
                    <p className="text-slate-300 italic">{ver.description}</p>
                  )}

                  <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400 pt-1">
                    <div>
                      Source: <strong className="text-slate-200 font-mono">{ver.source_id}</strong>
                    </div>
                    <div>
                      Duration: <strong className="text-emerald-400">{ver.duration_ms ? `${Math.round(ver.duration_ms)} ms` : "—"}</strong>
                    </div>
                  </div>

                  <div className="pt-2 flex flex-wrap gap-1">
                    {ver.tools?.map((t, idx) => (
                      <span key={idx} className="rounded bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-300 border border-slate-800">
                        {idx + 1}. {t.tool_name || t.name}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Create New Version Modal */}
      {isUpdateModalOpen && targetBaselineForUpdate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-slate-900 p-6 border border-slate-700 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-slate-100">
                Advance Baseline to v{targetBaselineForUpdate.current_version + 1}
              </h3>
              <Button variant="ghost" onClick={() => setIsUpdateModalOpen(false)}>
                ✕
              </Button>
            </div>

            <form onSubmit={handleCreateNewVersionSubmit} className="space-y-4">
              <div>
                <label className="block text-xs uppercase text-slate-400 mb-1">
                  Source Candidate Trace
                </label>
                <select
                  value={newVersionTraceId}
                  onChange={(e) => setNewVersionTraceId(e.target.value)}
                  required
                  className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                >
                  <option value="">Select candidate trace...</option>
                  {candidateTraces.map((t) => (
                    <option key={t.execution_id} value={t.execution_id}>
                      {t.agent_name} ({t.execution_id.slice(0, 8)}) — {t.status}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs uppercase text-slate-400 mb-1">
                  Change Description / Release Notes
                </label>
                <input
                  type="text"
                  placeholder="e.g. Added shipment confirmation step"
                  value={newVersionDescription}
                  onChange={(e) => setNewVersionDescription(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100 ring-1 ring-slate-800"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <Button variant="ghost" type="button" onClick={() => setIsUpdateModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={updateAction.busy || !newVersionTraceId}>
                  {updateAction.busy ? "Creating Version..." : "Create New Version"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

