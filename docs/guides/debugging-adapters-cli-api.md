# Débogage des adapters CLI & API — Journal de session (11 avril 2026)

Guide post-mortem documentant les cinq problèmes rencontrés lors de la mise
en service des adapters **CLI** (`pyworkflow`), **API** (FastAPI + uvicorn) et
**Celery** après leur implémentation initiale (ADR-007, ADR-008, ADR-011).

---

## Table des matières

1. [Contexte général](#1-contexte-général)
2. [Problème 1 — Test `is` identity sur une fonction cross-module](#2-problème-1--test-is-identity-sur-une-fonction-cross-module)
3. [Problème 2 — `examples.tui_demo` introuvable (`ModuleNotFoundError`)](#3-problème-2--examplestui_demo-introuvable-modulenotfounderror)
4. [Problème 3 — `engine.register()` n'existe pas](#4-problème-3--engineregister-nexiste-pas)
5. [Problème 4 — `RunStatus.SKIPPED` inexistant dans l'enum](#5-problème-4--runstatusskipped-inexistant-dans-lenum)
6. [Problème 5 — `api serve` toujours obligé de passer `--app`](#6-problème-5--api-serve-toujours-obligé-de-passer---app)
7. [Récapitulatif des fichiers modifiés](#7-récapitulatif-des-fichiers-modifiés)
8. [Leçons à retenir](#8-leçons-à-retenir)

---

## 1. Contexte général

### Ce qui venait d'être implémenté

| Adapter | ADR | Fichiers clés |
|---------|-----|---------------|
| API REST FastAPI + SQLite | ADR-011 | `adapters/api/` (18 fichiers) |
| Celery (worker distribué) | ADR-007 | `adapters/celery/` (5 fichiers) |
| CLI Typer + Rich | ADR-008 | `adapters/cli/` (13 fichiers) |

Les 535 tests existants passaient, et un smoke-test de l'API avait été validé
via `httpx + ASGITransport`. Mais au premier lancement **réel** en ligne de
commande, cinq problèmes se sont enchaînés.

### Environnement

```
Python 3.11 / macOS / zsh
pyworkflow-engine installé en mode éditable (pip install -e ".[api,cli]")
Tests : pytest 9.0.2 + pytest-asyncio + pytest-cov
```

---

## 2. Problème 1 — Test `is` identity sur une fonction cross-module

### Symptôme

```
FAILED tests/unit/test_celery_adapter.py::TestResolveHandler::test_resolves_top_level_function
AssertionError: assert <function sample_step_handler at 0x10c376e80> is sample_step_handler
```

### Diagnostic

Le test vérifiait qu'une fonction résolue dynamiquement **était** (`is`) le même
objet que celui importé en tête de fichier :

```python
# test_celery_adapter.py
def sample_step_handler() -> dict: ...

def test_resolves_top_level_function(self):
    handler = _resolve_handler("tests.unit.test_celery_adapter.sample_step_handler")
    assert handler is sample_step_handler   # ← FAUX en pratique
```

**Cause racine** : pytest cherche les tests dans `testpaths = ["tests"]`, sans
`pythonpath` configuré. Il insère donc `tests/` dans `sys.path` et importe le
fichier sous le nom de module `unit.test_celery_adapter`.

Quand `_resolve_handler` appelle ensuite
`importlib.import_module("tests.unit.test_celery_adapter")`, Python ne retrouve
pas ce nom dans `sys.modules` et **recharge** le module sous un nom différent.
Il y a alors deux objets `sample_step_handler` distincts en mémoire — le test
`is` échoue car `is` compare l'identité objet, pas la valeur.

```
sys.modules["unit.test_celery_adapter"].sample_step_handler   # id: 0x10c376e80
sys.modules["tests.unit.test_celery_adapter"].sample_step_handler  # id: 0x1097416c0
```

### Solution

**Deux corrections complémentaires :**

**a) `pyproject.toml`** — déclarer explicitement le chemin Python racine pour
que pytest importe toujours les modules depuis la racine du projet :

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]          # ← ajouté
```

**b) `tests/__init__.py`** — créer ce fichier (vide) pour faire de `tests/` un
package Python rooted à la racine. Sans lui, pytest ne peut pas construire un
chemin `tests.unit.*`.

```bash
touch tests/__init__.py
```

**c) `test_resolves_top_level_function`** — remplacer `is` par une comparaison
sémantique (`__qualname__` + `__module__`) car `is` est fragile dès qu'il y a
plusieurs entrées `sys.modules` :

```python
# Avant
assert handler is sample_step_handler

# Après
assert handler.__qualname__ == sample_step_handler.__qualname__
assert handler.__module__ == "tests.unit.test_celery_adapter"
```

### Leçon

> **Ne jamais utiliser `is` pour comparer des fonctions issues d'un `importlib.import_module()`.**
> Le rechargement de module (même accidentel) crée des objets distincts.
> Comparer `__qualname__` + `__module__` ou utiliser `==` si `__eq__` est défini.

---

## 3. Problème 2 — `examples.tui_demo` introuvable (`ModuleNotFoundError`)

### Symptôme

```bash
$ pyworkflow --app examples.tui_demo:engine tui
✗ Module introuvable : examples.tui_demo
  Vérifiez que le module est dans le PYTHONPATH.
```

### Diagnostic

La commande `pyworkflow` est un **script installé** (`pyproject.toml` →
`[project.scripts]`). Quand on le lance, Python exécute le binaire dans le
venv — la racine du projet n'est **pas** automatiquement dans `sys.path`,
contrairement à `python -m pyworkflow` ou à `python script.py`.

`examples/` est un répertoire à la racine du projet. Pour qu'il soit importable
en tant que `examples.tui_demo`, il faut que le répertoire *parent* (`./`) soit
dans `sys.path`. Or `loader.py` ne l'ajoutait pas.

### Solution

**`adapters/cli/loader.py`** — insérer `os.getcwd()` dans `sys.path` avant tout
`importlib.import_module()` :

```python
import sys, os

cwd = os.getcwd()
if cwd not in sys.path:
    sys.path.insert(0, cwd)   # ← permet d'importer depuis la racine du projet

module = importlib.import_module(module_path)
```

Amélioration du message d'erreur pour guider l'utilisateur :

```python
# Avant
"Vérifiez que le module est dans le PYTHONPATH."

# Après
f"Répertoire courant : {cwd}\n"
f"Lancez la commande depuis la racine du projet, ou :\n"
f"PYTHONPATH=. pyworkflow --app {resolved} ..."
```

### Leçon

> **Un script installé ne voit pas le CWD dans `sys.path`.** Toute CLI qui
> accepte des chemins de modules utilisateur doit insérer `os.getcwd()` elle-même,
> comme le font Uvicorn, Gunicorn et Celery.

---

## 4. Problème 3 — `engine.register()` n'existe pas

### Symptôme

```
✗ Erreur inattendue (AttributeError) : 'WorkflowEngine' object has no attribute 'register'
```

### Diagnostic

Le fichier exemple `examples/tui_demo.py` avait été écrit avec une API
hypothétique `engine.register(job)` qui n'a jamais existé dans la façade.
La méthode réelle s'appelle `save_job()`.

De plus, `save_job()` exige un backend de persistence configuré — appeler
`WorkflowEngine()` sans persistence et appeler `save_job()` lève :

```
WorkflowError: No persistence backend configured | Details: {'operation': 'save_job'}
```

### Solution

**`examples/tui_demo.py`** — trois corrections :

```python
# 1. Import ajouté
from pyworkflow_engine.adapters.storage.memory import InMemoryStorage

# 2. Méthode correcte
engine = WorkflowEngine()
engine.persistence = InMemoryStorage()   # ← persistence requise
engine.save_job(etl_job)                     # ← register() → save_job()
engine.save_job(monitoring_job)
```

`InMemoryStorage` est le bon choix pour un exemple/démo : zéro fichier,
zéro dépendance, fonctionne partout.

### Leçon

> **Les fichiers exemples sont du code de production.** Ils sont la première
> chose qu'un utilisateur va copier-coller. Tester leur import au même titre
> qu'un test unitaire (`python -c "import examples.tui_demo"` dans la CI).

---

## 5. Problème 4 — `RunStatus.SKIPPED` inexistant dans l'enum

### Symptôme

```
✗ Erreur inattendue (AttributeError) : SKIPPED
```

Levée par `formatters/tables.py` lors de `pyworkflow job list`.

### Diagnostic

`tables.py` définissait un dictionnaire de styles Rich indexé par valeur d'enum :

```python
_STATUS_STYLE: dict[RunStatus, str] = {
    ...
    RunStatus.SKIPPED: "[dim]↷ SKIPPED[/]",   # ← SKIPPED n'existe pas !
    ...
}
```

Or l'enum `RunStatus` dans `models/enums.py` ne contient pas `SKIPPED` :

```python
class RunStatus(str, Enum):
    PENDING, RUNNING, SUCCESS, FAILED, CANCELLED,
    WAITING_HUMAN, WAITING_EXTERNAL, SUSPENDED, TIMEOUT
```

Ce type de bug est **silencieux à l'import** car Python évalue les dict literals
paresseusement — l'`AttributeError` ne se produit qu'au moment où la ligne est
exécutée (lors du premier appel à `render_job_table`).

En plus de `SKIPPED` (inexistant), trois valeurs *existantes* manquaient :
`WAITING_HUMAN`, `WAITING_EXTERNAL`, `TIMEOUT`.

### Solution

**`adapters/cli/formatters/tables.py`** — corriger le dictionnaire pour qu'il
corresponde exactement à l'enum réel, sans valeur fantôme :

```python
_STATUS_STYLE: dict[RunStatus, str] = {
    RunStatus.SUCCESS:          "[bold green]✓ SUCCESS[/]",
    RunStatus.FAILED:           "[bold red]✗ FAILED[/]",
    RunStatus.RUNNING:          "[bold yellow]⟳ RUNNING[/]",
    RunStatus.PENDING:          "[dim]◯ PENDING[/]",
    RunStatus.SUSPENDED:        "[bold cyan]⏸ SUSPENDED[/]",
    RunStatus.CANCELLED:        "[dim red]✗ CANCELLED[/]",
    RunStatus.WAITING_HUMAN:    "[bold magenta]👤 WAITING_HUMAN[/]",
    RunStatus.WAITING_EXTERNAL: "[bold blue]⏳ WAITING_EXTERNAL[/]",
    RunStatus.TIMEOUT:          "[bold red]⏱ TIMEOUT[/]",
    # pas de SKIPPED — la valeur n'existe pas dans RunStatus
}
```

La fonction `_status()` utilise `.get(s, fallback)` ce qui aurait masqué
le problème à l'exécution... si Python avait seulement réussi à construire
le dict. L'erreur se produit bien **à la construction**, pas à l'accès.

### Leçon

> **Un `dict[MyEnum, ...]` dont les clés référencent des membres inexistants
> plante à la construction, pas à l'utilisation.** Ajouter un test qui vérifie
> que le dictionnaire de styles couvre exactement l'ensemble des valeurs de l'enum :
>
> ```python
> def test_status_style_covers_all_statuses():
>     from pyworkflow_engine.models.enums import RunStatus
>     from pyworkflow_engine.adapters.cli.formatters.tables import _STATUS_STYLE
>     assert set(_STATUS_STYLE.keys()) == set(RunStatus)
> ```

---

## 6. Problème 5 — `api serve` toujours obligé de passer `--app`

### Symptôme

```bash
$ pyworkflow api serve --port 8000
✗ Aucune application spécifiée.
  Utilisez --app module.path:engine ou définissez PYWORKFLOW_APP.
```

Et même avec `--app` :

```bash
$ pyworkflow --app examples.tui_demo:engine api serve --port 8000
INFO: Uvicorn running on http://127.0.0.1:8000
# → GET /        → 404 Not Found
# → GET /docs/   → 404 Not Found
```

### Diagnostic

**Sous-problème A — `--app` obligatoire pour l'API :**

Le loader `load_engine()` était appelé inconditionnellement dans `api serve`,
même quand l'utilisateur voulait juste un serveur REST vide (sans jobs
pré-enregistrés). La logique `--app` est un pattern hérité de la TUI/CLI (où
on inspecte *ses propres jobs*) mais elle ne s'applique pas au mode "serveur
autonome avec SQLite".

**Sous-problème B — `/docs/` → 404 :**

FastAPI était configuré avec `docs_url="/api/v1/docs"` mais aucune route
racine. Un utilisateur qui ouvre `http://localhost:8000` dans son navigateur
obtient un 404. De même, taper `/docs/` (l'URL par défaut de FastAPI) donne
un 404 car elle a été déplacée.

### Solution

**A) `adapters/cli/commands/api.py`** — rendre `--app` optionnel pour `api serve`.
Sans `--app`, créer un `WorkflowEngine` autonome avec `SQLiteStorage` :

```python
app_path = ctx.obj.get("app_path") if ctx.obj else None

if app_path:
    # Mode "avec application utilisateur" — charge l'instance existante
    engine = load_engine(app_path)
else:
    # Mode "standalone" — SQLite sur disque, aucun code utilisateur requis
    from pyworkflow_engine import WorkflowEngine
    from pyworkflow_engine.adapters.storage.sqlite import SQLiteStorage

    engine = WorkflowEngine()
    engine.persistence = SQLiteStorage(database_path=db)
```

**B) `adapters/api/app.py`** — ajouter une route `GET /` qui redirige vers
Swagger :

```python
from fastapi.responses import RedirectResponse

@app.get("/", include_in_schema=False)
async def _root() -> RedirectResponse:
    return RedirectResponse(url="/api/v1/docs")
```

**C) `adapters/cli/commands/api.py`** — afficher un banner Rich avec toutes
les URLs *avant* que uvicorn prenne la main :

```
╭───────────────────── ✓  PyWorkflow API ─────────────────────╮
│   🌐 Base URL  :  http://127.0.0.1:8000                     │
│   📖 Swagger   :  http://127.0.0.1:8000/api/v1/docs         │
│   📄 ReDoc     :  http://127.0.0.1:8000/api/v1/redoc        │
│   ⚙  OpenAPI   :  http://127.0.0.1:8000/api/v1/openapi.json │
│   ❤  Health    :  http://127.0.0.1:8000/api/v1/health       │
│   🗄  SQLite    :  workflow.db                               │
│   🔑 Auth      :  désactivée                                │
╰──────────────────── Ctrl+C pour arrêter ────────────────────╯
```

### Usage final

```bash
# Mode standalone — aucun code Python requis
pyworkflow api serve --port 8000

# Fichier SQLite explicite
pyworkflow api serve --db /var/data/prod.db --port 8000

# Mode applicatif — engine pré-configuré avec ses jobs
pyworkflow --app myproject.workflows:engine api serve --port 8000
```

### Leçon

> **Ne pas hériter mécaniquement du même pattern d'options pour des commandes
> qui ont des cas d'usage différents.** `--app` est indispensable pour inspecter
> *des jobs existants* (CLI/TUI), mais l'API REST doit pouvoir démarrer comme un
> serveur "zéro-config" (à la manière d'un `sqlite3 mydb.db`).

---

## 7. Récapitulatif des fichiers modifiés

| Fichier | Nature du changement |
|---------|----------------------|
| `pyproject.toml` | `pythonpath = ["."]` dans `[tool.pytest.ini_options]` |
| `tests/__init__.py` | Créé (vide) — fait de `tests/` un package rooted |
| `tests/unit/test_celery_adapter.py` | `is` → `__qualname__` + `__module__` |
| `examples/tui_demo.py` | `register()` → `save_job()` + `InMemoryStorage` |
| `adapters/cli/loader.py` | `sys.path.insert(0, cwd)` + meilleur message d'erreur |
| `adapters/cli/formatters/tables.py` | Suppression de `SKIPPED`, ajout des 3 statuts manquants |
| `adapters/cli/commands/api.py` | `--app` optionnel + standalone SQLite + banner Rich |
| `adapters/api/app.py` | Route `GET /` → redirect `/api/v1/docs` + import `RedirectResponse` |

---

## 8. Leçons à retenir

### 8.1 Tester les scripts installés séparément des tests unitaires

Un test `pytest` s'exécute dans un processus Python où `sys.path` inclut la
racine du projet. Un script installé (`pyworkflow`) s'exécute dans un contexte
différent. **Les deux doivent être testés**, idéalement via un test
d'intégration CLI :

```python
from typer.testing import CliRunner
from pyworkflow_engine.adapters.cli.main import app

def test_api_serve_standalone():
    runner = CliRunner()
    # Lance le serveur 0.1s puis l'arrête — vérifie que le démarrage fonctionne
    result = runner.invoke(app, ["api", "serve", "--help"])
    assert result.exit_code == 0
```

### 8.2 Synchroniser les dictionnaires de mapping enum à la compilation

Tout `dict[MyEnum, X]` littéral doit être couvert par un test d'exhaustivité :

```python
def test_status_style_is_exhaustive():
    assert set(_STATUS_STYLE) == set(RunStatus), (
        f"Valeurs manquantes : {set(RunStatus) - set(_STATUS_STYLE)}\n"
        f"Valeurs fantômes   : {set(_STATUS_STYLE) - set(RunStatus)}"
    )
```

Ce test aurait attrapé `SKIPPED` et les trois statuts manquants dès l'écriture.

### 8.3 Tester l'import de tous les fichiers exemples en CI

```python
# tests/unit/test_examples.py
import importlib, pytest

@pytest.mark.parametrize("mod", ["examples.tui_demo", "examples.basic_etl"])
def test_example_importable(mod):
    importlib.import_module(mod)   # ne doit pas lever d'exception
```

### 8.4 `sys.path` et `os.getcwd()` dans les CLIs orientées "loader"

Toute CLI qui accepte un chemin de module Python (`module:attr`) doit :
1. Insérer `os.getcwd()` dans `sys.path` avant d'importer
2. Documenter explicitement que la commande doit être lancée **depuis la racine
   du projet**
3. Afficher le `cwd` dans le message d'erreur `ModuleNotFoundError`

Références : uvicorn fait `sys.path.insert(0, ".")` dans son loader, Celery
aussi.

### 8.5 Design d'API CLI : distinguer "mode inspection" et "mode serveur"

| Mode | `--app` | Persistence |
|------|---------|-------------|
| `job list / inspect / tui` | **Requis** — inspecte vos jobs | Celle de votre engine |
| `api serve` (standalone) | **Optionnel** — serveur vide | SQLite auto sur `--db` |
| `api serve` (applicatif) | **Optionnel** — charge votre engine | Celle de votre engine |

Imposer `--app` à une commande "serveur" crée une friction inutile. Un serveur
REST doit pouvoir démarrer comme `sqlite3 mydb.db` : zéro configuration initiale.

### 8.6 Redirections et discoverabilité des URLs non-standard

Si `docs_url` est déplacé vers un chemin non-standard (`/api/v1/docs` au lieu
de `/docs`), **toujours** ajouter une redirection depuis la racine `/`. Un
utilisateur qui ouvre `http://localhost:8000` dans un navigateur s'attend à
trouver quelque chose d'utile, pas un 404.

```python
@app.get("/", include_in_schema=False)
async def _root() -> RedirectResponse:
    return RedirectResponse(url="/api/v1/docs")
```
