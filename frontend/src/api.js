// Thin wrapper around fetch for our backend API with Multi-Tenant & CSRF support.

let currentProjectId = null;
let cachedCsrfToken = null;

export function setActiveProjectId(id) {
  currentProjectId = id ? Number(id) : null;
}

export function getActiveProjectId() {
  return currentProjectId;
}

export function getCookie(name) {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
  return match ? decodeURIComponent(match[2]) : null;
}

export function getCsrfToken() {
  return cachedCsrfToken || getCookie("agentreliability_csrf");
}

const RAW_API_BASE = (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.VITE_API_BASE_URL) || "";
const API_BASE = RAW_API_BASE.replace(/\/+$/, "");

async function request(path, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };

  // Attach project scoping header if a project is active
  if (currentProjectId) {
    headers["X-Project-Id"] = String(currentProjectId);
  }

  // Attach double-submit CSRF token for cookie-authenticated mutating requests
  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }
  }

  // Bounded request timeout to prevent frontend hanging indefinitely on an unresponsive backend
  const timeoutMs = options.timeoutMs || 10000;
  let controller = null;
  let timeoutId = null;

  if (typeof AbortController !== "undefined" && !options.signal) {
    controller = new AbortController();
    timeoutId = setTimeout(() => {
      controller.abort();
    }, timeoutMs);
  }

  const fetchOptions = {
    ...options,
    headers,
    credentials: "include", // Ensure session and CSRF cookies are always included
    signal: options.signal || (controller ? controller.signal : undefined),
  };

  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  let res;
  try {
    res = await fetch(url, fetchOptions);
  } catch (netErr) {
    const rawMsg = netErr?.message || String(netErr);
    const isTimeout =
      netErr?.name === "AbortError" ||
      rawMsg.includes("abort") ||
      rawMsg.includes("timeout") ||
      rawMsg.includes("timed out");
    const isConnErr =
      rawMsg.includes("Load failed") ||
      rawMsg.includes("Failed to fetch") ||
      rawMsg.includes("NetworkError") ||
      netErr instanceof TypeError;
    const err = new Error(
      isTimeout
        ? `Backend Request Timed Out (${Math.round(timeoutMs / 1000)}s): The AgentReliability backend API stopped responding. The service may be hung, overloaded, or unresponsively blocked on I/O. Please run 'agentreliability doctor' or restart with 'agentreliability dev'.`
        : isConnErr
        ? "Backend Server Unreachable: Could not connect to AgentReliability backend API. Please verify that 'agentreliability dev' is running on port 8001."
        : `Network request failed: ${rawMsg}`
    );
    err.status = 0;
    err.isTimeout = isTimeout;
    err.isNetworkError = isConnErr || isTimeout;
    err.originalError = netErr;
    throw err;
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }

  // Capture CSRF token from response headers for cross-origin setups
  const csrfHeader = res.headers?.get ? res.headers.get("X-CSRF-Token") : null;
  if (csrfHeader) {
    cachedCsrfToken = csrfHeader;
  }

  // If unauthenticated (401), broadcast unauthorized event so app can redirect
  if (res.status === 401 && !path.startsWith("/api/auth/login") && !path.startsWith("/api/auth/register")) {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("agentreliability:unauthorized"));
    }
  }

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    const d = data?.detail;
    let msg = typeof d === "string" ? d : d?.message || "Request failed";
    if (res.status === 502 || res.status === 504) {
      msg = `Backend Gateway Error (${res.status}): The frontend dashboard proxy cannot reach the AgentReliability backend. Please ensure 'agentreliability dev' is running on port 8001.`;
    }
    const err = new Error(msg);
    err.status = res.status;
    err.isNetworkError = res.status === 502 || res.status === 504;
    err.problems = d?.problems || [];
    throw err;
  }
  return data;
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// ---- Authentication (Phase 5A) ----
export const register = (body) => request("/api/auth/register", json("POST", body));
export const login = (body) => request("/api/auth/login", json("POST", body));
export const logout = () => request("/api/auth/logout", { method: "POST" });
export const getMe = () => request("/api/auth/me");
export const forgotPassword = (body) => request("/api/auth/forgot-password", json("POST", body));
export const resetPassword = (body) => request("/api/auth/reset-password", json("POST", body));

// ---- Projects (Phase 5A) ----
export const listProjects = () => request("/api/projects");
export const createProject = (body) => request("/api/projects", json("POST", body));
export const getProject = (id) => request(`/api/projects/${id}`);
export const updateProject = (id, body) => request(`/api/projects/${id}`, json("PATCH", body));
export const archiveProject = (id, body) => request(`/api/projects/${id}`, json("DELETE", body));
export const claimProject = (id) => request(`/api/projects/${id}/claim`, { method: "POST" });

// ---- API Keys (Phase 5A) ----
export const listProjectKeys = (projectId) => request(`/api/projects/${projectId}/keys`);
export const createProjectKey = (projectId, body) =>
  request(`/api/projects/${projectId}/keys`, json("POST", body || {}));
export const revokeProjectKey = (projectId, keyId) =>
  request(`/api/projects/${projectId}/keys/${keyId}`, { method: "DELETE" });
export const rotateProjectKey = (projectId, keyId) =>
  request(`/api/projects/${projectId}/keys/${keyId}/rotate`, { method: "POST" });

// ---- Phase 1: Executions ----
export const listExecutions = () => request("/api/executions");
export const getExecution = (id) => request(`/api/executions/${id}`);
export const uploadLog = (file) => {
  const form = new FormData();
  form.append("file", file);
  return request("/api/executions", { method: "POST", body: form });
};

// ---- Phase 2: Tests & Replay ----
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

// ---- Phase 3: Live Traces ----
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
export const createTestFromTrace = (execId, body) =>
  request(`/api/traces/executions/${execId}/create-test`, json("POST", typeof body === "string" ? { name: body } : (body || {})));

// ---- Phase 4: CI/CD Testing ----
export const listCIRuns = () => request("/api/ci/runs");
export const getCIRun = (id) => request(`/api/ci/runs/${id}`);

// ---- Phase 6 Step 3: Baselines & Regression Testing ----
export const listBaselines = (agentName) =>
  request(agentName ? `/api/baselines?agent_name=${encodeURIComponent(agentName)}` : "/api/baselines");
export const getBaseline = (id) => request(`/api/baselines/${id}`);
export const createBaseline = (body) => request("/api/baselines", json("POST", body));
export const createBaselineVersion = (id, body) =>
  request(`/api/baselines/${id}/versions`, json("POST", body));
export const listBaselineVersions = (id) => request(`/api/baselines/${id}/versions`);
export const getBaselineVersion = (id, version) => request(`/api/baselines/${id}/versions/${version}`);
export const deleteBaseline = (id) => request(`/api/baselines/${id}`, { method: "DELETE" });
export const compareWithBaseline = (baselineId, body) =>
  request(`/api/baselines/${baselineId}/compare`, json("POST", body));
export const compareTraces = (baselineTraceId, candidateTraceId, durationTolerancePct = 50.0) =>
  request(
    `/api/regression/compare-traces?baseline_trace_id=${encodeURIComponent(baselineTraceId)}&candidate_trace_id=${encodeURIComponent(candidateTraceId)}&duration_tolerance_pct=${durationTolerancePct}`,
    { method: "POST" }
  );

// ---- Phase 6 Step 4: AI Failure Analysis & Diagnostics ----
export const getOllamaStatus = () => request("/api/failure-analysis/ollama/status");
export const diagnoseExecution = (body) => request("/api/failure-analysis/diagnose", json("POST", body));

// ---- Phase 7: One-Click Demo Experience ----
export const seedDemoData = () => request("/api/demo/seed", json("POST", {}));
export const getDemoStatus = () => request("/api/demo/status");

// ---- System & Instance Diagnostics ----
export const getSystemInfo = () => request("/api/v1/system/info");


