"""Example 1: Basic LangChain Chain with AgentReliability Tracing.

Demonstrates:
- Connecting AgentReliabilityCallbackHandler to a LangChain LCEL pipeline.
- Using a deterministic fake LLM (no external API keys or network required).
- Capturing chain start, intermediate runnable steps, LLM calls, and execution finish.
"""
import os
import sys
from pathlib import Path

# Ensure sdk is in python path for local execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk" / "src"))

from agentreliability.integrations.langchain import AgentReliabilityCallbackHandler
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


def main():
    api_key = os.environ.get("AGENTRELIABILITY_API_KEY", "ar_live_demo_key_example")
    endpoint = os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001")

    print("🚀 Running LangChain Basic Chain Example...")

    # 1. Initialize the AgentReliability Callback Handler
    handler = AgentReliabilityCallbackHandler(
        agent_name="customer_faq_agent",
        api_key=api_key,
        endpoint=endpoint,
        capture_io=True,
        metadata={"environment": "example", "version": "1.0.0"},
    )

    # 2. Build a standard LangChain Expression Language (LCEL) chain
    prompt = ChatPromptTemplate.from_template("Answer the customer query: {query}")
    fake_llm = FakeListChatModel(
        responses=["To reset your password, visit Settings -> Security -> Reset Password."]
    )
    parser = StrOutputParser()

    chain = (prompt | fake_llm | parser).with_config(run_name="faq_pipeline")

    # 3. Execute the chain with callbacks attached
    query = "How do I reset my password?"
    print(f"Input Query: {query}")

    result = chain.invoke({"query": query}, config={"callbacks": [handler]})
    print(f"Agent Output: {result}")

    # 4. Flush traces to AgentReliability AI backend
    handler.flush(timeout=3.0)
    print("✅ LangChain execution traced successfully and flushed to AgentReliability AI.")


if __name__ == "__main__":
    main()

