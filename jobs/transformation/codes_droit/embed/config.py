"""
Configuration du job embed-codes-droit (Job 3).

Toutes les valeurs sont surchargeables via variables d'environnement.
"""

from __future__ import annotations

import os

DEFAULT_MODEL: str = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-large")
BATCH_SIZE: int = int(os.environ.get("EMBEDDING_BATCH_SIZE", "100"))
CONTENT_TRUNC: int = int(os.environ.get("EMBEDDING_CONTENT_TRUNC", "1500"))
