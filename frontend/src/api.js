// Thin wrapper around fetch for our backend API.
async function request(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data?.detail;
    const err = new Error(typeof d === "string" ? d : d?.message || "Request failed");
    err.problems = d?.problems || [];
    throw err;
  }
  return data;
}

export const listExecutions = () => request("/api/executions");
export const getExecution = (id) => request(`/api/executions/${id}`);
export const uploadLog = (file) => {
  const form = new FormData();
  form.append("file", file);
  return request("/api/executions", { method: "POST", body: form });
};


// ---- Phase 2 ----
const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const getOverview = () => request("/api/overview");
export const getFailureAnalysis = () => request("/api/failure-analysis");
export const listTests = () => request("/api/tests");
export const getTest = (id) => request(`/api/tests/${id}`);
export const createTest = (body) => request("/api/tests", json("POST", body));
export const createTestFromExecution = (execId) =>
  request(`/api/tests/from-execution/${execId}`, { method: "POST" });
export const updateTest = (id, body) => request(`/api/tests/${id}`, json("PUT", body));
export const deleteTest = (id) => request(`/api/tests/${id}`, { method: "DELETE" });
export const runTest = (id) => request(`/api/tests/${id}/run`, { method: "POST" });
export const runAllTests = () => request("/api/tests/run-all", { method: "POST" });
export const listRuns = (testId) =>
  request(testId ? `/api/test-runs?test_id=${testId}` : "/api/test-runs");
export const getRun = (id) => request(`/api/test-runs/${id}`);

// ---- Phase 3 ----
export const listTraceExecutions = (params = {}) => {
  const q = new URLSearchParams();
  if (params.agent) q.set("agent", params.agent);
  if (params.status) q.set("status", params.status);
  if (params.failure_kind) q.set("failure_kind", params.failure_kind);
  if (params.since) q.set("since", params.since);
  if (params.limit) q.set("limit", params.limit);
  const s = q.toString();
  return request(s ? `/api/traces/executions?${s}` : "/api/traces/executions");
};
export const getTraceExecution = (id) => request(`/api/traces/executions/${id}`);
export const listTraceAgents = () => request("/api/traces/agents");
export const createTestFromTrace = (execId, name) =>
  request(`/api/traces/executions/${execId}/create-test`, json("POST", { name }));

// ---- Phase 4 ----
export const listCIRuns = () => request("/api/ci/runs");
export const getCIRun = (id) => request(`/api/ci/runs/${id}`);
