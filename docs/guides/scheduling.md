# Guide Scheduling : `ScheduleTrigger` et `CronExpression`

**Date** : 14 avril 2026  
**Status** : Implémenté (v0.4.0)  
**Principe** : Zéro dépendance externe — stdlib uniquement (`threading`, `datetime`)

---

## 🎯 Vue d'ensemble

Le scheduling est assuré par deux composants dans `pyworkflow_engine` :

| Composant | Rôle |
|---|---|
| `CronExpression` | Parse et évalue les expressions cron 5 champs |
| `ScheduleTrigger` | Thread daemon qui déclenche un `Job` selon l'expression cron |

```
ScheduleTrigger
    │
    ├── CronExpression("0 20 * * *")   → parse → sets d'entiers
    │       └── matches(datetime.now()) → True / False
    │
    ├── threading.Thread (daemon)      → boucle toutes les secondes
    │       ├── stop_event             → arrêt propre via threading.Event
    │       └── last_fired_minute_key  → anti double-déclenchement
    │
    └── BaseTrigger._do_fire()         → WorkflowEngine.run(job)
```

---

## 📦 Import

```python
from pyworkflow_engine import WorkflowEngine, ScheduleTrigger, CronExpression
# ou directement :
from pyworkflow_engine.adapters.triggers.schedule import ScheduleTrigger, CronExpression
```

---

## ⚙️ Expressions cron supportées

Format : `minute  hour  day  month  weekday`

| Champ | Plage | Exemple |
|---|---|---|
| minute | 0–59 | `30` = à la 30e minute |
| hour | 0–23 | `9` = 9h00 |
| day | 1–31 | `1,15` = le 1er et le 15 |
| month | 1–12 | `5,11` = mai et novembre |
| weekday | 0–6 | `1-5` = lundi–vendredi (0=dim, 6=sam) |

### Syntaxes supportées par champ

| Syntaxe | Signification | Exemple |
|---|---|---|
| `*` | toutes les valeurs | `* * * * *` = chaque minute |
| `n` | valeur exacte | `0 9 * * *` = 9h00 chaque jour |
| `*/n` | pas de n | `*/5 * * * *` = toutes les 5 min |
| `a-b` | plage inclusive | `0 9 * * 1-5` = 9h lun–ven |
| `a,b,c` | liste | `0 6 1,15 * *` = 6h le 1er et 15 |
| `a-b/n` | plage avec pas | `0 8-18/2 * * *` = toutes les 2h de 8h à 18h |

### Exemples des jobs du manifest

```
"0 1 * * *"      → Quotidien à 01h00 UTC      (ingestion-stripe-payments)
"0 2 * * *"      → Quotidien à 02h00 UTC      (ingestion-books-toscrape)
"0 1 * * 0"      → Dimanche à 01h00 UTC       (ingestion-restcountries)
"0 6 1 5,11 *"   → 1er mai et 1er novembre    (ingestion-imf)
"0 20 * * *"     → Quotidien à 20h00 UTC      (ingestion-strava-daily)
"30 20 * * *"    → Quotidien à 20h30 UTC      (llm-strava-daily-coaching)
```

> ⚠️ **Convention weekday** : `0 = dimanche`, `6 = samedi` (standard cron POSIX).  
> Python `datetime.weekday()` retourne `0=lundi` — le code convertit avec `(weekday + 1) % 7`.

---

## 🚀 Usage de base

### 1. Avec un `Job` déclaratif (API `@job` / `@step`)

```python
from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.adapters.triggers.schedule import ScheduleTrigger
from pyworkflow_engine.decorators import job, step

@step(name="do_work")
def do_work() -> dict:
    return {"status": "done"}

@job(name="my-scheduled-job", steps=[do_work])
def my_job():
    do_work()

# Démarrage
engine = WorkflowEngine()
trigger = ScheduleTrigger(
    engine=engine,
    job=my_job.build(),    # .build() construit le Job Pydantic
    cron="*/5 * * * *",    # toutes les 5 minutes
)
trigger.start()
```

### 2. Avec un `Job` impératif (API bas niveau)

```python
from pyworkflow_engine import WorkflowEngine, Job, Step, StepType
from pyworkflow_engine.adapters.triggers.schedule import ScheduleTrigger

def greet() -> dict:
    return {"message": "Hello!"}

job = Job(
    name="hello-job",
    steps=[Step(name="greet", step_type=StepType.FUNCTION, handler=greet)],
)

engine = WorkflowEngine()
trigger = ScheduleTrigger(engine=engine, job=job, cron="*/5 * * * *")
trigger.start()
```

---

## ⚙️ Paramètres de `ScheduleTrigger`

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `engine` | `WorkflowEngine` | — | Instance du moteur (obligatoire) |
| `job` | `Job` | — | Job à exécuter (obligatoire) |
| `cron` | `str` | — | Expression cron 5 champs (obligatoire) |
| `name` | `str` | `"ScheduleTrigger"` | Nom lisible du trigger |
| `initial_context_factory` | `Callable[[], dict]` | `None` | Fabrique de contexte appelée à chaque déclenchement |
| `timezone_aware` | `bool` | `False` | Si `True`, utilise `datetime.now(UTC)` |
| `on_run_complete` | `Callable[[JobRun], None]` | `None` | Callback appelé à chaque run terminé |
| `on_run_error` | `Callable[[Exception], None]` | `None` | Callback appelé en cas d'erreur |

---

## 🔄 Cycle de vie et états

```
      start()              stop()
IDLE ──────► RUNNING ────────────► STOPPED
                │
                │ (exception dans fire())
                ▼
              ERROR
```

| Méthode | Description |
|---|---|
| `trigger.start()` | Démarre le thread daemon |
| `trigger.stop(timeout=5.0)` | Arrêt propre (join avec timeout) |
| `trigger.fire()` | Déclenchement immédiat (manuel ou depuis le thread) |
| `trigger.state` | État courant (`TriggerState`) |
| `trigger.run_count` | Nombre de runs déclenchés |
| `trigger.cron` | `CronExpression` configurée |

---

## 📅 Contexte initial dynamique

`initial_context_factory` est appelé **à chaque** déclenchement pour injecter un contexte frais (date du jour, timestamp, etc.) :

```python
import datetime

trigger = ScheduleTrigger(
    engine=engine,
    job=my_job.build(),
    cron="0 20 * * *",     # chaque jour à 20h
    name="daily-job",
    timezone_aware=True,   # utilise UTC
    initial_context_factory=lambda: {
        "run_date": datetime.date.today().isoformat(),
        "triggered_at": datetime.datetime.now(datetime.UTC).isoformat(),
    },
)
```

Les clés du dict retourné sont accessibles dans les steps via les paramètres de fonction (injection automatique depuis le contexte).

---

## 💾 Avec persistence SQLite

Par défaut, `_do_fire()` appelle `engine.run()` (sans persistence).  
Pour persister chaque `JobRun`, utiliser `engine.run_with_storage()` via un job wrapper ou surcharger `fire()` :

```python
from pyworkflow_engine.config import WorkflowConfig, StorageConfig, EngineConfig

engine = WorkflowEngine(
    config=WorkflowConfig(
        storage=StorageConfig(db_path="workflow.db"),
        engine=EngineConfig(parallel=False),
    )
)

trigger = ScheduleTrigger(engine=engine, job=my_job.build(), cron="*/5 * * * *")
trigger.start()
```

---

## 🎛️ Plusieurs triggers simultanés

```python
engine = WorkflowEngine()

trigger_5min = ScheduleTrigger(
    engine=engine, job=job_a.build(),
    cron="*/5 * * * *", name="every-5min",
)
trigger_daily = ScheduleTrigger(
    engine=engine, job=job_b.build(),
    cron="0 1 * * *", name="daily-1am",
    timezone_aware=True,
)

trigger_5min.start()
trigger_daily.start()

# ... application en cours ...

trigger_5min.stop()
trigger_daily.stop()
```

---

## ⚠️ Points d'attention

| Point | Détail |
|---|---|
| **Granularité minute** | La boucle vérifie toutes les secondes mais le déclenchement est à la **minute** (pas de sub-minute) |
| **Anti double-fire** | La clé `(year, month, day, hour, minute)` garantit un seul déclenchement par minute |
| **Thread daemon** | S'arrête automatiquement à la fin du processus Python — toujours appeler `stop()` pour un arrêt propre |
| **Erreur fatale** | Une exception dans `fire()` → état `ERROR` + arrêt du thread. Surveiller `trigger.state` |
| **Double start** | `start()` sur un trigger `RUNNING` → `RuntimeError` immédiate |
| **fire() hors start()** | Possible (déclenchement manuel), mais le trigger doit avoir été au moins instancié |

---

## 🧪 Tester le scheduling sans attendre

```python
# Vérifier une expression cron sans démarrer de thread
from pyworkflow_engine.adapters.triggers.schedule import CronExpression
from datetime import datetime

expr = CronExpression("0 20 * * *")
print(expr.matches(datetime(2026, 4, 14, 20, 0)))   # True
print(expr.matches(datetime(2026, 4, 14, 20, 1)))   # False

# Déclencher manuellement (sans attendre la prochaine minute)
trigger = ScheduleTrigger(engine=engine, job=job.build(), cron="0 20 * * *")
job_run = trigger.fire()   # déclenchement immédiat, sans start()
print(job_run.status)
```

---

## 🏭 Orchestrateur central : `scheduler_runner.py`

En production, utilisez `jobs/ops/scheduler_runner.py` pour démarrer **tous** les jobs schedulés du manifest en une seule commande.

### Architecture

```
scheduler_runner.py
    │
    ├── load_manifest()            → lit jobs/manifest.yaml
    ├── load_job(job_def)          → importe chaque module dynamiquement
    └── ScheduleTrigger × N        → un thread par job schedulé
```

### Commandes disponibles

```bash
# Lister les jobs qui seraient démarrés (sans rien lancer)
python -m jobs.ops.scheduler_runner --dry-run

# Démarrer tous les jobs schedulés en avant-plan
python -m jobs.ops.scheduler_runner

# Démarrer en arrière-plan (fork daemon)
python -m jobs.ops.scheduler_runner --detach

# Vérifier l'état du runner détaché
python -m jobs.ops.scheduler_runner --status

# Arrêter le runner détaché
python -m jobs.ops.scheduler_runner --stop

# Ne démarrer qu'une sélection de jobs
python -m jobs.ops.scheduler_runner --only ingestion-strava-daily,ops-heartbeat-email

# Exclure des jobs
python -m jobs.ops.scheduler_runner --exclude ops-heartbeat-email
```

### Mode `--detach` : démon fork

Le mode `--detach` effectue un `os.fork()` :

- Le **processus parent** écrit le PID dans `logs/scheduler_runner.pid` et retourne immédiatement
- Le **processus enfant** appelle `os.setsid()` (détachement du terminal) et redirige stdout/stderr vers `logs/scheduler_runner.log`

```
logs/
├── scheduler_runner.pid       # PID du processus daemon
└── scheduler_runner.log       # Tous les logs du runner
```

> ⚠️ **macOS / Linux uniquement** — `os.fork()` n'est pas disponible sur Windows.

### Contexte injecté automatiquement

Chaque trigger créé par le runner injecte un contexte frais à chaque déclenchement :

```python
initial_context_factory=lambda: {
    "triggered_at": datetime.now(UTC).isoformat(),
    "job_name": name,
}
```

Ces clés sont accessibles comme paramètres de fonction dans les steps.

### Persistance du runner au reboot (macOS — launchd)

Pour que le runner survive aux redémarrages, créez un agent launchd :

```xml
<!-- ~/Library/LaunchAgents/com.pyworkflow.scheduler.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.pyworkflow.scheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/venv/bin/python</string>
        <string>-m</string>
        <string>jobs.ops.scheduler_runner</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/pyworkflow-engine</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/path/to/pyworkflow-engine/logs/scheduler_runner.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/pyworkflow-engine/logs/scheduler_runner.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.pyworkflow.scheduler.plist
```

---

## 🖥️ Visualisation : `schedule_status.py`

`jobs/ops/schedule_status.py` affiche un tableau coloré de tous les jobs schedulés du manifest avec leur prochain déclenchement calculé en temps réel.

### Commandes disponibles

```bash
# Vue d'ensemble (jobs schedulés uniquement)
python -m jobs.ops.schedule_status

# Inclure les jobs sans schedule
python -m jobs.ops.schedule_status --all

# Afficher les N prochains fires (toutes sources confondues)
python -m jobs.ops.schedule_status --next 10

# Sortie JSON brute du manifest
python -m jobs.ops.schedule_status --json
```

### Exemple de sortie

```
───────────────────────────────────────────────────────────────────────────────
  PyWorkflow Engine — Schedule Status  ·  2026-04-14 20:00 UTC
  17 jobs  ·  2 pipelines  ·  1 scheduler(s) actif(s)
───────────────────────────────────────────────────────────────────────────────

  Schedulers détachés actifs :
  🟢  scheduler_runner  PID 55802  logs → logs/scheduler_runner.log

  JOB                                  CRON                   PROCHAIN FIRE        ÉTAT         TAGS
  ─────────────────────────────────────────────────────────────────────────────────────────────────────
  ops-heartbeat-email                  */5 * * * *            14/04 20:05 dans 4min  🟢 PID 55802  ops, heartbeat
  ingestion-stripe-payments            0 1 * * *              15/04 01:00 dans 5h   ⚪ manifest   ingestion
  ingestion-strava-daily               0 20 * * *             14/04 20:00 dans 0min ⚪ manifest   strava
  ...
```

### Fonctionnement interne

1. Lit `jobs/manifest.yaml` via PyYAML
2. Pour chaque job avec `schedule`, appelle `CronExpression` pour calculer le prochain fire (scan minute par minute, max 1 an)
3. Détecte les schedulers actifs en cherchant les fichiers `.pid` dans `logs/` et en testant le PID avec `os.kill(pid, 0)`
4. Affiche un tableau ANSI coloré avec délais humains lisibles (`dans 4min`, `dans 2h 15min`)

---

## 💌 Job de test : `heartbeat_email.py`

`jobs/ops/heartbeat_email.py` est un job de validation du scheduling : il envoie un e-mail via SMTP toutes les 5 minutes.

### Pipeline

```
collect_metrics        → pid, hostname, mémoire RSS, run_number
    ↓
send_heartbeat_email   → SMTP (pyconnectors) ; skip gracieux si SMTP absent
    ↓
log_heartbeat          → log du résultat dans les logs du système
```

### Variables d'environnement requises

```ini
SMTP_HOST=pif.o2switch.net
SMTP_PORT=465
SMTP_USER=dev@awounfouet.com
SMTP_PASSWORD=<mot_de_passe>
SMTP_USE_SSL=true
NOTIFY_EMAIL=thomas.awounfouet@yahoo.com
```

### Modes CLI

```bash
# Exécution unique (test rapide)
python -m jobs.ops.heartbeat_email

# Simulation sans envoi SMTP
python -m jobs.ops.heartbeat_email --dry-run

# Boucle avec ScheduleTrigger (toutes les 5 min, avant-plan)
python -m jobs.ops.heartbeat_email --run-scheduler

# Boucle en arrière-plan (fork daemon)
python -m jobs.ops.heartbeat_email --detach

# Vérifier l'état du scheduler heartbeat
python -m jobs.ops.heartbeat_email --status

# Arrêter le scheduler heartbeat
python -m jobs.ops.heartbeat_email --stop
```

---

## 🗺️ Fichiers clés

| Fichier | Rôle |
|---|---|
| `src/pyworkflow_engine/adapters/triggers/schedule.py` | `CronExpression` + `ScheduleTrigger` |
| `src/pyworkflow_engine/adapters/triggers/manual.py` | `ManualTrigger` (référence) |
| `src/pyworkflow_engine/ports/trigger.py` | `BaseTrigger` + `TriggerState` |
| `jobs/manifest.yaml` | Catalogue déclaratif de tous les jobs et schedules |
| `jobs/ops/scheduler_runner.py` | Orchestrateur central — démarre tous les triggers |
| `jobs/ops/schedule_status.py` | Visualisation des schedules et prochains fires |
| `jobs/ops/heartbeat_email.py` | Job de test — email SMTP toutes les 5 min |
| `jobs/shared/loader.py` | `load_manifest()` + `load_job()` — chargement dynamique |
| `examples/triggers.py` | Exemples complets exécutables |
| `logs/scheduler_runner.pid` | PID du runner daemon (créé par `--detach`) |
| `logs/scheduler_runner.log` | Logs du runner daemon |
