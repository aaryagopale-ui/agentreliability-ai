/**
 * In-memory synthetic API service for Public Demo Mode with isolated session storage.
 *
 * Provides a 100% operational, fully interactive sandbox experience:
 * - Isolated per visitor session (using sessionStorage with in-memory fallback)
 * - Multi-tenant project switching, creation, renaming, and archiving
 * - Real-time trace observability, step timelines, and waterfall views
 * - Deterministic replay engine with mocked tool executions
 * - Golden baseline creation, versioning, drift comparisons, and promotions
 * - Interactive AI root cause diagnostics with ground truth evidence
 * - Phase 1 log upload & test case generation
 * - Project API key management & quickstarts
 * - CI/CD testing reports with regression diffs
 * - Zero network calls to production databases or Render backend
 */
import {
  DEMO_USER,
  DEMO_SYSTEM_INFO,
  DEMO_PROJECTS,
  DEMO_ALL_EXECUTIONS,
  DEMO_ALL_TRACES,
  DEMO_ALL_BASELINES,
  DEMO_ALL_TESTS,
  DEMO_ALL_TEST_RUNS,
  DEMO_ALL_CI_RUNS,
  DEMO_ALL_API_KEYS,
  DEMO_FAILURE_ANALYSIS_P1,
} from "./demoData.js";
import { demoStorage } from "./demoStorage.js";

function getInitialState() {
  return {
    user: JSON.parse(JSON.stringify(DEMO_USER)),
    systemInfo: JSON.parse(JSON.stringify(DEMO_SYSTEM_INFO)),
    projects: JSON.parse(JSON.stringify(DEMO_PROJECTS)),
    currentProjectId: 1,
    executions: JSON.parse(JSON.stringify(DEMO_ALL_EXECUTIONS)),
    traces: JSON.parse(JSON.stringify(DEMO_ALL_TRACES)),
    baselines: JSON.parse(JSON.stringify(DEMO_ALL_BASELINES)),
    tests: JSON.parse(JSON.stringify(DEMO_ALL_TESTS)),
    testRuns: JSON.parse(JSON.stringify(DEMO_ALL_TEST_RUNS)),
    ciRuns: JSON.parse(JSON.stringify(DEMO_ALL_CI_RUNS)),
    apiKeys: JSON.parse(JSON.stringify(DEMO_ALL_API_KEYS)),
  };
}

class DemoService {
  constructor() {
    this.state = demoStorage.load(getInitialState);
  }

  save() {
    demoStorage.save(this.state);
  }

  resetState() {
    demoStorage.clear();
    this._cachedUser = null;
    this._cachedSysInfo = null;
    this.state = demoStorage.load(getInitialState);
    return { message: "Demo state reset to initial sandbox" };
  }

  get currentProjectId() {
    return this.state.currentProjectId || 1;
  }

  setCurrentProjectId(id) {
    const numId = Number(id) || 1;
    this.state.currentProjectId = numId;
    this.save();
  }

  // =========================================================================
  // Auth & User
  // =========================================================================
  async getMe() {
    if (!this._cachedUser || this._cachedUserRaw !== this.state.user) {
      this._cachedUser = Object.freeze(JSON.parse(JSON.stringify(this.state.user)));
      this._cachedUserRaw = this.state.user;
    }
    return this._cachedUser;
  }

  async getSystemInfo() {
    if (!this._cachedSysInfo || this._cachedSysInfoRaw !== this.state.systemInfo) {
      this._cachedSysInfo = Object.freeze(JSON.parse(JSON.stringify(this.state.systemInfo)));
      this._cachedSysInfoRaw = this.state.systemInfo;
    }
    return this._cachedSysInfo;
  }

  async logout() {
    this.resetState();
    return { message: "Demo session cleared" };
  }

  // =========================================================================
  // Projects (Multi-Tenant)
  // =========================================================================
  async listProjects() {
    return JSON.parse(JSON.stringify(this.state.projects));
  }

  async getProject(id) {
    const proj = this.state.projects.find((p) => p.id === Number(id));
    if (!proj) throw new Error("Project not found");
    return JSON.parse(JSON.stringify(proj));
  }

  async createProject(body) {
    const newId = Date.now();
    const projName = body.name?.trim() || "New Agent Project";
    const newProj = {
      id: newId,
      name: projName,
      description: body.description?.trim() || "Created during interactive demo session",
      created_at: new Date().toISOString(),
      owner_id: this.state.user.id,
    };
    this.state.projects.push(newProj);

    // Automatically provision initial demo API key for the new project
    const initialKey = {
      id: Date.now() + 1,
      project_id: newId,
      name: `${projName} Default Key`,
      key_prefix: "ar_live_demo_" + Math.random().toString(36).substring(2, 6) + "_",
      created_at: new Date().toISOString(),
      is_demo: true,
    };
    this.state.apiKeys.push(initialKey);

    // Automatically seed an initial starter trace so the new project is immediately interactive
    const starterTrace = {
      execution_id: `demo-trace-p${newId}-1`,
      project_id: newId,
      agent_name: `${projName.toLowerCase().replace(/[^a-z0-9]/g, "_")}_agent`,
      status: "completed",
      failure_kind: null,
      duration_ms: 185.0,
      tool_call_count: 2,
      failed_tool_calls: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      metadata: { synthetic_demo: true, starter: true },
      events: [],
      tool_calls: [
        {
          call_id: "starter_c1",
          tool_name: "initialize_context",
          duration_ms: 45.0,
          status: "success",
          parameters: { environment: "demo_sandbox" },
          result: { ready: true },
        },
        {
          call_id: "starter_c2",
          tool_name: "generate_response",
          duration_ms: 140.0,
          status: "success",
          parameters: { prompt: "System readiness check" },
          result: { status: "operational" },
        },
      ],
    };
    this.state.traces.unshift(starterTrace);

    this.setCurrentProjectId(newId);
    this.save();

    return {
      ...JSON.parse(JSON.stringify(newProj)),
      api_key: `${initialKey.key_prefix}${Math.random().toString(36).substring(2, 16)}`,
    };
  }

  async updateProject(id, body) {
    const proj = this.state.projects.find((p) => p.id === Number(id));
    if (!proj) throw new Error("Project not found");
    if (body.name) proj.name = body.name.trim();
    if (body.description !== undefined) proj.description = body.description?.trim() || "";
    proj.updated_at = new Date().toISOString();
    this.save();
    return JSON.parse(JSON.stringify(proj));
  }

  async archiveProject(id) {
    const numId = Number(id);
    this.state.projects = this.state.projects.filter((p) => p.id !== numId);
    // Cleanup items associated with the archived project
    this.state.traces = this.state.traces.filter((t) => t.project_id !== numId);
    this.state.executions = this.state.executions.filter((e) => e.project_id !== numId);
    this.state.baselines = this.state.baselines.filter((b) => b.project_id !== numId);
    this.state.tests = this.state.tests.filter((t) => t.project_id !== numId);
    this.state.testRuns = this.state.testRuns.filter((r) => r.project_id !== numId);
    this.state.ciRuns = this.state.ciRuns.filter((c) => c.project_id !== numId);
    this.state.apiKeys = this.state.apiKeys.filter((k) => k.project_id !== numId);

    if (this.state.currentProjectId === numId) {
      this.state.currentProjectId = this.state.projects[0]?.id || 1;
    }
    this.save();
    return { message: "Project archived successfully" };
  }

  async claimProject(id) {
    return { message: "Project claimed in demo session" };
  }

  // =========================================================================
  // Overview Dashboard
  // =========================================================================
  async getOverview() {
    const projId = this.currentProjectId;
    const projExecs = this.state.executions.filter((e) => e.project_id === projId);
    const projTraces = this.state.traces.filter((t) => t.project_id === projId);
    const projTests = this.state.tests.filter((t) => t.project_id === projId);
    const projTestIds = new Set(projTests.map((t) => t.id));
    const projRuns = this.state.testRuns.filter((r) => r.project_id === projId || projTestIds.has(r.test_id));

    const passedTests = projTests.filter((t) => t.last_status === "passed" || t.last_status === "success").length;
    const failedTests = projTests.filter((t) => t.last_status === "failed").length;

    return {
      executions: {
        total: projExecs.length,
        passed: projExecs.filter((e) => e.status === "success").length,
        failed: projExecs.filter((e) => e.status === "failed").length,
      },
      live_traces: {
        total: projTraces.length,
        passed: projTraces.filter((t) => t.status === "completed" || t.status === "success").length,
        failed: projTraces.filter((t) => t.status === "failed").length,
      },
      tests: {
        total: projTests.length,
        passed: passedTests,
        failed: failedTests,
        not_run: Math.max(0, projTests.length - (passedTests + failedTests)),
      },
      recent_runs: JSON.parse(JSON.stringify(projRuns.slice(0, 5))),
    };
  }

  // =========================================================================
  // Phase 1: Uploaded Executions
  // =========================================================================
  async listExecutions() {
    const projId = this.currentProjectId;
    const items = this.state.executions.filter((e) => e.project_id === projId);
    return JSON.parse(JSON.stringify(items));
  }

  async getExecution(id) {
    const exec = this.state.executions.find((e) => e.id === Number(id));
    if (!exec) {
      const fallback = this.state.executions.find((e) => e.project_id === this.currentProjectId) || this.state.executions[0];
      return JSON.parse(JSON.stringify(fallback));
    }
    return JSON.parse(JSON.stringify(exec));
  }

  async uploadLog(file) {
    const newId = Date.now();
    const projId = this.currentProjectId;
    const currentProj = this.state.projects.find((p) => p.id === projId);
    const agentName = currentProj ? `${currentProj.name.toLowerCase().replace(/[^a-z0-9]/g, "_")}_agent` : "uploaded_agent";

    const newExec = {
      id: newId,
      project_id: projId,
      agent_name: agentName,
      status: "success",
      step_count: 2,
      finding_count: 0,
      created_at: new Date().toISOString(),
      findings: [],
      steps: [
        {
          step_index: 0,
          name: "parse_user_query",
          type: "tool_call",
          duration_ms: 32.0,
          timestamp: new Date().toISOString(),
          input: { file_name: file?.name || "agent_log.json" },
          output: { parsed_intent: "order_inquiry" },
        },
        {
          step_index: 1,
          name: "format_response",
          type: "llm_call",
          duration_ms: 120.0,
          timestamp: new Date().toISOString(),
          input: { intent: "order_inquiry" },
          output: { response: "Processed log successfully in demo mode." },
        },
      ],
    };
    this.state.executions.unshift(newExec);
    this.save();
    return { id: newId, message: "Log uploaded successfully in demo mode" };
  }

  async createTestFromExecution(execId) {
    const exec = await this.getExecution(execId);
    const toolSeq = (exec.steps || []).map((s) => s.name || s.type).filter(Boolean);
    const newTest = {
      id: Date.now(),
      project_id: this.currentProjectId,
      name: `Test from Execution #${exec.id} (${exec.agent_name})`,
      agent_name: exec.agent_name,
      description: `Generated from uploaded log #${exec.id}`,
      source_type: "execution",
      source_id: String(exec.id),
      step_count: (exec.steps || []).length,
      last_status: "not_run",
      created_at: new Date().toISOString(),
      input: { agent: exec.agent_name },
      expected: {
        status: exec.status || "success",
        tool_sequence: toolSeq,
        final_output: "Processed log successfully in demo mode.",
        error_conditions: exec.findings || [],
      },
      steps: (exec.steps || []).map((s, i) => ({
        step_index: i,
        step: i + 1,
        type: s.type || "tool_call",
        name: s.name || `step_${i + 1}`,
        status: s.status || "success",
        duration_ms: s.duration_ms || 45.0,
        input: s.input,
        output: s.output,
      })),
    };
    this.state.tests.push(newTest);
    this.save();
    return JSON.parse(JSON.stringify(newTest));
  }

  // =========================================================================
  // Live Traces & Observability
  // =========================================================================
  async listTraceExecutions(params = {}) {
    const projId = this.currentProjectId;
    let filtered = this.state.traces.filter((t) => t.project_id === projId);

    if (params.agent) {
      filtered = filtered.filter((t) => t.agent_name.toLowerCase().includes(params.agent.toLowerCase()));
    }
    if (params.status) {
      filtered = filtered.filter((t) => t.status === params.status);
    }
    if (params.failure_kind) {
      filtered = filtered.filter((t) => t.failure_kind === params.failure_kind);
    }
    return {
      items: JSON.parse(JSON.stringify(filtered)),
      total: filtered.length,
    };
  }

  async getTraceExecution(id) {
    const trace = this.state.traces.find((t) => t.execution_id === id);
    if (!trace) {
      const fallback = this.state.traces.find((t) => t.project_id === this.currentProjectId) || this.state.traces[0];
      return JSON.parse(JSON.stringify(fallback));
    }
    return JSON.parse(JSON.stringify(trace));
  }

  async listTraceAgents() {
    const projId = this.currentProjectId;
    const projTraces = this.state.traces.filter((t) => t.project_id === projId);
    const agents = Array.from(new Set(projTraces.map((t) => t.agent_name)));
    return agents;
  }

  async createTestFromTrace(execId, body) {
    const trace = await this.getTraceExecution(execId);
    const toolSeq = (trace.tool_calls || []).map((c) => c.tool_name).filter(Boolean);
    const newTest = {
      id: Date.now(),
      project_id: this.currentProjectId,
      name: (body && body.name) || `Test from ${trace.agent_name} (${trace.execution_id.slice(0, 8)})`,
      agent_name: trace.agent_name,
      description: `Generated from trace ${trace.execution_id}`,
      source_type: "trace",
      source_id: trace.execution_id,
      step_count: (trace.tool_calls || []).length,
      last_status: "not_run",
      created_at: new Date().toISOString(),
      input: trace.events?.[0]?.data?.user_prompt || { prompt: "Customer query" },
      expected: {
        status: trace.status === "failed" ? "failed" : "success",
        tool_sequence: toolSeq,
        final_output: trace.output || "Customer query completed.",
        error_conditions: trace.failure_kind ? [{ step_index: Math.max(0, toolSeq.length - 1), category: trace.failure_kind }] : [],
      },
      steps: (trace.tool_calls || []).map((c, i) => ({
        step_index: i,
        step: i + 1,
        type: "tool_call",
        name: c.tool_name,
        tool: c.tool_name,
        status: c.status || "success",
        duration_ms: c.duration_ms || 45.0,
        input: c.parameters,
        output: c.result || { status: "simulated_success" },
      })),
    };
    this.state.tests.push(newTest);
    this.save();
    return JSON.parse(JSON.stringify(newTest));
  }

  // =========================================================================
  // Golden Baselines & Regressions
  // =========================================================================
  async listBaselines() {
    const projId = this.currentProjectId;
    const items = this.state.baselines.filter((b) => b.project_id === projId);
    return JSON.parse(JSON.stringify(items));
  }

  async getBaseline(id) {
    const b = this.state.baselines.find((x) => x.id === Number(id));
    if (!b) throw new Error("Baseline not found");
    return JSON.parse(JSON.stringify(b));
  }

  async createBaseline(body) {
    const projId = this.currentProjectId;
    const projTraces = this.state.traces.filter((t) => t.project_id === projId);
    const trace = projTraces.find((t) => t.execution_id === body.source_id) || projTraces[0] || this.state.traces[0];
    const tools = (trace.tool_calls || []).map((t) => ({ tool_name: t.tool_name }));
    const toolSeq = tools.map((t) => t.tool_name);

    const newBaseline = {
      id: Date.now(),
      project_id: projId,
      name: body.name || `Baseline from ${trace.agent_name}`,
      agent_name: trace.agent_name,
      description: body.description || "Created from live execution trace in demo mode",
      current_version: 1,
      active_version: "v1",
      total_versions: 1,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      source_trace_id: trace.execution_id,
      version_data: {
        status: "success",
        source_id: trace.execution_id,
        duration_ms: trace.duration_ms || 200,
        tools,
        expected: {
          tool_sequence: toolSeq,
          strict_order: true,
          expected_output_fields: ["customer_id", "status"],
          status: "success",
          max_duration_ms: Math.round((trace.duration_ms || 200) * 1.5),
        },
      },
      versions: [
        {
          version: 1,
          description: "Initial baseline version",
          created_at: new Date().toISOString(),
          source_id: trace.execution_id,
          duration_ms: trace.duration_ms || 200,
          tools,
          expected: {
            tool_sequence: toolSeq,
            strict_order: true,
            expected_output_fields: ["customer_id", "status"],
            status: "success",
            max_duration_ms: Math.round((trace.duration_ms || 200) * 1.5),
          },
        },
      ],
    };
    this.state.baselines.unshift(newBaseline);
    this.save();
    return JSON.parse(JSON.stringify(newBaseline));
  }

  async createBaselineVersion(baselineId, body) {
    const baseline = this.state.baselines.find((b) => b.id === Number(baselineId));
    if (!baseline) throw new Error("Baseline not found");

    const projTraces = this.state.traces.filter((t) => t.project_id === this.currentProjectId);
    const trace = projTraces.find((t) => t.execution_id === body.source_id) || projTraces[0] || this.state.traces[0];
    const newVerNum = (baseline.current_version || 1) + 1;
    const tools = (trace.tool_calls || []).map((t) => ({ tool_name: t.tool_name }));
    const toolSeq = tools.map((t) => t.tool_name);

    const newVersion = {
      version: newVerNum,
      description: body.description || `Promoted version v${newVerNum}`,
      created_at: new Date().toISOString(),
      source_id: trace.execution_id,
      duration_ms: trace.duration_ms || 250,
      tools,
      expected: {
        tool_sequence: toolSeq,
        strict_order: true,
        expected_output_fields: ["customer_id", "status"],
        status: trace.status === "failed" ? "failed" : "success",
        max_duration_ms: Math.round((trace.duration_ms || 250) * 1.5),
      },
    };

    if (!baseline.versions) baseline.versions = [];
    baseline.versions.unshift(newVersion);
    baseline.current_version = newVerNum;
    baseline.total_versions = baseline.versions.length;
    baseline.version_data = newVersion;
    baseline.updated_at = new Date().toISOString();
    this.save();
    return JSON.parse(JSON.stringify(newVersion));
  }

  async deleteBaseline(id) {
    this.state.baselines = this.state.baselines.filter((b) => b.id !== Number(id));
    this.save();
    return { message: "Baseline deleted successfully" };
  }

  async listBaselineVersions(id) {
    const b = await this.getBaseline(id);
    return JSON.parse(JSON.stringify(b.versions || []));
  }

  async compareWithBaseline(baselineId, body) {
    const baseline = await this.getBaseline(baselineId);
    const candidateTraceId = body.candidate_trace_id;
    const projTraces = this.state.traces.filter((t) => t.project_id === this.currentProjectId);
    const candidate = projTraces.find((t) => t.execution_id === candidateTraceId) || projTraces[0] || this.state.traces[0];

    const activeVer =
      (baseline.versions && baseline.versions.find((v) => v.version === baseline.current_version)) ||
      baseline.versions?.[0] ||
      baseline.version_data ||
      {};
    const expectedSequence =
      activeVer.expected?.tool_sequence ||
      (activeVer.tools && activeVer.tools.map((t) => t.tool_name)) ||
      ["lookup_customer", "check_order_status", "issue_refund"];
    const actualSequence = candidate.tool_calls ? candidate.tool_calls.map((c) => c.tool_name) : [];

    const missing = expectedSequence.filter((step) => !actualSequence.includes(step));
    const baselineDuration = activeVer.duration_ms || activeVer.expected_duration_ms || 245.2;
    const isDurationOutlier = candidate.duration_ms > baselineDuration * 1.5;

    let verdict = "passed";
    let summary = "Candidate execution conforms strictly to the Golden Baseline step sequence and latency bounds.";
    const differences = [];
    let breakingCount = 0;
    let perfCount = 0;
    let infoCount = 0;

    if (missing.length > 0) {
      verdict = "regression";
      summary = `Breaking sequence regression: omitted expected step(s) [${missing.join(", ")}].`;
      breakingCount = missing.length;
      missing.forEach((tool) => {
        differences.push({
          category: "missing_tool_call",
          severity: "breaking_regression",
          message: `Expected tool '${tool}' was not called during candidate execution.`,
          evidence: { expected_tool: tool, observed_sequence: actualSequence },
        });
      });
    } else if (candidate.status === "failed") {
      verdict = "regression";
      summary = `Candidate execution failed with ${candidate.failure_kind || "error"}: ${candidate.error_message || "Unknown error"}.`;
      breakingCount = 1;
      differences.push({
        category: "execution_failure",
        severity: "breaking_regression",
        message: candidate.error_message || "Execution terminated with error.",
        evidence: { failure_kind: candidate.failure_kind, error_message: candidate.error_message },
      });
    } else if (isDurationOutlier) {
      verdict = "performance_warning";
      summary = `Latency regression: candidate duration (${Math.round(candidate.duration_ms)}ms) exceeds baseline (${Math.round(baselineDuration)}ms) by >50%.`;
      perfCount = 1;
      differences.push({
        category: "duration_regression",
        severity: "performance_regression",
        message: `Candidate duration was ${Math.round(candidate.duration_ms)}ms compared to baseline ${Math.round(baselineDuration)}ms.`,
        evidence: { baseline_ms: baselineDuration, candidate_ms: candidate.duration_ms },
      });
    }

    return {
      status: verdict === "passed" ? "passed" : "failed",
      verdict,
      classification: verdict === "passed" ? "no_regression" : verdict === "performance_warning" ? "performance_regression" : "breaking_regression",
      summary,
      baseline_version: activeVer.version || baseline.current_version || 1,
      baseline_duration_ms: baselineDuration,
      candidate_duration_ms: candidate.duration_ms,
      duration_drift_pct: Number((((candidate.duration_ms - baselineDuration) / baselineDuration) * 100).toFixed(1)),
      counts: {
        breaking: breakingCount,
        performance: perfCount,
        informational: infoCount,
      },
      baseline: {
        status: activeVer.status || "success",
        duration_ms: baselineDuration,
        tool_count: expectedSequence.length,
        tool_sequence: expectedSequence,
      },
      candidate: {
        status: candidate.status || "completed",
        duration_ms: candidate.duration_ms,
        tool_count: actualSequence.length,
        tool_sequence: actualSequence,
      },
      differences,
      expected_sequence: expectedSequence,
      actual_sequence: actualSequence,
      missing_steps: missing,
      compared_at: new Date().toISOString(),
    };
  }

  async compareTraces(baselineTraceId, candidateTraceId) {
    const baselines = await this.listBaselines();
    const baseId = baselines[0]?.id || 1;
    return this.compareWithBaseline(baseId, { candidate_trace_id: candidateTraceId });
  }

  // =========================================================================
  // Test Cases & Replay
  // =========================================================================
  async listTests() {
    const projId = this.currentProjectId;
    const items = this.state.tests.filter((t) => t.project_id === projId);
    return JSON.parse(JSON.stringify(items));
  }

  async getTest(id) {
    const t = this.state.tests.find((x) => x.id === Number(id));
    if (!t) throw new Error("Test case not found");
    return JSON.parse(JSON.stringify(t));
  }

  async createTest(body) {
    const projId = this.currentProjectId;
    const newTest = {
      id: Date.now(),
      project_id: projId,
      name: body.name || "New Demo Test",
      agent_name: body.agent_name || "support_triage_agent",
      description: body.description || "Interactive demo test",
      step_count: (body.steps || []).length,
      last_status: "not_run",
      created_at: new Date().toISOString(),
      input: body.input || {},
      expected: body.expected || {
        status: "success",
        tool_sequence: (body.steps || []).map((s) => s.name || s.tool),
        final_output: "Success",
        error_conditions: [],
      },
      steps: body.steps || [],
    };
    this.state.tests.push(newTest);
    this.save();
    return JSON.parse(JSON.stringify(newTest));
  }

  async updateTest(id, body) {
    const idx = this.state.tests.findIndex((t) => t.id === Number(id));
    if (idx !== -1) {
      this.state.tests[idx] = { ...this.state.tests[idx], ...body };
      this.save();
      return JSON.parse(JSON.stringify(this.state.tests[idx]));
    }
    return body;
  }

  async deleteTest(id) {
    this.state.tests = this.state.tests.filter((t) => t.id !== Number(id));
    this.save();
    return { message: "Test deleted successfully" };
  }

  async runTest(id) {
    const test = await this.getTest(id);
    const isPassing =
      (test.expected?.status === "success" || test.expected?.status === "passed") &&
      !test.name.toLowerCase().includes("timeout") &&
      !test.name.toLowerCase().includes("fail");
    const status = isPassing ? "passed" : "failed";
    const duration = isPassing ? 198.4 : 10024.0;
    const toolSeq = test.expected?.tool_sequence || test.steps?.map((s) => s.name || s.tool) || [];

    const mismatches = isPassing
      ? []
      : [
          {
            kind: test.expected?.error_conditions?.[0]?.category || "timeout",
            step_index: Math.max(0, (test.steps || []).length - 1),
            message: `Step ${(test.steps || []).length} exceeded deterministic timeout threshold (observed: 10024ms, threshold: 5000ms)`,
          },
        ];

    const observedSteps = (test.steps || []).map((s, i) => ({
      step_index: i,
      name: s.name || s.tool || `step_${i + 1}`,
      type: s.type || "tool_call",
      status: !isPassing && i === test.steps.length - 1 ? "failed" : "success",
      duration_ms: !isPassing && i === test.steps.length - 1 ? 10024.0 : s.duration_ms || 45.0,
      timestamp: new Date().toISOString(),
      input: s.input || s.expected_arguments,
      output: s.output || s.mock_output,
    }));

    const findings = isPassing
      ? []
      : [
          {
            step_index: Math.max(0, (test.steps || []).length - 1),
            category: test.expected?.error_conditions?.[0]?.category || "timeout",
            explanation: "External tool call timed out after 10024ms.",
          },
        ];

    const run = {
      id: Date.now(),
      test_id: test.id,
      project_id: this.currentProjectId,
      test_name: test.name,
      status,
      duration_ms: duration,
      created_at: new Date().toISOString(),
      disclaimer: "Deterministic simulation with mocked tools. No real model or network request was dispatched.",
      mismatches,
      mismatch_count: mismatches.length,
      observed: {
        tool_sequence: toolSeq,
        final_output: isPassing ? test.expected?.final_output || "Verified output" : null,
        steps: observedSteps,
        findings,
      },
      step_results: observedSteps.map((s) => ({
        step: s.step_index + 1,
        tool: s.name,
        status: s.status,
        duration_ms: s.duration_ms,
      })),
    };

    test.last_status = status;
    const testIdx = this.state.tests.findIndex((t) => t.id === test.id);
    if (testIdx !== -1) {
      this.state.tests[testIdx].last_status = status;
    }

    this.state.testRuns.unshift(run);
    this.save();
    return JSON.parse(JSON.stringify(run));
  }

  async runAllTests() {
    const projTests = await this.listTests();
    const results = [];
    for (const test of projTests) {
      const res = await this.runTest(test.id);
      results.push(res);
    }
    const passed = results.filter((r) => r.status === "passed" || r.status === "success").length;
    const failed = results.filter((r) => r.status === "failed").length;
    return {
      total: results.length,
      passed,
      failed,
      runs: results,
    };
  }

  async listRuns(testId) {
    const projId = this.currentProjectId;
    const projTests = this.state.tests.filter((t) => t.project_id === projId);
    const projTestIds = new Set(projTests.map((t) => t.id));

    let runs = this.state.testRuns.filter((r) => r.project_id === projId || projTestIds.has(r.test_id));
    if (testId) {
      runs = runs.filter((r) => r.test_id === Number(testId));
    }
    return JSON.parse(JSON.stringify(runs));
  }

  async getRun(id) {
    const run = this.state.testRuns.find((r) => r.id === Number(id));
    return JSON.parse(JSON.stringify(run || this.state.testRuns[0]));
  }

  // =========================================================================
  // CI/CD Runs
  // =========================================================================
  async listCIRuns() {
    const projId = this.currentProjectId;
    const runs = this.state.ciRuns.filter((c) => c.project_id === projId);
    return JSON.parse(JSON.stringify(runs));
  }

  async getCIRun(id) {
    const run = this.state.ciRuns.find((r) => r.id === Number(id));
    return JSON.parse(JSON.stringify(run || this.state.ciRuns[0]));
  }

  // =========================================================================
  // AI Failure Diagnostics & Analysis
  // =========================================================================
  async getFailureAnalysis() {
    const projId = this.currentProjectId;
    const projTraces = this.state.traces.filter((t) => t.project_id === projId);
    const failedTraces = projTraces.filter((t) => t.status === "failed");

    const projTests = this.state.tests.filter((t) => t.project_id === projId);
    const projTestIds = new Set(projTests.map((t) => t.id));
    const projRuns = this.state.testRuns.filter((r) => r.project_id === projId || projTestIds.has(r.test_id));
    const failingRuns = projRuns.filter((r) => r.status === "failed");

    const traceFailureKinds = {};
    failedTraces.forEach((t) => {
      const k = t.failure_kind || "unexpected_exception";
      traceFailureKinds[k] = (traceFailureKinds[k] || 0) + 1;
    });

    const executionFindings = {};
    const projExecs = this.state.executions.filter((e) => e.project_id === projId);
    projExecs.forEach((e) => {
      (e.findings || []).forEach((f) => {
        executionFindings[f.category] = (executionFindings[f.category] || 0) + 1;
      });
    });

    const replayMismatches = {};
    failingRuns.forEach((r) => {
      (r.mismatches || []).forEach((m) => {
        replayMismatches[m.kind] = (replayMismatches[m.kind] || 0) + 1;
      });
    });

    return {
      local_ai: {
        available: true,
        models: ["llama3:latest", "mistral:latest"],
        selected_model: "llama3:latest",
        base_url: "http://127.0.0.1:11434",
      },
      failed_traces: JSON.parse(JSON.stringify(failedTraces)),
      failing_runs: JSON.parse(JSON.stringify(failingRuns)),
      trace_failure_kinds: traceFailureKinds,
      execution_findings: executionFindings,
      replay_mismatches: replayMismatches,
      total_analyzed: failedTraces.length + failingRuns.length,
    };
  }

  async getOllamaStatus() {
    return { running: true, models: ["llama3:latest", "mistral:latest"] };
  }

  async diagnoseExecution(body) {
    const execId = String(body?.execution_id || "demo-trace-support-timeout-1");
    const isTimeout = execId.includes("timeout") || execId === "2" || execId === "102";

    if (isTimeout) {
      return {
        execution_id: execId,
        failure_kind: "timeout",
        confidence: 0.94,
        is_ai_generated: true,
        diagnostic_report: {
          primary_error: {
            error_type: "TimeoutError",
            error_message: "Gateway timeout after 10000ms calling external service socket",
            tool_name: "stripe_refund_charge",
          },
          confirmed_observations: [
            "Customer prompt requested transaction refund / external action.",
            "Identity and state verification checks completed in 102ms.",
            "External socket call hung for 10020ms without response from upstream host.",
            "No circuit breaker or timeout handler intercepted the stalled connection.",
          ],
          preceding_events: [
            { step_index: 1, tool_name: "lookup_customer", status: "success", duration_ms: 38.0 },
            { step_index: 2, tool_name: "check_order_status", status: "success", duration_ms: 64.2 },
            { step_index: 3, tool_name: "stripe_refund_charge", status: "failed", duration_ms: 10020.5 },
          ],
          timing_anomalies: [
            { description: "External socket duration (10020ms) was 85x higher than p50 baseline (118ms)." },
          ],
          regression_evidence: [
            { category: "latency", message: "Exceeded 5000ms maximum timeout SLA threshold." },
          ],
        },
        ai_analysis: {
          status: "completed",
          model_used: "llama3:latest",
          hypotheses: {
            failure_category: "External Gateway Socket Timeout",
            summary: "The agent encountered an unhandled socket read timeout while communicating with an external API. Upstream service failed to acknowledge within 10s, triggering an agent crash.",
            observed_evidence: [
              "External tool call initiated with transaction payload",
              "Socket read timed out after 10020ms",
              "Unhandled exception bubble halted subsequent orchestration steps",
            ],
            likely_contributing_factors: [
              "Missing per-tool HTTP client timeout configuration.",
              "Lack of exponential backoff or asynchronous webhook acknowledgement pattern.",
              "Absence of graceful user-facing error message generation.",
            ],
            suggested_debugging_steps: [
              "Configure a 3000ms timeout with circuit breaker on external integrations.",
              "Enqueue long operations as background jobs and return immediate pending status.",
              "Add fallback user explanation handler rather than terminating with unhandled error.",
            ],
            possible_code_areas_to_inspect: [
              "services/external_gateway.py",
              "agents/orchestration.py",
              "config/timeouts.py:GATEWAY_TIMEOUT_MS",
            ],
          },
        },
        suggested_mitigation:
          "1. Wrap external call with a 3.0s timeout and circuit breaker.\n2. Add asynchronous retry queue with idempotency keys.\n3. Instruct agent to inform the user of pending background status rather than halting.",
      };
    }

    return {
      execution_id: execId,
      failure_kind: "assertion_failed",
      confidence: 0.89,
      is_ai_generated: true,
      diagnostic_report: {
        primary_error: {
          error_type: "AssertionError",
          error_message: "Mandatory security step was skipped before privileged action execution",
          tool_name: "issue_refund",
        },
        confirmed_observations: [
          "Urgent user prompt triggered short-circuit in orchestration layer.",
          "Agent bypassed mandatory identity verification policy gate.",
          "Golden Baseline invariant strictly requires identity verification prior to authorization.",
        ],
        preceding_events: [
          { step_index: 1, tool_name: "lookup_customer", status: "success", duration_ms: 35.0 },
          { step_index: 2, tool_name: "issue_refund", status: "success", duration_ms: 88.0 },
        ],
        timing_anomalies: [],
        regression_evidence: [
          { category: "sequence_violation", message: "Omitted required verification tool." },
        ],
      },
      ai_analysis: {
        status: "completed",
        model_used: "llama3:latest",
        hypotheses: {
          failure_category: "Security Policy Sequence Drift",
          summary: "Prompt drift caused the language model to skip the required verification gate and execute a privileged action prematurely.",
          observed_evidence: [
            "User prompt included high urgency signals",
            "Model chose direct path to privileged action tool",
            "Security verification token was never created or validated",
          ],
          likely_contributing_factors: [
            "System prompt lacked strict tool prerequisite assertions.",
            "Orchestration layer permitted tool call without verifying prerequisite state.",
          ],
          suggested_debugging_steps: [
            "Lock agent tool sequence with Golden Baseline v2.",
            "Enforce deterministic policy gate in orchestration layer before action dispatch.",
          ],
          possible_code_areas_to_inspect: [
            "agents/policy_guard.py",
            "policies/authorization_gate.py",
          ],
        },
      },
      suggested_mitigation:
        "1. Lock agent tool sequence with Golden Baseline.\n2. Enforce deterministic policy gate in orchestration layer.",
    };
  }

  // =========================================================================
  // API Keys
  // =========================================================================
  async listProjectKeys(projectId) {
    const targetProjId = projectId ? Number(projectId) : this.currentProjectId;
    const keys = this.state.apiKeys.filter((k) => k.project_id === targetProjId);
    return JSON.parse(JSON.stringify(keys));
  }

  async createProjectKey(projectId, body) {
    const targetProjId = projectId ? Number(projectId) : this.currentProjectId;
    const keyPrefix = "ar_live_demo_" + Math.random().toString(36).substring(2, 6) + "_";
    const sampleKey = {
      id: Date.now(),
      project_id: targetProjId,
      name: body?.name || "New Demo Key",
      key_prefix: keyPrefix,
      created_at: new Date().toISOString(),
      is_demo: true,
    };
    this.state.apiKeys.push(sampleKey);
    this.save();
    return {
      ...JSON.parse(JSON.stringify(sampleKey)),
      key: `${keyPrefix}${Math.random().toString(36).substring(2, 16)}`,
    };
  }

  async revokeProjectKey(projectId, keyId) {
    this.state.apiKeys = this.state.apiKeys.filter((k) => k.id !== Number(keyId));
    this.save();
    return { message: "Demo key revoked successfully" };
  }

  // =========================================================================
  // Getting Started & Demo Seeding
  // =========================================================================
  async seedDemoData() {
    const projId = this.currentProjectId;
    const currentProj = this.state.projects.find((p) => p.id === projId);
    const agentName = currentProj ? `${currentProj.name.toLowerCase().replace(/[^a-z0-9]/g, "_")}_agent` : "demo_agent";

    // Add seeded traces if none exist for this project
    const existingTraces = this.state.traces.filter((t) => t.project_id === projId);
    if (existingTraces.length < 2) {
      const seeded = [
        {
          execution_id: `demo-trace-seed-${projId}-1`,
          project_id: projId,
          agent_name: agentName,
          status: "completed",
          failure_kind: null,
          duration_ms: 215.0,
          tool_call_count: 3,
          failed_tool_calls: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          metadata: { synthetic_demo: true },
          events: [],
          tool_calls: [
            { call_id: "sc1", tool_name: "lookup_record", duration_ms: 45.0, status: "success", parameters: { id: "rec_1" }, result: { found: true } },
            { call_id: "sc2", tool_name: "evaluate_conditions", duration_ms: 60.0, status: "success", parameters: { rule: "standard" }, result: { passed: true } },
            { call_id: "sc3", tool_name: "execute_action", duration_ms: 110.0, status: "success", parameters: { action: "dispatch" }, result: { dispatched: true } },
          ],
        },
        {
          execution_id: `demo-trace-seed-${projId}-2`,
          project_id: projId,
          agent_name: agentName,
          status: "failed",
          failure_kind: "timeout",
          duration_ms: 10020.0,
          tool_call_count: 2,
          failed_tool_calls: 1,
          created_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
          updated_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
          error_message: "Gateway timeout calling downstream microservice",
          error_type: "TimeoutError",
          metadata: { synthetic_demo: true },
          events: [],
          tool_calls: [
            { call_id: "sc4", tool_name: "lookup_record", duration_ms: 40.0, status: "success", parameters: { id: "rec_2" }, result: { found: true } },
            { call_id: "sc5", tool_name: "execute_action", duration_ms: 10020.0, status: "failed", error: "Connection timeout after 10.02s" },
          ],
        },
      ];
      this.state.traces.unshift(...seeded);
    }

    this.save();
    return {
      message: `Demo traces and test fixtures seeded for project '${currentProj?.name || projId}'`,
      traces_count: this.state.traces.filter((t) => t.project_id === projId).length,
    };
  }

  async getDemoStatus() {
    const projId = this.currentProjectId;
    const projTraces = this.state.traces.filter((t) => t.project_id === projId);
    return {
      demo_loaded: true,
      traces_count: projTraces.length,
      project_id: projId,
    };
  }
}

export const demoService = new DemoService();
