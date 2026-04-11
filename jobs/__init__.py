"""
Jobs — Flux opérationnels de production.

Ce package contient l'ensemble des jobs unitaires organisés par domaine :
- ``ingestion/``       — Extraction brute des sources → Data Lake
- ``transformation/``  — Nettoyage, typage, agrégation → Data Warehouse
- ``ml/``              — Pipelines de Machine Learning
- ``reporting/``       — Génération de rapports
- ``ops/``             — Maintenance et opérations
- ``shared/``          — Utilitaires partagés entre tous les jobs
"""
