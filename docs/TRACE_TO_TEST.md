# 🔄 Trace-to-Test Regression Workflow

Testing non-deterministic AI agents is difficult because agents interact with external tools, APIs, and models that change over time.

The **Trace-to-Test** workflow solves this by recording actual production agent executions and converting them into **deterministic, reproducible regression tests** in one click.

---

## 🎯 How Trace-to-Test Works

```
+---------------------+      Capture Trace      +------------------------+
| Real Python Agent   | ──────────────────────> | Captured Trace Record  |
| Execution in Prod   |                         | - Tool Call Sequence   |
+---------------------+                         | - Step Latency & I/O   |
                                                +-----------+------------+
                                                            |
                                                 1-Click    | Convert
                                                            v
+---------------------+      Zero-Cost Replay   +------------------------+
| Test History &      | <────────────────────── | Immutable Test Case    |
| Regression Diffing  |                         | - Sequence Assertions  |
+---------------------+                         | - Schema Assertions    |
                                                +------------------------+
```

---

## 1. Anatomy of a Generated Test Case

When you click **"Convert to Test Case"** on a trace, AgentReliability creates a test specification:

```json
{
  "name": "Order Fulfillment Flow",
  "description": "Auto-generated from trace order-exec-demo-101",
  "agent_name": "order_fulfillment_agent",
  "steps": [
    {
      "type": "tool_call",
      "name": "verify_client_credentials",
      "status": "success",
      "duration_ms": 14.5,
      "output": {"authenticated": true}
    },
    {
      "type": "tool_call",
      "name": "check_inventory",
      "status": "success",
      "duration_ms": 22.0,
      "output": {"available": true, "stock": 42}
    }
  ],
  "expected": {
    "status": "success",
    "tool_sequence": ["verify_client_credentials", "check_inventory"],
    "strict_order": true,
    "allow_additional_tools": false,
    "final_output": {"available": true, "stock": 42},
    "expected_output_fields": ["available", "stock"],
    "max_duration_ms": 100
  }
}
```

---

## 2. Deterministic Replay Engine

When a test is replayed:
1. **Zero External API Costs**: No paid LLMs or third-party APIs are called.
2. **`MockToolRegistry`**: Tool requests are answered using the recorded responses from the test case.
3. **Pure Determinism**: Replaying the test 100 times produces identical results every time.

---

## 3. Detected Regression Categories

When code changes introduce bugs or altered behavior, the replay engine flags the exact discrepancy:

| Category | Trigger | Example |
| :--- | :--- | :--- |
| `sequence_mismatch` | Tools called out of order | Expected `[auth, check, charge]`, observed `[auth, charge]` |
| `missing_expected_tool` | Required tool omitted | Tool `calculate_tax` was skipped |
| `unexpected_tool_call` | Unapproved extra tool executed | Unexpected tool `dangerous_delete` called |
| `output_mismatch` | Return schema differs | Missing required field `"order_id"` |
| `duration_regression` | Tool latency spike | Step took 1,500ms (max expected: 500ms) |
| `unexpected_exception` | Unhandled error thrown | Agent threw `KeyError: 'user_id'` |

---

## 4. Establishing Golden Baselines

You can designate any verified test run as a **Golden Baseline**:
1. Open **Regression Testing** in the dashboard.
2. Click **Create Baseline** and select your candidate trace.
3. When subsequent traces are captured, compare candidate runs directly against the baseline to review unified diffs of:
   - Tool call sequence diffs
   - Execution duration delta percentage
   - Payload changes

