# Journal des décisions architecturales

Ce dossier contient les **Architecture Decision Records (ADR)** du projet `pyworkflow-engine`.  
Chaque ADR documente une décision architecturale significative : son contexte, les alternatives considérées, et la décision retenue.

---

## Format des fichiers

```
YYYY-MM-DD_adr_NNN_<slug>.md
```

---

## Index

| Fichier | Titre | Date | Statut |
|---------|-------|------|--------|
| [2026-04-10_adr-001_naming-decision.md](./2026-04-10_adr-001_naming-decision.md) | ADR-001 — Décision de nommage du package | 10 avril 2026 | ✅ Décision prise |
| [2026-04-10_adr_002_architecture-refactoring-proposal.md](./2026-04-10_adr_002_architecture-refactoring-proposal.md) | ADR-002 — Refactoring architectural : `core/` monolithique → couches modulaires | 10 avril 2026 | ✅ Implémentée (v0.3.0) |
| [2026-04-10_adr_003_architecture-critique-integration.md](./2026-04-10_adr_003_architecture-critique-integration.md) | ADR-003 — Intégration de l'analyse critique dans le plan de refactoring | 10 avril 2026 | ✅ Implémentée (v0.3.0) |
| [2026-04-10-action-plan-v030.md](../guides/2026-04-10-action-plan-v030.md) | Plan d'action v0.3.0 — 5 sprints de stabilisation et refactoring | 10 avril 2026 | ✅ Terminé |
| [2026-04-11_adr_004_import-style-and-config-module.md](./2026-04-11_adr_004_import-style-and-config-module.md) | ADR-004 — Style d'imports absolus et introduction du module `config/` | 11 avril 2026 | ✅ Décision prise |
| [2026-04-11_adr_005_decorator-api.md](./2026-04-11_adr_005_decorator-api.md) | ADR-005 — API déclarative par décorateurs (`@step`, `@job`) | 11 avril 2026 | ✅ Implémentée (v0.5.0) |
| [2026-04-11_adr_006_hexagonal-ports-adapters.md](./2026-04-11_adr_006_hexagonal-ports-adapters.md) | ADR-006 — Architecture hexagonale : introduction `ports/` et réorganisation `adapters/` | 11 avril 2026 | ✅ Implémentée (v0.6.0) |
| [2026-04-11_adr_007_celery-adapter-integration.md](./2026-04-11_adr_007_celery-adapter-integration.md) | ADR-007 — Intégration Celery : adapter complexe vs simple executor | 11 avril 2026 | ✅ Décision prise |
| [2026-04-11_adr_008_cli-adapter-typer-rich.md](./2026-04-11_adr_008_cli-adapter-typer-rich.md) | ADR-008 — CLI Adapter : Typer + Rich dans `adapters/cli/` | 11 avril 2026 | ✅ Décision prise |
| [2026-04-11_adr_009_tui-adapter-textual-rich.md](./2026-04-11_adr_009_tui-adapter-textual-rich.md) | ADR-009 — TUI Adapter : Textual + Rich dans `adapters/tui/` | 11 avril 2026 | ✅ Décision prise |
| [2026-04-11_adr_010_gui-adapter-nicegui.md](./2026-04-11_adr_010_gui-adapter-nicegui.md) | ADR-010 — GUI Adapter : NiceGUI dans `adapters/gui/` | 11 avril 2026 | ✅ Décision prise |
| [2026-04-11_adr_011_api-adapter-fastapi-sqlite.md](./2026-04-11_adr_011_api-adapter-fastapi-sqlite.md) | ADR-011 — API Adapter : FastAPI + SQLite dans `adapters/api/` | 11 avril 2026 | ✅ Décision prise |
| [2026-04-12_adr_012_rename-persistence-to-storage.md](./2026-04-12_adr_012_rename-persistence-to-storage.md) | ADR-012 — Renommage `persistence` → `storage` dans tout le codebase | 12 avril 2026 | ✅ Décision prise |

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
