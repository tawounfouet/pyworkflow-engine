"""
Connections — Factories de connexions pour les sources de données.

Centralise la création de clients / connexions utilisés par les jobs.
Chaque factory lit ses secrets depuis les variables d'environnement.

Examples:
    >>> from jobs.shared.connections import get_stripe_client
    >>> client = get_stripe_client()
"""

from __future__ import annotations

import os
from typing import Any


def get_env_or_raise(var: str) -> str:
    """Récupère une variable d'environnement ou lève une erreur claire."""
    value = os.environ.get(var)
    if not value:
        msg = (
            f"Variable d'environnement '{var}' non définie. "
            f"Ajoutez-la dans votre fichier .env ou vos variables d'environnement."
        )
        raise EnvironmentError(msg)
    return value


# ── Exemples de factories ────────────────────────────────────────────
# Décommenter et adapter selon les sources réelles du projet.


# def get_stripe_client() -> Any:
#     """Crée un client Stripe depuis STRIPE_API_KEY."""
#     import stripe  # noqa: PLC0415
#     stripe.api_key = get_env_or_raise("STRIPE_API_KEY")
#     return stripe


# def get_pg_engine() -> Any:
#     """Crée un engine SQLAlchemy vers PostgreSQL."""
#     from sqlalchemy import create_engine  # noqa: PLC0415
#     return create_engine(get_env_or_raise("PG_CONNECTION_STRING"))


# def get_sftp_client() -> Any:
#     """Crée un client SFTP."""
#     import paramiko  # noqa: PLC0415
#     client = paramiko.SSHClient()
#     client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#     client.connect(
#         hostname=get_env_or_raise("SFTP_HOST"),
#         username=get_env_or_raise("SFTP_USER"),
#         password=get_env_or_raise("SFTP_PASSWORD"),
#     )
#     return client.open_sftp()
