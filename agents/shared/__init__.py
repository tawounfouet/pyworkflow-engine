"""shared — Utilitaires transversaux pour les agents IA (ADR-019).

Re-exports principaux :
  - loader      : load_all_agents, load_agent_by_slug, load_manifest
  - runner      : AgentRunner, AgentRunnerError
  - handoff     : AgentHandoff, HandoffRequest, HandoffResult   (ADR-021 Phase 1)
  - pipeline    : AgentPipeline, AgentStage, AgentPipelineResult (ADR-021 Phase 3)
  - guardrails  : GuardrailChain, Guardrail, GuardrailResult    (ADR-021 Phase 4)
  - configs     : presets (BALANCED, CREATIVE, PRECISE, …)
  - tool_sets   : collections d'outils pré-packagés
"""
