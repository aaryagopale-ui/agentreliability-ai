/**
 * Comprehensive, realistic synthetic dataset for Public Demo Mode.
 *
 * Provides instant, zero-backend interactive exploration of:
 * - Multi-tenant Projects
 * - Live Observability & Trace Execution Timelines (Nested Tool Calls, Args, Latency)
 * - Golden Baselines & Regression Drift Comparisons
 * - Deterministic Replay Engine & Test Suites
 * - AI Root-Cause Failure Diagnostics
 * - Automated CI/CD Testing Matrix
 */

export const DEMO_USER = {
  id: 9999,
  name: "Demo Explorer (Guest)",
  email: "guest@agentreliability-demo.com",
  role: "demo_visitor",
  is_demo: true,
  created_at: "2026-10-20T00:00:00Z",
};

export const DEMO_SYSTEM_INFO = {
  instance_id: "ar_demo_sandbox",
  database_name: "Public Demo (Synthetic In-Memory Store)",
  database_path: "Client-Side In-Memory Sandbox",
  database_engine: "demo",
  environment: "demo",
  is_demo: true,
  version: "0.1.0-demo",
};

export const DEMO_PROJECTS = [
  {
    id: 1,
    name: "Customer Support AI",
    description: "Autonomous customer service triage, order tracking, and refund processing agent.",
    created_at: "2026-10-20T10:00:00Z",
    owner_id: 9999,
  },
  {
    id: 2,
    name: "Research & Synthesis Agent",
    description: "Multi-step web retrieval, document parsing, and technical synthesis agent.",
    created_at: "2026-10-21T12:00:00Z",
    owner_id: 9999,
  },
  {
    id: 3,
    name: "Financial Fraud Guard",
    description: "Real-time payment risk scoring and anti-money laundering anomaly detection.",
    created_at: "2026-10-22T14:30:00Z",
    owner_id: 9999,
  },
];

// ---------------------------------------------------------------------------
// Traces & Execution Timelines (Project 1: Customer Support AI)
// ---------------------------------------------------------------------------
const now = new Date();
const iso = (minutesAgo) => new Date(now.getTime() - minutesAgo * 60 * 1000).toISOString();

export const DEMO_TRACES_P1 = [
  {
    execution_id: "demo-trace-support-success-1",
    project_id: 1,
    agent_name: "support_triage_agent",
    status: "completed",
    failure_kind: null,
    duration_ms: 245.2,
    tool_call_count: 3,
    failed_tool_calls: 0,
    created_at: iso(12),
    updated_at: iso(12),
    metadata: {
      synthetic_demo: true,
      channel: "customer_portal",
      session_id: "sess_support_9041",
    },
    events: [
      {
        id: "evt_1",
        execution_id: "demo-trace-support-success-1",
        event_type: "run_start",
        name: "support_triage_agent:start",
        timestamp: iso(12),
        data: {
          user_prompt: "My order #99214 was delayed by 4 days. Can I get a full refund?",
          customer_email: "jane.doe@example.com",
        },
      },
      {
        id: "evt_2",
        execution_id: "demo-trace-support-success-1",
        event_type: "tool_start",
        name: "lookup_customer",
        timestamp: iso(12),
        data: {
          call_id: "call_cust_01",
          tool_name: "lookup_customer",
          parameters: { email: "jane.doe@example.com" },
        },
      },
      {
        id: "evt_3",
        execution_id: "demo-trace-support-success-1",
        event_type: "tool_end",
        name: "lookup_customer:end",
        timestamp: iso(12),
        data: {
          call_id: "call_cust_01",
          tool_name: "lookup_customer",
          duration_ms: 42.1,
          result: {
            customer_id: "cust_8821",
            full_name: "Jane Doe",
            tier: "Gold VIP",
            lifetime_orders: 18,
            verified: true,
          },
        },
      },
      {
        id: "evt_4",
        execution_id: "demo-trace-support-success-1",
        event_type: "tool_start",
        name: "check_order_status",
        timestamp: iso(12),
        data: {
          call_id: "call_ord_02",
          tool_name: "check_order_status",
          parameters: { order_id: "ord_99214" },
        },
      },
      {
        id: "evt_5",
        execution_id: "demo-trace-support-success-1",
        event_type: "tool_end",
        name: "check_order_status:end",
        timestamp: iso(12),
        data: {
          call_id: "call_ord_02",
          tool_name: "check_order_status",
          duration_ms: 88.5,
          result: {
            order_id: "ord_99214",
            carrier: "FedEx Express",
            status: "delayed_in_transit",
            days_delayed: 4,
            order_total_usd: 149.99,
            eligible_for_instant_refund: true,
          },
        },
      },
      {
        id: "evt_6",
        execution_id: "demo-trace-support-success-1",
        event_type: "tool_start",
        name: "issue_refund",
        timestamp: iso(12),
        data: {
          call_id: "call_ref_03",
          tool_name: "issue_refund",
          parameters: {
            customer_id: "cust_8821",
            order_id: "ord_99214",
            amount_usd: 149.99,
            reason: "carrier_delay_sla_breach",
          },
        },
      },
      {
        id: "evt_7",
        execution_id: "demo-trace-support-success-1",
        event_type: "tool_end",
        name: "issue_refund:end",
        timestamp: iso(12),
        data: {
          call_id: "call_ref_03",
          tool_name: "issue_refund",
          duration_ms: 95.3,
          result: {
            refund_id: "ref_8829104",
            status: "approved",
            processor_confirmation: "ch_stripe_demo_ok",
            email_receipt_sent: true,
          },
        },
      },
      {
        id: "evt_8",
        execution_id: "demo-trace-support-success-1",
        event_type: "run_end",
        name: "support_triage_agent:finish",
        timestamp: iso(12),
        data: {
          final_response:
            "I apologize for the 4-day delay on order #99214! As a Gold VIP customer, I have issued a full refund of $149.99 to your original payment method. A confirmation email has been sent.",
        },
      },
    ],
    tool_calls: [
      {
        call_id: "call_cust_01",
        tool_name: "lookup_customer",
        parameters: { email: "jane.doe@example.com" },
        result: { customer_id: "cust_8821", tier: "Gold VIP", verified: true },
        duration_ms: 42.1,
        status: "success",
      },
      {
        call_id: "call_ord_02",
        tool_name: "check_order_status",
        parameters: { order_id: "ord_99214" },
        result: { status: "delayed_in_transit", eligible_for_instant_refund: true },
        duration_ms: 88.5,
        status: "success",
      },
      {
        call_id: "call_ref_03",
        tool_name: "issue_refund",
        parameters: { customer_id: "cust_8821", order_id: "ord_99214", amount_usd: 149.99 },
        result: { refund_id: "ref_8829104", status: "approved" },
        duration_ms: 95.3,
        status: "success",
      },
    ],
  },
  {
    execution_id: "demo-trace-support-timeout-1",
    project_id: 1,
    agent_name: "support_triage_agent",
    status: "failed",
    failure_kind: "timeout",
    duration_ms: 10024.0,
    tool_call_count: 2,
    failed_tool_calls: 1,
    created_at: iso(28),
    updated_at: iso(28),
    metadata: {
      synthetic_demo: true,
      channel: "customer_portal",
      error_message: "Gateway socket read timed out after 10000ms while executing 'stripe_refund_charge'",
    },
    events: [
      {
        id: "evt_t1",
        execution_id: "demo-trace-support-timeout-1",
        event_type: "run_start",
        name: "support_triage_agent:start",
        timestamp: iso(28),
        data: { user_prompt: "Refund order #44910 immediately." },
      },
      {
        id: "evt_t2",
        execution_id: "demo-trace-support-timeout-1",
        event_type: "tool_start",
        name: "lookup_customer",
        timestamp: iso(28),
        data: { call_id: "call_cust_t1", tool_name: "lookup_customer" },
      },
      {
        id: "evt_t3",
        execution_id: "demo-trace-support-timeout-1",
        event_type: "tool_end",
        name: "lookup_customer:end",
        timestamp: iso(28),
        data: {
          call_id: "call_cust_t1",
          duration_ms: 24.0,
          result: { customer_id: "cust_1104", verified: true },
        },
      },
      {
        id: "evt_t4",
        execution_id: "demo-trace-support-timeout-1",
        event_type: "tool_start",
        name: "stripe_refund_charge",
        timestamp: iso(28),
        data: { call_id: "call_str_t2", tool_name: "stripe_refund_charge" },
      },
      {
        id: "evt_t5",
        execution_id: "demo-trace-support-timeout-1",
        event_type: "tool_end",
        name: "stripe_refund_charge:timeout",
        timestamp: iso(28),
        data: {
          call_id: "call_str_t2",
          duration_ms: 10000.0,
          error: "SocketTimeoutException: Read timed out connecting to payment endpoint",
        },
      },
      {
        id: "evt_t6",
        execution_id: "demo-trace-support-timeout-1",
        event_type: "run_end",
        name: "support_triage_agent:error",
        timestamp: iso(28),
        data: { error: "Execution terminated: tool call timeout" },
      },
    ],
    tool_calls: [
      {
        call_id: "call_cust_t1",
        tool_name: "lookup_customer",
        parameters: { customer_id: "cust_1104" },
        result: { verified: true },
        duration_ms: 24.0,
        status: "success",
      },
      {
        call_id: "call_str_t2",
        tool_name: "stripe_refund_charge",
        parameters: { amount: 89.0 },
        error: "SocketTimeoutException: Read timed out connecting to payment endpoint",
        duration_ms: 10000.0,
        status: "timeout",
      },
    ],
  },
  {
    execution_id: "demo-trace-support-regressed-1",
    project_id: 1,
    agent_name: "support_triage_agent",
    status: "failed",
    failure_kind: "assertion_failed",
    duration_ms: 184.0,
    tool_call_count: 2,
    failed_tool_calls: 1,
    created_at: iso(45),
    updated_at: iso(45),
    metadata: {
      synthetic_demo: true,
      channel: "customer_portal",
      error_message: "Baseline sequence check failed: missing required step 'verify_customer_identity'",
    },
    events: [
      {
        id: "evt_r1",
        execution_id: "demo-trace-support-regressed-1",
        event_type: "run_start",
        name: "support_triage_agent:start",
        timestamp: iso(45),
        data: { user_prompt: "Can I get a refund on order #8841?" },
      },
      {
        id: "evt_r2",
        execution_id: "demo-trace-support-regressed-1",
        event_type: "tool_start",
        name: "lookup_customer",
        timestamp: iso(45),
        data: { call_id: "call_r1", tool_name: "lookup_customer" },
      },
      {
        id: "evt_r3",
        execution_id: "demo-trace-support-regressed-1",
        event_type: "tool_end",
        name: "lookup_customer:end",
        timestamp: iso(45),
        data: { call_id: "call_r1", duration_ms: 38.0, result: { customer_id: "cust_994" } },
      },
      {
        id: "evt_r4",
        execution_id: "demo-trace-support-regressed-1",
        event_type: "tool_start",
        name: "issue_refund",
        timestamp: iso(45),
        data: { call_id: "call_r2", tool_name: "issue_refund" },
      },
      {
        id: "evt_r5",
        execution_id: "demo-trace-support-regressed-1",
        event_type: "tool_end",
        name: "issue_refund:rejected",
        timestamp: iso(45),
        data: {
          call_id: "call_r2",
          duration_ms: 46.0,
          error: "PermissionDenied: identity verification step omitted before refund execution",
        },
      },
      {
        id: "evt_r6",
        execution_id: "demo-trace-support-regressed-1",
        event_type: "run_end",
        name: "support_triage_agent:error",
        timestamp: iso(45),
        data: { error: "Security assertion failed: unverified refund request" },
      },
    ],
    tool_calls: [
      {
        call_id: "call_r1",
        tool_name: "lookup_customer",
        parameters: { customer_id: "cust_994" },
        result: { customer_id: "cust_994" },
        duration_ms: 38.0,
        status: "success",
      },
      {
        call_id: "call_r2",
        tool_name: "issue_refund",
        parameters: { amount: 50.0 },
        error: "PermissionDenied: identity verification step omitted before refund execution",
        duration_ms: 46.0,
        status: "failed",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Golden Baselines (Project 1)
// ---------------------------------------------------------------------------
export const DEMO_BASELINES_P1 = [
  {
    id: 1,
    project_id: 1,
    name: "Support Triage Golden Baseline (Demo)",
    agent_name: "support_triage_agent",
    active_version: "v1",
    total_versions: 2,
    created_at: "2026-10-21T11:00:00Z",
    updated_at: "2026-10-24T15:30:00Z",
    source_trace_id: "demo-trace-support-success-1",
    versions: [
      {
        version: "v1",
        description: "Locked baseline for standard customer refund flow",
        created_at: "2026-10-21T11:00:00Z",
        source_trace_id: "demo-trace-support-success-1",
        expected_duration_ms: 245.2,
        duration_tolerance_pct: 50.0,
        rules: {
          require_tools_sequence: ["lookup_customer", "check_order_status", "issue_refund"],
          max_failed_tool_calls: 0,
        },
      },
      {
        version: "v2",
        description: "Added identity verification security gate",
        created_at: "2026-10-24T15:30:00Z",
        source_trace_id: "demo-trace-support-success-1",
        expected_duration_ms: 290.0,
        duration_tolerance_pct: 40.0,
        rules: {
          require_tools_sequence: ["lookup_customer", "verify_customer_identity", "check_order_status", "issue_refund"],
          max_failed_tool_calls: 0,
        },
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Test Cases & Replay Runs (Project 1)
// ---------------------------------------------------------------------------
export const DEMO_TESTS_P1 = [
  {
    id: 1,
    project_id: 1,
    name: "Support Triage Refund Flow (Demo)",
    agent_name: "support_triage_agent",
    description: "Verifies that an agent properly looks up customer, checks status, and issues refund on delay.",
    source_type: "trace",
    source_id: "demo-trace-support-success-1",
    step_count: 3,
    last_status: "passed",
    created_at: "2026-10-21T11:15:00Z",
    steps: [
      {
        step: 1,
        tool: "lookup_customer",
        expected_arguments: { email: "jane.doe@example.com" },
        mock_output: { customer_id: "cust_8821", tier: "Gold VIP", verified: true },
      },
      {
        step: 2,
        tool: "check_order_status",
        expected_arguments: { order_id: "ord_99214" },
        mock_output: { status: "delayed_in_transit", eligible_for_instant_refund: true },
      },
      {
        step: 3,
        tool: "issue_refund",
        expected_arguments: { customer_id: "cust_8821", order_id: "ord_99214" },
        mock_output: { refund_id: "ref_8829104", status: "approved" },
      },
    ],
  },
  {
    id: 2,
    project_id: 1,
    name: "Timeout Graceful Recovery Test (Demo)",
    agent_name: "support_triage_agent",
    description: "Tests agent resilience when external payment gateway hangs.",
    source_type: "trace",
    source_id: "demo-trace-support-timeout-1",
    step_count: 2,
    last_status: "failed",
    created_at: "2026-10-22T09:20:00Z",
    steps: [
      {
        step: 1,
        tool: "lookup_customer",
        expected_arguments: { customer_id: "cust_1104" },
        mock_output: { verified: true },
      },
      {
        step: 2,
        tool: "stripe_refund_charge",
        expected_arguments: { amount: 89.0 },
        mock_output: { error: "timeout" },
      },
    ],
  },
];

export const DEMO_TEST_RUNS_P1 = [
  {
    id: 101,
    test_id: 1,
    test_name: "Support Triage Refund Flow (Demo)",
    status: "passed",
    duration_ms: 198.4,
    created_at: iso(10),
    step_results: [
      { step: 1, tool: "lookup_customer", status: "passed", duration_ms: 32.1 },
      { step: 2, tool: "check_order_status", status: "passed", duration_ms: 74.0 },
      { step: 3, tool: "issue_refund", status: "passed", duration_ms: 92.3 },
    ],
  },
  {
    id: 102,
    test_id: 2,
    test_name: "Timeout Graceful Recovery Test (Demo)",
    status: "failed",
    duration_ms: 10024.0,
    created_at: iso(25),
    error_message: "Step 2 'stripe_refund_charge' timed out after 10000ms",
    step_results: [
      { step: 1, tool: "lookup_customer", status: "passed", duration_ms: 24.0 },
      { step: 2, tool: "stripe_refund_charge", status: "failed", error: "Timeout after 10000ms", duration_ms: 10000.0 },
    ],
  },
];

// ---------------------------------------------------------------------------
// CI/CD Runs (Project 1)
// ---------------------------------------------------------------------------
export const DEMO_CI_RUNS_P1 = [
  {
    id: 42,
    project_id: 1,
    branch: "main",
    commit_sha: "0bba4ef",
    commit_message: "feat: add payment gateway circuit breaker",
    trigger: "push",
    status: "passed",
    tests_total: 8,
    tests_passed: 8,
    tests_failed: 0,
    duration_seconds: 4.8,
    created_at: iso(30),
  },
  {
    id: 41,
    project_id: 1,
    branch: "feature/prompt-update",
    commit_sha: "9f82d1c",
    commit_message: "refactor: simplify triage agent prompt instructions",
    trigger: "pull_request",
    status: "failed",
    tests_total: 8,
    tests_passed: 6,
    tests_failed: 2,
    duration_seconds: 5.2,
    created_at: iso(120),
    failure_summary: "Regression detected: 'verify_customer_identity' was bypassed in refund flow.",
  },
  {
    id: 40,
    project_id: 1,
    branch: "main",
    commit_sha: "ae608bc",
    commit_message: "chore: update agent test fixtures",
    trigger: "push",
    status: "passed",
    tests_total: 8,
    tests_passed: 8,
    tests_failed: 0,
    duration_seconds: 4.5,
    created_at: iso(360),
  },
];

// ---------------------------------------------------------------------------
// AI Failure Analysis & Diagnostics (Project 1)
// ---------------------------------------------------------------------------
export const DEMO_FAILURE_ANALYSIS_P1 = {
  total_analyzed: 14,
  breakdown: [
    { failure_kind: "timeout", count: 6, percentage: 42.8 },
    { failure_kind: "tool_failure", count: 5, percentage: 35.7 },
    { failure_kind: "assertion_failed", count: 3, percentage: 21.5 },
  ],
  top_culprits: [
    { tool_name: "stripe_refund_charge", failure_count: 5, avg_latency_ms: 8420 },
    { tool_name: "issue_refund", failure_count: 3, avg_latency_ms: 110 },
    { tool_name: "check_order_status", failure_count: 1, avg_latency_ms: 140 },
  ],
};

// ---------------------------------------------------------------------------
// Simulated API Keys for Public Demo Mode
// ---------------------------------------------------------------------------
export const DEMO_API_KEYS_P1 = [
  {
    id: 1,
    project_id: 1,
    name: "Customer Support Production Key (Demo)",
    key_prefix: "ar_live_demo_cs_",
    created_at: "2026-10-20T10:05:00Z",
    last_used_at: iso(12),
    is_demo: true,
  },
  {
    id: 2,
    project_id: 1,
    name: "CI/CD Pipeline Key (Demo)",
    key_prefix: "ar_live_demo_ci_",
    created_at: "2026-10-21T08:00:00Z",
    last_used_at: iso(30),
    is_demo: true,
  },
];

