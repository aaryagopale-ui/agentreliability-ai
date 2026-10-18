# Demo Project: Agent Automated Regression Testing

This directory contains an example AI agent project with deterministic regression tests that run in local CLI and GitHub Actions workflows.

## Directory Structure
- `agent-tests/test_pass.json`: A passing agent test case with expected tool responses.
- `agent-tests/test_fail.json`: A failing regression test case (mock tool fails with HTTP 500).
- `agent-tests/baseline.json`: Baseline test results against which regression analysis is performed.
- `app.py`: Demo support agent implementation.

## How to Run Tests Locally

From project root:
```bash
# 1. Install SDK in editable mode
pip install -e ./sdk

# 2. Run only passing tests
agentreliability test --project ./demo_project/agent-tests/test_pass.json

# 3. Run all tests with baseline regression comparison
agentreliability test \
  --project ./demo_project/agent-tests \
  --output ./test-results/results.json \
  --baseline ./demo_project/agent-tests/baseline.json
```

Notice:
- Exit code is `0` when all tests pass.
- Exit code is `1` when failures or regressions are detected.

## Upload Results to AgentReliability Dashboard
To send test results to your local AgentReliability backend:
```bash
export AGENTRELIABILITY_ENDPOINT="http://localhost:8000"
export AGENTRELIABILITY_API_KEY="ar_YOUR_KEY"

agentreliability test \
  --project ./demo_project/agent-tests \
  --output ./test-results/results.json \
  --upload
```
View results under the **CI/CD Testing** tab in the web dashboard!

