# Order Processing Agent — MVP Validation Suite

This directory contains a sample agent application and automated tests designed to validate the **AgentReliability AI** developer experience and core platform capabilities:

1. **`order_agent.py`**: An independent, realistic Python agent that implements an e-commerce order fulfillment workflow:
   - Verifies customer credentials (tests secret redaction of tokens and API keys).
   - Checks inventory stock.
   - Retrieves physical warehouse locations (nested tool call inside inventory check).
   - Calculates pricing, taxes, and discounts.
   - Generates an order confirmation.

2. **`test_mvp_scenarios.py`**: Automated end-to-end test exercising:
   - **Scenario A (Success):** All tools succeed; checks nested tool hierarchy and client-side secret redaction.
   - **Scenario B (Controlled Tool Failure):** Inventory service fails with `InventoryUnavailableError`; asserts exception recording and failure classification.
   - **Scenario C (Behavioral Regression):** Warehouse lookup is skipped and confirmation output schema is altered.

---

## How to Run Locally

### 1. Ensure Backend is Running
The AgentReliability backend must be active on port `8001`:
```bash
PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --port 8001 --host 127.0.0.1
```

### 2. Run the MVP Validation Script
```bash
backend/.venv/bin/python examples/mvp_validation/test_mvp_scenarios.py
```

### 3. Run the Agent Standalone
```bash
export AGENTRELIABILITY_ENDPOINT="http://127.0.0.1:8001"
export AGENTRELIABILITY_API_KEY="<your-project-api-key>"
export AGENTRELIABILITY_CAPTURE_IO="1"

backend/.venv/bin/python examples/mvp_validation/order_agent.py
```

---

## Verified Capabilities

- **Zero-Crash Monitoring:** Ingestion errors never break the agent.
- **Client-Side Redaction:** Sensitive auth tokens and keys are sanitized to `[REDACTED]` before leaving memory.
- **Hierarchy Awareness:** Nested tool calls automatically track `parent_call_id`.
- **Database Persistence:** Executions, tool spans, errors, and metadata are cleanly stored in SQLite.
- **Multi-Tenant Scoping:** All traces strictly attach to the authorized project.

