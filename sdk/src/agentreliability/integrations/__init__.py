"""Framework integrations for AgentReliability AI SDK.

Provides optional callbacks and connectors for popular agent frameworks:
- CrewAI (`agentreliability.integrations.crewai`)
- LangChain (`agentreliability.integrations.langchain`)
- LangGraph (`agentreliability.integrations.langgraph`)
"""
from __future__ import annotations

# Safe CrewAI exports
try:
    from . import crewai
    from .crewai import (
        CREWAI_AVAILABLE,
        AgentReliabilityCrewListener,
        setup_crewai_tracing,
    )
except ImportError:
    crewai = None  # type: ignore[assignment]
    CREWAI_AVAILABLE = False
    AgentReliabilityCrewListener = None  # type: ignore[misc,assignment]
    setup_crewai_tracing = None  # type: ignore[assignment]

# Safe LangChain exports
try:
    from . import langchain
    from .langchain import AgentReliabilityCallbackHandler
except ImportError:
    langchain = None  # type: ignore[assignment]
    AgentReliabilityCallbackHandler = None  # type: ignore[misc,assignment]

# Safe LangGraph exports
try:
    from . import langgraph
    from .langgraph import AgentReliabilityGraphHandler
except ImportError:
    langgraph = None  # type: ignore[assignment]
    AgentReliabilityGraphHandler = None  # type: ignore[misc,assignment]

__all__ = [
    # Submodules
    "crewai",
    "langchain",
    "langgraph",
    # CrewAI
    "CREWAI_AVAILABLE",
    "AgentReliabilityCrewListener",
    "setup_crewai_tracing",
    # LangChain / LangGraph
    "AgentReliabilityCallbackHandler",
    "AgentReliabilityGraphHandler",
]

