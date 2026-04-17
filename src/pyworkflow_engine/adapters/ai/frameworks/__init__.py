"""
adapters/ai/frameworks — Runtimes agents optionnels.

Chaque module encapsule un framework agent tiers derrière le port
``BaseAgentRuntime`` (ports/ai/runtime.py).

Modules disponibles :
  - ``native``         — wrap de ``AgentRunner`` existant (aucune dep)
  - ``openai_agents``  — OpenAI Agents SDK (pip install openai-agents)
  - ``langgraph``      — LangGraph StateGraph (pip install langgraph)
  - ``autogen``        — AutoGen GroupChat (pip install autogen-agentchat)
  - ``factory``        — Factory ``get_agent_runtime()``

Architecture : ADR-022 (framework adapter integration patterns)
"""
