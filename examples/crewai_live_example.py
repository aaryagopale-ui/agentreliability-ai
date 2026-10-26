"""CrewAI Live Multi-Agent Integration Example with AgentReliability AI Tracing.

Demonstrates:
1. Setting up CrewAI event tracing via `agentreliability.integrations.crewai.setup_crewai_tracing`.
2. Initializing 2 authentic CrewAI agents: Database Auditor and Risk Analyst.
3. Defining 2 deterministic local Python tools with `@tool`: `check_database` and `calculate_risk`.
4. Using an in-process local mock LLM client conforming to OpenAI Completion specs (no paid APIs or network calls).
5. Executing the workflow using authentic `crew.kickoff()`.
6. Transmitting the full multi-agent execution hierarchy to AgentReliability AI backend.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure sdk is on path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "sdk" / "src"))

from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from openai.types.completion_usage import CompletionUsage

from crewai.agent.core import Agent
from crewai.crew import Crew
from crewai.events import crewai_event_bus
from crewai.llm import LLM
from crewai.task import Task
from crewai.tools import tool

from agentreliability.integrations.crewai import setup_crewai_tracing


# -----------------------------------------------------------------------------
# 1. Deterministic Local Tools
# -----------------------------------------------------------------------------

tool_execution_counts = {"check_database": 0, "calculate_risk": 0}


@tool("check_database")
def check_database(account_id: str) -> str:
    """Check database records for user account status and balance."""
    tool_execution_counts["check_database"] += 1
    return json.dumps({
        "account_id": account_id,
        "owner": "Alice Developer",
        "status": "verified_active",
        "balance_usd": 12500.0,
        "flagged": False,
    })


@tool("calculate_risk")
def calculate_risk(account_id: str, balance_usd: float = 0.0) -> str:
    """Calculate deterministic risk score and compliance rating for an account."""
    tool_execution_counts["calculate_risk"] += 1
    score = 15 if balance_usd > 10000 else 45
    return json.dumps({
        "account_id": account_id,
        "risk_score": score,
        "rating": "low_risk" if score < 30 else "moderate_risk",
        "approved": True,
    })


# -----------------------------------------------------------------------------
# 2. Local Deterministic LLM Mock Client
# -----------------------------------------------------------------------------

def build_deterministic_llm(tool_name: str, tool_args: dict, final_response: str) -> LLM:
    """Construct a CrewAI LLM backed by a deterministic local completion mock."""
    llm = LLM(model="gpt-4o-mini", api_key="local-mock-key")
    step = 0
    client = MagicMock()

    def mock_create(**kwargs: Any) -> Any:
        nonlocal step
        step += 1

        # Step 1: Agent decides to invoke its assigned tool
        if step == 1:
            tool_call = ChatCompletionMessageToolCall(
                id=f"call_{tool_name}_{step}",
                type="function",
                function=Function(name=tool_name, arguments=json.dumps(tool_args)),
            )
            msg = ChatCompletionMessage(role="assistant", content=None, tool_calls=[tool_call])
        # Step 2: Agent receives tool output and produces final summary
        else:
            msg = ChatCompletionMessage(role="assistant", content=final_response)

        choice = Choice(finish_reason="stop", index=0, message=msg)
        usage = CompletionUsage(completion_tokens=25, prompt_tokens=35, total_tokens=60)
        chat_comp = ChatCompletion(
            id=f"comp_{tool_name}_{step}",
            choices=[choice],
            created=1700000000,
            model="gpt-4o-mini",
            object="chat.completion",
            usage=usage,
        )

        resp = MagicMock()
        resp.parse.return_value = chat_comp
        resp.text = json.dumps(chat_comp.model_dump())
        resp.http_response = MagicMock(status_code=200)
        return resp

    client.chat.completions.with_raw_response.create.side_effect = mock_create
    llm._client = client
    llm._get_sync_client = lambda: client
    return llm


# -----------------------------------------------------------------------------
# 3. Execution Runner
# -----------------------------------------------------------------------------

def run_crewai_live_workflow(
    endpoint: str = "http://127.0.0.1:8001",
    api_key: str | None = None,
    crew_name: str = "crewai_financial_audit_crew",
) -> dict[str, Any]:
    print("=" * 70)
    print("🚀 Starting Live Genuine CrewAI Execution with AgentReliability Tracing")
    print("=" * 70)

    resolved_api_key = api_key or os.environ.get("AGENTRELIABILITY_API_KEY")
    if not resolved_api_key:
        print("❌ Error: AGENTRELIABILITY_API_KEY environment variable is missing.", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Target Endpoint : {endpoint}")
    print(f"✓ API Key prefix  : {resolved_api_key[:12]}...")
    print(f"✓ Crew Name       : {crew_name}")

    # Step 1: Hook AgentReliability event listener to CrewAI event bus
    listener = setup_crewai_tracing(
        agent_name=crew_name,
        endpoint=endpoint,
        api_key=resolved_api_key,
        capture_io=True,
        metadata={"environment": "local_verification", "engine": "crewai-v1.15"},
    )
    print("✓ AgentReliabilityCrewListener registered with CrewAI event bus.")

    # Step 2: Initialize LLMs for each agent
    auditor_llm = build_deterministic_llm(
        tool_name="check_database",
        tool_args={"account_id": "ACC-AUDIT-901"},
        final_response="Database audit confirmed: Account ACC-AUDIT-901 is verified active with $12,500 balance.",
    )
    analyst_llm = build_deterministic_llm(
        tool_name="calculate_risk",
        tool_args={"account_id": "ACC-AUDIT-901", "balance_usd": 12500.0},
        final_response="Risk analysis complete: ACC-AUDIT-901 evaluated at low risk (score 15). Audit approved.",
    )

    # Step 3: Define 2 distinct CrewAI Agents
    database_auditor = Agent(
        role="Database Auditor",
        goal="Verify account status and ledger records in database",
        backstory="Senior internal auditor verifying account validity.",
        llm=auditor_llm,
        tools=[check_database],
        verbose=False,
    )

    risk_analyst = Agent(
        role="Risk Analyst",
        goal="Assess solvency and calculate compliance risk score",
        backstory="Quantitative financial risk analyst assessing ledger health.",
        llm=analyst_llm,
        tools=[calculate_risk],
        verbose=False,
    )

    # Step 4: Define sequential CrewAI Tasks
    task_audit = Task(
        description="Verify account status for ACC-AUDIT-901 using check_database tool.",
        expected_output="Account ledger verification summary.",
        agent=database_auditor,
    )

    task_risk = Task(
        description="Calculate risk score for ACC-AUDIT-901 using calculate_risk tool based on audit findings.",
        expected_output="Final risk score and compliance certification.",
        agent=risk_analyst,
    )

    # Step 5: Assemble Crew and run genuine kickoff
    crew = Crew(
        agents=[database_auditor, risk_analyst],
        tasks=[task_audit, task_risk],
        verbose=False,
    )

    print("\nExecuting crew.kickoff()...")
    crew_output = crew.kickoff()
    print("✓ crew.kickoff() finished successfully!")
    print(f"  Result Output: {crew_output.raw if hasattr(crew_output, 'raw') else crew_output}")

    # Step 6: Flush CrewAI event bus and AgentReliability transport
    crewai_event_bus.flush(timeout=3.0)
    listener.flush(timeout=3.0)

    exec_id = listener.execution_id
    print(f"\n✅ Telemetry transmitted to AgentReliability backend.")
    print(f"   Captured Execution ID: {exec_id}")
    print(f"   Tool Executions: check_database={tool_execution_counts['check_database']}, calculate_risk={tool_execution_counts['calculate_risk']}")

    return {
        "status": "success",
        "execution_id": exec_id,
        "tool_counts": tool_execution_counts,
        "output": str(crew_output),
    }


if __name__ == "__main__":
    ep = os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001")
    key = os.environ.get("AGENTRELIABILITY_API_KEY")
    run_crewai_live_workflow(endpoint=ep, api_key=key)
