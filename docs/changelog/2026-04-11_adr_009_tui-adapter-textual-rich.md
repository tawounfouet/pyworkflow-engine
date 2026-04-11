# ADR-009 — TUI Adapter : Textual + Rich dans `adapters/tui/`

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-009                             |
| **Date**    | 11 avril 2026                       |
| **Statut**  | ✅ Décision prise                   |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (architecture hexagonale), ADR-007 (adapter complexe vs simple), ADR-008 (CLI adapter Typer + Rich) |
| **Version cible** | v0.9.0                         |

---

## Contexte

### Situation actuelle

La CLI (ADR-008) est implémentée et fonctionnelle dans `adapters/cli/`. Elle couvre les cas d'usage **non-interactifs** : scriptabilité, CI/CD, pipes Unix, one-shot commands. Le placeholder `adapters/tui/` existe avec un `__init__.py` vide.

Le `pyproject.toml` ne déclare pas encore d'extra `tui`. Le dossier `adapters/tui/` est prévu dans l'arborescence hexagonale (ADR-006) mais n'est pas spécifié.

### Le besoin

La CLI est excellente pour l'automatisation, mais inadaptée à la **supervision interactive en temps réel**. Les scénarios non couverts :

| Scénario | CLI (ADR-008) | Besoin TUI |
|---|---|---|
| Suivre un run en cours (logs en streaming, progression des steps) | ❌ `run status` = snapshot unique | ✅ Live refresh |
| Naviguer entre jobs et runs sans retaper de commandes | ❌ Chaque vue = commande séparée | ✅ Navigation clavier fluide |
| Inspecter un DAG de manière interactive (expand/collapse) | ⚠️ Rich Tree statique | ✅ Tree widget interactif |
| Vue d'ensemble instantanée (dashboard) | ❌ Pas de vue agrégée | ✅ Dashboard avec panels |
| Actions rapides (lancer, annuler, reprendre) en contexte | ❌ Copier-coller les IDs | ✅ `Enter` / `r` / `c` sur la sélection |
| Supervision via SSH sur un serveur distant | ✅ Fonctionne | ✅ Fonctionne nativement |
| Supervision sans déployer d'infrastructure web | ❌ (pas de web UI) | ✅ Zéro infra |

### La question

1. Quel framework TUI choisir pour Python en 2026 ?
2. Comment structurer l'adapter TUI dans l'architecture hexagonale ?
3. Comment la TUI s'articule-t-elle avec la CLI existante ?
4. Quelle granularité de screens/widgets pour la Phase 1 ?
5. Peut-on réutiliser les formatters Rich de la CLI ?

---

## Analyse

### Comparaison des frameworks TUI Python

| Critère | `curses` (stdlib) | `urwid` | `prompt_toolkit` | **`textual`** |
|---|---|---|---|---|
| Widgets riches (DataTable, Tree, Tabs) | ❌ Manuel | ⚠️ Basiques | ⚠️ Orienté prompt | ✅ **Prêts à l'emploi** |
| Layout system | ❌ Coordonnées manuelles | ⚠️ Pile/Columns | ⚠️ Limité | ✅ **CSS-like (grid, dock, fr)** |
| Async natif | ❌ | ❌ | ✅ | ✅ **asyncio first** |
| Réactivité (events / messages) | ❌ Boucle manuelle | ⚠️ Signals basiques | ⚠️ | ✅ **Message-based, reactive attributes** |
| Rich integration | ❌ | ❌ | ⚠️ | ✅ **Natif (même auteur — Will McGuinness)** |
| Testabilité | ❌ Très difficile | ⚠️ | ⚠️ | ✅ **Framework `pilot` dédié** |
| Theming / CSS | ❌ | ❌ | ❌ | ✅ **TCSS (Textual CSS)** |
| Mode web (remote browser) | ❌ | ❌ | ❌ | ✅ **`textual serve` — sans modif de code** |
| Maturité 2026 | Stable mais archaïque | Stable mais niche | Stable | ✅ **Actif, v1.x, >25k ★ GitHub** |
| Courbe d'apprentissage | Haute (bas niveau) | Moyenne | Moyenne | ✅ **Faible (API déclarative)** |

#### Verdict : Textual

Textual est le seul framework offrant simultanément :
- Des **widgets prêts à l'emploi** (`DataTable`, `Tree`, `RichLog`, `Header`, `Footer`, `Tabs`)
- Un **layout CSS** (`grid`, `dock`, unités fractionnelles `fr`)
- L'**async natif** (crucial pour le live refresh des runs)
- L'intégration **Rich native** (même écosystème que la CLI)
- Un **framework de test** dédié (`pilot`)
- Le mode **`textual serve`** (supervision à distance via navigateur, sans API REST)

### Synergie Rich + Textual — réutilisation des acquis CLI

Rich (déjà utilisé par la CLI) et Textual partagent le même auteur et le même système de rendu. Les acquis de la CLI sont partiellement réutilisables :

| Élément CLI | Réutilisable en TUI ? | Stratégie |
|---|---|---|
| `_STATUS_STYLE` (dict statut → style Rich) | ✅ Directement | Import partagé |
| `_fmt_dt()`, `_fmt_ms()` (formatage dates/durées) | ✅ Directement | Import partagé |
| `_default()` (sérialiseur JSON fallback) | ✅ Directement | Import partagé |
| `render_job_table()` → Rich Table | ⚠️ **Non** — Rich Table ≠ Textual DataTable | La logique d'extraction de données est réutilisable, le rendu Rich Table non |
| `render_job_tree()` → Rich Tree | ⚠️ **Non** — Rich Tree ≠ Textual Tree widget | Même principe : données oui, rendu non |
| `jobs_to_json()` / `run_to_json()` | ✅ Directement | Pour export JSON depuis la TUI |
| `error_handler` decorator | ❌ Non — la TUI gère les erreurs via `notify()` | Pattern différent |
| `load_engine()` | ✅ Directement | Le loader est indépendant de l'interface |

**Recommandation** : extraire les **transformations de données communes** (modèles → dicts/strings) dans un module partagé `adapters/_shared/transforms.py` à terme. En Phase 1, la TUI importe directement depuis `adapters/cli/formatters/` pour les utilitaires purs.

### Adapter simple vs complexe (règle ADR-007)

| Critère ADR-007 | Évaluation pour la TUI |
|---|---|
| 2+ fichiers coordonnés | ✅ app + screens + widgets + styles + events |
| Dépendance tierce avec configuration propre | ✅ Textual (TCSS, bindings, screen stack) |
| Concepts spécifiques au-delà du port | ✅ Screens, widgets, keybindings, CSS, Textual messages |

→ La TUI est un **adapter complexe** → `adapters/tui/` (package dédié), conformément à ADR-007.

### Architecture Textual : App → Screens → Widgets

```
┌──────────────────────────────────────────────────────────┐
│               WorkflowTUI (App)                          │
│    Textual App — point d'entrée, bindings globaux,       │
│    CSS path, référence vers WorkflowEngine               │
│                                                          │
│  ┌─────────────────┐  ┌──────────────────┐               │
│  │ DashboardScreen │  │  JobDetailScreen │               │
│  │                 │  │                  │               │
│  │ ┌─────────────┐ │  │ ┌──────────────┐ │               │
│  │ │  JobTable   │ │  │ │  JobTree     │ │  ← Widgets   │
│  │ │ (DataTable) │ │  │ │  (Tree)      │ │    composites │
│  │ └─────────────┘ │  │ └──────────────┘ │               │
│  │ ┌─────────────┐ │  │ ┌──────────────┐ │               │
│  │ │  RunTable   │ │  │ │ MetadataPanel│ │               │
│  │ │ (DataTable) │ │  │ └──────────────┘ │               │
│  │ └─────────────┘ │  └──────────────────┘               │
│  └─────────────────┘                                     │
│                                                          │
│  ┌─────────────────┐  ┌──────────────────┐               │
│  │ RunDetailScreen │  │ RunHistoryScreen │               │
│  │                 │  │                  │               │
│  │ ┌─────────────┐ │  │ ┌──────────────┐ │               │
│  │ │StepProgress │ │  │ │  RunTable    │ │               │
│  │ │ (DataTable) │ │  │ │ (filtrable)  │ │               │
│  │ └─────────────┘ │  │ └──────────────┘ │               │
│  │ ┌─────────────┐ │  └──────────────────┘               │
│  │ │  LogPanel   │ │                                     │
│  │ │  (RichLog)  │ │                                     │
│  │ └─────────────┘ │                                     │
│  └─────────────────┘                                     │
└──────────────────────────────────────────────────────────┘
```

### Navigation — screens et keybindings

| Touche | Action | Scope |
|---|---|---|
| `q` / `Ctrl+C` | Quitter la TUI | Global |
| `?` | Afficher l'aide des raccourcis | Global |
| `d` | Basculer vers le Dashboard | Global |
| `j` | Basculer vers la liste des jobs | Global |
| `h` | Basculer vers l'historique des runs | Global |
| `Enter` | Inspecter l'élément sélectionné (job → détail, run → détail) | DataTable |
| `r` | Lancer le job sélectionné | JobTable |
| `Escape` | Retour au screen précédent | Navigation |
| `c` | Annuler le run sélectionné | RunDetailScreen |
| `R` | Reprendre le run suspendu sélectionné | RunDetailScreen |
| `/` | Filtrer / rechercher | DataTable |
| `F5` / `Ctrl+R` | Forcer le rafraîchissement | Tout screen |

### Refresh strategy — polling vs push

| Approche | Complexité | Latence | Recommandation |
|---|---|---|---|
| **Polling** (`set_interval`) | Faible — timer Textual natif | 1-2s | ✅ **Phase 1** |
| **Push** (EventBus interne) | Moyenne — nécessite un bus d'événements dans le moteur | Temps réel | ⏳ Phase 2, si `EventBus` ajouté au core |
| **Filesystem watch** (watchdog) | Moyenne — dépendance supplémentaire | ~500ms | ❌ Rejeté — inadapté (le state n'est pas dans des fichiers) |

En Phase 1, chaque screen avec données dynamiques (Dashboard, RunDetail) utilise `self.set_interval(2.0, self._refresh)` pour le polling. Le `RunDetailScreen` peut descendre à 1s pour le suivi live.

### Intégration avec la CLI (ADR-008)

La TUI est **lancée depuis la CLI** via une sous-commande dédiée :

```bash
# Depuis la CLI
pyworkflow tui --app myproject.workflows:engine

# Équivalent avec env var
export PYWORKFLOW_APP=myproject.workflows:engine
pyworkflow tui
```

Cela réutilise :
- Le **loader** (`load_engine()`) existant — pas de duplication
- Les **options globales** (`--app`, `--verbose`) du callback Typer root
- Le **mécanisme de discovery** (`PYWORKFLOW_APP` env var)

La sous-commande `tui` est **optionnelle** : elle n'apparaît dans `--help` que si `textual` est installé (import conditionnel dans `main.py`).

### Textual `serve` — mode web gratuit

Textual offre un mode web qui sert la TUI dans un navigateur **sans modification de code** :

```bash
# Terminal classique
pyworkflow tui --app myproject.workflows:engine

# Servir dans un navigateur (remote, via SSH tunnel, etc.)
textual serve "pyworkflow_engine.adapters.tui.app:WorkflowTUI"
```

Cela permet une supervision à distance sans implémenter d'API REST ni de Web UI — un pont naturel vers l'éventuel adapter `api/` ou `web/` futur.

### Comparaison avec l'écosystème workflow

| Aspect | Airflow | Prefect | Dagster | Luigi | Temporal | **PyWorkflow (proposé)** |
|---|---|---|---|---|---|---|
| Web UI | ✅ Flask | ✅ React | ✅ React | ✅ Tornado | ✅ React | ⏳ Futur (Streamlit ou FastAPI) |
| TUI native | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ **Différenciateur unique** |
| CLI | ✅ Click | ✅ Typer | ✅ Click | ✅ argparse | ✅ | ✅ Typer (ADR-008) |
| SSH-friendly monitoring | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Zero-infra monitoring | ❌ (webserver) | ❌ (server) | ❌ (dagit) | ❌ (scheduler) | ❌ (server) | ✅ |
| Remote browser (sans web app) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (`textual serve`) |

**La TUI est un différenciateur unique** dans l'écosystème workflow Python. Aucun concurrent majeur n'offre de supervision interactive terminal-native.

---

## Décision

### La TUI vit dans `adapters/tui/` — adapter complexe, Textual + Rich

### Extra `pyproject.toml`

```toml
[project.optional-dependencies]
# ...existing extras...
tui = ["textual>=1.0", "rich>=13.0"]
```

L'extra `all` doit inclure `tui` :

```toml
all = [
    "pyworkflow-engine[django,fastapi,celery,sqlalchemy,postgresql,mysql,snowflake,streamlit,structlog,cli,tui]",
]
```

### Structure cible

```
adapters/tui/
├── __init__.py           ← re-export WorkflowTUI, lazy import guard (pattern ADR-008)
├── app.py                ← WorkflowTUI(App) — point d'entrée Textual, bindings globaux
├── screens/
│   ├── __init__.py
│   ├── dashboard.py      ← DashboardScreen — vue d'ensemble (jobs + runs récents)
│   ├── job_detail.py     ← JobDetailScreen — inspection DAG/steps/metadata
│   ├── run_detail.py     ← RunDetailScreen — suivi run en temps réel (steps + logs)
│   └── run_history.py    ← RunHistoryScreen — historique filtrable des runs
├── widgets/
│   ├── __init__.py
│   ├── job_table.py      ← DataTable des jobs enregistrés
│   ├── run_table.py      ← DataTable des runs (statuts colorés)
│   ├── step_progress.py  ← DataTable des steps d'un run (live update)
│   ├── job_tree.py       ← Tree widget pour visualiser le DAG
│   ├── log_panel.py      ← RichLog pour les logs en streaming
│   └── status_bar.py     ← Footer avec statistiques globales
├── styles/
│   ├── __init__.py
│   └── theme.tcss        ← Textual CSS — layout, couleurs, spacings
└── events.py             ← Custom Textual messages (RunUpdated, StepCompleted, RefreshRequested)
```

### Contrat de chaque fichier

#### `app.py` — Point d'entrée Textual

```python
"""WorkflowTUI — interface terminal interactive pour PyWorkflow Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

if TYPE_CHECKING:
    from pyworkflow_engine.facade import WorkflowEngine

from pyworkflow_engine.adapters.tui.screens.dashboard import DashboardScreen


class WorkflowTUI(App[None]):
    """Application Textual pour la supervision interactive de workflows.

    Args:
        engine: Instance WorkflowEngine résolue par le loader CLI.

    Usage::

        from pyworkflow_engine.adapters.tui import WorkflowTUI
        tui = WorkflowTUI(engine)
        tui.run()
    """

    TITLE = "PyWorkflow Engine"
    SUB_TITLE = "Workflow Orchestration TUI"
    CSS_PATH = "styles/theme.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quitter", priority=True),
        Binding("d", "switch_screen('dashboard')", "Dashboard"),
        Binding("j", "switch_screen('jobs')", "Jobs"),
        Binding("h", "switch_screen('history')", "Historique"),
        Binding("question_mark", "help", "Aide"),
    ]

    def __init__(self, engine: WorkflowEngine, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.engine = engine

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())

    def action_switch_screen(self, screen_name: str) -> None:
        from pyworkflow_engine.adapters.tui.screens.dashboard import DashboardScreen
        from pyworkflow_engine.adapters.tui.screens.job_detail import JobListScreen
        from pyworkflow_engine.adapters.tui.screens.run_history import RunHistoryScreen

        screens = {
            "dashboard": DashboardScreen,
            "jobs": JobListScreen,
            "history": RunHistoryScreen,
        }
        screen_cls = screens.get(screen_name)
        if screen_cls:
            self.switch_screen(screen_cls())
```

**Contrat** :
- Reçoit une instance `WorkflowEngine` — **jamais** de `--app` path (le loader est la responsabilité de la CLI ou de l'appelant)
- `self.engine` est accessible par tous les screens via `self.app.engine`
- Les bindings globaux gèrent la navigation entre screens
- Le `CSS_PATH` pointe vers le fichier TCSS dédié

#### `screens/dashboard.py` — Dashboard principal

```python
"""DashboardScreen — vue d'ensemble jobs + runs récents."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from pyworkflow_engine.adapters.tui.widgets.job_table import JobTable
from pyworkflow_engine.adapters.tui.widgets.run_table import RunTable
from pyworkflow_engine.adapters.tui.widgets.status_bar import StatusBar


class DashboardScreen(Screen):
    """Écran principal — jobs enregistrés et runs récents côte à côte."""

    BINDINGS = [
        ("r", "refresh", "Rafraîchir"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("[bold]📊 Dashboard[/bold]", classes="screen-title")
        with Horizontal():
            with Vertical(classes="panel"):
                yield Static("[bold cyan]📋 Jobs enregistrés[/bold cyan]")
                yield JobTable(id="job-table")
            with Vertical(classes="panel"):
                yield Static("[bold cyan]📜 Runs récents[/bold cyan]")
                yield RunTable(id="run-table")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        self._refresh_data()
        self.set_interval(5.0, self._refresh_data)

    def _refresh_data(self) -> None:
        engine = self.app.engine
        self.query_one("#job-table", JobTable).load_jobs(engine.list_jobs())
        self.query_one("#run-table", RunTable).load_runs(
            engine.list_job_runs(limit=20)
        )

    def action_refresh(self) -> None:
        self._refresh_data()
```

**Contrat** :
- `compose()` déclare le layout (jamais de `self.mount()` impératif sauf pour le refresh)
- Polling via `set_interval(5.0, ...)` — compromis entre fraîcheur et charge
- Accès au moteur via `self.app.engine` exclusivement

#### `screens/run_detail.py` — Suivi run en temps réel

```python
"""RunDetailScreen — suivi d'un run en temps réel."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from pyworkflow_engine.adapters.tui.widgets.log_panel import LogPanel
from pyworkflow_engine.adapters.tui.widgets.step_progress import StepProgressTable


class RunDetailScreen(Screen):
    """Écran de détail d'un run — steps + logs, rafraîchissement live."""

    BINDINGS = [
        ("escape", "pop_screen", "Retour"),
        ("c", "cancel_run", "Annuler"),
        ("shift+r", "resume_run", "Reprendre"),
        ("r", "refresh", "Rafraîchir"),
    ]

    def __init__(self, run_id: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.run_id = run_id

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold]🔍 Run [cyan]{self.run_id[:12]}…[/cyan][/bold]",
            classes="screen-title",
        )
        with Horizontal():
            with Vertical(classes="panel"):
                yield Static("[bold]Steps[/bold]")
                yield StepProgressTable(id="step-table")
            with Vertical(classes="panel"):
                yield Static("[bold]Logs[/bold]")
                yield LogPanel(id="log-panel")

    def on_mount(self) -> None:
        self._refresh_run()
        self.set_interval(1.0, self._refresh_run)  # 1s pour le live

    def _refresh_run(self) -> None:
        job_run = self.app.engine.get_job_run(self.run_id)
        if job_run is None:
            self.notify("Run introuvable", severity="error")
            return
        self.query_one("#step-table", StepProgressTable).update_steps(
            job_run.step_runs
        )

    def action_cancel_run(self) -> None:
        cancelled = self.app.engine.cancel(self.run_id)
        if cancelled:
            self.notify(f"Run {self.run_id[:12]}… annulé", severity="warning")
        else:
            self.notify("Impossible d'annuler ce run", severity="error")
        self._refresh_run()

    def action_resume_run(self) -> None:
        try:
            self.app.engine.resume(self.run_id)
            self.notify(f"Run {self.run_id[:12]}… repris", severity="information")
        except Exception as e:
            self.notify(f"Échec reprise : {e}", severity="error")
        self._refresh_run()

    def action_refresh(self) -> None:
        self._refresh_run()
```

**Contrat** :
- Reçoit `run_id` en constructeur (passé lors du `push_screen()`)
- Polling à 1s (plus agressif que le dashboard — le run est en cours)
- Actions `cancel` et `resume` utilisent directement la facade
- Notifications Textual (`self.notify()`) pour les retours utilisateur — pas de `console.print`

#### `widgets/job_table.py` — DataTable des jobs

```python
"""JobTable widget — DataTable listant les jobs enregistrés."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import DataTable

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job


class JobTable(DataTable):
    """Table interactive des jobs avec navigation clavier.

    L'appui sur ``Enter`` émet un événement ``RowSelected`` capté
    par le screen parent pour naviguer vers le JobDetailScreen.
    """

    def on_mount(self) -> None:
        self.add_columns("Nom", "Steps", "Version", "Executor", "Description")
        self.cursor_type = "row"

    def load_jobs(self, jobs: list[Job]) -> None:
        self.clear()
        for job in jobs:
            self.add_row(
                job.name,
                str(len(job.steps)),
                job.version or "—",
                job.default_executor.value if job.default_executor else "local",
                job.description or "—",
                key=job.name,
            )
```

#### `widgets/run_table.py` — DataTable des runs

```python
"""RunTable widget — DataTable des runs avec statuts colorés."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import DataTable

if TYPE_CHECKING:
    from pyworkflow_engine.models import JobRun

from pyworkflow_engine.models.enums import RunStatus

# Mapping statut → (label, style) partageable avec d'autres widgets TUI
STATUS_MARKUP: dict[RunStatus, tuple[str, str]] = {
    RunStatus.SUCCESS:   ("✓ SUCCESS",   "green"),
    RunStatus.FAILED:    ("✗ FAILED",    "red"),
    RunStatus.RUNNING:   ("⟳ RUNNING",   "yellow"),
    RunStatus.PENDING:   ("◯ PENDING",   "dim"),
    RunStatus.SUSPENDED: ("⏸ SUSPENDED", "cyan"),
    RunStatus.SKIPPED:   ("↷ SKIPPED",   "dim"),
    RunStatus.CANCELLED: ("✗ CANCELLED", "red"),
}


class RunTable(DataTable):
    """Table interactive des workflow runs.

    L'appui sur ``Enter`` émet un événement ``RowSelected`` capté
    par le screen parent pour naviguer vers le RunDetailScreen.
    """

    def on_mount(self) -> None:
        self.add_columns("Run ID", "Job", "Statut", "Début", "Durée")
        self.cursor_type = "row"

    def load_runs(self, runs: list[JobRun]) -> None:
        self.clear()
        for run in runs:
            label, color = STATUS_MARKUP.get(
                run.status, (str(run.status.value), "white")
            )
            started = (
                run.start_time.strftime("%Y-%m-%d %H:%M:%S")
                if run.start_time
                else "—"
            )
            dur_ms = (
                int((run.end_time - run.start_time).total_seconds() * 1000)
                if run.start_time and run.end_time
                else None
            )
            duration = f"{dur_ms}ms" if dur_ms and dur_ms < 1000 else (
                f"{dur_ms / 1000:.2f}s" if dur_ms else "—"
            )
            self.add_row(
                run.job_run_id[:12] + "…",
                run.job_name,
                Text(label, style=color),
                started,
                duration,
                key=run.job_run_id,
            )
```

#### `widgets/step_progress.py` — Progression des steps en temps réel

```python
"""StepProgress widget — table des steps d'un run avec live update."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import DataTable

if TYPE_CHECKING:
    from pyworkflow_engine.models.run import StepRun

from pyworkflow_engine.adapters.tui.widgets.run_table import STATUS_MARKUP


class StepProgressTable(DataTable):
    """Table des steps avec mise à jour en temps réel."""

    def on_mount(self) -> None:
        self.add_columns("Step", "Statut", "Durée", "Erreur")
        self.cursor_type = "row"

    def update_steps(self, step_runs: list[StepRun]) -> None:
        self.clear()
        for sr in step_runs:
            label, color = STATUS_MARKUP.get(
                sr.status, (str(sr.status.value), "white")
            )
            duration = (
                f"{sr.duration_ms}ms" if sr.duration_ms and sr.duration_ms < 1000
                else f"{sr.duration_ms / 1000:.2f}s" if sr.duration_ms
                else "—"
            )
            self.add_row(
                sr.step_name,
                Text(label, style=color),
                duration,
                sr.error or "—",
            )
```

#### `widgets/log_panel.py` — Logs en streaming

```python
"""LogPanel widget — RichLog pour les logs en temps réel."""

from __future__ import annotations

from textual.widgets import RichLog


class LogPanel(RichLog):
    """Panel de logs scrollable avec auto-scroll.

    En Phase 1, les logs sont poussés manuellement par le screen.
    En Phase 2, un EventBus pourra alimenter le panel en push.
    """

    def on_mount(self) -> None:
        self.auto_scroll = True

    def append_log(self, message: str, style: str = "") -> None:
        if style:
            self.write(f"[{style}]{message}[/]")
        else:
            self.write(message)
```

#### `widgets/job_tree.py` — Visualisation DAG interactive

```python
"""JobTree widget — Tree widget pour visualiser le DAG d'un job."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Tree

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job


class JobTree(Tree[str]):
    """Arbre interactif représentant le DAG d'un job.

    Chaque step est un nœud. Les dépendances sont représentées
    comme des sous-nœuds (expand/collapse natif Textual).
    """

    def load_job(self, job: Job) -> None:
        self.clear()
        self.root.set_label(f"📋 {job.name}")
        for step in job.steps:
            node = self.root.add(f"⚙️  {step.name}", expand=True)
            if step.depends_on:
                deps_node = node.add("⤷ dépendances", expand=False)
                for dep in step.depends_on:
                    deps_node.add_leaf(f"← {dep}")
            if step.step_type:
                node.add_leaf(f"type: {step.step_type.value}")
        self.root.expand()
```

#### `widgets/status_bar.py` — Footer avec statistiques

```python
"""StatusBar widget — footer avec stats globales."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Barre de statut affichant les compteurs globaux."""

    def update_stats(
        self,
        total_jobs: int,
        total_runs: int,
        suspended: int,
    ) -> None:
        self.update(
            f"  📋 {total_jobs} jobs  │  "
            f"📊 {total_runs} runs  │  "
            f"⏸ {suspended} suspendus  │  "
            f"[dim]? aide  q quitter[/dim]"
        )
```

#### `styles/theme.tcss` — Textual CSS

```css
/* Theme PyWorkflow Engine TUI
 *
 * Conventions :
 *   - .screen-title  : titre en haut de chaque screen
 *   - .panel         : conteneur bordé (grille, sections)
 *   - DataTable      : prend tout l'espace vertical disponible
 *   - StatusBar      : footer ancré en bas
 */

Screen {
    background: $surface;
}

.screen-title {
    dock: top;
    height: 3;
    content-align: center middle;
    background: $primary-background;
    color: $text;
    text-style: bold;
    padding: 1;
}

.panel {
    width: 1fr;
    height: 1fr;
    margin: 1;
    border: solid $primary;
    padding: 1;
}

DataTable {
    height: 1fr;
}

DataTable > .datatable--cursor {
    background: $accent;
    color: $text;
}

RichLog {
    height: 1fr;
    border: solid $secondary;
    padding: 0 1;
}

StatusBar {
    dock: bottom;
    height: 1;
    background: $primary-background;
    color: $text-muted;
    content-align: center middle;
    padding: 0 2;
}

Tree {
    height: 1fr;
    padding: 1;
}
```

#### `events.py` — Messages Textual personnalisés

```python
"""Custom Textual messages pour la communication inter-widgets."""

from __future__ import annotations

from textual.message import Message


class RunUpdated(Message):
    """Émis quand un run change de statut (polling ou push)."""

    def __init__(self, run_id: str, new_status: str) -> None:
        super().__init__()
        self.run_id = run_id
        self.new_status = new_status


class StepCompleted(Message):
    """Émis quand un step termine son exécution."""

    def __init__(self, run_id: str, step_name: str, status: str) -> None:
        super().__init__()
        self.run_id = run_id
        self.step_name = step_name
        self.status = status


class RefreshRequested(Message):
    """Émis pour demander un rafraîchissement global des données."""
    pass
```

#### `__init__.py` — Re-export avec lazy import guard

```python
"""TUI adapter — interface terminal interactive pour PyWorkflow Engine.

Installation : ``pip install pyworkflow-engine[tui]``

Usage::

    from pyworkflow_engine.adapters.tui import WorkflowTUI
    from pyworkflow_engine import WorkflowEngine

    engine = WorkflowEngine(persistence=my_backend)
    app = WorkflowTUI(engine)
    app.run()
"""

from __future__ import annotations

__all__ = ["WorkflowTUI"]


def __getattr__(name: str) -> object:
    if name == "WorkflowTUI":
        try:
            from pyworkflow_engine.adapters.tui.app import WorkflowTUI
            return WorkflowTUI
        except ImportError as exc:
            raise ImportError(
                "Le TUI adapter nécessite 'textual'. "
                "Installez-le avec : pip install pyworkflow-engine[tui]"
            ) from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

**Pattern identique** à `adapters/cli/__init__.py` (ADR-008) — lazy import via `__getattr__` PEP 562.

### Intégration CLI — sous-commande `tui`

Un fichier `adapters/cli/commands/tui.py` ajoute la sous-commande :

```python
"""Sous-commande TUI — lance l'interface Textual interactive."""

from __future__ import annotations

import typer

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(
    name="tui",
    help="Lancer l'interface terminal interactive (Textual).",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
@error_handler
def launch_tui(ctx: typer.Context) -> None:
    """Lance l'interface terminal interactive PyWorkflow."""
    try:
        from pyworkflow_engine.adapters.tui import WorkflowTUI
    except ImportError:
        from rich.console import Console
        Console(stderr=True).print(
            "[bold red]✗[/bold red] La TUI nécessite 'textual'. "
            "Installez avec : [cyan]pip install pyworkflow-engine[tui][/cyan]"
        )
        raise typer.Exit(4)

    engine = load_engine(ctx.obj["app_path"])
    tui_app = WorkflowTUI(engine)
    tui_app.run()
```

Et dans `adapters/cli/main.py`, import conditionnel :

```python
# TUI sub-command — optionnel, n'apparaît que si textual est installé
try:
    from pyworkflow_engine.adapters.cli.commands import tui as tui_commands
    app.add_typer(tui_commands.app, name="tui")
except ImportError:
    pass
```

### Flux de dépendances

```
pyworkflow tui --app myproject:engine
       │
       ▼
  main.py (Typer)
       │  ctx.obj["app_path"]
       ▼
  commands/tui.py
       │  load_engine(app_path)
       ▼
  loader.py  ──→  facade.py (WorkflowEngine)
       │
       ▼
  tui/app.py (WorkflowTUI)
       │  self.engine
       ▼
  screens/  ──→  widgets/  ──→  facade methods
                     │
                     ▼
              styles/theme.tcss
```

La TUI est un **adapter pur** : elle dépend uniquement de la facade `WorkflowEngine` et n'a aucune connaissance des ports, de l'engine interne, ou des autres adapters (sauf le loader CLI partagé).

---

## Plan d'implémentation

### Phase 1 — Scaffold et DashboardScreen (v0.9.0-alpha)

| Tâche | Fichier | Effort |
|---|---|---|
| `app.py` — `WorkflowTUI(App)`, bindings, CSS path | `adapters/tui/app.py` | 1h |
| `styles/theme.tcss` — layout de base | `adapters/tui/styles/theme.tcss` | 1h |
| `widgets/job_table.py` — DataTable des jobs | `adapters/tui/widgets/job_table.py` | 1h |
| `widgets/run_table.py` — DataTable des runs | `adapters/tui/widgets/run_table.py` | 1h30 |
| `widgets/status_bar.py` — footer stats | `adapters/tui/widgets/status_bar.py` | 30min |
| `screens/dashboard.py` — layout + polling | `adapters/tui/screens/dashboard.py` | 2h |
| `__init__.py` — lazy import guard | `adapters/tui/__init__.py` | 15min |
| `commands/tui.py` — intégration CLI | `adapters/cli/commands/tui.py` | 30min |
| `pyproject.toml` — extra `tui`, update `all` | `pyproject.toml` | 10min |

**Total Phase 1 : ~8h**

### Phase 2 — Détail et navigation (v0.9.0-beta)

| Tâche | Fichier | Effort |
|---|---|---|
| `screens/job_detail.py` — DAG tree + metadata | `adapters/tui/screens/job_detail.py` | 2h |
| `widgets/job_tree.py` — Tree widget interactif | `adapters/tui/widgets/job_tree.py` | 1h30 |
| `screens/run_detail.py` — live refresh 1s | `adapters/tui/screens/run_detail.py` | 2h |
| `widgets/step_progress.py` — steps live | `adapters/tui/widgets/step_progress.py` | 1h |
| `widgets/log_panel.py` — RichLog streaming | `adapters/tui/widgets/log_panel.py` | 1h |
| `events.py` — messages personnalisés | `adapters/tui/events.py` | 1h |
| Navigation inter-screens (Enter, Escape) | screens/*.py | 1h |

**Total Phase 2 : ~9h30**

### Phase 3 — Historique, tests, polish (v0.9.0)

| Tâche | Fichier | Effort |
|---|---|---|
| `screens/run_history.py` — filtres (job, statut) | `adapters/tui/screens/run_history.py` | 2h |
| Actions depuis la TUI (run, cancel, resume) | screens/*.py | 1h |
| Tests avec Textual `pilot` | `tests/unit/adapters/tui/` | 3h |
| Documentation | `docs/integrations/tui.md` | 1h |
| `textual serve` documentation | `docs/integrations/tui.md` | 30min |

**Total Phase 3 : ~7h30**

### Effort total estimé : ~25h

---

## Alternatives considérées

### Alternative A — `curses` (stdlib)

Utiliser la bibliothèque standard `curses` pour zéro dépendance.

**Pour** : Aucune dépendance supplémentaire, cohérent avec la philosophie "zero deps".
**Contre** :
- API bas niveau (coordonnées manuelles, pas de widgets, pas de layout)
- Pas de DataTable, pas de Tree, pas de couleurs riches
- Pas de CSS, pas de theming
- Extrêmement verbeux pour un dashboard multi-panels
- Pas testable facilement
- La TUI est un **extra optionnel** — les dépendances sont acceptables

**Verdict** : ❌ Rejetée — effort disproportionné pour un résultat inférieur. La TUI est opt-in.

### Alternative B — `urwid`

Utiliser urwid, framework TUI mature et léger.

**Pour** : Mature, léger (~300 KB), fonctionne sur des terminaux exotiques.
**Contre** :
- Widgets basiques (pas de DataTable riche, pas de Tree avancé)
- Pas d'intégration Rich (deux mondes de rendu incompatibles)
- Pas de CSS/theming
- Pas de mode web (`textual serve`)
- Communauté réduite en 2026

**Verdict** : ❌ Rejetée — Textual couvre tous les cas d'urwid avec des widgets supérieurs.

### Alternative C — `prompt_toolkit`

Utiliser prompt_toolkit (utilisé par IPython, pgcli).

**Pour** : Excellent pour les prompts interactifs, async natif.
**Contre** :
- Orienté prompt/REPL, pas dashboard
- Pas de widgets riches (DataTable, Tree)
- Pas de layout CSS
- Pas de framework de test intégré
- La TUI n'est pas un REPL — c'est un dashboard

**Verdict** : ❌ Rejetée — mauvais paradigme (prompt vs dashboard).

### Alternative D — Web UI directement (Streamlit ou FastAPI)

Sauter la TUI et implémenter une Web UI.

**Pour** : Interface plus riche, accessible depuis n'importe quel navigateur.
**Contre** :
- Nécessite une infrastructure (serveur web, port exposé)
- Ne fonctionne pas en SSH sans tunnel
- Plus complexe à implémenter (frontend + backend)
- L'extra `streamlit` est déjà prévu séparément
- La TUI et la Web UI ne sont pas mutuellement exclusives

**Verdict** : ❌ Rejetée comme remplacement — la Web UI viendra en complément (v1.x). La TUI couvre le cas "zero infra" qui restera toujours pertinent.

### Alternative E — Ne rien faire (CLI suffit)

Ne pas implémenter de TUI, se contenter de la CLI.

**Pour** : Zéro effort supplémentaire.
**Contre** :
- La supervision interactive reste un besoin non couvert
- Différenciateur perdu face à l'écosystème
- Le placeholder `adapters/tui/` existe déjà dans l'architecture — dette architecturale

**Verdict** : ❌ Rejetée — la TUI est un différenciateur unique et le besoin de supervision interactive est réel.

---

## Conséquences

### Positives

- **Différenciateur unique** — aucun concurrent workflow Python n'offre de TUI native
- **Zero infra** — supervision interactive sans déployer de serveur web
- **SSH-friendly** — monitoring depuis n'importe quel terminal distant
- **Mode web gratuit** — `textual serve` offre un accès navigateur sans code supplémentaire
- **Réutilisation Rich** — même écosystème de rendu que la CLI (ADR-008)
- **Réutilisation loader** — `load_engine()` partagé entre CLI et TUI
- **Testable** — framework `pilot` dédié pour les tests d'interaction
- **Cohérence hexagonale** — adapter pur qui dépend uniquement de la facade

### Négatives

- **Dépendance Textual** — ~5 MB de dépendances supplémentaires pour l'extra `tui`
- **Courbe d'apprentissage** — Textual CSS et le modèle Screen/Widget sont spécifiques
- **Maintenance widgets** — les widgets doivent suivre l'évolution des modèles (`Job`, `JobRun`, `StepRun`)
- **Limites terminal** — résolution, taille, support Unicode/emoji varient selon les terminaux

### Risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Textual breaking change (API v2) | Faible | Moyen | Pin `textual>=1.0,<2.0` ; l'API est stabilisée depuis la v1 |
| Performance polling sur gros volumes | Moyenne | Faible | `limit=` sur les requêtes facade, intervalle configurable |
| Terminal exotique (Windows cmd, tmux ancien) | Faible | Faible | Textual gère la compatibilité ; documentation des terminaux supportés |
| Confusion TUI vs CLI (2 interfaces) | Faible | Faible | Documentation claire des cas d'usage respectifs |

---

## Références

- [Textual documentation](https://textual.textualize.io/)
- [Textual CSS reference](https://textual.textualize.io/css_types/)
- [Textual `pilot` testing](https://textual.textualize.io/guide/testing/)
- [Textual `serve` (web mode)](https://textual.textualize.io/guide/devtools/#textual-serve)
- [Rich documentation](https://rich.readthedocs.io/) — même auteur
- [Textual GitHub — 25k+ stars](https://github.com/Textualize/textual)
- ADR-006 — Architecture hexagonale
- ADR-007 — Adapter complexe vs simple (règle de placement)
- ADR-008 — CLI Adapter Typer + Rich
