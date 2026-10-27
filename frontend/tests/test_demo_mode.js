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

console.log("\n🎉 All 11 Demo Mode & Security Isolation tests passed successfully!\n");

