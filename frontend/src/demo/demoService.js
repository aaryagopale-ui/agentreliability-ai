/**
 * In-memory synthetic API service for Public Demo Mode.
 *
 * Intercepts API requests when demo mode is active, serving rich, realistic
 * interactive data with zero network latency, zero database load, and
 * 100% isolation from production data.
 */
import {
  DEMO_USER,
  DEMO_SYSTEM_INFO,
  DEMO_PROJECTS,
  DEMO_TRACES_P1,
  DEMO_BASELINES_P1,
  DEMO_TESTS_P1,
  DEMO_TEST_RUNS_P1,
  DEMO_CI_RUNS_P1,
  DEMO_FAILURE_ANALYSIS_P1,
  DEMO_API_KEYS_P1,
} from "./demoData.js";

class DemoService {
  constructor() {
    this.resetState();
  }

  resetState() {
    this.user = { ...DEMO_USER };
    this.systemInfo = { ...DEMO_SYSTEM_INFO };
    this.projects = JSON.parse(JSON.stringify(DEMO_PROJECTS));
    this.currentProjectId = 1;
    this.traces = JSON.parse(JSON.stringify(DEMO_TRACES_P1));
    this.baselines = JSON.parse(JSON.stringify(DEMO_BASELINES_P1));
    this.tests = JSON.parse(JSON.stringify(DEMO_TESTS_P1));
    this.testRuns = JSON.parse(JSON.stringify(DEMO_TEST_RUNS_P1));
    this.ciRuns = JSON.parse(JSON.stringify(DEMO_CI_RUNS_P1));
    this.failureAnalysis = JSON.parse(JSON.stringify(DEMO_FAILURE_ANALYSIS_P1));
    this.apiKeys = JSON.parse(JSON.stringify(DEMO_API_KEYS_P1));
  }

  setCurrentProjectId(id) {
    this.currentProjectId = Number(id) || 1;
  }

  // --- Auth & User ---
  async getMe() {
    return { ...this.user };
  }

  async getSystemInfo() {
    return { ...this.systemInfo };
  }

  async logout() {
    // In demo mode, "logout" resets the demo state
    this.resetState();
    return { message: "Demo state reset" };
  }

  // --- Projects ---
  async listProjects() {
    return [...this.projects];
  }

  async getProject(id) {
    const proj = this.projects.find((p) => p.id === Number(id));
    if (!proj) throw new Error("Project not found");
    return { ...proj };
  }

  async createProject(body) {
    const newProj = {
      id: Date.now(),
      name: body.name || "Custom Demo Agent",
      description: body.description || "Created during demo session",
      created_at: new Date().toISOString(),
      owner_id: this.user.id,
    };
    this.projects.push(newProj);
    return newProj;
  }

  // --- Overview ---
  async getOverview() {
    const passedTests = this.tests.filter((t) => t.last_status === "passed").length;
    const failedTests = this.tests.filter((t) => t.last_status === "failed").length;
    return {
      executions: {
        total: 18,
        passed: 15,
        failed: 3,
      },
      live_traces: {
        total: this.traces.length,
        passed: this.traces.filter((t) => t.status === "completed").length,
        failed: this.traces.filter((t) => t.status === "failed").length,
      },
      tests: {
        total: this.tests.length,
        passed: passedTests,
        failed: failedTests,
        not_run: 0,
      },
      recent_runs: this.testRuns.slice(0, 5),
    };
  }

  // --- Live Traces & Observability ---
  async listTraceExecutions(params = {}) {
    let filtered = [...this.traces];
    if (params.agent) {
      filtered = filtered.filter((t) => t.agent_name.toLowerCase().includes(params.agent.toLowerCase()));
    }
    if (params.status) {
      filtered = filtered.filter((t) => t.status === params.status);
    }
    return {
      items: filtered,
      total: filtered.length,
    };
  }

  async getTraceExecution(id) {
    const trace = this.traces.find((t) => t.execution_id === id);
    if (!trace) {
      // Fallback: return first trace if exact ID not found
      return this.traces[0];
    }
    return JSON.parse(JSON.stringify(trace));
  }

  async listTraceAgents() {
    const agents = Array.from(new Set(this.traces.map((t) => t.agent_name)));
    return agents;
  }

  async createTestFromTrace(execId, body) {
    const trace = await this.getTraceExecution(execId);
    const newTest = {
      id: Date.now(),
      project_id: this.currentProjectId,
      name: (body && body.name) || `Test from ${trace.agent_name}`,
      agent_name: trace.agent_name,
      description: `Generated from trace ${trace.execution_id}`,
      source_type: "trace",
      source_id: trace.execution_id,
      step_count: trace.tool_calls.length,
      last_status: "not_run",
      created_at: new Date().toISOString(),
      steps: trace.tool_calls.map((c, i) => ({
        step: i + 1,
        tool: c.tool_name,
        expected_arguments: c.parameters,
        mock_output: c.result || { status: "simulated_success" },
      })),
    };
    this.tests.push(newTest);
    return newTest;
  }

  // --- Golden Baselines & Regressions ---
  async listBaselines() {
    return [...this.baselines];
  }

  async getBaseline(id) {
    const b = this.baselines.find((x) => x.id === Number(id));
    if (!b) throw new Error("Baseline not found");
    return { ...b };
  }

  async listBaselineVersions(id) {
    const b = await this.getBaseline(id);
    return b.versions || [];
  }

  async compareWithBaseline(baselineId, body) {
    const baseline = await this.getBaseline(baselineId);
    const candidateTraceId = body.candidate_trace_id;
    const candidate = this.traces.find((t) => t.execution_id === candidateTraceId) || this.traces[0];

    const activeVer = baseline.versions.find((v) => v.version === baseline.active_version) || baseline.versions[0];
    const expectedSequence = activeVer.rules?.require_tools_sequence || [];
    const actualSequence = candidate.tool_calls.map((c) => c.tool_name);

    // Check missing tools
    const missing = expectedSequence.filter((step) => !actualSequence.includes(step));
    const isDurationOutlier = candidate.duration_ms > activeVer.expected_duration_ms * 1.5;

    let verdict = "passed";
    let classification = "no_regression";
    let message = "Execution conforms strictly to the Golden Baseline step sequence and latency bounds.";

    if (missing.length > 0) {
      verdict = "failed";
      classification = "breaking_regression";
      message = `Breaking sequence regression: omitted expected step(s) [${missing.join(", ")}].`;
    } else if (isDurationOutlier) {
      verdict = "failed";
      classification = "performance_regression";
      message = `Performance regression: candidate duration (${Math.round(candidate.duration_ms)}ms) exceeds baseline (${Math.round(activeVer.expected_duration_ms)}ms) by >50%.`;
    }

    return {
      status: verdict,
      verdict,
      classification,
      summary: message,
      baseline_version: activeVer.version,
      baseline_duration_ms: activeVer.expected_duration_ms,
      candidate_duration_ms: candidate.duration_ms,
      duration_drift_pct: Number((((candidate.duration_ms - activeVer.expected_duration_ms) / activeVer.expected_duration_ms) * 100).toFixed(1)),
      expected_sequence: expectedSequence,
      actual_sequence: actualSequence,
      missing_steps: missing,
      compared_at: new Date().toISOString(),
    };
  }

  async compareTraces(baselineTraceId, candidateTraceId) {
    return this.compareWithBaseline(1, { candidate_trace_id: candidateTraceId });
  }

  // --- Test Cases & Replay ---
  async listTests() {
    return [...this.tests];
  }

  async getTest(id) {
    const t = this.tests.find((x) => x.id === Number(id));
    if (!t) throw new Error("Test case not found");
    return { ...t };
  }

  async createTest(body) {
    const newTest = {
      id: Date.now(),
      project_id: this.currentProjectId,
      name: body.name || "New Demo Test",
      agent_name: body.agent_name || "support_triage_agent",
      description: body.description || "Interactive demo test",
      step_count: (body.steps || []).length,
      last_status: "not_run",
      created_at: new Date().toISOString(),
      steps: body.steps || [],
    };
    this.tests.push(newTest);
    return newTest;
  }

  async runTest(id) {
    const test = await this.getTest(id);
    const isPassing = !test.name.toLowerCase().includes("timeout") && !test.name.toLowerCase().includes("fail");
    const status = isPassing ? "passed" : "failed";
    const duration = isPassing ? 210.0 : 10020.0;

    const run = {
      id: Date.now(),
      test_id: test.id,
      test_name: test.name,
      status,
      duration_ms: duration,
      created_at: new Date().toISOString(),
      step_results: (test.steps || []).map((s) => ({
        step: s.step,
        tool: s.tool,
        status: status === "failed" && s.step === 2 ? "failed" : "passed",
        duration_ms: 45.0,
      })),
    };

    test.last_status = status;
    this.testRuns.unshift(run);
    return run;
  }

  async runAllTests() {
    const results = [];
    for (const test of this.tests) {
      const res = await this.runTest(test.id);
      results.push(res);
    }
    const passed = results.filter((r) => r.status === "passed").length;
    const failed = results.filter((r) => r.status === "failed").length;
    return {
      total: results.length,
      passed,
      failed,
      runs: results,
    };
  }

  async listRuns() {
    return [...this.testRuns];
  }

  async getRun(id) {
    const run = this.testRuns.find((r) => r.id === Number(id));
    return run || this.testRuns[0];
  }

  // --- CI/CD Runs ---
  async listCIRuns() {
    return [...this.ciRuns];
  }

  async getCIRun(id) {
    const run = this.ciRuns.find((r) => r.id === Number(id));
    return run || this.ciRuns[0];
  }

  // --- AI Failure Diagnostics ---
  async getFailureAnalysis() {
    return { ...this.failureAnalysis };
  }

  async diagnoseExecution(body) {
    const execId = body?.execution_id || "demo-trace-support-timeout-1";
    if (execId.includes("timeout")) {
      return {
        execution_id: execId,
        failure_kind: "timeout",
        confidence: 0.94,
        root_cause: "External socket read timeout in payment gateway (stripe_refund_charge).",
        explanation:
          "The agent initiated a refund call to an external payment processor, but the upstream socket connection hung for 10.02s before timing out. The agent had no fallback mechanism or circuit breaker configured.",
        suggested_mitigation:
          "1. Wrap 'stripe_refund_charge' with a 3.0s timeout and circuit breaker.\n2. Add asynchronous retry queue with idempotency keys.\n3. Instruct agent to inform the user of pending background status rather than halting.",
        is_ai_generated: true,
      };
    }
    return {
      execution_id: execId,
      failure_kind: "assertion_failed",
      confidence: 0.89,
      root_cause: "Prompt drift led to skipping 'verify_customer_identity' gate.",
      explanation:
        "The language model directly executed 'issue_refund' without performing the mandatory customer identity check defined in the Golden Baseline sequence.",
      suggested_mitigation:
        "1. Lock agent tool sequence with Golden Baseline v2.\n2. Enforce deterministic policy gate in orchestration layer before refund tool execution.",
      is_ai_generated: true,
    };
  }

  // --- API Keys (Read-Only Demo Protection) ---
  async listProjectKeys() {
    return [...this.apiKeys];
  }

  async createProjectKey() {
    // Provide safe synthetic feedback without creating real backend tokens
    const sampleKey = {
      id: Date.now(),
      project_id: this.currentProjectId,
      name: "New Demo Key",
      key_prefix: "ar_live_demo_tmp_",
      created_at: new Date().toISOString(),
      is_demo: true,
    };
    this.apiKeys.push(sampleKey);
    return {
      ...sampleKey,
      key: "ar_live_demo_sample_token_not_for_production",
    };
  }

  async revokeProjectKey(projectId, keyId) {
    this.apiKeys = this.apiKeys.filter((k) => k.id !== Number(keyId));
    return { message: "Demo key revoked" };
  }
}

export const demoService = new DemoService();

