# ADR-001 — Décision de nommage du package

> **Date :** 10 avril 2026  
> **Statut :** ✅ Décision prise — statu quo conservé  
> **Type :** Architecture Decision Record (ADR)

---

## Contexte

Lors de la revue post-migration (`ias_workflow_engine` → `pyworkflow_engine` v0.2.0), deux alternatives de renommage ont été évaluées :

1. **`workflow_engine`** — retirer le préfixe `py`
2. **`pyworkflow`** — retirer le suffixe `engine`

L'objectif déclaré était de réduire la verbosité à l'import et de supprimer la "redondance" avec le fait que le package est déjà implicitement un moteur.

---

## Alternatives analysées

### Option A — `workflow_engine`

```python
from workflow_engine import WorkflowEngine
```

| Critère | Évaluation |
|---------|-----------|
| Unicité PyPI | ❌ Nom générique — collision probable |
| Convention communauté | ⚠️ Hors convention (le préfixe `py` est établi : pytest, pydantic, pymongo…) |
| Lisibilité import | ⚠️ Ambigu — quel `workflow_engine` parmi d'éventuels homonymes ? |
| Cohérence repo/package | ⚠️ `pyworkflow-engine` (repo) / `workflow_engine` (package) — incohérence |

**Verdict : rejeté.**

---

### Option B — `pyworkflow`

```python
from pyworkflow import WorkflowEngine
```

| Critère | Évaluation |
|---------|-----------|
| Unicité PyPI | ❌ **Pris** — `pyworkflow` est un package actif (GUI workflow pour Scipion) |
| Risque de confusion | 🔴 Import identique à un package existant et maintenu |
| Cohérence repo/package | ⚠️ `pyworkflow-engine` (repo) / `pyworkflow` (package) — suffixe perdu |

**Verdict : rejeté.**

---

### Option C (retenue) — `pyworkflow_engine` (statu quo)

```python
from pyworkflow_engine import WorkflowEngine
```

| Critère | Évaluation |
|---------|-----------|
| Unicité PyPI | ✅ Nom disponible et distinctif |
| Convention communauté | ✅ Préfixe `py` respecté |
| Lisibilité import | ✅ Non ambigu, auto-documenté |
| Cohérence repo/package | ✅ `pyworkflow-engine` / `pyworkflow_engine` — mapping direct |
| Coût migration | ✅ Nul — évite une 3ème migration (v0.1 → v0.2 venait de se terminer) |

**Verdict : retenu.**

---

## Décision

**Le nom `pyworkflow_engine` est conservé.**

La verbosité perçue à l'import est adressée par la **convention d'alias**, pratique standard dans l'écosystème Python (`numpy as np`, `pandas as pd`, `sqlalchemy as sa`) :

```python
import pyworkflow_engine as pwf

engine = pwf.WorkflowEngine()
job    = pwf.Job(name="ETL", steps=[...])
step   = pwf.Step(name="fetch", callable=fetch_data)
```

Cette approche offre la concision souhaitée **sans risque de collision** ni coût de migration.

---

## Conséquences

- Aucune modification du code source, des imports, ou de la configuration.
- Le `README.md` peut mentionner l'alias `pwf` comme convention recommandée pour les projets utilisant intensivement le package.
- La règle est documentée ici pour éviter de rouvrir le débat lors de futures revues.
