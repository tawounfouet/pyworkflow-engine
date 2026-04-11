# Journal des décisions architecturales

Ce dossier contient les **Architecture Decision Records (ADR)** du projet `pyworkflow-engine`.  
Chaque ADR documente une décision architecturale significative : son contexte, les alternatives considérées, et la décision retenue.

---

## Format des fichiers

```
YYYY-MM-DD-<slug>.md
```

---

## Index

| Fichier | Titre | Date | Statut |
|---------|-------|------|--------|
| [2026-04-10-naming-decision.md](./2026-04-10-naming-decision.md) | ADR-001 — Décision de nommage du package | 10 avril 2026 | ✅ Décision prise |
| [2026-04-10-architecture-refactoring-proposal.md](./2026-04-10-architecture-refactoring-proposal.md) | ADR-002 — Refactoring architectural : `core/` monolithique → couches modulaires | 10 avril 2026 | 🔵 Proposition |
| [2026-04-10-architecture-critique-integration.md](./2026-04-10-architecture-critique-integration.md) | ADR-003 — Intégration de l'analyse critique dans le plan de refactoring | 10 avril 2026 | 🔵 Proposition |
| [2026-04-10-action-plan-v030.md](./2026-04-10-action-plan-v030.md) | Plan d'action v0.3.0 — 5 sprints de stabilisation et refactoring | 10 avril 2026 | 🚧 En cours |
| [2026-04-11-import-style-and-config-module.md](./2026-04-11-import-style-and-config-module.md) | ADR-004 — Style d'imports absolus et introduction du module `config/` | 11 avril 2026 | ✅ Décision prise |
| [2026-04-11-decorator-api.md](./2026-04-11-decorator-api.md) | ADR-005 — API déclarative par décorateurs (`@step`, `@job`) | 11 avril 2026 | ✅ Implémentée (v0.5.0) |
| [2026-04-11-hexagonal-ports-adapters.md](./2026-04-11-hexagonal-ports-adapters.md) | ADR-006 — Architecture hexagonale : introduction `ports/` et réorganisation `adapters/` | 11 avril 2026 | 🔵 Proposition |

---

## Statuts possibles

| Statut | Signification |
|--------|--------------|
| 🔵 Proposition | En discussion, pas encore validée |
| ✅ Décision prise | Validée, applicable immédiatement |
| 🚧 En cours | Implémentation en cours |
| ✅ Implémentée | Entièrement réalisée |
| ❌ Rejetée | Évaluée et rejetée, avec justification |
| 🔄 Remplacée | Supersédée par une ADR plus récente |
