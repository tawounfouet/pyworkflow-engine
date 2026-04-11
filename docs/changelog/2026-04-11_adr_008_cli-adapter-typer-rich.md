# ADR-008 — CLI Adapter : Typer + Rich dans `adapters/cli/`

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-008                             |
| **Date**    | 11 avril 2026                       |
| **Statut**  | ✅ Décision prise                   |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (architecture hexagonale), ADR-007 (adapter complexe vs simple) |
| **Version cible** | v0.8.0                         |

---

## Contexte

### Situation actuelle

Le placeholder `adapters/cli/` existe mais ne contient qu'un `__init__.py` vide. Le `pyproject.toml` déclare déjà :

```toml
# Extra
cli = ["click>=8.0", "rich>=13.0"]

# Entrypoint (ancien chemin, non fonctionnel)
[project.scripts]
workflow = "pyworkflow_engine.cli.main:cli"
```

L'entrypoint pointe vers `pyworkflow_engine.cli.main:cli` — un chemin obsolète (avant la réorganisation hexagonale ADR-006). Il doit migrer vers `pyworkflow_engine.adapters.cli.main`.

Le `WorkflowEngine` (facade) expose déjà toutes les opérations nécessaires :

| Méthode facade | Description |
|---|---|
| `run(job, initial_context)` | Exécution pure en mémoire |
| `run_with_persistence(job_or_name, initial_context)` | Exécution avec sauvegarde |
| `resume(run_id)` | Reprendre un workflow suspendu |
| `cancel(run_id)` | Annuler un workflow suspendu |
| `get_status(run_id)` | Statut d'un run |
| `list_suspended()` | Lister les runs suspendus |
| `validate_job(job)` | Valider sans exécuter |
| `get_execution_plan(job)` | Plan d'exécution (DAG) |
| `save_job(job)` / `get_job(name)` / `list_jobs()` / `delete_job(name)` | CRUD jobs |
| `get_job_run(run_id)` / `list_job_runs(...)` | Historique d'exécutions |
| `register_executor(name, executor)` / `list_executors()` | Gestion des executors |

### La question

Comment structurer l'adapter CLI pour :
1. Exposer ces opérations de manière ergonomique en ligne de commande ?
2. Découvrir les jobs définis dans le code utilisateur ?
3. S'intégrer proprement dans l'architecture hexagonale ?
4. Choisir le bon framework CLI (Click vs Typer) ?

---

## Analyse

### Click vs Typer

| Critère | Click | Typer |
|---|---|---|
| Auto-complétion shell | Plugin externe (`click-completion`) | Intégrée (`typer --install-completion`) |
| Type hints | Non exploités | Exploités pour valider les arguments |
| Boilerplate | Verbeux (`@click.option`, `@click.argument`) | Minimal (annotations Python) |
| Sub-commands | `@click.group()` | `typer.Typer()` + `add_typer()` |
| Rich integration | Manuelle | Native (`rich_markup_mode="rich"`) |
| Testabilité | `CliRunner` | `CliRunner` (hérité de Click) |
| Dépendance | Standalone | Dépend de Click (superset) |
| Adoption 2026 | Standard établi | Standard moderne (FastAPI ecosystem) |

**Verdict** : **Typer** — moins de boilerplate, type hints natifs, Rich intégré, même testabilité. Typer est un superset de Click ; la migration est naturelle.

### Adapter simple vs complexe (règle ADR-007)

La CLI coche les 3 critères d'un adapter complexe :

| Critère | Évaluation |
|---|---|
| 2+ fichiers coordonnés | ✅ main + commands + formatters + loader |
| Dépendance tierce avec config propre | ✅ Typer + Rich |
| Concepts spécifiques au-delà du port | ✅ Sub-commands, formatters, discovery, exit codes |

→ La CLI reste dans `adapters/cli/` (package dédié), conformément à la règle ADR-007.

### Découverte des jobs — le problème central

La CLI ne peut rien faire sans un `WorkflowEngine` peuplé de jobs. Comment le créer ?

| Approche | Description | Complexité | Recommandation |
|---|---|---|---|
| **`--app` module path** | `pyworkflow --app myproject.workflows:engine job list` | Faible | ✅ **Phase 1** |
| **Env var** | `PYWORKFLOW_APP=myproject.workflows:engine` | Faible | ✅ **Phase 1** (complémentaire) |
| **Auto-discovery** | Scanner `*.py` pour les `@job` décorés | Moyenne | ⏳ Phase 2 |
| **Config file** | `pyworkflow.toml` avec `app = "myproject.workflows:engine"` | Moyenne | ⏳ Phase 2 |

Pattern inspiré de l'écosystème :
- Celery : `celery --app myproject worker`
- FastAPI/Uvicorn : `uvicorn myproject:app`
- Flask : `flask --app myproject run`

Convention : si l'attribut n'est pas spécifié, chercher `engine` par défaut dans le module.

```bash
# Explicite
pyworkflow --app myproject.workflows:engine job list

# Convention (cherche `engine` dans le module)
pyworkflow --app myproject.workflows job list

# Via env var
export PYWORKFLOW_APP=myproject.workflows:engine
pyworkflow job list
```

### Sub-commands groupés vs flat

```bash
# Groupé (retenu) — scalable, discoverable, pas d'ambiguïté
pyworkflow job list
pyworkflow job inspect etl-pipeline
pyworkflow run start etl-pipeline --param env=prod
pyworkflow run status abc-123
pyworkflow run history --limit 10
pyworkflow executor list

# Flat (rejeté) — ambiguïté dès qu'on dépasse 5 commandes
pyworkflow list-jobs
pyworkflow run etl-pipeline       ← "run" est à la fois verbe et namespace
pyworkflow run-status abc-123
```

**Verdict** : sub-commands groupés. Trois groupes initiaux : `job`, `run`, `executor`.

### Output format — scriptabilité

Un flag global `--format` est essentiel pour l'intégration dans des pipelines :

```bash
# Humain (défaut) — Rich tables
pyworkflow job list

# Scriptable — JSON brut
pyworkflow job list --format json | jq '.[].name'
```

Deux formats en Phase 1 : `table` (défaut, Rich) et `json`. YAML éventuel en Phase 2.

### Exit codes structurés

| Code | Signification |
|------|--------------|
| `0` | Succès |
| `1` | Erreur job (JobNotFoundError, validation) |
| `2` | Erreur step (StepExecutionError) |
| `3` | Erreur import (module introuvable, pas de WorkflowEngine) |
| `4` | Erreur configuration (persistence manquante, etc.) |
| `5` | Erreur inattendue |

---

## Décision

### La CLI vit dans `adapters/cli/` — adapter complexe, Typer + Rich

### Structure cible

```
adapters/cli/
├── __init__.py           ← re-export `app` (instance Typer)
├── main.py               ← app Typer root + callback global (--app, --format, --verbose)
├── commands/
│   ├── __init__.py
│   ├── job.py            ← job list, job inspect, job validate
│   ├── run.py            ← run start, run status, run history, run retry
│   └── executor.py       ← executor list (Phase 2)
├── formatters/
│   ├── __init__.py
│   ├── tables.py         ← Rich Table renderers (jobs, runs, steps)
│   ├── trees.py          ← Rich Tree renderer (DAG visualization)
│   └── json_output.py    ← JSON serialization pour --format json
├── loader.py             ← load_engine() — import dynamique du WorkflowEngine utilisateur
├── errors.py             ← error_handler decorator, exit codes stylisés
└── callbacks.py          ← version callback, global option processing
```

### Contrat de chaque fichier

#### `main.py` — Point d'entrée Typer

```python
"""CLI entrypoint — Typer application root."""

from __future__ import annotations

from typing import Optional

import typer

from pyworkflow_engine.adapters.cli.commands import job, run

app = typer.Typer(
    name="pyworkflow",
    help="PyWorkflow Engine — workflow orchestration CLI.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

app.add_typer(job.app, name="job")
app.add_typer(run.app, name="run")


@app.callback()
def main(
    ctx: typer.Context,
    app_path: Optional[str] = typer.Option(
        None,
        "--app",
        "-a",
        envvar="PYWORKFLOW_APP",
        help="Python path to WorkflowEngine instance (e.g. myproject.workflows:engine)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table, json",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Global options propagated to all sub-commands via ctx.obj."""
    ctx.ensure_object(dict)
    ctx.obj["app_path"] = app_path
    ctx.obj["format"] = output_format
    ctx.obj["verbose"] = verbose
```

#### `loader.py` — Discovery et import du WorkflowEngine

```python
"""Loader — import dynamique de l'instance WorkflowEngine utilisateur."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.facade import WorkflowEngine


def load_engine(app_path: str | None) -> WorkflowEngine:
    """Importe le module et retourne l'instance WorkflowEngine.

    Convention :
        - ``"myproject.workflows:engine"`` → attribut explicite
        - ``"myproject.workflows"`` → cherche ``engine`` par défaut

    Raises:
        SystemExit(3): Si le module ou l'attribut est introuvable.
        SystemExit(3): Si l'objet n'est pas une instance WorkflowEngine.
    """
    from pyworkflow_engine.facade import WorkflowEngine as _WE

    if not app_path:
        from rich.console import Console
        Console(stderr=True).print(
            "[red]✗[/red] --app requis ou variable PYWORKFLOW_APP non définie."
        )
        raise SystemExit(3)

    module_path, _, attr = app_path.rpartition(":")
    if not module_path:
        module_path = attr
        attr = "engine"

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        from rich.console import Console
        Console(stderr=True).print(f"[red]✗[/red] Module introuvable : {module_path}")
        raise SystemExit(3) from exc

    engine = getattr(module, attr, None)
    if engine is None:
        from rich.console import Console
        Console(stderr=True).print(
            f"[red]✗[/red] Attribut '{attr}' introuvable dans {module_path}"
        )
        raise SystemExit(3)

    if not isinstance(engine, _WE):
        from rich.console import Console
        Console(stderr=True).print(
            f"[red]✗[/red] {app_path} n'est pas une instance WorkflowEngine "
            f"(type: {type(engine).__name__})"
        )
        raise SystemExit(3)

    return engine
```

#### `errors.py` — Gestion d'erreurs centralisée

```python
"""Error handler decorator et exit codes pour la CLI."""

from __future__ import annotations

import functools
from typing import Any, Callable

import typer
from rich.console import Console

from pyworkflow_engine.exceptions import (
    DAGValidationError,
    StepExecutionError,
    WorkflowError,
    WorkflowFailed,
)
from pyworkflow_engine.ports.persistence import JobNotFoundError, PersistenceError

err = Console(stderr=True)

# Exit codes structurés
EXIT_OK = 0
EXIT_JOB_ERROR = 1
EXIT_STEP_ERROR = 2
EXIT_IMPORT_ERROR = 3
EXIT_CONFIG_ERROR = 4
EXIT_UNEXPECTED = 5


def error_handler(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator qui intercepte les exceptions et produit des messages Rich."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except JobNotFoundError as e:
            err.print(f"[red]✗[/red] Job introuvable : {e}")
            raise typer.Exit(EXIT_JOB_ERROR) from e
        except DAGValidationError as e:
            err.print(f"[red]✗[/red] DAG invalide : {e}")
            raise typer.Exit(EXIT_JOB_ERROR) from e
        except StepExecutionError as e:
            err.print(f"[red]✗[/red] Échec step : {e}")
            raise typer.Exit(EXIT_STEP_ERROR) from e
        except WorkflowFailed as e:
            err.print(f"[red]✗[/red] Workflow échoué : {e}")
            raise typer.Exit(EXIT_STEP_ERROR) from e
        except PersistenceError as e:
            err.print(f"[red]✗[/red] Erreur persistence : {e}")
            raise typer.Exit(EXIT_CONFIG_ERROR) from e
        except WorkflowError as e:
            err.print(f"[red]✗[/red] Erreur workflow : {e}")
            raise typer.Exit(EXIT_JOB_ERROR) from e
        except Exception as e:
            err.print(f"[red]✗[/red] Erreur inattendue : {e}")
            raise typer.Exit(EXIT_UNEXPECTED) from e

    return wrapper
```

#### `commands/job.py` — Gestion des jobs

```python
"""Job management commands."""

from __future__ import annotations

import typer
from rich.console import Console

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(help="Manage workflow jobs.", no_args_is_help=True)
console = Console()


@app.command("list")
@error_handler
def list_jobs(ctx: typer.Context) -> None:
    """List all registered jobs."""
    engine = load_engine(ctx.obj["app_path"])
    jobs = engine.list_jobs()

    if ctx.obj["format"] == "json":
        from pyworkflow_engine.adapters.cli.formatters.json_output import jobs_to_json

        typer.echo(jobs_to_json(jobs))
    else:
        from pyworkflow_engine.adapters.cli.formatters.tables import render_job_table

        render_job_table(console, jobs)


@app.command("inspect")
@error_handler
def inspect_job(
    ctx: typer.Context,
    name: str = typer.Argument(help="Job name to inspect"),
) -> None:
    """Show detailed job structure (steps, DAG, config)."""
    engine = load_engine(ctx.obj["app_path"])
    job = engine.get_job(name)

    if job is None:
        from pyworkflow_engine.ports.persistence import JobNotFoundError

        raise JobNotFoundError(f"Job '{name}' not found")

    from pyworkflow_engine.adapters.cli.formatters.trees import render_job_tree

    render_job_tree(console, job)


@app.command("validate")
@error_handler
def validate_job(
    ctx: typer.Context,
    name: str = typer.Argument(help="Job name to validate"),
) -> None:
    """Validate a job without executing it."""
    engine = load_engine(ctx.obj["app_path"])
    job = engine.get_job(name)

    if job is None:
        from pyworkflow_engine.ports.persistence import JobNotFoundError

        raise JobNotFoundError(f"Job '{name}' not found")

    warnings = engine.validate_job(job)
    if warnings:
        for w in warnings:
            console.print(f"[yellow]⚠[/yellow] {w}")
    else:
        console.print("[green]✓[/green] Job valide — aucun avertissement.")
```

#### `commands/run.py` — Exécution et monitoring

```python
"""Run execution and monitoring commands."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(help="Execute and monitor workflow runs.", no_args_is_help=True)
console = Console()


@app.command("start")
@error_handler
def start_run(
    ctx: typer.Context,
    job_name: str = typer.Argument(help="Job name to execute"),
    param: Optional[list[str]] = typer.Option(
        None, "--param", "-p", help="key=value parameters"
    ),
    watch: bool = typer.Option(False, "--watch", "-w", help="Live progress display"),
) -> None:
    """Execute a workflow job."""
    engine = load_engine(ctx.obj["app_path"])
    params = dict(p.split("=", 1) for p in (param or []))

    result = engine.run_with_persistence(job_name, initial_context=params)

    if ctx.obj["format"] == "json":
        from pyworkflow_engine.adapters.cli.formatters.json_output import run_to_json

        typer.echo(run_to_json(result))
    else:
        from pyworkflow_engine.adapters.cli.formatters.tables import render_run_result

        render_run_result(console, result)


@app.command("status")
@error_handler
def run_status(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="Run ID to check"),
) -> None:
    """Show status of a specific run."""
    engine = load_engine(ctx.obj["app_path"])
    job_run = engine.get_job_run(run_id)

    if job_run is None:
        console.print(f"[red]✗[/red] Run '{run_id}' introuvable.")
        raise typer.Exit(1)

    from pyworkflow_engine.adapters.cli.formatters.tables import render_run_status

    render_run_status(console, job_run)


@app.command("history")
@error_handler
def run_history(
    ctx: typer.Context,
    job_name: Optional[str] = typer.Option(None, "--job", "-j", help="Filter by job"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """Show execution history."""
    engine = load_engine(ctx.obj["app_path"])
    runs = engine.list_job_runs(job_name=job_name, limit=limit)

    if ctx.obj["format"] == "json":
        from pyworkflow_engine.adapters.cli.formatters.json_output import runs_to_json

        typer.echo(runs_to_json(runs))
    else:
        from pyworkflow_engine.adapters.cli.formatters.tables import render_run_history

        render_run_history(console, runs)
```

#### `formatters/tables.py` — Rich Tables

```python
"""Rich Table formatters for CLI output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job, JobRun

from pyworkflow_engine.models.enums import RunStatus

STATUS_STYLES: dict[RunStatus, str] = {
    RunStatus.SUCCESS: "[bold green]✓ SUCCESS[/]",
    RunStatus.FAILED: "[bold red]✗ FAILED[/]",
    RunStatus.RUNNING: "[bold yellow]⟳ RUNNING[/]",
    RunStatus.PENDING: "[dim]◯ PENDING[/]",
    RunStatus.SUSPENDED: "[bold cyan]⏸ SUSPENDED[/]",
    RunStatus.SKIPPED: "[dim]↷ SKIPPED[/]",
    RunStatus.CANCELLED: "[dim red]✗ CANCELLED[/]",
}


def render_job_table(console: Console, jobs: list[Job]) -> None:
    """Render a list of jobs as a Rich Table."""
    table = Table(title="📋 Registered Jobs", show_lines=True)
    table.add_column("Name", style="bold cyan")
    table.add_column("Steps", justify="right")
    table.add_column("Version", style="dim")
    table.add_column("Description")

    for job in jobs:
        table.add_row(
            job.name,
            str(len(job.steps)),
            job.version or "—",
            getattr(job, "description", None) or "—",
        )
    console.print(table)


def render_run_result(console: Console, job_run: JobRun) -> None:
    """Render a single run result with step details."""
    style = STATUS_STYLES.get(job_run.status, str(job_run.status))
    console.print(f"\n  Run [bold]{job_run.job_run_id}[/] → {style}\n")

    if job_run.step_runs:
        table = Table(show_lines=True)
        table.add_column("Step", style="cyan")
        table.add_column("Status")
        table.add_column("Duration", justify="right", style="dim")

        for sr in job_run.step_runs:
            table.add_row(
                sr.step_name,
                STATUS_STYLES.get(sr.status, str(sr.status)),
                f"{sr.duration_ms:.0f}ms" if hasattr(sr, "duration_ms") and sr.duration_ms else "—",
            )
        console.print(table)


def render_run_status(console: Console, job_run: JobRun) -> None:
    """Render run status overview."""
    style = STATUS_STYLES.get(job_run.status, str(job_run.status))
    console.print(f"  Run   : [bold]{job_run.job_run_id}[/]")
    console.print(f"  Job   : {job_run.job_name}")
    console.print(f"  Status: {style}")


def render_run_history(console: Console, runs: list[JobRun]) -> None:
    """Render run history as a Rich Table."""
    table = Table(title="📜 Run History", show_lines=True)
    table.add_column("Run ID", style="bold")
    table.add_column("Job", style="cyan")
    table.add_column("Status")
    table.add_column("Started", style="dim")

    for run in runs:
        table.add_row(
            run.job_run_id[:12] + "…",
            run.job_name,
            STATUS_STYLES.get(run.status, str(run.status)),
            str(run.started_at) if hasattr(run, "started_at") and run.started_at else "—",
        )
    console.print(table)
```

#### `formatters/trees.py` — Rich Tree (DAG)

```python
"""Rich Tree formatters — DAG visualization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.tree import Tree

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job


def render_job_tree(console: Console, job: Job) -> None:
    """Render a job as a Rich Tree with metadata and step DAG."""
    tree = Tree(f"🔧 [bold]{job.name}[/]")

    # Metadata
    meta = tree.add("📌 Metadata")
    meta.add(f"Version : {job.version or '—'}")
    meta.add(f"Steps   : {len(job.steps)}")

    # Steps DAG
    steps_node = tree.add(f"📦 Steps ({len(job.steps)})")
    for step in job.steps:
        deps = f" ← [{', '.join(step.dependencies)}]" if step.dependencies else ""
        icon = "🔄" if step.retry_count else "▸"
        label = f"{icon} {step.name}{deps}"
        if step.timeout:
            label += f" [dim](timeout: {step.timeout}s)[/]"
        steps_node.add(label)

    console.print(tree)
```

#### `formatters/json_output.py` — Sortie JSON

```python
"""JSON serialization for --format json output."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job, JobRun


def _serialize(obj: Any) -> Any:
    """Fallback serializer for non-JSON types."""
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return str(obj)


def jobs_to_json(jobs: list[Job]) -> str:
    """Serialize jobs list to JSON string."""
    data = [
        {
            "name": j.name,
            "version": j.version,
            "steps": len(j.steps),
            "step_names": [s.name for s in j.steps],
        }
        for j in jobs
    ]
    return json.dumps(data, indent=2, default=_serialize)


def run_to_json(job_run: JobRun) -> str:
    """Serialize a single JobRun to JSON string."""
    data = {
        "run_id": job_run.job_run_id,
        "job_name": job_run.job_name,
        "status": job_run.status.value,
        "step_runs": [
            {"step": sr.step_name, "status": sr.status.value}
            for sr in job_run.step_runs
        ],
    }
    return json.dumps(data, indent=2, default=_serialize)


def runs_to_json(runs: list[JobRun]) -> str:
    """Serialize a list of JobRuns to JSON string."""
    data = [
        {
            "run_id": r.job_run_id,
            "job_name": r.job_name,
            "status": r.status.value,
        }
        for r in runs
    ]
    return json.dumps(data, indent=2, default=_serialize)
```

#### `__init__.py` — Re-exports publics

```python
"""CLI adapter — interface en ligne de commande pour PyWorkflow Engine.

Installation : ``pip install pyworkflow-engine[cli]``

Usage::

    pyworkflow --app myproject.workflows:engine job list
    pyworkflow --app myproject.workflows:engine run start etl-pipeline
"""

try:
    from pyworkflow_engine.adapters.cli.main import app
except ImportError as exc:
    raise ImportError(
        "Le CLI adapter nécessite les dépendances 'typer' et 'rich'. "
        "Installez-les avec : pip install pyworkflow-engine[cli]"
    ) from exc

__all__ = ["app"]
```

---

## Modifications requises dans le projet existant

### 1. `pyproject.toml` — Extra CLI et entrypoint

```toml
# Avant
cli = ["click>=8.0", "rich>=13.0"]

[project.scripts]
workflow = "pyworkflow_engine.cli.main:cli"

# Après
cli = ["typer>=0.9", "rich>=13.0"]

[project.scripts]
pyworkflow = "pyworkflow_engine.adapters.cli.main:app"
```

Changements :
- **click → typer** : Typer dépend de Click, donc pas de perte de compatibilité.
- **Entrypoint rename** : `workflow` → `pyworkflow` (plus explicite, pas de conflit avec d'autres packages).
- **Chemin corrigé** : `pyworkflow_engine.cli.main:cli` → `pyworkflow_engine.adapters.cli.main:app` (architecture hexagonale).

### 2. `pyproject.toml` — Extra `all` (aucun changement nécessaire)

L'extra `all` inclut déjà `cli`. Typer remplaçant Click, aucune modification.

### 3. Alias court (optionnel)

```toml
[project.scripts]
pyworkflow = "pyworkflow_engine.adapters.cli.main:app"
pwf = "pyworkflow_engine.adapters.cli.main:app"
```

L'alias `pwf` offre un raccourci pour l'usage quotidien. Optionnel, à décider selon les retours.

---

## Mapping commandes → fichiers → facade

| Commande | Fichier | Méthode facade | Formatter |
|---|---|---|---|
| `pyworkflow job list` | `commands/job.py::list_jobs()` | `engine.list_jobs()` | `formatters/tables.py::render_job_table()` |
| `pyworkflow job inspect <n>` | `commands/job.py::inspect_job()` | `engine.get_job(n)` | `formatters/trees.py::render_job_tree()` |
| `pyworkflow job validate <n>` | `commands/job.py::validate_job()` | `engine.validate_job(job)` | Inline Rich |
| `pyworkflow run start <j>` | `commands/run.py::start_run()` | `engine.run_with_persistence(j)` | `formatters/tables.py::render_run_result()` |
| `pyworkflow run status <id>` | `commands/run.py::run_status()` | `engine.get_job_run(id)` | `formatters/tables.py::render_run_status()` |
| `pyworkflow run history` | `commands/run.py::run_history()` | `engine.list_job_runs(...)` | `formatters/tables.py::render_run_history()` |

### Séparation des responsabilités

```
  commands/     →  orchestration CLI (args, options, routing)
       ↓
  loader.py     →  import dynamique du WorkflowEngine
       ↓
  facade.py     →  logique métier (domaine, engine)
       ↓
  formatters/   →  rendu visuel (Rich tables, trees, JSON)
```

Les commandes ne contiennent **aucune logique d'affichage**. Les formatters ne contiennent **aucune logique métier**. Cette séparation permet :
- De tester les commandes sans vérifier le rendu visuel
- De changer le format (`table` → `json`) via `--format` sans toucher aux commandes
- De réutiliser les formatters entre commandes

---

## Comparaison avec l'écosystème

| Aspect | Celery CLI | Airflow CLI | Prefect CLI | **PyWorkflow (proposé)** |
|---|---|---|---|---|
| Framework | Click | Click | Typer | **Typer** |
| Discovery | `--app module` | config file | API server | **`--app module` + env var** |
| Sub-commands | `celery worker`, `celery beat` | `airflow dags list` | `prefect flow-run` | **`pyworkflow job list`** |
| Output format | text only | table + json | table + json | **table + json** |
| DAG visualization | Non | Web UI | Web UI | **Rich Tree (terminal)** |
| Exit codes | Basiques | Basiques | Structurés | **Structurés (0-5)** |
| Live progress | Non | Web UI | Web UI | **`--watch` (Phase 2)** |

---

## Plan d'implémentation

### Phase 1 — Scaffolding et commandes essentielles (v0.8.0-alpha)

| Tâche | Fichier | Effort |
|---|---|---|
| `main.py` + callback global | `adapters/cli/main.py` | 30 min |
| `loader.py` (import dynamique) | `adapters/cli/loader.py` | 1h |
| `errors.py` (error handler) | `adapters/cli/errors.py` | 30 min |
| `callbacks.py` (version) | `adapters/cli/callbacks.py` | 15 min |
| `commands/job.py` (list, inspect, validate) | `adapters/cli/commands/job.py` | 2h |
| `commands/run.py` (start, status, history) | `adapters/cli/commands/run.py` | 2h |
| `formatters/tables.py` (tous les renderers) | `adapters/cli/formatters/tables.py` | 1h30 |
| `formatters/trees.py` (DAG tree) | `adapters/cli/formatters/trees.py` | 1h |
| `formatters/json_output.py` | `adapters/cli/formatters/json_output.py` | 30 min |
| `__init__.py` (re-export + guard) | `adapters/cli/__init__.py` | 15 min |
| Mise à jour `pyproject.toml` | `pyproject.toml` | 15 min |

### Phase 2 — Tests et polish (v0.8.0-beta)

| Tâche | Fichier | Effort |
|---|---|---|
| Tests unitaires (mock engine, CliRunner) | `tests/unit/adapters/cli/` | 3h |
| Tests `loader.py` (import dynamique) | `tests/unit/adapters/cli/test_loader.py` | 1h |
| Tests formatters (snapshot testing) | `tests/unit/adapters/cli/test_formatters.py` | 1h |
| `commands/executor.py` (list) | `adapters/cli/commands/executor.py` | 1h |
| `--watch` Live progress (Rich Live) | `commands/run.py` | 2h |
| Shell completion docs | `docs/integrations/cli.md` | 30 min |

### Phase 3 — Extensions (post v0.8.0)

| Tâche | Fichier | Effort |
|---|---|---|
| Config file discovery (`pyworkflow.toml`) | `adapters/cli/loader.py` | 2h |
| Auto-discovery des `@job` décorés | `adapters/cli/loader.py` | 2h |
| `dag` commande (ASCII DAG avancé) | `commands/job.py` | 1h |
| Alias `pwf` | `pyproject.toml` | 5 min |

### Effort total estimé : ~23h (Phase 1 : ~10h, Phase 2 : ~8h, Phase 3 : ~5h)

---

## Alternatives considérées

### Alternative A — Rester sur Click

Garder Click comme framework CLI.

**Pour** : Déjà déclaré dans `pyproject.toml`, très mature.
**Contre** :
- Plus verbeux (decorators `@click.option` vs type hints Typer)
- Pas d'intégration Rich native
- Pas d'auto-complétion shell intégrée
- L'écosystème moderne (FastAPI, Pydantic, etc.) converge vers Typer

**Verdict** : ❌ Rejetée — Typer est un superset de Click ; aucune perte, que des gains.

### Alternative B — Adapter CLI simple (un seul fichier)

Tout mettre dans `adapters/cli/main.py`.

**Pour** : Simple pour commencer.
**Contre** :
- Fichier monolithique (~500+ lignes) mêlant commands, formatters, loader, errors
- Impossible de tester les formatters indépendamment des commandes
- Incohérent avec la règle ADR-007 (adapter complexe = package dédié)
- La CLI remplit les 3 critères d'un adapter complexe

**Verdict** : ❌ Rejetée — viole les principes établis par ADR-007.

### Alternative C — CLI hors du package (outil séparé `pyworkflow-cli`)

Publier un package séparé.

**Pour** : Isolation totale, versionning indépendant.
**Contre** :
- Overhead de maintenance disproportionné
- L'écosystème Python (Django, Celery, Airflow) embarque la CLI dans le package principal
- L'entrypoint `[project.scripts]` est déjà défini dans `pyproject.toml`

**Verdict** : ❌ Rejetée — à reconsidérer uniquement si la CLI devient très volumineuse.

### Alternative D — Argparse pur (stdlib)

Utiliser argparse pour zéro dépendance même pour la CLI.

**Pour** : Cohérent avec la philosophie "zero deps".
**Contre** :
- Extrêmement verbeux pour des sub-commands imbriquées
- Pas de tables, pas de couleurs, pas de trees sans Rich
- La CLI est **opt-in** (`pip install pyworkflow-engine[cli]`) — l'extra justifie des dépendances

**Verdict** : ❌ Rejetée — la CLI est un extra optionnel, les dépendances sont acceptables.

---

## Conséquences

### Positives

- **Ergonomie** — sub-commands claires, auto-complétion, aide contextuelle Rich
- **Scriptabilité** — `--format json` + exit codes structurés permettent l'intégration dans des pipelines CI/CD
- **Testabilité** — séparation commands / formatters / loader ; chaque couche testable indépendamment avec `CliRunner`
- **Cohérence architecturale** — la CLI est un adapter qui dépend uniquement de la facade, comme tout adapter hexagonal
- **Extensibilité** — ajouter une commande = 1 fonction dans `commands/`, 1 formatter si besoin
- **Discovery standard** — pattern `--app module:attr` familier (Celery, Uvicorn, Flask)

### Négatives

- **Dépendance Typer** — ajoute ~2 packages (typer + click) à l'extra `cli`
- **Complexité structurelle** — 10+ fichiers pour la CLI vs 1 fichier pour un executor simple
- **Maintenance** — les formatters doivent suivre l'évolution des modèles (`Job`, `JobRun`)

### Risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Typer breaking change (pre-1.0) | Faible | Moyen | Pin `typer>=0.9,<1.0` ; Typer est quasi stable |
| Loader échoue sur des setups exotiques | Moyenne | Faible | Messages d'erreur clairs, fallback env var |
| Formatters désynchronisés avec les modèles | Moyenne | Faible | Tests snapshot, TYPE_CHECKING imports |

---

## Références

- [Typer documentation](https://typer.tiangolo.com/)
- [Rich documentation](https://rich.readthedocs.io/)
- [Celery CLI](https://docs.celeryq.dev/en/stable/reference/cli.html) — pattern `--app` discovery
- [Uvicorn CLI](https://www.uvicorn.org/) — pattern `module:app`
- [Click → Typer migration](https://typer.tiangolo.com/tutorial/first-steps/) — Typer est un superset de Click
- ADR-006 — Architecture hexagonale
- ADR-007 — Adapter complexe vs simple (règle de placement)
