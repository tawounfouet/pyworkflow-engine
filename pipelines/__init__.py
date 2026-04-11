"""
Pipelines — Orchestration et chaînage des jobs.

Ce package contient les pipelines qui chaînent plusieurs jobs unitaires
(depuis ``jobs/``) en scénarios opérationnels complets :

- ``daily/``      — Pipelines quotidiennes
- ``weekly/``     — Pipelines hebdomadaires
- ``monthly/``    — Pipelines mensuelles
- ``on_demand/``  — Pipelines manuelles (backfill, reprocess…)
- ``shared/``     — Utilitaires d'orchestration partagés
"""
