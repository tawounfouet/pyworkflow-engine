# agents/ — Catalogue d'agents IA concrets

> Instances déclaratives du modèle `Agent`, organisées par rôle (`AgentRole`).
> Miroir du pattern `jobs/` et `pipelines/` pour la couche IA (ADR-019).

## Structure

```
agents/
├── __init__.py
├── README.md               ← ce fichier
├── manifest.yaml           ← Registre déclaratif des agents
│
├── assistants/             # AgentRole.ASSISTANT
│   └── general_assistant.py
├── researchers/            # AgentRole.RESEARCHER
│   └── doc_researcher.py
├── coders/                 # AgentRole.CODER
│   └── code_reviewer.py
├── analysts/               # AgentRole.ANALYST
│   └── data_analyst.py
├── orchestrators/          # AgentRole.ORCHESTRATOR
│   └── pipeline_planner.py
│
├── _template/              # Template copier-coller
│   └── agent_example.py
│
└── shared/                 # Utilitaires transversaux
    ├── configs.py          # Presets AgentConfig (CREATIVE, PRECISE, BALANCED…)
    ├── loader.py           # Chargement dynamique depuis le manifest
    ├── runner.py           # Exécution réelle d'un agent (LLM)
    ├── prompts/
    │   └── base_prompts.py # Fragments de system prompts composables
    └── tool_sets.py        # Groupes de tool_ids courants
```

## Convention de nommage

| Élément          | Pattern                        | Exemple                    |
|-----------------|--------------------------------|----------------------------|
| Fichier agent   | `{nom_descriptif}.py`          | `general_assistant.py`     |
| Variable agent  | `{nom_descriptif}` (snake_case)| `general_assistant`        |
| Slug agent      | `{nom-descriptif}` (kebab-case)| `general-assistant`        |
| Dossier rôle    | `{role_pluriel}/`              | `assistants/`, `coders/`   |

## Créer un nouvel agent

1. Copier `_template/agent_example.py` dans le dossier correspondant au rôle
2. Remplacer les TODO
3. Ajouter l'entrée dans `manifest.yaml`
4. (Optionnel) Réutiliser les presets de `shared/configs.py` et `shared/prompts/`

## Utilisation

### Import direct

```python
from agents.assistants.general_assistant import general_assistant

# L'agent est une instance Agent prête à l'emploi
print(general_assistant.name)       # "General Assistant"
print(general_assistant.slug)       # "general-assistant"
print(general_assistant.role)       # AgentRole.ASSISTANT
```

### Avec le manifest

```python
import yaml
import importlib

with open("agents/manifest.yaml") as f:
    catalog = yaml.safe_load(f)

for entry in catalog["agents"]:
    module = importlib.import_module(entry["module"])
    agent = getattr(module, entry["attr"])
    print(f"{agent.slug} ({agent.role})")
```

### Exécution réelle (AgentRunner)

Le `AgentRunner` connecte un agent du catalogue à un vrai LLM (OpenAI, Anthropic, etc.) :

```python
from agents.assistants.general_assistant import general_assistant
from agents.shared.runner import AgentRunner

# One-shot
runner = AgentRunner(general_assistant)           # utilise OPENAI_API_KEY
response = runner.ask("Explique le pattern hexagonal.")
print(response.content)                           # réponse LLM
print(response.usage.total_tokens)                # métriques

# Conversation multi-turn (le contexte est maintenu)
runner.ask("Donne un exemple concret.")
runner.ask("Et les inconvénients ?")

# Override du modèle ou de la température
runner = AgentRunner(general_assistant, model="gpt-4o-mini")
runner.ask("Bonjour", temperature=0.2)

# Session interactive (REPL)
runner.repl()
```

Prérequis :
```bash
pip install openai                    # ou: pip install pyworkflow-engine[ai]
export OPENAI_API_KEY=sk-...          # ou dans .env
```

### CLI

```bash
# Lister les agents
pyworkflow agent list
pyworkflow agent list --role coder

# Inspecter un agent
pyworkflow agent inspect general-assistant

# One-shot (une question → une réponse)
pyworkflow agent run general-assistant "Résume le concept de l'architecture hexagonale" -v
pyworkflow agent run code-reviewer "Review: def add(a,b): return a+b" --model gpt-4o-mini

# Chat interactif (REPL)
pyworkflow agent chat general-assistant -v
pyworkflow agent chat code-reviewer --model gpt-4o-mini
```

## Liens

- **ADR-019** — [`docs/changelog/2026-04-12_adr_019_agents-catalog-directory.md`](../docs/changelog/2026-04-12_adr_019_agents-catalog-directory.md)
- **Modèle Agent** — [`src/pyworkflow_engine/models/ai/agent.py`](../src/pyworkflow_engine/models/ai/agent.py)
- **Types IA** — [`src/pyworkflow_engine/models/ai/types.py`](../src/pyworkflow_engine/models/ai/types.py)
- **Jobs (même pattern)** — [`jobs/README.md`](../jobs/README.md)
- **Pipelines (même pattern)** — [`pipelines/README.md`](../pipelines/README.md)
