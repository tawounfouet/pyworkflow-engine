"""
Connecteur pour [NOM_SOURCE].

TODO: Remplacer [NOM_SOURCE], TemplateClient, et les variables d'environnement.

Ce fichier sert de point de départ pour créer un connecteur vers une
nouvelle source de données. Voir la checklist complète dans :
``docs/data-plateforme/03-patterns-conventions.md`` § 9.
"""

from __future__ import annotations

import os
from typing import Any


class TemplateClient:
    """Connecteur vers [NOM_SOURCE].

    Exemples de sources : API REST, base de données, SFTP, etc.
    """

    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url

    @classmethod
    def from_env(cls) -> TemplateClient:
        """Factory depuis variables d'environnement.

        TODO: Remplacer par les vraies variables de la source.
        """
        return cls(
            api_key=os.environ["TODO_API_KEY"],
            base_url=os.environ.get("TODO_BASE_URL", "https://api.example.com"),
        )

    def fetch_data(
        self,
        since: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Extraction des données depuis la source.

        TODO: Implémenter l'appel réel (pagination, auth, retry…).

        Args:
            since: Date de début d'extraction (ISO 8601).
            limit: Nombre maximum d'enregistrements.

        Returns:
            Liste de dictionnaires bruts.
        """
        raise NotImplementedError("TODO: implémenter fetch_data pour cette source")
