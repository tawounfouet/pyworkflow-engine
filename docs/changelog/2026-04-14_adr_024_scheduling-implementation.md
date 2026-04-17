# ADR-024 — Implémentation complète du système de scheduling

| Champ | Valeur |
|---|---|
| **ID** | ADR-024 |
| **Date** | 14 avril 2026 |
| **Statut** | ✅ Implémenté et validé |
| **Auteur** | équipe pyworkflow-engine |
| **Décisions liées** | ADR-006 (hexagonal), ADR-014 (pipeline model), ADR-016 (master integration plan) |
| **Version cible** | v0.4.0 |

---

## Contexte

### Avant cette ADR

Le moteur disposait d'un `ScheduleTrigger` et d'un `CronExpression` fonctionnels dans
`src/pyworkflow_engine/adapters/triggers/schedule.py`, mais il manquait :

1. **Un point d'entrée unique** pour démarrer *tous* les jobs schedulés en production
2. **Un outil de visualisation** des schedules et prochains déclenchements
3. **Un job de test observable** pour valider la chaîne scheduling → SMTP de bout en bout
4. **Un manifest déclaratif** associant chaque job à son expression cron
5. **La documentation** du cycle de vie, des paramètres et des patterns d'utilisation

### Problème à résoudre

> Comment orchestrer N jobs schedulés hétérogènes (ingestion, LLM, ops) dans un seul
> processus Python, sans dépendance à un broker externe (Celery, Redis, APScheduler) ?

---

## Décision

### Architecture retenue

```
jobs/manifest.yaml                    ← source de vérité déclarative
    │
    ▼
jobs/ops/scheduler_runner.py          ← orchestrateur central
    │  load_manifest() + load_job()
    │
    ├── ScheduleTrigger("*/5 * * * *")   ← ops-heartbeat-email
    ├── ScheduleTrigger("0 1 * * *")     ← ingestion-stripe-payments
    ├── ScheduleTrigger("0 20 * * *")    ← ingestion-strava-daily
    └── ... (N triggers en threads daemon)
```

### Flux d'exécution

```
--detach
    │
    os.fork()
        │
        ├── Parent : écrit logs/scheduler_runner.pid → retourne
        └── Enfant :
                os.setsid()           ← détachement terminal
                redirect stdout/stderr → logs/scheduler_runner.log
                _build_triggers()     ← charge manifest + crée ScheduleTriggers
                _run_loop()           ← time.sleep(10) + Ctrl+C handler
```

---

## Composants créés

### 1. `jobs/ops/scheduler_runner.py` — Orchestrateur central

**Responsabilités :**
- Lit `jobs/manifest.yaml` via `jobs.shared.loader.load_manifest()`
- Charge chaque `Job` Pydantic via `jobs.shared.loader.load_job(job_def)`
- Crée un `ScheduleTrigger` par entrée ayant un champ `schedule`
- Démarre et supervise tous les triggers dans un unique processus Python
- Gère le cycle de vie daemon (fork/setsid, PID file, SIGTERM)

**Interface CLI :**

| Commande | Comportement |
|---|---|
| *(sans args)* | Démarre en avant-plan, Ctrl+C pour arrêter |
| `--dry-run` | Liste les jobs sans démarrer |
| `--only JOB1,JOB2` | Filtre — ne démarre que ces jobs |
| `--exclude JOB1,JOB2` | Filtre — exclut ces jobs |
| `--detach` | Fork daemon, PID dans `logs/scheduler_runner.pid` |
| `--status` | Vérifie si le daemon est actif (via PID file) |
| `--stop` | Envoie SIGTERM au daemon |

**Fichiers d'état :**
```
logs/scheduler_runner.pid   ← PID du processus daemon
logs/scheduler_runner.log   ← Tous les logs (mode --detach)
```

**Contexte injecté à chaque déclenchement :**
```python
initial_context_factory=lambda: {
    "triggered_at": datetime.now(UTC).isoformat(),
    "job_name": name,
}
```

---

### 2. `jobs/ops/schedule_status.py` — Visualisation

**Responsabilités :**
- Lit `jobs/manifest.yaml` (PyYAML)
- Calcule le prochain fire de chaque expression cron via `CronExpression` (scan minute-par-minute, max 1 an)
- Détecte les schedulers daemon actifs via `os.kill(pid, 0)` sur les `.pid` files dans `logs/`
- Affiche un tableau ANSI coloré avec délais humains lisibles

**Interface CLI :**

| Option | Comportement |
|---|---|
| *(sans args)* | Tableau des jobs schedulés uniquement |
| `--all` | Inclut les jobs sans schedule |
| `--next N` | Prochains N déclenchements (jobs + pipelines, triés par heure) |
| `--json` | Sortie JSON brute du manifest |

---

### 3. `jobs/ops/heartbeat_email.py` — Job de test

**Responsabilités :**
- Valider la chaîne scheduling → email SMTP de bout en bout
- Servir de référence d'implémentation pour les jobs ops

**Pipeline :**
```
collect_metrics        → pid, hostname, mémoire RSS, run_number
    ↓
send_heartbeat_email   → SMTP SSL via pyconnectors (skip gracieux si SMTP absent)
    ↓
log_heartbeat          → log structuré du résultat
```

**Schedule manifest :** `*/5 * * * *` (toutes les 5 minutes)

---

### 4. Entrée `jobs/manifest.yaml` ajoutée

```yaml
- name: ops-heartbeat-email
  module: jobs.ops.heartbeat_email
  attr: heartbeat_email_job
  schedule: "*/5 * * * *"
  owner: data-team@company.com
  tags: [ops, heartbeat, email, scheduling, test]
```

---

## Décisions techniques

### D1 — Stdlib uniquement pour le scheduling

**Retenu :** `threading.Thread` (daemon) + `time.sleep(1)` + `datetime`  
**Rejeté :** APScheduler, Celery Beat, rq-scheduler, cron système

**Justification :**
- Zéro dépendance externe supplémentaire
- Granularité minute amplement suffisante pour les jobs de données
- Contrôle total du cycle de vie (stop propre, état observable)
- Cohérence avec le principe « stdlib d'abord » du projet

### D2 — Manifest déclaratif YAML

**Retenu :** `jobs/manifest.yaml` comme source de vérité pour les schedules  
**Rejeté :** décoration des jobs avec `@schedule(cron=...)`, base de données

**Justification :**
- Séparation claire entre la définition du job (code) et son ordonnancement (config)
- Lisible et diffable en git
- Permet `--dry-run` et `schedule_status.py` sans instancier les jobs
- Pattern standard (dbt, Airflow DAGs, GitHub Actions)

### D3 — Fork Unix comme mécanisme daemon

**Retenu :** `os.fork()` + `os.setsid()` + redirection des FDs  
**Rejeté :** `subprocess.Popen(... start_new_session=True)`, `nohup`, systemd

**Justification :**
- Pas de dépendance à un gestionnaire de services externe
- Le processus enfant hérite de l'environnement Python chargé (dotenv, imports)
- PID file simple pour le contrôle (status/stop)
- Compatible macOS et Linux
- Limitation connue : Windows non supporté (acceptable pour ce projet)

### D4 — Chargement dynamique via `jobs.shared.loader`

**Retenu :** `importlib.import_module(module)` + `getattr(mod, attr)`  
**Rejeté :** import statique de tous les jobs au démarrage, registry pattern

**Justification :**
- Le manifest est la liste exhaustive des jobs — pas besoin d'un registry séparé
- Les jobs non schedulés ne sont pas chargés (économie mémoire)
- Les erreurs de chargement sont isolées (un job cassé n'empêche pas les autres)
- Cohérence avec le loader déjà utilisé par la CLI et le TUI

### D5 — Calcul `next_fire` par scan minute-par-minute

**Retenu :** itération `+1 minute` jusqu'à `expr.matches()`, max 525 600 itérations (1 an)  
**Rejeté :** calcul analytique (mathématique), bibliothèque `croniter`

**Justification :**
- Réutilise `CronExpression` existante sans duplication de logique
- Max ~10 ms pour les expressions les plus rares (1x/an)
- Pas de nouvelle dépendance
- Facilement testable et débuggable

---

## Résultats de validation

```bash
# --dry-run : 17 jobs listés correctement
python -m jobs.ops.scheduler_runner --dry-run
# → 17 trigger(s) seraient démarrés.

# --detach : daemon démarré
python -m jobs.ops.scheduler_runner --detach
# → 🚀 Scheduler runner lancé en arrière-plan — PID 55802

# --status : confirmation
python -m jobs.ops.scheduler_runner --status
# → 🟢 Scheduler runner en cours — PID 55802

# schedule_status.py : tableau coloré avec prochains fires
python -m jobs.ops.schedule_status --next 5
# → 5 prochains déclenchements listés et triés

# heartbeat_email : test end-to-end SMTP
python -m jobs.ops.heartbeat_email --dry-run
# → Dry-run : email simulé, run #1
```

---

## Corrections de bugs (issues découvertes lors de l'implémentation)

| Bug | Fichier | Avant | Après |
|---|---|---|---|
| Faute de frappe dans l'adresse email | `.env` | `thomas.awounfoouet@yahoo.com` | `thomas.awounfouet@yahoo.com` |
| `run_number` absent du retour de `send_heartbeat_email` | `heartbeat_email.py` | `{"status": "sent", "to": ..., "subject": ...}` | `{..., "run_number": run_number}` |
| Idem pour le cas `"skipped"` | `heartbeat_email.py` | `{"status": "skipped", "to": "", "subject": ""}` | `{..., "run_number": run_number}` |

Le bug `run_number` causait un affichage `run #0` dans le step `log_heartbeat` parce que
`run_number` n'était pas propagé dans le contexte entre les steps.

---

## Pistes d'évolutions futures

### Court terme

| Évolution | Effort | Valeur |
|---|---|---|
| **Survival reboot macOS** — agent launchd `.plist` | Faible | Haute — le daemon redémarre automatiquement après reboot |
| **Survival reboot Linux** — unit systemd | Faible | Haute — idem |
| **Persistance des runs** — écrire chaque JobRun dans SQLite | Moyen | Haute — traçabilité, audit, debugging |

### Moyen terme

| Évolution | Effort | Valeur |
|---|---|---|
| **Monitoring / alerting** — état des triggers dans `schedule_status.py` (dernier run, statut, erreurs) | Moyen | Haute — visibilité opérationnelle |
| **Retry automatique** — `on_run_error` + backoff + alerte email/Slack | Moyen | Haute — résilience en production |
| **Dashboard TUI** (`textual`) — vue live des triggers avec refresh | Élevé | Moyenne — confort de monitoring |
| **Historique des runs** — `--history N` dans `schedule_status.py` | Moyen | Moyenne — débogage facilité |

### Long terme

| Évolution | Effort | Valeur |
|---|---|---|
| **Métriques Prometheus** — exposition des compteurs de runs | Élevé | Haute si environnement cloud |
| **Distributed scheduling** — Celery Beat comme backend alternatif | Très élevé | Conditionnelle — uniquement si scale horizontal requis |
| **Hot-reload du manifest** — rechargement sans restart sur modification de `manifest.yaml` | Élevé | Moyenne — commodité dev |

---

## Impact sur la documentation

| Document | Action |
|---|---|
| `docs/guides/scheduling.md` | ✅ Mis à jour — ajout sections `scheduler_runner`, `schedule_status`, `heartbeat_email`, mode `--detach`, launchd, tableau fichiers clés |
| `docs/changelog/2026-04-14_adr_024_*.md` | ✅ Ce document |
| `docs/changelog/README.md` | ⬜ À mettre à jour (entrée ADR-024) |

---

## Fichiers créés / modifiés

| Fichier | Action | Description |
|---|---|---|
| `jobs/ops/scheduler_runner.py` | ✅ Créé | Orchestrateur central — 299 lignes |
| `jobs/ops/schedule_status.py` | ✅ Créé | Visualisation des schedules — 319 lignes |
| `jobs/ops/heartbeat_email.py` | ✅ Créé + corrigé | Job de test SMTP — 464 lignes |
| `jobs/manifest.yaml` | ✅ Mis à jour | Entrée `ops-heartbeat-email` ajoutée |
| `.env` | ✅ Corrigé | Faute de frappe `NOTIFY_EMAIL` |
| `docs/guides/scheduling.md` | ✅ Mis à jour | Sections orchestrateur + visualisation |
| `pyproject.toml` | ✅ Mis à jour | `pyyaml>=6.0` ajouté aux dépendances |
