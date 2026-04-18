"""
Shared — Utilitaires transversaux pour tous les jobs.

Fournit les abstractions communes :
- ``datalake``      — Lecture/écriture Data Lake (local, S3, Azure Blob)
- ``warehouse``     — Accès Data Warehouse (DuckDB, PostgreSQL)
- ``connections``   — Factories de connexions (DB, API, SFTP…)
- ``validators``    — Validations de données communes
- ``notifications`` — Alertes (Slack, email, Teams…)
- ``loader``        — Chargement dynamique des jobs depuis manifest.yaml
- ``persistence``   — Synchronisation du catalogue jobs → workflow.db
"""
