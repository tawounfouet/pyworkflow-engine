"""
adapters/ai — adaptateurs du sous-système IA (ADR-016 Phase 4).

Ce package regroupe :
  - ``llm/``     : clients LLM concrets (OpenAI, Anthropic, Gemini, Groq, Ollama)
  - ``tools/``   : tools concrets (calculator, http_client, web_search, executor)
  - ``skills/``  : skills concrets + registry
  - ``storage/`` : backends de persistence IA (InMemory, SQLite)
"""
