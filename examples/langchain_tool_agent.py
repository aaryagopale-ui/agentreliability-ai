"""Example 2: LangChain Tool-Using Pipeline with AgentReliability Tracing.

Demonstrates:
- Wrapping Python functions with `@tool`.
- Tracing tool invocations, inputs, outputs, and exact duration.
- Hierarchical span relationships between parent chains and child tools.
"""
import os
import sys
from pathlib import Path

# Ensure sdk is in python path for local execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk" / "src"))

from agentreliability.integrations.langchain import AgentReliabilityCallbackHandler
from langchain_core.tools import tool
from langchain_core.runnables import RunnableLambda


# 1. Define tools with schema and docstrings
@tool
def lookup_exchange_rate(currency: str) -> float:
    """Look up the real-time currency exchange rate against USD."""
    rates = {"EUR": 1.08, "GBP": 1.27, "JPY": 0.0065, "INR": 0.012}
    return rates.get(currency.upper(), 1.0)


@tool
def calculate_conversion(amount: float, rate: float) -> float:
    """Calculate the converted amount given a rate."""
    return round(amount * rate, 2)


def main():
    api_key = os.environ.get("AGENTRELIABILITY_API_KEY", "ar_live_demo_key_example")
    endpoint = os.environ.get("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001")

    print("🚀 Running LangChain Tool Agent Example...")

    handler = AgentReliabilityCallbackHandler(
        agent_name="currency_converter_agent",
        api_key=api_key,
        endpoint=endpoint,
        capture_io=True,
    )

    # 2. Build a composite runnable pipeline that invokes tools
    def conversion_pipeline_fn(inputs: dict, config: dict) -> dict:
        curr = inputs["currency"]
        amt = inputs["amount"]
        
        # Tool 1: Lookup rate
        rate = lookup_exchange_rate.invoke({"currency": curr}, config=config)
        
        # Tool 2: Compute total
        converted = calculate_conversion.invoke({"amount": amt, "rate": rate}, config=config)
        
        return {
            "source_currency": curr,
            "source_amount": amt,
            "rate": rate,
            "converted_usd": converted,
        }

    pipeline = RunnableLambda(conversion_pipeline_fn).with_config(run_name="conversion_pipeline")

    # 3. Invoke with handler callbacks
    req = {"currency": "EUR", "amount": 250.0}
    print(f"Input: {req}")

    res = pipeline.invoke(req, config={"callbacks": [handler]})
    print(f"Output: {res}")

    # 4. Flush trace events
    handler.flush(timeout=3.0)
    print("✅ LangChain tool execution spans captured and transmitted.")


if __name__ == "__main__":
    main()

