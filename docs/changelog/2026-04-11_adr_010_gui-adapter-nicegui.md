# ADR-010 — GUI Adapter : NiceGUI dans `adapters/gui/`

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-010                             |
| **Date**    | 11 avril 2026                       |
| **Statut**  | ✅ Décision prise                   |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (architecture hexagonale), ADR-007 (adapter complexe vs simple), ADR-008 (CLI adapter Typer + Rich), ADR-009 (TUI adapter Textual + Rich) |
| **Version cible** | v1.0.0                         |

---

## Contexte

### Situation actuelle

La CLI (ADR-008) couvre les cas **non-interactifs** (scriptabilité, CI/CD, pipes Unix). La TUI (ADR-009) couvre la **supervision interactive en terminal** (SSH, zero infra, live refresh). Le placeholder `adapters/gui/` n'existe pas encore mais est prévu dans l'arborescence hexagonale (ADR-006).

Le `pyproject.toml` ne déclare pas d'extra `gui`. Aucune interface graphique web/desktop n'est implémentée.

### Le besoin

La CLI et la TUI couvrent les développeurs et les opérateurs en terminal. Cependant, une catégorie entière de cas d'usage reste non couverte :

| Scénario | CLI (ADR-008) | TUI (ADR-009) | Besoin GUI |
|---|---|---|---|
| Visualisation graphique du DAG (nœuds, arêtes, dépendances) | ❌ Rich Tree statique | ⚠️ Tree textuel (pas de canvas) | ✅ Graphe interactif (zoom, pan, highlight) |
| Dashboard temps réel accessible via navigateur | ❌ | ⚠️ `textual serve` limité | ✅ Web UI native, multi-onglets |
| Tableaux triables/filtrables haute capacité | ❌ Sortie statique | ⚠️ DataTable Textual (perf limitée >1000 rows) | ✅ AG Grid — virtualisation, tri serveur, filtrage |
| Supervision multi-utilisateurs simultanée | ❌ | ❌ (1 session terminal) | ✅ WebSocket push, N sessions navigateur |
| Intégration future avec une API REST | ❌ | ❌ | ✅ FastAPI natif (même processus) |
| Accessibilité non-développeurs (product owners, managers) | ❌ Terminal requis | ❌ Terminal requis | ✅ Navigateur web standard |
| Visualisation de métriques et KPIs | ❌ | ⚠️ Limité (texte) | ✅ Charts interactifs (ECharts, Plotly) |
| Configuration de jobs via formulaires | ❌ CLI flags | ❌ | ✅ Formulaires dynamiques, validation temps réel |

### La question

1. Quel framework GUI / Web UI choisir pour Python en 2026 ?
2. Comment structurer l'adapter GUI dans l'architecture hexagonale ?
3. Comment la GUI s'articule-t-elle avec la CLI et la TUI existantes ?
4. Quelle stratégie de rendu : desktop natif, web serveur, ou hybride ?
5. Comment gérer le push en temps réel (statuts runs, progression steps) ?
6. Quelle est la stratégie de visualisation du DAG ?

---

## Analyse

### Pré-sélection — 11 frameworks évalués

L'écosystème Python offre un large éventail de frameworks GUI. Nous avons évalué **11 candidats** répartis en 4 catégories :

| Catégorie | Frameworks évalués |
|---|---|
| **Desktop natif** | Tkinter (stdlib), PyQt6/PySide6, wxPython, Kivy, DearPyGui, PyGObject, Toga |
| **Web — Python-first** | Flet, NiceGUI |
| **Web — data/ML oriented** | Streamlit, Gradio |

### Phase 1 : Élimination (11 → 4 finalistes)

#### Éliminés immédiatement

| Framework | Raison d'élimination |
|---|---|
| **Tkinter** | Apparence archaïque, pas de composant DataTable/DataGrid moderne, pas de rendu DAG, pas de WebSocket. Inadapté pour un dashboard professionnel en 2026. |
| **wxPython** | Dépendances natives lourdes (wxWidgets C++), installation complexe multi-plateforme, écosystème en déclin. Pas de rendu DAG intégré. |
| **Kivy** | Orienté mobile/tactile, paradigme OpenGL — surdimensionné pour un dashboard. API non-standard, courbe d'apprentissage élevée pour du simple CRUD/dashboard. |
| **PyGObject** (GTK) | Dépendance sur GTK/GLib (installation pénible hors Linux), communauté Python réduite, pas de composant DataGrid avancé. |
| **Toga** (BeeWare) | Ambitieux mais immature en 2026 — widgets limités (pas de DataGrid, pas de Tree, pas de graphe). Cible le packaging natif (iOS/Android), pas notre besoin. |
| **Streamlit** | Orienté data science / prototypage rapide. Modèle re-run complet à chaque interaction (pas de state granulaire). Pas de WebSocket push natif, pas de routage multi-pages robuste. Déjà prévu comme extra séparé (`streamlit`) pour les demos — pas comme GUI principale. |
| **Gradio** | Orienté démo ML (inputs → outputs). Aucun composant DataGrid, pas de DAG, pas de routage. Inadapté pour un dashboard d'orchestration. |

#### 4 finalistes retenus

| Finaliste | Catégorie | Forces principales |
|---|---|---|
| **PyQt6** | Desktop natif | Écosystème massif, QGraphicsScene pour DAG, QTableView performant |
| **DearPyGui** | Desktop natif | Rendu GPU (60fps), node editor intégré, API pythonique |
| **Flet** | Web — Python-first | Flutter UI, multi-plateforme (web/desktop/mobile), Material Design |
| **NiceGUI** | Web — Python-first | FastAPI natif, AG Grid, Mermaid/vis.js, WebSocket push |

### Phase 2 : Matrice de scoring pondérée (4 finalistes)

#### Critères et pondérations

Les poids reflètent les priorités du projet `pyworkflow-engine` :

| Critère | Poids | Justification |
|---|---|---|
| **Visualisation DAG** | ×5 | Cœur du besoin — un orchestrateur doit montrer le graphe |
| **DataTable/DataGrid** | ×4 | Listing jobs, runs, steps — le contenu principal du dashboard |
| **Temps réel (push)** | ×4 | Supervision live des runs — sans polling agressif |
| **Installation / poids** | ×3 | Cohérent avec l'esprit "léger" du projet |
| **Synergie FastAPI** | ×3 | Le futur adapter `api/` REST est prévu — partager le même serveur est un avantage majeur |
| **Multi-plateforme** | ×2 | Le web est universel ; le desktop est un bonus |
| **Courbe d'apprentissage** | ×2 | Productivité de l'équipe |
| **Communauté / maturité** | ×2 | Support long terme, ressources, écosystème |
| **Extensibilité** | ×1 | Capacité à ajouter des composants custom |

**Total maximum** : 26 critères-poids × 4 (score max) = **104 points**

#### Scores détaillés

##### Visualisation DAG (×5)

| Framework | Score | Justification |
|---|---|---|
| PyQt6 | 3/4 | `QGraphicsScene` + `QGraphicsView` pour DAG interactif — puissant mais **tout est à coder manuellement** (nœuds, arêtes, layout, algorithme de placement) |
| DearPyGui | 4/4 | **Node editor intégré** (`dpg.add_node_editor`) — nativement conçu pour les graphes. Le meilleur rendu technique brut |
| Flet | 1/4 | **Aucun composant graphe/DAG natif**. Canvas basique, pas de bibliothèque de graphes. Nécessiterait une intégration JavaScript custom |
| NiceGUI | 4/4 | **Mermaid.js** (`ui.mermaid()`) pour les DAG statiques + **vis.js** (via `ui.html()` / `ui.run_javascript()`) pour les graphes interactifs. Intégration directe de bibliothèques JS riches |

##### DataTable/DataGrid (×4)

| Framework | Score | Justification |
|---|---|---|
| PyQt6 | 3/4 | `QTableView` + `QAbstractTableModel` — performant (virtualisation native), tri, filtrage. Mais tout est manuel (modèle, delegate, headers) |
| DearPyGui | 2/4 | `dpg.add_table()` — basique, pas de virtualisation, pas de tri/filtre intégré. Tables GPU mais fonctionnalités limitées |
| Flet | 3/4 | `ft.DataTable` — Material Design, tri, pagination. Correct mais pas au niveau d'AG Grid |
| NiceGUI | 4/4 | **AG Grid** (`ui.aggrid()`) — le standard industrie. Virtualisation, tri serveur, filtrage, groupement, export CSV, thèmes, infinite scroll. ~2 lignes de code pour un grid complet |

##### Temps réel / push (×4)

| Framework | Score | Justification |
|---|---|---|
| PyQt6 | 2/4 | Signals/slots Qt — push intra-processus. Pas de WebSocket natif pour le multi-client. Threading requis pour le non-bloquant |
| DearPyGui | 1/4 | Pas de push natif. Boucle de rendu GPU à 60fps — le "refresh" est implicite mais **l'alimentation en données doit être manuelle** (polling thread) |
| Flet | 3/4 | `page.pubsub` pour le push inter-sessions. WebSocket sous-jacent. Correct mais pas natif FastAPI |
| NiceGUI | 4/4 | **WebSocket natif** (chaque client = connexion WS permanente). `ui.timer()` pour le polling, `app.storage` pour le state partagé, `ui.notify()` pour le push instantané. FastAPI SSE aussi disponible |

##### Installation / poids (×3)

| Framework | Score | Justification |
|---|---|---|
| PyQt6 | 1/4 | **~75 MB** installé (Qt runtime complet). Compilation C++ sur certaines plateformes. Installation lourde et lente |
| DearPyGui | 2/4 | **~25 MB** (rendu GPU). Wheels pré-compilées disponibles mais dépendance OpenGL |
| Flet | 3/4 | **~15 MB** (Flutter runtime + WebSocket server). Wheels pures Python + binaires légers |
| NiceGUI | 4/4 | **~8 MB** installé. Pur Python (FastAPI + Starlette + uvicorn). Pas de compilation, pas de runtime lourd. `pip install nicegui` ≈ 5 secondes |

##### Synergie FastAPI / future API adapter (×3)

| Framework | Score | Justification |
|---|---|---|
| PyQt6 | 0/4 | Aucune — monde Qt desktop, incompatible avec un serveur web |
| DearPyGui | 0/4 | Aucune — boucle de rendu GPU, pas de serveur HTTP |
| Flet | 1/4 | Serveur web Flet propriétaire — pas FastAPI, pas standard ASGI |
| NiceGUI | 4/4 | **NiceGUI EST FastAPI**. `app.native` expose directement l'app FastAPI. Ajouter des routes REST = `@app.get("/api/jobs")`. Le futur adapter `api/` peut vivre dans le même processus sans reverse proxy |

##### Multi-plateforme (×2)

| Framework | Score | Justification |
|---|---|---|
| PyQt6 | 3/4 | Desktop Linux/macOS/Windows natif. Pas de mode web (sauf QtWebEngine = Chromium embarqué) |
| DearPyGui | 2/4 | Desktop Linux/macOS/Windows. Pas de mode web. Dépendance GPU (pas de headless facile) |
| Flet | 4/4 | **Web + Desktop + Mobile** (Flutter). Le plus multi-plateforme objectivement |
| NiceGUI | 3/4 | **Web natif** (tout navigateur). Mode desktop via `ui.run(native=True)` (webview léger). Pas de mobile mais le web y répond |

##### Courbe d'apprentissage (×2)

| Framework | Score | Justification |
|---|---|---|
| PyQt6 | 1/4 | Qt est puissant mais complexe — signals/slots, modèle MVC Qt, QML vs Widgets, threading Qt. Documentation abondante mais courbe raide |
| DearPyGui | 3/4 | API pythonique et directe (style ImGui). Documentation correcte. Moins de concepts à maîtriser |
| Flet | 3/4 | Flutter-like mais en Python. Relativement intuitif. Documentation claire |
| NiceGUI | 4/4 | **API la plus concise**. `ui.table(...)`, `ui.button(...)`, `ui.mermaid(...)`. Documentation excellente, exemples abondants. Un développeur Python est productif en ~1h |

##### Communauté / maturité (×2)

| Framework | Score | Justification |
|---|---|---|
| PyQt6 | 4/4 | **30+ ans** d'écosystème Qt. Riverbank Computing. Stack Overflow massif. Le plus mature objectivement |
| DearPyGui | 2/4 | ~7k ★ GitHub. Communauté niche (data viz, outils internes). Maintenu mais petit |
| Flet | 3/4 | ~12k ★ GitHub. Soutenu par Flet Inc. Communauté active et croissante |
| NiceGUI | 3/4 | ~10k ★ GitHub. Maintenu par Zauberzeug GmbH. Release régulières, Discord actif. Croissance rapide depuis 2023 |

##### Extensibilité (×1)

| Framework | Score | Justification |
|---|---|---|
| PyQt6 | 4/4 | Écosystème Qt illimité — tout est possible avec assez d'effort |
| DearPyGui | 3/4 | Extensible via callbacks GPU. Plugin system pour custom widgets |
| Flet | 2/4 | Custom controls Flutter limités depuis Python. Nécessite Dart pour les widgets avancés |
| NiceGUI | 4/4 | **Injection JS/HTML/CSS directe** — `ui.html()`, `ui.run_javascript()`, `ui.add_css()`. Tout composant web (Vue.js, React, Web Components) est intégrable |

#### Tableau récapitulatif des scores

| Critère | Poids | PyQt6 | DearPyGui | Flet | **NiceGUI** |
|---|---|---|---|---|---|
| Visualisation DAG | ×5 | 15 | 20 | 5 | **20** |
| DataTable/DataGrid | ×4 | 12 | 8 | 12 | **16** |
| Temps réel (push) | ×4 | 8 | 4 | 12 | **16** |
| Installation / poids | ×3 | 3 | 6 | 9 | **12** |
| Synergie FastAPI | ×3 | 0 | 0 | 3 | **12** |
| Multi-plateforme | ×2 | 6 | 4 | 8 | 6 |
| Courbe d'apprentissage | ×2 | 2 | 6 | 6 | **8** |
| Communauté / maturité | ×2 | 8 | 4 | 6 | 6 |
| Extensibilité | ×1 | 4 | 3 | 2 | **4** |
| **TOTAL** | **/104** | **58** | **55** | **63** | **100** |
| **Pourcentage** | | **56%** | **53%** | **61%** | **96%** |

> **NiceGUI domine avec 100/104 (96%)**, loin devant Flet (61%), PyQt6 (56%) et DearPyGui (53%).

### Pourquoi NiceGUI — synthèse des avantages décisifs

#### 1. DAG visualization de premier ordre

```python
# Mermaid.js pour les DAG statiques — 3 lignes de code
ui.mermaid("""
graph TD
    A[extract] --> B[transform]
    B --> C[load]
    B --> D[validate]
""")

# vis.js pour les graphes interactifs (zoom, drag, highlight)
ui.html("""<div id="dag"></div>""")
ui.run_javascript("""
    const nodes = new vis.DataSet([...]);
    const edges = new vis.DataSet([...]);
    new vis.Network(document.getElementById('dag'), {nodes, edges}, options);
""")
```

Aucun autre framework Python n'offre Mermaid.js en une ligne. Pour un orchestrateur de workflows, c'est un avantage décisif.

#### 2. AG Grid — le standard industrie des DataGrids

```python
ui.aggrid({
    "columnDefs": [
        {"headerName": "Job", "field": "name", "sortable": True, "filter": True},
        {"headerName": "Status", "field": "status", "cellStyle": status_style},
        {"headerName": "Steps", "field": "step_count", "sortable": True},
    ],
    "rowData": jobs_data,
}).classes("w-full h-96")
```

Virtualisation (>100k lignes sans lag), tri serveur, filtrage avancé, groupement, export CSV — tout intégré. Incomparable avec les DataTables de Flet ou DearPyGui.

#### 3. FastAPI natif — pont vers le futur adapter `api/`

NiceGUI **est** une application FastAPI. Cela signifie :

```python
from nicegui import app, ui

# GUI — pages web
@ui.page("/")
def dashboard():
    ui.label("Dashboard")

# API REST — même processus, même port
@app.get("/api/v1/jobs")
async def api_list_jobs():
    return engine.list_jobs()
```

Le futur adapter `api/` (REST, prévu post-v1.0) pourra cohabiter dans le même processus. Pas de reverse proxy, pas de CORS, pas de port supplémentaire. C'est un avantage architectural unique.

#### 4. WebSocket push — temps réel sans polling

Chaque client navigateur maintient une connexion WebSocket permanente avec le serveur NiceGUI. Les mises à jour sont poussées instantanément :

```python
# Timer côté serveur — vérifie les changements et push automatiquement
ui.timer(2.0, lambda: update_run_table())

# Notification push instantanée
ui.notify(f"Run {run_id[:12]}… terminé ✓", type="positive")
```

Le polling n'est qu'un fallback. En Phase 2, un `EventBus` interne pourra déclencher des push sans timer.

#### 5. Installation ultra-légère

```bash
pip install nicegui  # ~8 MB, pur Python, 5 secondes
```

Comparé à PyQt6 (~75 MB, compilation C++), DearPyGui (~25 MB, GPU), ou même Flet (~15 MB, Flutter runtime). Cohérent avec la philosophie "léger" du projet.

### Adapter simple vs complexe (règle ADR-007)

| Critère ADR-007 | Évaluation pour la GUI |
|---|---|
| 2+ fichiers coordonnés | ✅ app + views + components + state + styles |
| Dépendance tierce avec configuration propre | ✅ NiceGUI (pages, routing, storage, theming) |
| Concepts spécifiques au-delà du port | ✅ Pages web, composants UI, WebSocket, CSS, state management |

→ La GUI est un **adapter complexe** → `adapters/gui/` (package dédié), conformément à ADR-007.

### Architecture NiceGUI : App → Pages → Components

```
┌──────────────────────────────────────────────────────────────┐
│               WorkflowGUI (NiceGUI App)                      │
│    Point d'entrée, config, state global,                     │
│    référence vers WorkflowEngine                             │
│                                                              │
│  ┌─────────────────────┐  ┌────────────────────┐             │
│  │   Dashboard Page    │  │  Job Detail Page   │             │
│  │   /                 │  │  /job/{name}       │             │
│  │                     │  │                    │             │
│  │ ┌─────────────────┐ │  │ ┌────────────────┐ │             │
│  │ │ JobTable        │ │  │ │ DAGGraph       │ │  ← Compo-  │
│  │ │ (AG Grid)       │ │  │ │ (Mermaid/vis)  │ │    sants   │
│  │ └─────────────────┘ │  │ └────────────────┘ │    réutil.  │
│  │ ┌─────────────────┐ │  │ ┌────────────────┐ │             │
│  │ │ RunTable        │ │  │ │ MetadataCard   │ │             │
│  │ │ (AG Grid)       │ │  │ └────────────────┘ │             │
│  │ └─────────────────┘ │  └────────────────────┘             │
│  │ ┌─────────────────┐ │                                     │
│  │ │ StatusBadges    │ │  ┌────────────────────┐             │
│  │ └─────────────────┘ │  │ Run Detail Page   │             │
│  └─────────────────────┘  │ /run/{id}         │             │
│                           │                    │             │
│  ┌─────────────────────┐  │ ┌────────────────┐ │             │
│  │  Run History Page   │  │ │ StepProgress   │ │             │
│  │  /runs              │  │ │ (AG Grid)      │ │             │
│  │                     │  │ └────────────────┘ │             │
│  │ ┌─────────────────┐ │  │ ┌────────────────┐ │             │
│  │ │ RunTable        │ │  │ │ LogViewer      │ │             │
│  │ │ (filtrable)     │ │  │ │ (ui.log)       │ │             │
│  │ └─────────────────┘ │  │ └────────────────┘ │             │
│  └─────────────────────┘  └────────────────────┘             │
│                                                              │
│  ┌─────────────────────┐                                     │
│  │  Settings Page      │                                     │
│  │  /settings          │                                     │
│  └─────────────────────┘                                     │
│                                                              │
│  ┌──────────────────────────────────────────────┐            │
│  │  Shared: Sidebar, Toolbar, StatusBadge       │            │
│  └──────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────┘
```

### Navigation — pages et routage

NiceGUI utilise le routage FastAPI natif. Chaque vue est une page avec une URL :

| URL | Page | Description |
|---|---|---|
| `/` | Dashboard | Vue d'ensemble — jobs + runs récents + badges de statut |
| `/job/{name}` | Job Detail | DAG graphique, metadata, steps, executor |
| `/runs` | Run History | Historique filtrable (job, statut, date) — AG Grid |
| `/run/{id}` | Run Detail | Steps live, logs streaming, actions (cancel, resume) |
| `/settings` | Settings | Configuration de l'instance (thème, refresh interval) |

La sidebar assure la navigation entre les pages. Les liens dans les tables (job name → `/job/{name}`, run ID → `/run/{id}`) permettent la drill-down.

### Refresh strategy — push vs polling

| Approche | Complexité | Latence | Recommandation |
|---|---|---|---|
| **Timer + push** (`ui.timer`) | Faible — timer NiceGUI natif + push WebSocket auto | 1-2s | ✅ **Phase 1** |
| **EventBus + push** | Moyenne — nécessite EventBus dans le core | Temps réel (<100ms) | ⏳ Phase 2 |
| **SSE (Server-Sent Events)** | Faible — FastAPI SSE natif | ~500ms | ⏳ Phase 2, pour les clients API |

En Phase 1, `ui.timer(2.0, callback)` interroge la facade et NiceGUI pousse automatiquement les changements via WebSocket. C'est plus performant que le polling HTTP car le client ne fait pas de requêtes — le serveur pousse les diffs UI.

### Intégration avec la CLI (ADR-008)

La GUI est **lancée depuis la CLI** via une sous-commande dédiée :

```bash
# Depuis la CLI
pyworkflow gui --app myproject.workflows:engine

# Avec port personnalisé
pyworkflow gui --app myproject.workflows:engine --port 8080

# Avec env var
export PYWORKFLOW_APP=myproject.workflows:engine
pyworkflow gui
```

Cela réutilise :
- Le **loader** (`load_engine()`) existant — pas de duplication
- Les **options globales** (`--app`, `--verbose`) du callback Typer root
- Le **mécanisme de discovery** (`PYWORKFLOW_APP` env var)

La sous-commande `gui` est **optionnelle** : elle n'apparaît dans `--help` que si `nicegui` est installé (import conditionnel dans `main.py`, pattern ADR-008/009).

### Comparaison avec l'écosystème workflow

| Aspect | Airflow | Prefect | Dagster | Luigi | Temporal | **PyWorkflow (proposé)** |
|---|---|---|---|---|---|---|
| Web UI | ✅ Flask lourd | ✅ React SPA | ✅ React SPA | ⚠️ Tornado basique | ✅ React SPA | ✅ NiceGUI (Python-only) |
| DAG visualization | ✅ D3.js | ✅ React Flow | ✅ Custom React | ⚠️ Graphviz statique | ❌ | ✅ Mermaid + vis.js |
| Real-time updates | ✅ Polling | ✅ WebSocket | ✅ GraphQL subscriptions | ❌ Refresh manuel | ✅ gRPC | ✅ WebSocket natif |
| API REST intégrée | ✅ Séparé | ✅ Séparé | ✅ GraphQL | ❌ | ✅ gRPC | ✅ **Même processus** (FastAPI) |
| Infra requise | Webserver + scheduler + DB | Server + DB | Dagit + daemon | Scheduler | Server + DB | **Aucune** — `pyworkflow gui` |
| Frontend stack | Python + JS/React | TypeScript + React | TypeScript + React | Python | TypeScript + React | **Python uniquement** |
| TUI native | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (ADR-009) |

**Avantage clé** : PyWorkflow est le seul orchestrateur offrant CLI + TUI + GUI (web) en **Python pur**, sans frontend JavaScript séparé, et sans infrastructure obligatoire.

---

## Décision

### La GUI vit dans `adapters/gui/` — adapter complexe, NiceGUI

### Extra `pyproject.toml`

```toml
[project.optional-dependencies]
# ...existing extras...
gui = ["nicegui>=2.0"]
```

L'extra `all` doit inclure `gui` :

```toml
all = [
    "pyworkflow-engine[django,fastapi,celery,sqlalchemy,postgresql,mysql,snowflake,streamlit,structlog,cli,tui,gui]",
]
```

### Structure cible

```
adapters/gui/
├── __init__.py           ← re-export WorkflowGUI, lazy import guard (pattern ADR-008/009)
├── app.py                ← WorkflowGUI — point d'entrée NiceGUI, config, launch
├── config.py             ← GUIConfig dataclass — port, host, title, theme, refresh_interval
├── state.py              ← GUIState — state management réactif, cache facade calls
├── views/
│   ├── __init__.py
│   ├── dashboard.py      ← Page "/" — vue d'ensemble (jobs + runs récents + badges)
│   ├── job_detail.py     ← Page "/job/{name}" — DAG graphique + metadata + steps
│   ├── run_detail.py     ← Page "/run/{id}" — steps live + logs + actions
│   ├── run_history.py    ← Page "/runs" — historique filtrable AG Grid
│   └── settings.py       ← Page "/settings" — configuration thème et refresh
├── components/
│   ├── __init__.py
│   ├── job_table.py      ← AG Grid des jobs enregistrés
│   ├── run_table.py      ← AG Grid des runs (statuts colorés)
│   ├── step_progress.py  ← AG Grid des steps d'un run (live update)
│   ├── dag_graph.py      ← Mermaid.js (statique) + vis.js (interactif) pour le DAG
│   ├── log_viewer.py     ← ui.log() pour les logs en streaming
│   ├── status_badge.py   ← Badges colorés pour les statuts (RunStatus → chip)
│   ├── toolbar.py        ← Barre d'outils (refresh, actions contextuelles)
│   └── sidebar.py        ← Sidebar de navigation entre pages
├── styles/
│   ├── __init__.py
│   └── theme.py          ← Configuration du thème NiceGUI (couleurs, dark mode, brand)
└── assets/
    └── fonts/            ← Polices custom (optionnel)
```

### Contrat de chaque fichier

#### `app.py` — Point d'entrée NiceGUI

```python
"""WorkflowGUI — interface web pour PyWorkflow Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.facade import WorkflowEngine

from pyworkflow_engine.adapters.gui.config import GUIConfig
from pyworkflow_engine.adapters.gui.state import GUIState


class WorkflowGUI:
    """Application web NiceGUI pour la supervision de workflows.

    Args:
        engine: Instance WorkflowEngine résolue par le loader CLI.
        config: Configuration optionnelle (port, host, thème).

    Usage::

        from pyworkflow_engine.adapters.gui import WorkflowGUI
        gui = WorkflowGUI(engine)
        gui.run()  # Ouvre http://localhost:8080
    """

    def __init__(
        self,
        engine: WorkflowEngine,
        config: GUIConfig | None = None,
    ) -> None:
        self.engine = engine
        self.config = config or GUIConfig()
        self.state = GUIState(engine)

    def _setup_pages(self) -> None:
        """Enregistre les pages NiceGUI (routage FastAPI)."""
        from nicegui import ui

        from pyworkflow_engine.adapters.gui.views.dashboard import dashboard_page
        from pyworkflow_engine.adapters.gui.views.job_detail import job_detail_page
        from pyworkflow_engine.adapters.gui.views.run_detail import run_detail_page
        from pyworkflow_engine.adapters.gui.views.run_history import run_history_page
        from pyworkflow_engine.adapters.gui.views.settings import settings_page

        @ui.page("/")
        def _dashboard() -> None:
            dashboard_page(self.state)

        @ui.page("/job/{name}")
        def _job_detail(name: str) -> None:
            job_detail_page(self.state, name)

        @ui.page("/run/{run_id}")
        def _run_detail(run_id: str) -> None:
            run_detail_page(self.state, run_id)

        @ui.page("/runs")
        def _run_history() -> None:
            run_history_page(self.state)

        @ui.page("/settings")
        def _settings() -> None:
            settings_page(self.state, self.config)

    def run(self) -> None:
        """Lance le serveur NiceGUI (bloquant)."""
        from pyworkflow_engine.adapters.gui.styles.theme import apply_theme

        apply_theme(self.config)
        self._setup_pages()

        from nicegui import ui

        ui.run(
            host=self.config.host,
            port=self.config.port,
            title=self.config.title,
            reload=False,
            show=self.config.open_browser,
        )
```

**Contrat** :
- Reçoit une instance `WorkflowEngine` — **jamais** de `--app` path (le loader est la responsabilité de la CLI ou de l'appelant)
- `GUIState` encapsule l'accès à la facade + le cache réactif
- Les pages sont des fonctions (pas des classes) — idiomatique NiceGUI
- `run()` est bloquant (uvicorn event loop) — appelé en dernier

#### `config.py` — Configuration de la GUI

```python
"""Configuration de la GUI NiceGUI."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GUIConfig:
    """Configuration de l'interface web.

    Tous les champs ont des valeurs par défaut sensées.
    Surchargeable via les flags CLI ou un fichier de config futur.
    """

    host: str = "127.0.0.1"
    port: int = 8080
    title: str = "PyWorkflow Engine"
    dark_mode: bool = True
    refresh_interval: float = 2.0  # secondes — fréquence du timer
    open_browser: bool = True
    primary_color: str = "#4A90D9"
    page_size: int = 50  # lignes par défaut dans les AG Grids
```

#### `state.py` — State management réactif

```python
"""State management pour la GUI — cache et accès facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.facade import WorkflowEngine
    from pyworkflow_engine.models import Job, JobRun


class GUIState:
    """State centralisé, interroge la facade et expose les données aux views.

    Le state est **par serveur** (pas par client) — adapté à un
    usage mono-utilisateur ou équipe restreinte. Pour le multi-tenant,
    un adapter ``api/`` dédié est prévu.
    """

    def __init__(self, engine: WorkflowEngine) -> None:
        self._engine = engine

    @property
    def engine(self) -> WorkflowEngine:
        return self._engine

    def list_jobs(self) -> list[Job]:
        return self._engine.list_jobs()

    def list_runs(self, *, limit: int = 50) -> list[JobRun]:
        return self._engine.list_job_runs(limit=limit)

    def get_job(self, name: str) -> Job | None:
        return self._engine.get_job(name)

    def get_run(self, run_id: str) -> JobRun | None:
        return self._engine.get_job_run(run_id)

    def get_runs_for_job(
        self,
        job_name: str,
        *,
        limit: int = 50,
    ) -> list[JobRun]:
        return self._engine.list_job_runs(job_name=job_name, limit=limit)

    def run_job(self, job_name: str, *, context: dict | None = None) -> JobRun:
        return self._engine.run(job_name, context=context or {})

    def cancel_run(self, run_id: str) -> bool:
        return self._engine.cancel(run_id)

    def resume_run(
        self,
        run_id: str,
        *,
        outputs: dict | None = None,
    ) -> JobRun:
        return self._engine.resume(run_id, outputs=outputs)
```

**Contrat** :
- Pas de cache intelligent en Phase 1 (chaque appel = appel facade direct)
- En Phase 2, ajout possible d'un cache TTL léger ou d'un mécanisme de dirty-checking
- Les views n'accèdent **jamais** directement à la facade — toujours via `GUIState`

#### `views/dashboard.py` — Dashboard principal

```python
"""Dashboard — page d'accueil avec vue d'ensemble."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.state import GUIState


def dashboard_page(state: GUIState) -> None:
    """Construit la page dashboard."""
    from nicegui import ui

    from pyworkflow_engine.adapters.gui.components.job_table import render_job_table
    from pyworkflow_engine.adapters.gui.components.run_table import render_run_table
    from pyworkflow_engine.adapters.gui.components.sidebar import render_sidebar
    from pyworkflow_engine.adapters.gui.components.status_badge import render_status_summary
    from pyworkflow_engine.adapters.gui.components.toolbar import render_toolbar

    render_sidebar()
    with ui.column().classes("w-full p-4 ml-64"):
        render_toolbar("Dashboard")
        render_status_summary(state)

        with ui.row().classes("w-full gap-4"):
            with ui.card().classes("flex-1"):
                ui.label("📋 Jobs enregistrés").classes("text-lg font-bold")
                job_grid = render_job_table(state)
            with ui.card().classes("flex-1"):
                ui.label("📊 Runs récents").classes("text-lg font-bold")
                run_grid = render_run_table(state)

        # Auto-refresh via timer
        def refresh() -> None:
            job_grid.options["rowData"] = _jobs_to_rows(state)
            job_grid.update()
            run_grid.options["rowData"] = _runs_to_rows(state)
            run_grid.update()

        ui.timer(state.engine.config.refresh_interval if hasattr(state.engine, "config") else 2.0, refresh)
```

#### `views/job_detail.py` — Détail d'un job avec DAG

```python
"""Job Detail — page de détail avec visualisation DAG."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.state import GUIState


def job_detail_page(state: GUIState, job_name: str) -> None:
    """Construit la page de détail d'un job."""
    from nicegui import ui

    from pyworkflow_engine.adapters.gui.components.dag_graph import render_dag
    from pyworkflow_engine.adapters.gui.components.sidebar import render_sidebar

    job = state.get_job(job_name)
    render_sidebar()
    with ui.column().classes("w-full p-4 ml-64"):
        if job is None:
            ui.label(f"❌ Job '{job_name}' introuvable").classes("text-red-500 text-xl")
            return

        ui.label(f"📋 {job.name}").classes("text-2xl font-bold")

        with ui.row().classes("w-full gap-4"):
            # Metadata card
            with ui.card().classes("flex-1"):
                ui.label("Metadata").classes("text-lg font-bold")
                with ui.grid(columns=2).classes("gap-2"):
                    ui.label("Version:").classes("font-bold")
                    ui.label(job.version or "—")
                    ui.label("Steps:").classes("font-bold")
                    ui.label(str(len(job.steps)))
                    ui.label("Executor:").classes("font-bold")
                    ui.label(
                        job.default_executor.value
                        if job.default_executor
                        else "local"
                    )
                    ui.label("Description:").classes("font-bold")
                    ui.label(job.description or "—")

            # DAG visualization
            with ui.card().classes("flex-1"):
                ui.label("🔀 DAG").classes("text-lg font-bold")
                render_dag(job)

        # Actions
        with ui.row().classes("gap-2 mt-4"):
            ui.button(
                "▶ Lancer",
                on_click=lambda: _run_job(state, job_name),
            ).props("color=positive")
            ui.button(
                "📊 Historique",
                on_click=lambda: ui.navigate.to(f"/runs?job={job_name}"),
            )


def _run_job(state: GUIState, job_name: str) -> None:
    from nicegui import ui

    try:
        run = state.run_job(job_name)
        ui.notify(f"Run {run.job_run_id[:12]}… lancé ✓", type="positive")
        ui.navigate.to(f"/run/{run.job_run_id}")
    except Exception as e:
        ui.notify(f"Échec : {e}", type="negative")
```

#### `views/run_detail.py` — Suivi run en temps réel

```python
"""Run Detail — suivi d'un run en temps réel."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.state import GUIState


def run_detail_page(state: GUIState, run_id: str) -> None:
    """Construit la page de détail d'un run avec live refresh."""
    from nicegui import ui

    from pyworkflow_engine.adapters.gui.components.log_viewer import render_log_viewer
    from pyworkflow_engine.adapters.gui.components.sidebar import render_sidebar
    from pyworkflow_engine.adapters.gui.components.step_progress import render_step_progress

    render_sidebar()
    with ui.column().classes("w-full p-4 ml-64"):
        run = state.get_run(run_id)
        if run is None:
            ui.label(f"❌ Run '{run_id}' introuvable").classes("text-red-500 text-xl")
            return

        ui.label(f"🔍 Run {run_id[:12]}…").classes("text-2xl font-bold")

        # Status + metadata
        from pyworkflow_engine.adapters.gui.components.status_badge import status_chip

        with ui.row().classes("gap-4 items-center"):
            status_chip(run.status)
            ui.label(f"Job: {run.job_name}").classes("font-bold")
            if run.start_time:
                ui.label(
                    f"Début: {run.start_time.strftime('%Y-%m-%d %H:%M:%S')}"
                )

        with ui.row().classes("w-full gap-4 mt-4"):
            # Steps progress
            with ui.card().classes("flex-1"):
                ui.label("⚙️ Steps").classes("text-lg font-bold")
                step_grid = render_step_progress(run.step_runs)

            # Logs
            with ui.card().classes("flex-1"):
                ui.label("📜 Logs").classes("text-lg font-bold")
                log_viewer = render_log_viewer()

        # Actions
        with ui.row().classes("gap-2 mt-4"):
            ui.button(
                "✗ Annuler",
                on_click=lambda: _cancel(state, run_id),
            ).props("color=negative")
            ui.button(
                "↻ Reprendre",
                on_click=lambda: _resume(state, run_id),
            ).props("color=warning")

        # Live refresh
        def refresh() -> None:
            updated = state.get_run(run_id)
            if updated:
                step_grid.options["rowData"] = _steps_to_rows(updated.step_runs)
                step_grid.update()

        ui.timer(1.0, refresh)


def _cancel(state: GUIState, run_id: str) -> None:
    from nicegui import ui

    if state.cancel_run(run_id):
        ui.notify(f"Run {run_id[:12]}… annulé", type="warning")
    else:
        ui.notify("Impossible d'annuler ce run", type="negative")


def _resume(state: GUIState, run_id: str) -> None:
    from nicegui import ui

    try:
        state.resume_run(run_id)
        ui.notify(f"Run {run_id[:12]}… repris", type="positive")
    except Exception as e:
        ui.notify(f"Échec reprise : {e}", type="negative")
```

#### `components/dag_graph.py` — Visualisation DAG

```python
"""DAG visualization — Mermaid.js et vis.js pour les graphes de jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job


def render_dag(job: Job) -> None:
    """Rend le DAG du job en Mermaid.js.

    Phase 1 : Mermaid.js (statique, déclaratif).
    Phase 2 : vis.js (interactif, zoom, drag, highlight).
    """
    from nicegui import ui

    mermaid_code = _job_to_mermaid(job)
    ui.mermaid(mermaid_code).classes("w-full")


def _job_to_mermaid(job: Job) -> str:
    """Convertit un Job en syntaxe Mermaid graph TD."""
    lines = ["graph TD"]
    for step in job.steps:
        # Nœud avec label
        node_id = step.name.replace(" ", "_").replace("-", "_")
        lines.append(f"    {node_id}[{step.name}]")

        # Arêtes pour les dépendances
        if step.depends_on:
            for dep in step.depends_on:
                dep_id = dep.replace(" ", "_").replace("-", "_")
                lines.append(f"    {dep_id} --> {node_id}")

    return "\n".join(lines)
```

**Contrat** :
- Phase 1 : Mermaid.js — déclaratif, zéro JS custom, rendu SVG
- Phase 2 : vis.js — interactif (zoom, drag, click-to-inspect), nécessite `ui.run_javascript()`
- La conversion `Job → Mermaid` est une pure transformation de données, testable unitairement

#### `components/job_table.py` — AG Grid des jobs

```python
"""JobTable component — AG Grid des jobs enregistrés."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.state import GUIState


def render_job_table(state: GUIState) -> object:
    """Rend un AG Grid des jobs enregistrés.

    Returns:
        L'objet AG Grid NiceGUI (pour le refresh ultérieur via timer).
    """
    from nicegui import ui

    jobs = state.list_jobs()
    row_data = [
        {
            "name": job.name,
            "steps": len(job.steps),
            "version": job.version or "—",
            "executor": (
                job.default_executor.value if job.default_executor else "local"
            ),
            "description": job.description or "—",
        }
        for job in jobs
    ]

    grid = ui.aggrid(
        {
            "columnDefs": [
                {
                    "headerName": "Job",
                    "field": "name",
                    "sortable": True,
                    "filter": True,
                    "cellRenderer": "agGroupCellRenderer",
                },
                {"headerName": "Steps", "field": "steps", "sortable": True, "width": 100},
                {"headerName": "Version", "field": "version", "sortable": True, "width": 120},
                {"headerName": "Executor", "field": "executor", "filter": True, "width": 120},
                {"headerName": "Description", "field": "description", "flex": 1},
            ],
            "rowData": row_data,
            "rowSelection": "single",
            "animateRows": True,
        }
    ).classes("w-full h-96")

    # Navigation vers le détail au clic
    async def on_row_click(e) -> None:
        job_name = e.args["data"]["name"]
        ui.navigate.to(f"/job/{job_name}")

    grid.on("cellClicked", on_row_click)
    return grid
```

#### `components/run_table.py` — AG Grid des runs

```python
"""RunTable component — AG Grid des runs avec statuts colorés."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.state import GUIState

from pyworkflow_engine.models.enums import RunStatus

STATUS_COLORS: dict[RunStatus, str] = {
    RunStatus.SUCCESS:   "#4CAF50",  # vert
    RunStatus.FAILED:    "#F44336",  # rouge
    RunStatus.RUNNING:   "#FF9800",  # orange
    RunStatus.PENDING:   "#9E9E9E",  # gris
    RunStatus.SUSPENDED: "#2196F3",  # bleu
    RunStatus.SKIPPED:   "#607D8B",  # gris-bleu
    RunStatus.CANCELLED: "#E91E63",  # rose
}


def render_run_table(state: GUIState, *, limit: int = 50) -> object:
    """Rend un AG Grid des runs récents.

    Returns:
        L'objet AG Grid NiceGUI (pour le refresh ultérieur via timer).
    """
    from nicegui import ui

    runs = state.list_runs(limit=limit)
    row_data = _runs_to_rows(runs)

    grid = ui.aggrid(
        {
            "columnDefs": [
                {
                    "headerName": "Run ID",
                    "field": "run_id_short",
                    "sortable": True,
                    "width": 140,
                },
                {
                    "headerName": "Job",
                    "field": "job_name",
                    "sortable": True,
                    "filter": True,
                },
                {
                    "headerName": "Statut",
                    "field": "status",
                    "sortable": True,
                    "filter": True,
                    "cellStyle": {"function": _status_cell_style_js()},
                },
                {"headerName": "Début", "field": "started", "sortable": True},
                {"headerName": "Durée", "field": "duration", "sortable": True, "width": 120},
            ],
            "rowData": row_data,
            "rowSelection": "single",
            "animateRows": True,
        }
    ).classes("w-full h-96")

    # Navigation vers le détail au clic
    async def on_row_click(e) -> None:
        run_id = e.args["data"]["run_id"]
        ui.navigate.to(f"/run/{run_id}")

    grid.on("cellClicked", on_row_click)
    return grid


def _runs_to_rows(runs: list) -> list[dict]:
    """Convertit les JobRun en row data pour AG Grid."""
    rows = []
    for run in runs:
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
        duration = (
            f"{dur_ms}ms" if dur_ms and dur_ms < 1000
            else f"{dur_ms / 1000:.2f}s" if dur_ms
            else "—"
        )
        rows.append(
            {
                "run_id": run.job_run_id,
                "run_id_short": run.job_run_id[:12] + "…",
                "job_name": run.job_name,
                "status": run.status.value,
                "started": started,
                "duration": duration,
            }
        )
    return rows


def _status_cell_style_js() -> str:
    """Retourne une fonction JS pour colorier les cellules de statut."""
    return """
        function(params) {
            const colors = {
                'SUCCESS': '#4CAF50',
                'FAILED': '#F44336',
                'RUNNING': '#FF9800',
                'PENDING': '#9E9E9E',
                'SUSPENDED': '#2196F3',
                'SKIPPED': '#607D8B',
                'CANCELLED': '#E91E63',
            };
            const color = colors[params.value] || '#FFFFFF';
            return {
                'color': color,
                'fontWeight': 'bold',
            };
        }
    """
```

#### `components/status_badge.py` — Badges de statut

```python
"""StatusBadge component — chips colorés pour les statuts."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.state import GUIState
    from pyworkflow_engine.models.enums import RunStatus


STATUS_CONFIG: dict[str, tuple[str, str, str]] = {
    # status_value: (label, color, icon)
    "SUCCESS":   ("Success",   "positive", "check_circle"),
    "FAILED":    ("Failed",    "negative", "error"),
    "RUNNING":   ("Running",   "warning",  "play_circle"),
    "PENDING":   ("Pending",   "grey",     "schedule"),
    "SUSPENDED": ("Suspended", "info",     "pause_circle"),
    "SKIPPED":   ("Skipped",   "grey-7",   "skip_next"),
    "CANCELLED": ("Cancelled", "pink",     "cancel"),
}


def status_chip(status: RunStatus) -> None:
    """Rend un chip Quasar coloré pour un RunStatus."""
    from nicegui import ui

    label, color, icon = STATUS_CONFIG.get(
        status.value, (status.value, "grey", "help")
    )
    ui.chip(label, color=color, icon=icon)


def render_status_summary(state: GUIState) -> None:
    """Rend une ligne de badges résumant les compteurs de statut."""
    from nicegui import ui

    runs = state.list_runs(limit=1000)
    from collections import Counter

    counts = Counter(run.status.value for run in runs)

    with ui.row().classes("gap-2 mb-4"):
        for status_val, (label, color, icon) in STATUS_CONFIG.items():
            count = counts.get(status_val, 0)
            if count > 0:
                ui.chip(
                    f"{label}: {count}",
                    color=color,
                    icon=icon,
                ).props("outline")
```

#### `components/step_progress.py` — AG Grid des steps live

```python
"""StepProgress component — AG Grid des steps d'un run en temps réel."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.models.run import StepRun


def render_step_progress(step_runs: list[StepRun]) -> object:
    """Rend un AG Grid des steps d'un run.

    Returns:
        L'objet AG Grid NiceGUI (pour le refresh ultérieur via timer).
    """
    from nicegui import ui

    row_data = _steps_to_rows(step_runs)

    grid = ui.aggrid(
        {
            "columnDefs": [
                {"headerName": "Step", "field": "name", "sortable": True},
                {
                    "headerName": "Statut",
                    "field": "status",
                    "sortable": True,
                    "cellStyle": {"function": _status_cell_style_js()},
                },
                {"headerName": "Durée", "field": "duration", "sortable": True, "width": 120},
                {"headerName": "Erreur", "field": "error", "flex": 1},
            ],
            "rowData": row_data,
            "animateRows": True,
        }
    ).classes("w-full h-64")
    return grid


def _steps_to_rows(step_runs: list) -> list[dict]:
    """Convertit les StepRun en row data pour AG Grid."""
    rows = []
    for sr in step_runs:
        duration = (
            f"{sr.duration_ms}ms" if sr.duration_ms and sr.duration_ms < 1000
            else f"{sr.duration_ms / 1000:.2f}s" if sr.duration_ms
            else "—"
        )
        rows.append(
            {
                "name": sr.step_name,
                "status": sr.status.value,
                "duration": duration,
                "error": sr.error or "—",
            }
        )
    return rows


def _status_cell_style_js() -> str:
    """Fonction JS pour colorier les statuts des steps."""
    return """
        function(params) {
            const colors = {
                'SUCCESS': '#4CAF50',
                'FAILED': '#F44336',
                'RUNNING': '#FF9800',
                'PENDING': '#9E9E9E',
                'SUSPENDED': '#2196F3',
                'SKIPPED': '#607D8B',
                'CANCELLED': '#E91E63',
            };
            return {color: colors[params.value] || '#FFF', fontWeight: 'bold'};
        }
    """
```

#### `components/log_viewer.py` — Logs en streaming

```python
"""LogViewer component — affichage des logs en temps réel."""

from __future__ import annotations


def render_log_viewer() -> object:
    """Rend un widget de logs scrollable.

    Phase 1 : ui.log() — simple, auto-scroll.
    Phase 2 : log enrichi avec niveaux, filtrage, et couleurs.

    Returns:
        L'objet log NiceGUI (pour le push ultérieur).
    """
    from nicegui import ui

    log = ui.log(max_lines=500).classes("w-full h-64")
    return log
```

#### `components/toolbar.py` — Barre d'outils

```python
"""Toolbar component — barre d'outils contextuelle."""

from __future__ import annotations


def render_toolbar(title: str) -> None:
    """Rend la barre d'outils en haut de chaque page."""
    from nicegui import ui

    with ui.row().classes("w-full items-center justify-between mb-4"):
        ui.label(title).classes("text-3xl font-bold")
        with ui.row().classes("gap-2"):
            ui.button(
                icon="refresh",
                on_click=lambda: ui.navigate.to(ui.context.client.page.path),
            ).props("flat round")
```

#### `components/sidebar.py` — Navigation latérale

```python
"""Sidebar component — navigation entre les pages."""

from __future__ import annotations


def render_sidebar() -> None:
    """Rend la sidebar de navigation."""
    from nicegui import ui

    with ui.left_drawer(value=True).classes("bg-gray-900 text-white"):
        ui.label("PyWorkflow").classes("text-xl font-bold p-4")
        ui.separator()

        with ui.column().classes("p-2 gap-1"):
            _nav_item("📊", "Dashboard", "/")
            _nav_item("📋", "Jobs", "/")
            _nav_item("📜", "Runs", "/runs")
            _nav_item("⚙️", "Settings", "/settings")


def _nav_item(icon: str, label: str, path: str) -> None:
    """Rend un item de navigation dans la sidebar."""
    from nicegui import ui

    ui.button(
        f"{icon}  {label}",
        on_click=lambda: ui.navigate.to(path),
    ).props("flat align=left").classes("w-full text-left text-white")
```

#### `styles/theme.py` — Configuration du thème

```python
"""Theme configuration — couleurs, dark mode, brand."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig


def apply_theme(config: GUIConfig) -> None:
    """Applique le thème NiceGUI global."""
    from nicegui import ui

    ui.dark_mode(config.dark_mode)
    ui.colors(primary=config.primary_color)
```

#### `__init__.py` — Re-export avec lazy import guard

```python
"""GUI adapter — interface web pour PyWorkflow Engine.

Installation : ``pip install pyworkflow-engine[gui]``

Usage::

    from pyworkflow_engine.adapters.gui import WorkflowGUI
    from pyworkflow_engine import WorkflowEngine

    engine = WorkflowEngine(persistence=my_backend)
    gui = WorkflowGUI(engine)
    gui.run()  # Ouvre http://localhost:8080
"""

from __future__ import annotations

__all__ = ["WorkflowGUI"]


def __getattr__(name: str) -> object:
    if name == "WorkflowGUI":
        try:
            from pyworkflow_engine.adapters.gui.app import WorkflowGUI
            return WorkflowGUI
        except ImportError as exc:
            raise ImportError(
                "Le GUI adapter nécessite 'nicegui'. "
                "Installez-le avec : pip install pyworkflow-engine[gui]"
            ) from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

**Pattern identique** à `adapters/cli/__init__.py` (ADR-008) et `adapters/tui/__init__.py` (ADR-009) — lazy import via `__getattr__` PEP 562.

### Intégration CLI — sous-commande `gui`

Un fichier `adapters/cli/commands/gui.py` ajoute la sous-commande :

```python
"""Sous-commande GUI — lance l'interface web NiceGUI."""

from __future__ import annotations

import typer

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(
    name="gui",
    help="Lancer l'interface web (NiceGUI).",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
@error_handler
def launch_gui(
    ctx: typer.Context,
    port: int = typer.Option(8080, "--port", "-p", help="Port du serveur web."),
    host: str = typer.Option("127.0.0.1", "--host", help="Adresse d'écoute."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Ne pas ouvrir le navigateur."),
) -> None:
    """Lance l'interface web PyWorkflow (NiceGUI)."""
    try:
        from pyworkflow_engine.adapters.gui import WorkflowGUI
    except ImportError:
        from rich.console import Console
        Console(stderr=True).print(
            "[bold red]✗[/bold red] La GUI nécessite 'nicegui'. "
            "Installez avec : [cyan]pip install pyworkflow-engine[gui][/cyan]"
        )
        raise typer.Exit(4)

    from pyworkflow_engine.adapters.gui.config import GUIConfig

    engine = load_engine(ctx.obj["app_path"])
    config = GUIConfig(
        port=port,
        host=host,
        open_browser=not no_browser,
    )
    gui = WorkflowGUI(engine, config=config)
    gui.run()
```

Et dans `adapters/cli/main.py`, import conditionnel :

```python
# GUI sub-command — optionnel, n'apparaît que si nicegui est installé
try:
    from pyworkflow_engine.adapters.cli.commands import gui as gui_commands
    app.add_typer(gui_commands.app, name="gui")
except ImportError:
    pass
```

### Flux de dépendances

```
pyworkflow gui --app myproject:engine --port 8080
       │
       ▼
  main.py (Typer)
       │  ctx.obj["app_path"]
       ▼
  commands/gui.py
       │  load_engine(app_path)
       ▼
  loader.py  ──→  facade.py (WorkflowEngine)
       │
       ▼
  gui/app.py (WorkflowGUI)
       │  self.engine → GUIState
       ▼
  views/  ──→  components/  ──→  state.py ──→ facade methods
                    │
                    ▼
             styles/theme.py
                    │
                    ▼
         NiceGUI (FastAPI + uvicorn)
              http://localhost:8080
```

La GUI est un **adapter pur** : elle dépend uniquement de la facade `WorkflowEngine` (via `GUIState`) et n'a aucune connaissance des ports, de l'engine interne, ou des autres adapters (sauf le loader CLI partagé).

### Synergie future : adapter `api/` dans le même processus

L'un des avantages architecturaux majeurs de NiceGUI est la possibilité de cohabiter avec un adapter REST dans le même processus :

```
pyworkflow gui --app myproject:engine
       │
       ▼
  NiceGUI (FastAPI)
       │
       ├── GUI pages  ← /          (dashboard)
       │               ← /job/{n}  (job detail)
       │               ← /run/{id} (run detail)
       │               ← /runs     (history)
       │
       ├── API REST   ← /api/v1/jobs     (list jobs)
       │               ← /api/v1/runs     (list runs)
       │               ← /api/v1/run/{id} (run detail)
       │
       └── WebSocket  ← /ws/events  (push en temps réel)
```

Cette convergence GUI + API dans le même processus FastAPI est **impossible** avec PyQt6, DearPyGui, ou Flet. C'est un avantage architectural qui pèse sur la trajectoire post-v1.0.

---

## Plan d'implémentation

### Phase 1 — Scaffold et Dashboard (v1.0.0-alpha)

| Tâche | Fichier | Effort |
|---|---|---|
| `app.py` — `WorkflowGUI`, config, launch | `adapters/gui/app.py` | 1h30 |
| `config.py` — `GUIConfig` dataclass | `adapters/gui/config.py` | 30min |
| `state.py` — `GUIState`, wrapper facade | `adapters/gui/state.py` | 1h |
| `styles/theme.py` — thème NiceGUI | `adapters/gui/styles/theme.py` | 30min |
| `components/sidebar.py` — navigation | `adapters/gui/components/sidebar.py` | 1h |
| `components/toolbar.py` — barre d'outils | `adapters/gui/components/toolbar.py` | 30min |
| `components/job_table.py` — AG Grid jobs | `adapters/gui/components/job_table.py` | 1h30 |
| `components/run_table.py` — AG Grid runs | `adapters/gui/components/run_table.py` | 2h |
| `components/status_badge.py` — chips statut | `adapters/gui/components/status_badge.py` | 45min |
| `views/dashboard.py` — page "/" | `adapters/gui/views/dashboard.py` | 2h |
| `__init__.py` — lazy import guard | `adapters/gui/__init__.py` | 15min |
| `commands/gui.py` — intégration CLI | `adapters/cli/commands/gui.py` | 45min |
| `pyproject.toml` — extra `gui`, update `all` | `pyproject.toml` | 10min |

**Total Phase 1 : ~12h**

### Phase 2 — Detail pages et DAG (v1.0.0-beta)

| Tâche | Fichier | Effort |
|---|---|---|
| `views/job_detail.py` — page "/job/{name}" | `adapters/gui/views/job_detail.py` | 2h |
| `components/dag_graph.py` — Mermaid DAG | `adapters/gui/components/dag_graph.py` | 2h |
| `views/run_detail.py` — page "/run/{id}", live | `adapters/gui/views/run_detail.py` | 2h30 |
| `components/step_progress.py` — AG Grid steps | `adapters/gui/components/step_progress.py` | 1h30 |
| `components/log_viewer.py` — logs streaming | `adapters/gui/components/log_viewer.py` | 1h |
| Navigation inter-pages (click job → detail, click run → detail) | views/*.py, components/*.py | 1h |

**Total Phase 2 : ~10h**

### Phase 3 — Historique, settings, vis.js, tests, polish (v1.0.0)

| Tâche | Fichier | Effort |
|---|---|---|
| `views/run_history.py` — page "/runs", filtres AG Grid | `adapters/gui/views/run_history.py` | 2h |
| `views/settings.py` — page "/settings" | `adapters/gui/views/settings.py` | 1h |
| DAG interactif vis.js (zoom, drag, highlight) | `components/dag_graph.py` | 3h |
| Actions depuis la GUI (run, cancel, resume, validate) | views/*.py | 1h30 |
| Tests (Selenium ou Playwright via NiceGUI test client) | `tests/unit/adapters/gui/` | 4h |
| Documentation | `docs/integrations/gui.md` | 1h30 |

**Total Phase 3 : ~13h**

### Effort total estimé : ~35h

---

## Alternatives considérées

### Alternative A — PyQt6 (desktop natif)

Utiliser PyQt6/PySide6 pour une application desktop native.

**Pour** :
- Écosystème massif (30+ ans), `QGraphicsScene` pour DAG, `QTableView` performant
- Application desktop indépendante — pas de navigateur requis
- Multi-plateforme (Linux, macOS, Windows)

**Contre** :
- **~75 MB** d'installation (Qt runtime complet) — incohérent avec l'esprit "léger"
- **Aucune synergie FastAPI** — deux mondes incompatibles (Qt event loop vs asyncio)
- Pas de mode web — chaque utilisateur doit installer Qt localement
- Courbe d'apprentissage élevée (signals/slots, modèle MVC Qt, QML vs Widgets)
- Threading complexe pour le non-bloquant (pas d'async natif)
- L'adapter `api/` futur devrait être un processus séparé avec CORS

**Verdict** : ❌ Rejetée — trop lourd, pas de web, pas de synergie avec la trajectoire FastAPI du projet.

### Alternative B — DearPyGui (desktop GPU)

Utiliser DearPyGui pour un rendu GPU haute performance.

**Pour** :
- **Node editor intégré** (`dpg.add_node_editor()`) — le meilleur rendu DAG technique brut
- Rendu GPU (60fps), fluide et réactif
- API pythonique et directe

**Contre** :
- **Pas de mode web** — desktop uniquement, dépendance OpenGL
- **Pas de DataGrid avancé** — tables basiques sans virtualisation, tri ou filtrage intégrés
- **Pas de push temps réel** natif — boucle de rendu GPU mais alimentation manuelle
- Aucune synergie FastAPI
- Communauté niche (~7k ★) — risque de maintenance à long terme
- ~25 MB d'installation avec dépendances GPU

**Verdict** : ❌ Rejetée — excellent pour le DAG mais trop limité sur tous les autres critères (DataGrid, web, push, FastAPI).

### Alternative C — Flet (web + desktop Flutter)

Utiliser Flet pour une application multi-plateforme (web, desktop, mobile).

**Pour** :
- **Multi-plateforme complet** — web, desktop, mobile en un codebase Python
- Material Design cohérent et moderne
- WebSocket pour le push inter-sessions (`page.pubsub`)
- Communauté active (~12k ★), soutenu par Flet Inc.

**Contre** :
- **Aucun composant DAG/graphe natif** — Canvas basique, nécessiterait JS custom
- DataTable correcte mais pas au niveau d'AG Grid (pas de virtualisation, export limité)
- Serveur web propriétaire — **pas FastAPI**, pas standard ASGI
- Le futur adapter `api/` ne peut pas cohabiter dans le même processus
- ~15 MB d'installation (Flutter runtime)

**Verdict** : ❌ Rejetée — le plus multi-plateforme mais l'absence de DAG et la non-synergie FastAPI sont rédhibitoires. Le score (63/104 = 61%) est honorable mais insuffisant face à NiceGUI.

### Alternative D — Streamlit

Utiliser Streamlit pour un dashboard rapide.

**Pour** :
- Prototypage ultra-rapide — dashboard en 30 minutes
- Écosystème riche pour la data visualization
- Hébergement gratuit (Streamlit Cloud)

**Contre** :
- **Modèle re-run** — tout le script est ré-exécuté à chaque interaction (pas de state granulaire)
- **Pas de WebSocket push** — polling uniquement
- **Pas de routage multi-pages robuste** — `st.sidebar` et `st.multipage` sont limités
- **Pas de DAG interactif** — `st.graphviz_chart` est statique
- Déjà prévu comme extra séparé (`streamlit`) pour les démos — pas comme GUI principale
- Le modèle de re-run est incompatible avec une supervision live performante

**Verdict** : ❌ Rejetée comme GUI principale — reste un extra séparé (`streamlit`) pour les démos et le prototypage rapide.

### Alternative E — Gradio

Utiliser Gradio pour une interface.

**Pour** :
- Très rapide pour les interfaces input/output (modèle ML).

**Contre** :
- **Aucun composant DataGrid** — orienté inputs → outputs (ML démo)
- **Pas de DAG** — aucun composant graphe
- **Pas de routage** — une seule page
- Inadapté pour un dashboard d'orchestration multi-pages

**Verdict** : ❌ Rejetée — framework ML, pas un framework dashboard.

### Alternative F — Ne rien faire (CLI + TUI suffisent)

Ne pas implémenter de GUI, se contenter de la CLI et de la TUI.

**Pour** : Zéro effort supplémentaire, `textual serve` offre déjà un mode web basique.

**Contre** :
- Pas de visualisation DAG graphique (le besoin #1)
- Pas de DataGrid performant (AG Grid vs DataTable Textual)
- Pas accessible aux non-développeurs (product owners, managers)
- Pas de synergie FastAPI pour le futur adapter `api/`
- `textual serve` est un pont, pas une GUI web — pas de routing, pas de composants web natifs
- Tous les concurrents majeurs (Airflow, Prefect, Dagster, Temporal) offrent une Web UI

**Verdict** : ❌ Rejetée — la GUI web est une attente standard de l'écosystème workflow. Ne pas en avoir est un déficit compétitif.

---

## Conséquences

### Positives

- **Visualisation DAG native** — Mermaid.js (Phase 1) + vis.js (Phase 2) pour les graphes interactifs
- **AG Grid intégré** — le standard industrie des DataGrids (virtualisation, tri, filtrage, export)
- **WebSocket push** — mises à jour temps réel sans polling HTTP agressif
- **Synergie FastAPI** — le futur adapter `api/` peut cohabiter dans le même processus sans infrastructure supplémentaire
- **Installation légère** — ~8 MB (pur Python), `pip install nicegui` en 5 secondes
- **Python-only** — aucun JavaScript/TypeScript à maintenir (contrairement à Airflow, Prefect, Dagster)
- **Zero infra** — `pyworkflow gui` lance tout (serveur + navigateur) — comparable à `jupyter notebook`
- **Accessible** — non-développeurs peuvent superviser via leur navigateur web standard
- **Réutilisation loader** — `load_engine()` partagé entre CLI, TUI et GUI
- **Cohérence hexagonale** — adapter pur qui dépend uniquement de la facade via `GUIState`

### Négatives

- **Dépendance NiceGUI** — le framework est plus jeune que PyQt/Qt (risque de changements API)
- **Limite mono-thread** — NiceGUI est single-process ; pour le multi-tenant haute charge, un adapter `api/` séparé (FastAPI standalone) serait nécessaire
- **Pas de mode desktop natif** — NiceGUI offre `ui.run(native=True)` (webview) mais ce n'est pas une app native — acceptable car le web est notre cible
- **JavaScript indirect** — pour vis.js interactif (Phase 2), il faut écrire du JS via `ui.run_javascript()` — perte partielle du "Python-only"
- **Dépendance à AG Grid** — composant tiers intégré dans NiceGUI ; une mise à jour AG Grid breaking serait propagée

### Risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| NiceGUI breaking change (API v3+) | Faible | Moyen | Pin `nicegui>=2.0,<3.0` ; l'API v2 est stable. Zauberzeug maintient activement la rétrocompatibilité |
| Performance avec >10k jobs/runs simultanés | Moyenne | Faible | AG Grid virtualise côté client ; `limit=` sur les requêtes facade ; pagination serveur |
| Navigateur requis (pas de mode headless) | Faible | Faible | La TUI (ADR-009) couvre le cas headless/SSH. La GUI est complémentaire |
| NiceGUI disparaît / n'est plus maintenu | Très faible | Élevé | Le projet est soutenu par Zauberzeug GmbH (entreprise allemande), en croissance. En dernier recours, la GUI est un adapter isolé — remplaçable sans impact sur le core |
| Conflit de port avec d'autres services | Faible | Faible | Port configurable (`--port`), détection automatique de port libre possible en Phase 2 |

---

## Références

- [NiceGUI documentation](https://nicegui.io/documentation)
- [NiceGUI GitHub — 10k+ stars](https://github.com/zauberzeug/nicegui)
- [AG Grid documentation](https://www.ag-grid.com/javascript-data-grid/)
- [Mermaid.js documentation](https://mermaid.js.org/)
- [vis.js Network documentation](https://visjs.github.io/vis-network/docs/network/)
- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [NiceGUI + FastAPI integration](https://nicegui.io/documentation/section_server_sge)
- [PyQt6 documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [DearPyGui documentation](https://dearpygui.readthedocs.io/)
- [Flet documentation](https://flet.dev/docs/)
- [Streamlit documentation](https://docs.streamlit.io/)
- ADR-006 — Architecture hexagonale
- ADR-007 — Adapter complexe vs simple (règle de placement)
- ADR-008 — CLI Adapter Typer + Rich
- ADR-009 — TUI Adapter Textual + Rich
