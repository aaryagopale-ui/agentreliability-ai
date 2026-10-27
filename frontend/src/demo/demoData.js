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
// Phase 1 Uploaded Executions (Project 1)
// ---------------------------------------------------------------------------
export const DEMO_EXECUTIONS_P1 = [
  {
    id: 1,
    project_id: 1,
    agent_name: "support_triage_agent",
    status: "success",
    step_count: 3,
    finding_count: 0,
    created_at: iso(15),
    findings: [],
    steps: [
      {
        step_index: 0,
        name: "lookup_customer",
        type: "tool_call",
        duration_ms: 42.1,
        timestamp: iso(15),
        input: { email: "jane.doe@example.com" },
        output: { customer_id: "cust_8821", full_name: "Jane Doe", tier: "Gold VIP", verified: true },
      },
      {
        step_index: 1,
        name: "check_order_status",
        type: "tool_call",
        duration_ms: 85.3,
        timestamp: iso(15),
        input: { order_id: "ord_99214" },
        output: { order_id: "ord_99214", status: "delayed_in_transit", delayed_days: 4, eligible_for_refund: true },
      },
      {
        step_index: 2,
        name: "issue_refund",
        type: "tool_call",
        duration_ms: 117.8,
        timestamp: iso(15),
        input: { customer_id: "cust_8821", order_id: "ord_99214", amount: 89.0 },
        output: { refund_id: "ref_8829104", status: "approved", amount: 89.0 },
      },
    ],
  },
  {
    id: 2,
    project_id: 1,
    agent_name: "support_triage_agent",
    status: "failed",
    step_count: 3,
    finding_count: 1,
    created_at: iso(25),
    findings: [
      {
        step_index: 2,
        category: "timeout",
        explanation: "Socket read timed out after 10020ms while calling stripe_refund_charge.",
      },
    ],
    steps: [
      {
        step_index: 0,
        name: "lookup_customer",
        type: "tool_call",
        duration_ms: 38.0,
        timestamp: iso(25),
        input: { email: "alex.smith@example.com" },
        output: { customer_id: "cust_1104", verified: true },
      },
      {
        step_index: 1,
        name: "check_order_status",
        type: "tool_call",
        duration_ms: 64.2,
        timestamp: iso(25),
        input: { order_id: "ord_77180" },
        output: { status: "damaged", eligible_for_refund: true },
      },
      {
        step_index: 2,
        name: "stripe_refund_charge",
        type: "tool_call",
        duration_ms: 10020.5,
        timestamp: iso(25),
        input: { charge_id: "ch_3N82bX2eZvKYlo2C1", amount: 145.0 },
        output: { error: "upstream_timeout", code: 504 },
      },
    ],
  },
  {
    id: 3,
    project_id: 1,
    agent_name: "support_triage_agent",
    status: "failed",
    step_count: 2,
    finding_count: 1,
    created_at: iso(50),
    findings: [
      {
        step_index: 1,
        category: "tool_failure",
        explanation: "Validation error: parameter 'currency_code' is required.",
      },
    ],
    steps: [
      {
        step_index: 0,
        name: "lookup_customer",
        type: "tool_call",
        duration_ms: 40.2,
        timestamp: iso(50),
        input: { email: "bob.jones@example.com" },
        output: { customer_id: "cust_4402", verified: true },
      },
      {
        step_index: 1,
        name: "issue_refund",
        type: "tool_call",
        duration_ms: 72.1,
        timestamp: iso(50),
        input: { customer_id: "cust_4402", amount: 50.0 },
        output: { error: "invalid_request", message: "Parameter 'currency_code' is required." },
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
    description: "Locked baseline for customer refund workflow with verified tool sequence and latency constraints.",
    current_version: 1,
    active_version: "v1",
    total_versions: 2,
    created_at: "2026-10-21T11:00:00Z",
    updated_at: "2026-10-24T15:30:00Z",
    source_trace_id: "demo-trace-support-success-1",
    version_data: {
      status: "success",
      source_id: "demo-trace-support-success-1",
      duration_ms: 245.2,
      tools: [
        { tool_name: "lookup_customer" },
        { tool_name: "check_order_status" },
        { tool_name: "issue_refund" },
      ],
      expected: {
        tool_sequence: ["lookup_customer", "check_order_status", "issue_refund"],
        strict_order: true,
        expected_output_fields: ["customer_id", "refund_id", "status"],
        status: "success",
        max_duration_ms: 500,
      },
    },
    versions: [
      {
        version: 1,
        description: "Locked baseline for standard customer refund flow",
        created_at: "2026-10-21T11:00:00Z",
        source_id: "demo-trace-support-success-1",
        duration_ms: 245.2,
        tools: [
          { tool_name: "lookup_customer" },
          { tool_name: "check_order_status" },
          { tool_name: "issue_refund" },
        ],
        expected: {
          tool_sequence: ["lookup_customer", "check_order_status", "issue_refund"],
          strict_order: true,
          expected_output_fields: ["customer_id", "refund_id", "status"],
          status: "success",
          max_duration_ms: 500,
        },
      },
      {
        version: 2,
        description: "Added identity verification security gate",
        created_at: "2026-10-24T15:30:00Z",
        source_id: "demo-trace-support-success-1",
        duration_ms: 290.0,
        tools: [
          { tool_name: "lookup_customer" },
          { tool_name: "verify_customer_identity" },
          { tool_name: "check_order_status" },
          { tool_name: "issue_refund" },
        ],
        expected: {
          tool_sequence: ["lookup_customer", "verify_customer_identity", "check_order_status", "issue_refund"],
          strict_order: true,
          expected_output_fields: ["customer_id", "refund_id", "status"],
          status: "success",
          max_duration_ms: 600,
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
    input: { order_id: "ord_99214", customer_email: "jane.doe@example.com" },
    expected: {
      status: "success",
      tool_sequence: ["lookup_customer", "check_order_status", "issue_refund"],
      final_output: "Your refund of $89.00 for order #99214 has been approved and processed.",
      error_conditions: [],
    },
    steps: [
      {
        step_index: 0,
        type: "tool_call",
        name: "lookup_customer",
        status: "success",
        duration_ms: 42,
        timeout_ms: 5000,
        input: { email: "jane.doe@example.com" },
        output: { customer_id: "cust_8821", tier: "Gold VIP", verified: true },
      },
      {
        step_index: 1,
        type: "tool_call",
        name: "check_order_status",
        status: "success",
        duration_ms: 85,
        timeout_ms: 5000,
        input: { order_id: "ord_99214" },
        output: { status: "delayed_in_transit", eligible_for_instant_refund: true },
      },
      {
        step_index: 2,
        type: "tool_call",
        name: "issue_refund",
        status: "success",
        duration_ms: 118,
        timeout_ms: 5000,
        input: { customer_id: "cust_8821", order_id: "ord_99214" },
        output: { refund_id: "ref_8829104", status: "approved" },
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
    input: { order_id: "ord_77180", customer_email: "alex.smith@example.com" },
    expected: {
      status: "success",
      tool_sequence: ["lookup_customer", "stripe_refund_charge"],
      final_output: "Refund processed successfully.",
      error_conditions: [],
    },
    steps: [
      {
        step_index: 0,
        type: "tool_call",
        name: "lookup_customer",
        status: "success",
        duration_ms: 38,
        timeout_ms: 5000,
        input: { customer_id: "cust_1104" },
        output: { verified: true },
      },
      {
        step_index: 1,
        type: "tool_call",
        name: "stripe_refund_charge",
        status: "failed",
        duration_ms: 10020,
        timeout_ms: 5000,
        input: { amount: 89.0 },
        output: { error: "timeout" },
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
    disclaimer: "Deterministic simulation with mocked tool responses. No model or live API was executed.",
    mismatches: [],
    mismatch_count: 0,
    observed: {
      tool_sequence: ["lookup_customer", "check_order_status", "issue_refund"],
      final_output: "Your refund of $89.00 for order #99214 has been approved and processed.",
      steps: [
        {
          step_index: 0,
          name: "lookup_customer",
          type: "tool_call",
          duration_ms: 42.1,
          timestamp: iso(10),
          input: { email: "jane.doe@example.com" },
          output: { customer_id: "cust_8821", tier: "Gold VIP", verified: true },
        },
        {
          step_index: 1,
          name: "check_order_status",
          type: "tool_call",
          duration_ms: 85.3,
          timestamp: iso(10),
          input: { order_id: "ord_99214" },
          output: { status: "delayed_in_transit", eligible_for_instant_refund: true },
        },
        {
          step_index: 2,
          name: "issue_refund",
          type: "tool_call",
          duration_ms: 117.8,
          timestamp: iso(10),
          input: { customer_id: "cust_8821", order_id: "ord_99214" },
          output: { refund_id: "ref_8829104", status: "approved" },
        },
      ],
      findings: [],
    },
  },
  {
    id: 102,
    test_id: 2,
    test_name: "Timeout Graceful Recovery Test (Demo)",
    status: "failed",
    duration_ms: 10024.0,
    created_at: iso(25),
    disclaimer: "Deterministic simulation with mocked tool responses. No model or live API was executed.",
    mismatches: [
      {
        kind: "timeout",
        step_index: 1,
        message: "Step 2 exceeded timeout threshold of 5000ms (observed: 10024ms)",
      },
    ],
    mismatch_count: 1,
    observed: {
      tool_sequence: ["lookup_customer", "stripe_refund_charge"],
      final_output: null,
      steps: [
        {
          step_index: 0,
          name: "lookup_customer",
          type: "tool_call",
          duration_ms: 38.0,
          timestamp: iso(25),
          input: { customer_id: "cust_1104" },
          output: { verified: true },
        },
        {
          step_index: 1,
          name: "stripe_refund_charge",
          type: "tool_call",
          duration_ms: 10024.0,
          timestamp: iso(25),
          input: { amount: 89.0 },
          output: { error: "socket_read_timeout" },
        },
      ],
      findings: [
        {
          step_index: 1,
          category: "timeout",
          explanation: "Socket read timed out after 10024ms while calling stripe_refund_charge.",
        },
      ],
    },
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
    commit_sha: "0bba4ef18c",
    commit_message: "feat: add payment gateway circuit breaker",
    actor: "ci-bot",
    trigger: "push",
    status: "passed",
    total: 12,
    passed: 12,
    failed: 0,
    duration_ms: 4820.0,
    created_at: iso(30),
    report: {
      regression: {
        counts: {
          new_failures: 0,
          fixed_failures: 1,
        },
      },
      results: [
        {
          name: "test_customer_lookup_tier_vip",
          status: "passed",
          file: "tests/test_support_triage.py",
          mismatches: [],
        },
        {
          name: "test_order_delay_refund_instant",
          status: "passed",
          file: "tests/test_support_triage.py",
          mismatches: [],
        },
        {
          name: "test_payment_gateway_timeout_breaker",
          status: "passed",
          file: "tests/test_support_triage.py",
          mismatches: [],
        },
      ],
    },
  },
  {
    id: 41,
    project_id: 1,
    branch: "feature/prompt-update",
    commit_sha: "9f82d1c5a2",
    commit_message: "refactor: simplify triage agent prompt instructions",
    actor: "developer",
    trigger: "pull_request",
    status: "failed",
    total: 12,
    passed: 10,
    failed: 2,
    duration_ms: 3910.0,
    created_at: iso(120),
    report: {
      regression: {
        counts: {
          new_failures: 2,
          fixed_failures: 0,
        },
      },
      results: [
        {
          name: "test_customer_lookup_tier_vip",
          status: "passed",
          file: "tests/test_support_triage.py",
          mismatches: [],
        },
        {
          name: "test_golden_baseline_invariant_sequence",
          status: "failed",
          file: "tests/test_golden_baselines.py",
          mismatches: [
            {
              kind: "breaking_regression",
              message: "Missing mandatory invariant tool 'verify_customer_identity' from execution sequence.",
            },
          ],
        },
        {
          name: "test_refund_authorization_gate",
          status: "failed",
          file: "tests/test_security_gates.py",
          mismatches: [
            {
              kind: "security_violation",
              message: "Refund triggered without completed customer identity gate verification.",
            },
          ],
        },
      ],
    },
  },
  {
    id: 40,
    project_id: 1,
    branch: "main",
    commit_sha: "ae608bc741",
    commit_message: "chore: update agent test fixtures",
    actor: "developer",
    trigger: "push",
    status: "passed",
    total: 8,
    passed: 8,
    failed: 0,
    duration_ms: 4500.0,
    created_at: iso(360),
    report: {
      regression: {
        counts: {
          new_failures: 0,
          fixed_failures: 0,
        },
      },
      results: [
        {
          name: "test_customer_lookup_tier_vip",
          status: "passed",
          file: "tests/test_support_triage.py",
          mismatches: [],
        },
      ],
    },
  },
];

// ---------------------------------------------------------------------------
// AI Failure Analysis & Diagnostics (Project 1)
// ---------------------------------------------------------------------------
export const DEMO_FAILURE_ANALYSIS_P1 = {
  local_ai: {
    available: true,
    models: ["llama3:latest", "mistral:latest"],
    selected_model: "llama3:latest",
    base_url: "http://127.0.0.1:11434",
  },
  failed_traces: [
    {
      execution_id: "demo-trace-support-timeout-1",
      agent_name: "support_triage_agent",
      failure_kind: "timeout",
      started_at: iso(25),
      duration_ms: 10020.5,
      error_message: "Gateway timeout after 10000ms calling stripe_refund_charge",
      error_type: "TimeoutError",
      tool_calls: [
        { call_id: "c1", tool_name: "lookup_customer", status: "success", duration_ms: 38.0 },
        { call_id: "c2", tool_name: "check_order_status", status: "success", duration_ms: 64.2 },
        { call_id: "c3", tool_name: "stripe_refund_charge", status: "failed", duration_ms: 10020.5 },
      ],
    },
    {
      execution_id: "demo-trace-support-error-1",
      agent_name: "support_triage_agent",
      failure_kind: "tool_failure",
      started_at: iso(50),
      duration_ms: 320.1,
      error_message: "400 Bad Request: Parameter 'currency_code' is required.",
      error_type: "ApiError",
      tool_calls: [
        { call_id: "c4", tool_name: "lookup_customer", status: "success", duration_ms: 40.2 },
        { call_id: "c5", tool_name: "issue_refund", status: "failed", duration_ms: 72.1 },
      ],
    },
    {
      execution_id: "demo-trace-support-regression-1",
      agent_name: "support_triage_agent",
      failure_kind: "assertion_failed",
      started_at: iso(75),
      duration_ms: 195.4,
      error_message: "Sequence regression: verify_customer_identity step skipped.",
      error_type: "AssertionError",
      tool_calls: [
        { call_id: "c6", tool_name: "lookup_customer", status: "success", duration_ms: 35.0 },
        { call_id: "c7", tool_name: "issue_refund", status: "success", duration_ms: 88.0 },
      ],
    },
  ],
  failing_runs: [
    {
      id: 102,
      test_name: "Timeout Graceful Recovery Test (Demo)",
      created_at: iso(30),
      duration_ms: 10020.0,
      status: "failed",
      mismatches: [
        {
          kind: "timeout",
          step_index: 1,
          message: "Step 2 exceeded timeout threshold of 5000ms (observed: 10020ms)",
        },
      ],
    },
  ],
  trace_failure_kinds: {
    timeout: 6,
    tool_failure: 5,
    assertion_failed: 3,
  },
  execution_findings: {
    timeout: 2,
    tool_failure: 1,
  },
  replay_mismatches: {
    timeout: 1,
    tool_sequence: 1,
  },
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

// ===========================================================================
// PROJECT 2: Research & Synthesis Agent
// ===========================================================================

export const DEMO_EXECUTIONS_P2 = [
  {
    id: 201,
    project_id: 2,
    agent_name: "deep_research_agent",
    status: "success",
    step_count: 3,
    finding_count: 0,
    created_at: iso(45),
    findings: [],
    steps: [
      {
        step_index: 0,
        name: "search_arxiv",
        type: "tool_call",
        duration_ms: 180.2,
        timestamp: iso(45),
        input: { query: "large language models test-time compute reasoning" },
        output: { results_count: 5, top_paper_id: "2408.03314" },
      },
      {
        step_index: 1,
        name: "download_pdf_text",
        type: "tool_call",
        duration_ms: 310.5,
        timestamp: iso(45),
        input: { paper_id: "2408.03314" },
        output: { pages_extracted: 14, text_length_chars: 48210 },
      },
      {
        step_index: 2,
        name: "synthesize_literature_matrix",
        type: "llm_call",
        duration_ms: 620.0,
        timestamp: iso(45),
        input: { focus_area: "scaling search vs pretraining compute" },
        output: { key_insights_count: 4, summary: "Test-time search yields exponential returns on verifiable domains." },
      },
    ],
  },
  {
    id: 202,
    project_id: 2,
    agent_name: "deep_research_agent",
    status: "failed",
    step_count: 2,
    finding_count: 1,
    created_at: iso(90),
    findings: [
      {
        step_index: 1,
        category: "timeout",
        explanation: "Rate limiter blocked upstream ArXiv mirror after 10000ms socket hang.",
      },
    ],
    steps: [
      {
        step_index: 0,
        name: "search_arxiv",
        type: "tool_call",
        duration_ms: 195.0,
        timestamp: iso(90),
        input: { query: "reinforcement learning from verifier feedback" },
        output: { results_count: 3, top_paper_id: "2409.01122" },
      },
      {
        step_index: 1,
        name: "download_pdf_text",
        type: "tool_call",
        duration_ms: 10015.0,
        timestamp: iso(90),
        input: { paper_id: "2409.01122" },
        output: { error: "gateway_timeout", code: 504 },
      },
    ],
  },
];

export const DEMO_TRACES_P2 = [
  {
    execution_id: "demo-trace-research-success-1",
    project_id: 2,
    agent_name: "deep_research_agent",
    status: "completed",
    failure_kind: null,
    duration_ms: 1110.7,
    tool_call_count: 3,
    failed_tool_calls: 0,
    created_at: iso(45),
    updated_at: iso(45),
    metadata: { synthetic_demo: true, task: "arxiv_synthesis" },
    events: [
      {
        id: "evt_p2_1",
        execution_id: "demo-trace-research-success-1",
        event_type: "run_start",
        name: "deep_research_agent:start",
        timestamp: iso(45),
        data: { query: "Latest advances in test-time reasoning compute scaling" },
      },
      {
        id: "evt_p2_2",
        execution_id: "demo-trace-research-success-1",
        event_type: "tool_start",
        name: "search_arxiv",
        timestamp: iso(45),
        data: { tool_name: "search_arxiv", parameters: { query: "test-time compute reasoning" } },
      },
      {
        id: "evt_p2_3",
        execution_id: "demo-trace-research-success-1",
        event_type: "tool_end",
        name: "search_arxiv:end",
        timestamp: iso(45),
        data: { tool_name: "search_arxiv", duration_ms: 180.2, result: { papers: 5 } },
      },
    ],
    tool_calls: [
      { call_id: "c_r1", tool_name: "search_arxiv", duration_ms: 180.2, status: "success", parameters: { query: "test-time compute" }, result: { count: 5 } },
      { call_id: "c_r2", tool_name: "download_pdf_text", duration_ms: 310.5, status: "success", parameters: { paper_id: "2408.03314" }, result: { pages: 14 } },
      { call_id: "c_r3", tool_name: "synthesize_literature_matrix", duration_ms: 620.0, status: "success", parameters: { mode: "executive_summary" }, result: { matrix_created: true } },
    ],
  },
  {
    execution_id: "demo-trace-research-timeout-1",
    project_id: 2,
    agent_name: "deep_research_agent",
    status: "failed",
    failure_kind: "timeout",
    duration_ms: 10210.0,
    tool_call_count: 2,
    failed_tool_calls: 1,
    created_at: iso(90),
    updated_at: iso(90),
    error_message: "Gateway timeout after 10000ms calling download_pdf_text",
    error_type: "TimeoutError",
    metadata: { synthetic_demo: true, task: "arxiv_synthesis" },
    events: [],
    tool_calls: [
      { call_id: "c_r4", tool_name: "search_arxiv", duration_ms: 195.0, status: "success", parameters: { query: "rlvf" }, result: { count: 3 } },
      { call_id: "c_r5", tool_name: "download_pdf_text", duration_ms: 10015.0, status: "failed", error: "Connection timed out after 10.01s", parameters: { paper_id: "2409.01122" } },
    ],
  },
];

export const DEMO_BASELINES_P2 = [
  {
    id: 2,
    project_id: 2,
    name: "Literature Review Invariant Baseline",
    agent_name: "deep_research_agent",
    description: "Guarantees that papers are verified and parsed before synthesis generation.",
    current_version: 1,
    active_version: "v1",
    total_versions: 1,
    created_at: "2026-10-21T14:00:00Z",
    updated_at: "2026-10-21T14:00:00Z",
    source_trace_id: "demo-trace-research-success-1",
    version_data: {
      status: "success",
      source_id: "demo-trace-research-success-1",
      duration_ms: 1110.7,
      tools: [
        { tool_name: "search_arxiv" },
        { tool_name: "download_pdf_text" },
        { tool_name: "synthesize_literature_matrix" },
      ],
      expected: {
        tool_sequence: ["search_arxiv", "download_pdf_text", "synthesize_literature_matrix"],
        strict_order: true,
        expected_output_fields: ["matrix_created"],
        status: "success",
        max_duration_ms: 3000,
      },
    },
    versions: [
      {
        version: 1,
        description: "Initial ArXiv multi-hop retrieval baseline",
        created_at: "2026-10-21T14:00:00Z",
        source_id: "demo-trace-research-success-1",
        duration_ms: 1110.7,
        tools: [
          { tool_name: "search_arxiv" },
          { tool_name: "download_pdf_text" },
          { tool_name: "synthesize_literature_matrix" },
        ],
        expected: {
          tool_sequence: ["search_arxiv", "download_pdf_text", "synthesize_literature_matrix"],
          strict_order: true,
          expected_output_fields: ["matrix_created"],
          status: "success",
          max_duration_ms: 3000,
        },
      },
    ],
  },
];

export const DEMO_TESTS_P2 = [
  {
    id: 201,
    project_id: 2,
    name: "ArXiv Retrieval & Synthesis Benchmark",
    agent_name: "deep_research_agent",
    description: "Evaluates multi-paper parsing and structured summary formatting.",
    source_type: "trace",
    source_id: "demo-trace-research-success-1",
    step_count: 3,
    last_status: "passed",
    created_at: "2026-10-22T10:00:00Z",
    input: { query: "test-time compute" },
    expected: {
      status: "success",
      tool_sequence: ["search_arxiv", "download_pdf_text", "synthesize_literature_matrix"],
      final_output: "Synthesis completed.",
      error_conditions: [],
    },
    steps: [
      { step_index: 0, type: "tool_call", name: "search_arxiv", status: "success", duration_ms: 180, output: { count: 5 } },
      { step_index: 1, type: "tool_call", name: "download_pdf_text", status: "success", duration_ms: 310, output: { pages: 14 } },
      { step_index: 2, type: "llm_call", name: "synthesize_literature_matrix", status: "success", duration_ms: 620, output: { matrix_created: true } },
    ],
  },
];

export const DEMO_TEST_RUNS_P2 = [
  {
    id: 2001,
    test_id: 201,
    project_id: 2,
    test_name: "ArXiv Retrieval & Synthesis Benchmark",
    status: "passed",
    duration_ms: 1110.7,
    created_at: iso(40),
    disclaimer: "Deterministic simulation with mocked tools.",
    mismatches: [],
    mismatch_count: 0,
    observed: {
      tool_sequence: ["search_arxiv", "download_pdf_text", "synthesize_literature_matrix"],
      final_output: "Synthesis completed.",
      steps: [
        { step_index: 0, name: "search_arxiv", type: "tool_call", duration_ms: 180, status: "success", output: { count: 5 } },
        { step_index: 1, name: "download_pdf_text", type: "tool_call", duration_ms: 310, status: "success", output: { pages: 14 } },
        { step_index: 2, name: "synthesize_literature_matrix", type: "llm_call", duration_ms: 620, status: "success", output: { matrix_created: true } },
      ],
      findings: [],
    },
  },
];

export const DEMO_CI_RUNS_P2 = [
  {
    id: 201,
    project_id: 2,
    branch: "main",
    commit_sha: "e82d119a",
    commit_message: "feat: add PDF semantic section chunker",
    actor: "research-dev",
    trigger: "push",
    status: "passed",
    total: 6,
    passed: 6,
    failed: 0,
    duration_ms: 6120.0,
    created_at: iso(180),
    report: {
      regression: { counts: { new_failures: 0, fixed_failures: 0 } },
      results: [
        { name: "test_arxiv_query_sanitization", status: "passed", file: "tests/test_arxiv.py", mismatches: [] },
        { name: "test_pdf_extraction_unicode_support", status: "passed", file: "tests/test_pdf.py", mismatches: [] },
      ],
    },
  },
];

export const DEMO_API_KEYS_P2 = [
  {
    id: 21,
    project_id: 2,
    name: "Research Synthesis CLI Key (Demo)",
    key_prefix: "ar_live_demo_rs_",
    created_at: "2026-10-21T12:05:00Z",
    last_used_at: iso(45),
    is_demo: true,
  },
];

// ===========================================================================
// PROJECT 3: Financial Fraud Guard
// ===========================================================================

export const DEMO_EXECUTIONS_P3 = [
  {
    id: 301,
    project_id: 3,
    agent_name: "fraud_guard_agent",
    status: "success",
    step_count: 3,
    finding_count: 0,
    created_at: iso(20),
    findings: [],
    steps: [
      {
        step_index: 0,
        name: "check_geo_ip_anomaly",
        type: "tool_call",
        duration_ms: 28.4,
        timestamp: iso(20),
        input: { ip: "198.51.100.44", user_home_country: "US" },
        output: { detected_country: "US", distance_km: 12.0, is_vpn: false },
      },
      {
        step_index: 1,
        name: "calculate_velocity_score",
        type: "tool_call",
        duration_ms: 45.1,
        timestamp: iso(20),
        input: { card_token: "tok_visa_4412", timeframe_minutes: 60 },
        output: { tx_count: 1, total_volume_usd: 85.0, velocity_risk: "low" },
      },
      {
        step_index: 2,
        name: "authorize_payment_intent",
        type: "tool_call",
        duration_ms: 82.0,
        timestamp: iso(20),
        input: { intent_id: "pi_99014", risk_tier: "tier_1_verified" },
        output: { authorization_status: "approved", fraud_score: 0.02 },
      },
    ],
  },
  {
    id: 302,
    project_id: 3,
    agent_name: "fraud_guard_agent",
    status: "failed",
    step_count: 3,
    finding_count: 1,
    created_at: iso(70),
    findings: [
      {
        step_index: 2,
        category: "tool_failure",
        explanation: "Risk score (0.91) triggered automated transaction freeze.",
      },
    ],
    steps: [
      {
        step_index: 0,
        name: "check_geo_ip_anomaly",
        type: "tool_call",
        duration_ms: 32.1,
        timestamp: iso(70),
        input: { ip: "203.0.113.19", user_home_country: "US" },
        output: { detected_country: "NG", distance_km: 8400.0, is_vpn: true },
      },
      {
        step_index: 1,
        name: "calculate_velocity_score",
        type: "tool_call",
        duration_ms: 48.0,
        timestamp: iso(70),
        input: { card_token: "tok_mc_9821", timeframe_minutes: 60 },
        output: { tx_count: 9, total_volume_usd: 4820.0, velocity_risk: "extreme" },
      },
      {
        step_index: 2,
        name: "authorize_payment_intent",
        type: "tool_call",
        duration_ms: 61.2,
        timestamp: iso(70),
        input: { intent_id: "pi_88190" },
        output: { authorization_status: "blocked_high_risk", fraud_score: 0.91 },
      },
    ],
  },
];

export const DEMO_TRACES_P3 = [
  {
    execution_id: "demo-trace-fraud-clean-1",
    project_id: 3,
    agent_name: "fraud_guard_agent",
    status: "completed",
    failure_kind: null,
    duration_ms: 155.5,
    tool_call_count: 3,
    failed_tool_calls: 0,
    created_at: iso(20),
    updated_at: iso(20),
    metadata: { synthetic_demo: true, channel: "payment_gateway_hook" },
    events: [],
    tool_calls: [
      { call_id: "c_f1", tool_name: "check_geo_ip_anomaly", duration_ms: 28.4, status: "success", parameters: { ip: "198.51.100.44" }, result: { is_vpn: false } },
      { call_id: "c_f2", tool_name: "calculate_velocity_score", duration_ms: 45.1, status: "success", parameters: { card: "tok_visa_4412" }, result: { risk: "low" } },
      { call_id: "c_f3", tool_name: "authorize_payment_intent", duration_ms: 82.0, status: "success", parameters: { intent_id: "pi_99014" }, result: { status: "approved" } },
    ],
  },
  {
    execution_id: "demo-trace-fraud-flag-1",
    project_id: 3,
    agent_name: "fraud_guard_agent",
    status: "failed",
    failure_kind: "tool_failure",
    duration_ms: 141.3,
    tool_call_count: 3,
    failed_tool_calls: 1,
    created_at: iso(70),
    updated_at: iso(70),
    error_message: "Automated transaction block: High-risk geo velocity anomaly detected.",
    error_type: "FraudBlockException",
    metadata: { synthetic_demo: true, channel: "payment_gateway_hook" },
    events: [],
    tool_calls: [
      { call_id: "c_f4", tool_name: "check_geo_ip_anomaly", duration_ms: 32.1, status: "success", parameters: { ip: "203.0.113.19" }, result: { is_vpn: true } },
      { call_id: "c_f5", tool_name: "calculate_velocity_score", duration_ms: 48.0, status: "success", parameters: { card: "tok_mc_9821" }, result: { risk: "extreme" } },
      { call_id: "c_f6", tool_name: "authorize_payment_intent", duration_ms: 61.2, status: "failed", error: "Blocked: Fraud score 0.91 exceeds threshold", parameters: { intent_id: "pi_88190" } },
    ],
  },
];

export const DEMO_BASELINES_P3 = [
  {
    id: 3,
    project_id: 3,
    name: "AML Transaction Screening Baseline",
    agent_name: "fraud_guard_agent",
    description: "Requires dual-pass geo IP check and velocity scoring before any card authorization.",
    current_version: 1,
    active_version: "v1",
    total_versions: 1,
    created_at: "2026-10-22T14:45:00Z",
    updated_at: "2026-10-22T14:45:00Z",
    source_trace_id: "demo-trace-fraud-clean-1",
    version_data: {
      status: "success",
      source_id: "demo-trace-fraud-clean-1",
      duration_ms: 155.5,
      tools: [
        { tool_name: "check_geo_ip_anomaly" },
        { tool_name: "calculate_velocity_score" },
        { tool_name: "authorize_payment_intent" },
      ],
      expected: {
        tool_sequence: ["check_geo_ip_anomaly", "calculate_velocity_score", "authorize_payment_intent"],
        strict_order: true,
        expected_output_fields: ["authorization_status"],
        status: "success",
        max_duration_ms: 500,
      },
    },
    versions: [
      {
        version: 1,
        description: "Initial fraud policy screening baseline",
        created_at: "2026-10-22T14:45:00Z",
        source_id: "demo-trace-fraud-clean-1",
        duration_ms: 155.5,
        tools: [
          { tool_name: "check_geo_ip_anomaly" },
          { tool_name: "calculate_velocity_score" },
          { tool_name: "authorize_payment_intent" },
        ],
        expected: {
          tool_sequence: ["check_geo_ip_anomaly", "calculate_velocity_score", "authorize_payment_intent"],
          strict_order: true,
          expected_output_fields: ["authorization_status"],
          status: "success",
          max_duration_ms: 500,
        },
      },
    ],
  },
];

export const DEMO_TESTS_P3 = [
  {
    id: 301,
    project_id: 3,
    name: "Clean Consumer Transaction Flow",
    agent_name: "fraud_guard_agent",
    description: "Tests fast-path low risk card transaction verification.",
    source_type: "trace",
    source_id: "demo-trace-fraud-clean-1",
    step_count: 3,
    last_status: "passed",
    created_at: "2026-10-22T15:00:00Z",
    input: { amount: 85.0, card: "tok_visa_4412" },
    expected: {
      status: "success",
      tool_sequence: ["check_geo_ip_anomaly", "calculate_velocity_score", "authorize_payment_intent"],
      final_output: "Transaction authorized.",
      error_conditions: [],
    },
    steps: [
      { step_index: 0, type: "tool_call", name: "check_geo_ip_anomaly", status: "success", duration_ms: 28, output: { is_vpn: false } },
      { step_index: 1, type: "tool_call", name: "calculate_velocity_score", status: "success", duration_ms: 45, output: { risk: "low" } },
      { step_index: 2, type: "tool_call", name: "authorize_payment_intent", status: "success", duration_ms: 82, output: { status: "approved" } },
    ],
  },
];

export const DEMO_TEST_RUNS_P3 = [
  {
    id: 3001,
    test_id: 301,
    project_id: 3,
    test_name: "Clean Consumer Transaction Flow",
    status: "passed",
    duration_ms: 155.5,
    created_at: iso(15),
    disclaimer: "Deterministic simulation with mocked tools.",
    mismatches: [],
    mismatch_count: 0,
    observed: {
      tool_sequence: ["check_geo_ip_anomaly", "calculate_velocity_score", "authorize_payment_intent"],
      final_output: "Transaction authorized.",
      steps: [
        { step_index: 0, name: "check_geo_ip_anomaly", type: "tool_call", duration_ms: 28, status: "success", output: { is_vpn: false } },
        { step_index: 1, name: "calculate_velocity_score", type: "tool_call", duration_ms: 45, status: "success", output: { risk: "low" } },
        { step_index: 2, name: "authorize_payment_intent", type: "tool_call", duration_ms: 82, status: "success", output: { status: "approved" } },
      ],
      findings: [],
    },
  },
];

export const DEMO_CI_RUNS_P3 = [
  {
    id: 301,
    project_id: 3,
    branch: "main",
    commit_sha: "a9103c8b",
    commit_message: "feat: add residential proxy risk weighting",
    actor: "fraud-sec-ops",
    trigger: "push",
    status: "passed",
    total: 10,
    passed: 10,
    failed: 0,
    duration_ms: 4210.0,
    created_at: iso(95),
    report: {
      regression: { counts: { new_failures: 0, fixed_failures: 0 } },
      results: [
        { name: "test_velocity_counter_sliding_window", status: "passed", file: "tests/test_velocity.py", mismatches: [] },
      ],
    },
  },
];

export const DEMO_API_KEYS_P3 = [
  {
    id: 31,
    project_id: 3,
    name: "Payment Gateway Ingestion Hook (Demo)",
    key_prefix: "ar_live_demo_fg_",
    created_at: "2026-10-22T14:35:00Z",
    last_used_at: iso(20),
    is_demo: true,
  },
];

// ===========================================================================
// COMBINED MULTI-TENANT COLLECTIONS
// ===========================================================================

export const DEMO_ALL_EXECUTIONS = [
  ...DEMO_EXECUTIONS_P1,
  ...DEMO_EXECUTIONS_P2,
  ...DEMO_EXECUTIONS_P3,
];

export const DEMO_ALL_TRACES = [
  ...DEMO_TRACES_P1,
  ...DEMO_TRACES_P2,
  ...DEMO_TRACES_P3,
];

export const DEMO_ALL_BASELINES = [
  ...DEMO_BASELINES_P1,
  ...DEMO_BASELINES_P2,
  ...DEMO_BASELINES_P3,
];

export const DEMO_ALL_TESTS = [
  ...DEMO_TESTS_P1,
  ...DEMO_TESTS_P2,
  ...DEMO_TESTS_P3,
];

export const DEMO_ALL_TEST_RUNS = [
  ...DEMO_TEST_RUNS_P1,
  ...DEMO_TEST_RUNS_P2,
  ...DEMO_TEST_RUNS_P3,
];

export const DEMO_ALL_CI_RUNS = [
  ...DEMO_CI_RUNS_P1,
  ...DEMO_CI_RUNS_P2,
  ...DEMO_CI_RUNS_P3,
];

export const DEMO_ALL_API_KEYS = [
  ...DEMO_API_KEYS_P1,
  ...DEMO_API_KEYS_P2,
  ...DEMO_API_KEYS_P3,
];


