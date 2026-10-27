/**
 * Test suite for Public Demo Mode & Security Isolation.
 * Verifies that:
 * 1. isDemoMode() correctly identifies demo vs production environments.
 * 2. Production domain (agentreliability-ai.vercel.app) is never treated as demo.
 * 3. Demo domain (agentreliability-demo.vercel.app) activates demo mode.
 * 4. demoService delivers complete synthetic datasets (projects, traces, baselines, tests, AI diagnostics).
 * 5. Mutations in demo mode do not leak to or require network/backend resources.
 */
import assert from "node:assert";
import { isDemoMode } from "../src/demo/isDemoMode.js";
import { demoService } from "../src/demo/demoService.js";

console.log("🧪 Running Demo Mode & Security Isolation Test Suite...\n");

// --- Test 1: Production Domain Isolation ---
console.log("Test 1: Verify production website is NEVER detected as demo mode");
global.window = { location: { hostname: "agentreliability-ai.vercel.app", search: "" } };
assert.strictEqual(isDemoMode(), false, "Production website must not activate demo mode");

// CRITICAL SECURITY TEST: Ensure ?demo=true or any URL parameter CANNOT activate demo mode on production
global.window = { location: { hostname: "agentreliability-ai.vercel.app", search: "?demo=true" } };
assert.strictEqual(isDemoMode(), false, "Production website with ?demo=true must NEVER activate demo mode");

global.window = { location: { hostname: "agentreliability-ai.vercel.app", search: "?demo=1&user=admin" } };
assert.strictEqual(isDemoMode(), false, "Production website with ?demo=1 must NEVER activate demo mode");

global.window = { location: { hostname: "app.agentreliability.com", search: "?demo=true" } };
assert.strictEqual(isDemoMode(), false, "Custom production domain with ?demo=true must NEVER activate demo mode");
console.log("  ✅ Passed: Production domains with ?demo=true are strictly blocked from demo mode");

// --- Test 2: Standard Localhost Default ---
console.log("Test 2: Verify localhost defaults to normal development (not demo)");
global.window = { location: { hostname: "localhost", search: "" } };
assert.strictEqual(isDemoMode(), false, "Localhost without query param must not activate demo mode");
console.log("  ✅ Passed: localhost -> isDemoMode() === false");

// --- Test 3: Demo Vercel Domain Activation ---
console.log("Test 3: Verify agentreliability-demo.vercel.app activates demo mode");
global.window = { location: { hostname: "agentreliability-demo.vercel.app", search: "" } };
assert.strictEqual(isDemoMode(), true, "agentreliability-demo.vercel.app must activate demo mode");
console.log("  ✅ Passed: https://agentreliability-demo.vercel.app -> isDemoMode() === true");

// --- Test 4: Query Parameter Preview Activation ---
console.log("Test 4: Verify ?demo=true query parameter activates demo mode for testing");
global.window = { location: { hostname: "localhost", search: "?demo=true" } };
assert.strictEqual(isDemoMode(), true, "Query param ?demo=true must activate demo mode");
console.log("  ✅ Passed: localhost?demo=true -> isDemoMode() === true");

// --- Test 5: Synthetic User & System Info ---
console.log("Test 5: Verify demo user and system info");
const user = await demoService.getMe();
assert.strictEqual(user.id, 9999);
assert.strictEqual(user.is_demo, true);
assert.ok(user.name.includes("Demo"));

const sys = await demoService.getSystemInfo();
assert.strictEqual(sys.database_engine, "demo");
assert.strictEqual(sys.is_demo, true);
console.log("  ✅ Passed: Demo user & system info loaded correctly");

// --- Test 6: Multi-Tenant Projects ---
console.log("Test 6: Verify demo projects list");
const projs = await demoService.listProjects();
assert.strictEqual(projs.length, 3, "Demo should provide 3 sample projects");
assert.strictEqual(projs[0].name, "Customer Support AI");
assert.strictEqual(projs[1].name, "Research & Synthesis Agent");
assert.strictEqual(projs[2].name, "Financial Fraud Guard");
console.log("  ✅ Passed: 3 distinct demo projects available");

// --- Test 7: Trace Executions & Observability ---
console.log("Test 7: Verify trace executions (success, timeout, regression)");
const traces = await demoService.listTraceExecutions();
assert.strictEqual(traces.total, 3);
const successTrace = traces.items.find((t) => t.status === "completed");
const timeoutTrace = traces.items.find((t) => t.failure_kind === "timeout");
const regressedTrace = traces.items.find((t) => t.failure_kind === "assertion_failed");
assert.ok(successTrace, "Success trace must exist");
assert.ok(timeoutTrace, "Timeout trace must exist");
assert.ok(regressedTrace, "Regressed trace must exist");
assert.strictEqual(successTrace.tool_call_count, 3);
assert.strictEqual(timeoutTrace.failed_tool_calls, 1);
console.log("  ✅ Passed: Traces cover all key failure modes & tool calls");

// --- Test 8: Golden Baselines & Drift Comparison ---
console.log("Test 8: Verify Golden Baselines and regression detection");
const baselines = await demoService.listBaselines();
assert.strictEqual(baselines.length, 1);
const b = baselines[0];
assert.strictEqual(b.total_versions, 2);

// Compare successful trace -> should pass
const okComp = await demoService.compareWithBaseline(b.id, { candidate_trace_id: successTrace.execution_id });
assert.strictEqual(okComp.status, "passed");
assert.strictEqual(okComp.classification, "no_regression");

// Compare regressed trace -> should detect breaking regression
const regComp = await demoService.compareWithBaseline(b.id, { candidate_trace_id: regressedTrace.execution_id });
assert.strictEqual(regComp.status, "failed");
assert.strictEqual(regComp.classification, "breaking_regression");
assert.ok(regComp.missing_steps.length > 0);
console.log("  ✅ Passed: Golden baseline successfully identifies regressions");

// --- Test 9: Interactive Test Execution & Simulation ---
console.log("Test 9: Verify running test cases in-memory");
const tests = await demoService.listTests();
assert.strictEqual(tests.length, 2);

const testRunResult = await demoService.runTest(tests[0].id);
assert.strictEqual(testRunResult.test_id, tests[0].id);
assert.strictEqual(testRunResult.status, "passed");

const allRuns = await demoService.runAllTests();
assert.strictEqual(allRuns.total, 2);
assert.strictEqual(allRuns.passed, 1);
assert.strictEqual(allRuns.failed, 1);
console.log("  ✅ Passed: In-memory replay engine executes tests seamlessly");

// --- Test 10: AI Failure Analysis & Root Cause ---
console.log("Test 10: Verify AI failure diagnosis");
const diag = await demoService.diagnoseExecution({ execution_id: timeoutTrace.execution_id });
assert.strictEqual(diag.failure_kind, "timeout");
assert.strictEqual(diag.is_ai_generated, true);
assert.ok(diag.confidence > 0.9);
assert.ok(diag.suggested_mitigation.length > 0);
console.log("  ✅ Passed: AI diagnostics provide actionable mitigations");

// --- Test 11: Demo State Reset ---
console.log("Test 11: Verify state reset idempotency");
await demoService.createProject({ name: "Temporary Project" });
assert.strictEqual((await demoService.listProjects()).length, 4);
demoService.resetState();
assert.strictEqual((await demoService.listProjects()).length, 3);
console.log("  ✅ Passed: Reset restored initial synthetic state");

// --- Test 12: Executions Page Contract & Upload Simulation ---
console.log("Test 12: Verify Executions (Phase 1) schema compatibility");
const execs = await demoService.listExecutions();
assert.ok(execs.length >= 3, "Executions list must contain seeded items");
const exec1 = await demoService.getExecution(execs[0].id);
assert.strictEqual(typeof exec1.id, "number");
assert.ok(Array.isArray(exec1.findings), "exec.findings must be an array");
assert.ok(Array.isArray(exec1.steps), "exec.steps must be an array");
assert.strictEqual(typeof exec1.step_count, "number");
assert.strictEqual(typeof exec1.finding_count, "number");

// Test upload log & test case promotion
const uploadRes = await demoService.uploadLog({ name: "test_agent_log.json" });
assert.ok(uploadRes.id, "uploadLog must return new ID");
const uploadedExec = await demoService.getExecution(uploadRes.id);
assert.ok(uploadedExec, "Uploaded execution must be retrievable");
const promotedTest = await demoService.createTestFromExecution(uploadRes.id);
assert.ok(promotedTest.id, "Promotion must create a new test case");
assert.ok(promotedTest.expected, "Promoted test must contain expected contract");
console.log("  ✅ Passed: Executions schema, upload, and promotion contracts verified");

// --- Test 13: Failure Analysis UI Schema Compatibility ---
console.log("Test 13: Verify Failure Analysis UI schema compatibility");
const fa = await demoService.getFailureAnalysis();
assert.ok(Array.isArray(fa.failed_traces), "failed_traces must be an array");
assert.ok(fa.failed_traces.length > 0, "failed_traces must have items");
assert.ok(Array.isArray(fa.failing_runs), "failing_runs must be an array");
assert.strictEqual(typeof fa.trace_failure_kinds, "object");
assert.strictEqual(typeof fa.execution_findings, "object");
assert.strictEqual(typeof fa.replay_mismatches, "object");
assert.ok(fa.local_ai?.available, "local_ai.available must be true");
assert.ok(Array.isArray(fa.local_ai?.models), "local_ai.models must be an array");

// Test diagnose execution contract expected by FailureAnalysis.jsx
const diagDetail = await demoService.diagnoseExecution({ execution_id: "demo-trace-support-timeout-1" });
assert.ok(diagDetail.diagnostic_report?.primary_error, "primary_error must exist");
assert.ok(Array.isArray(diagDetail.diagnostic_report?.confirmed_observations), "confirmed_observations must be array");
assert.ok(Array.isArray(diagDetail.diagnostic_report?.preceding_events), "preceding_events must be array");
assert.ok(diagDetail.ai_analysis?.hypotheses?.summary, "AI hypotheses summary must exist");
assert.ok(Array.isArray(diagDetail.ai_analysis?.hypotheses?.suggested_debugging_steps), "suggested steps must exist");
console.log("  ✅ Passed: Failure Analysis & AI diagnostics contracts match UI requirements");

// --- Test 14: Replay Engine & RunDetail Schema Compatibility ---
console.log("Test 14: Verify Replay Engine & RunDetail contracts");
const sampleTest = await demoService.getTest(1);
assert.ok(sampleTest.expected, "Test case must contain expected object");
assert.ok(Array.isArray(sampleTest.expected.tool_sequence), "expected.tool_sequence must be an array");
assert.ok(Array.isArray(sampleTest.expected.error_conditions), "expected.error_conditions must be an array");

const runDetail = await demoService.getRun(101);
assert.ok(runDetail.test_name, "run.test_name must exist");
assert.ok(Array.isArray(runDetail.mismatches), "run.mismatches must be an array");
assert.ok(runDetail.observed, "run.observed must exist");
assert.ok(Array.isArray(runDetail.observed.tool_sequence), "observed.tool_sequence must be array");
assert.ok(Array.isArray(runDetail.observed.steps), "observed.steps must be array");
assert.ok(Array.isArray(runDetail.observed.findings), "observed.findings must be array");
console.log("  ✅ Passed: Replay and RunDetail contracts verified");

// --- Test 15: Golden Baselines Full Lifecycle & Comparison Contract ---
console.log("Test 15: Verify Golden Baselines versioning & UI comparison contract");
const bl = await demoService.getBaseline(1);
assert.ok(bl.version_data, "baseline.version_data must exist");
assert.ok(Array.isArray(bl.version_data.tools), "version_data.tools must be array");
assert.ok(Array.isArray(bl.version_data.expected?.tool_sequence), "expected tool_sequence must exist");

// Create new version
const newVer = await demoService.createBaselineVersion(1, {
  source_id: "demo-trace-support-success-1",
  description: "Automated test version promotion",
});
assert.strictEqual(newVer.version, 2);
const updatedBl = await demoService.getBaseline(1);
assert.strictEqual(updatedBl.current_version, 2);

// Compare contract with candidate
const compResult = await demoService.compareWithBaseline(1, { candidate_trace_id: "demo-trace-support-timeout-1" });
assert.ok(compResult.verdict, "comparison must have a verdict");
assert.ok(compResult.counts, "comparison must include counts for severity badges");
assert.ok(compResult.baseline?.tool_sequence, "baseline tool sequence must exist in comparison");
assert.ok(compResult.candidate?.tool_sequence, "candidate tool sequence must exist in comparison");
assert.ok(Array.isArray(compResult.differences), "differences must be an array");
console.log("  ✅ Passed: Golden baseline lifecycle and comparison contracts verified");

// --- Test 16: CI/CD Testing Contract ---
console.log("Test 16: Verify CI/CD Testing report contract");
const ciRuns = await demoService.listCIRuns();
assert.ok(ciRuns.length > 0, "CI runs must exist");
const ciDetail = await demoService.getCIRun(ciRuns[0].id);
assert.ok(ciDetail.report?.regression?.counts, "Regression counts must exist");
assert.ok(Array.isArray(ciDetail.report?.results), "Report results must be an array");
console.log("  ✅ Passed: CI/CD testing report structure verified");

// --- Test 17: Multi-Tenant Project Switching & Scoped Datasets ---
console.log("Test 17: Verify multi-tenant project switching across Projects 1, 2, and 3");
// Switch to Project 2 (Research & Synthesis Agent)
demoService.setCurrentProjectId(2);
assert.strictEqual(demoService.currentProjectId, 2);
const p2Traces = await demoService.listTraceExecutions();
assert.ok(p2Traces.items.length > 0, "Project 2 must have traces");
assert.ok(p2Traces.items.every(t => t.project_id === 2), "All returned traces must belong to Project 2");
const p2Baselines = await demoService.listBaselines();
assert.ok(p2Baselines.every(b => b.project_id === 2), "Baselines must belong to Project 2");
const p2Overview = await demoService.getOverview();
assert.strictEqual(p2Overview.live_traces.total, p2Traces.total);

// Switch to Project 3 (Financial Fraud Guard)
demoService.setCurrentProjectId(3);
assert.strictEqual(demoService.currentProjectId, 3);
const p3Traces = await demoService.listTraceExecutions();
assert.ok(p3Traces.items.length > 0, "Project 3 must have traces");
assert.ok(p3Traces.items.every(t => t.project_id === 3), "All returned traces must belong to Project 3");
const p3Keys = await demoService.listProjectKeys(3);
assert.ok(p3Keys.every(k => k.project_id === 3), "API keys must belong to Project 3");
console.log("  ✅ Passed: Projects 1, 2, and 3 have completely isolated, domain-specific datasets");

// --- Test 18: Full Project Lifecycle (Creation, API Key, Seeding, Test Case) ---
console.log("Test 18: Verify project creation and Getting Started onboarding workflow");
const createdProj = await demoService.createProject({
  name: "Autonomous DevOps Incident Bot",
  description: "Automated alert triage and rollback agent",
});
assert.ok(createdProj.id, "Created project must have unique ID");
assert.ok(createdProj.api_key.startsWith("ar_live_demo_"), "Project creation must return immediate API key");
assert.strictEqual(demoService.currentProjectId, createdProj.id, "Active project must switch to newly created project");

// Verify starter trace was automatically provisioned
const starterTraces = await demoService.listTraceExecutions();
assert.ok(starterTraces.total >= 1, "New project should have an active starter trace");

// Seed demo data for the new project
const seedRes = await demoService.seedDemoData();
assert.ok(seedRes.traces_count >= 2, "Seeding demo data must populate project traces");

// Create and run a new test case in the newly created project
const newTest = await demoService.createTest({
  name: "Alert Triage Verification Test",
  agent_name: "devops_incident_bot",
  steps: [
    { name: "query_datadog_alert", type: "tool_call", status: "success" },
    { name: "evaluate_rollback_policy", type: "tool_call", status: "success" },
  ],
  expected: {
    status: "success",
    tool_sequence: ["query_datadog_alert", "evaluate_rollback_policy"],
    final_output: "Incident resolved",
    error_conditions: [],
  },
});
assert.strictEqual(newTest.project_id, createdProj.id);
const testRun = await demoService.runTest(newTest.id);
assert.strictEqual(testRun.status, "passed");
assert.strictEqual(testRun.test_name, "Alert Triage Verification Test");
console.log("  ✅ Passed: Dynamic project creation, API key banner, trace seeding, and test execution verified");

// --- Test 19: Project Renaming and Archiving ---
console.log("Test 19: Verify project renaming and archiving");
const renamedProj = await demoService.updateProject(createdProj.id, {
  name: "Autonomous SRE Commander",
});
assert.strictEqual(renamedProj.name, "Autonomous SRE Commander");

await demoService.archiveProject(createdProj.id);
const remainingProjects = await demoService.listProjects();
assert.strictEqual(remainingProjects.some(p => p.id === createdProj.id), false, "Archived project must be removed");
console.log("  ✅ Passed: Project renaming and archiving operational");

// --- Test 20: Sandbox Reset to Pristine State ---
console.log("Test 20: Verify Reset Demo restores pristine initial state");
demoService.resetState();
const freshProjects = await demoService.listProjects();
assert.strictEqual(freshProjects.length, 3, "Pristine state must restore the 3 canonical demo projects");
assert.strictEqual(demoService.currentProjectId, 1, "Pristine state must reset active project to 1");
console.log("  ✅ Passed: Reset restored clean initial sandbox state");

// --- Test 21: Object Reference Stability & Infinite Re-render Prevention ---
console.log("Test 21: Verify getMe() and getSystemInfo() return stable references across consecutive reads");
const u1 = await demoService.getMe();
const u2 = await demoService.getMe();
assert.strictEqual(u1, u2, "getMe() must return stable object reference to prevent React re-render loops");

const s1 = await demoService.getSystemInfo();
const s2 = await demoService.getSystemInfo();
assert.strictEqual(s1, s2, "getSystemInfo() must return stable object reference to prevent React re-render loops");
console.log("  ✅ Passed: Object references are stable across consecutive reads");

// --- Test 22: Overview Interactive Navigation Wiring ---
console.log("Test 22: Verify Overview interactive navigation triggers");
import { readFileSync } from "node:fs";
const overviewContent = readFileSync(new URL("../src/pages/Overview.jsx", import.meta.url), "utf-8");
assert.ok(overviewContent.includes('onClick={() => goTo?.("monitoring")}'), "Live SDK Traces stat card must navigate to monitoring");
assert.ok(overviewContent.includes('onClick={() => goTo?.("executions")}'), "Uploaded Logs stat card must navigate to executions");
assert.ok(overviewContent.includes('onClick={() => goTo?.("tests")}'), "Test Cases stat card must navigate to tests");
assert.ok(overviewContent.includes('Live Agent Monitoring\n          </button>'), "Overview narrative must have clickable Live Agent Monitoring button");

const appContent = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf-8");
assert.ok(appContent.includes("userRef = useRef"), "App.jsx must use userRef to stabilize fetchProjects");
assert.ok(appContent.includes("}, []);"), "fetchProjects in App.jsx must have stable empty dependency array to prevent effect recreation loops");
console.log("  ✅ Passed: Overview and App.jsx navigation & loop prevention validated");

console.log("\n🎉 All 22 Demo Mode, Multi-Tenant, Navigation & Security Isolation tests passed successfully!\n");

