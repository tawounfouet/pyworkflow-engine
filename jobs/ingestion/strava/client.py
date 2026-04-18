"""
StravaClient — Connecteur HTTP pour Strava API v3.

Adapté depuis ``_archives/jules_strava-api-v3/strava_client.py``.
Extraction en client pur sans dépendances externes au projet.

Authentification : OAuth2 Refresh Token (token renouvelé automatiquement).

Variables d'environnement :
    STRAVA_CLIENT_ID      : Client ID de l'application Strava
    STRAVA_CLIENT_SECRET  : Client Secret de l'application Strava
    STRAVA_REFRESH_TOKEN  : Refresh token (généré par setup_auth.py)

Rate limits Strava :
    - 200 req / 15 min
    - 2 000 req / jour
    Le client gère automatiquement les 429 avec attente + retry.
"""

from __future__ import annotations

import os
import time
from typing import Any

from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.ingestion.strava.client")

_BASE_URL = "https://www.strava.com/api/v3"
_TOKEN_URL = "https://www.strava.com/oauth/token"

# Pause entre les pages de pagination (Strava recommande de ne pas spammer)
_PAGE_PAUSE_S = 2.0


class RateLimitExceededException(Exception):
    """Levée quand les quotas Strava sont épuisés (15 min ou journalier)."""


class StravaClient:
    """Client HTTP Strava API v3 avec gestion OAuth2 et rate limiting.

    Usage::

        client = StravaClient.from_env()
        athlete = client.get("/athlete")
        activities = client.get_paginated("/athlete/activities", per_page=200)
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        max_retries: int = 3,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._max_retries = max_retries
        self._access_token: str | None = None
        self._refresh_access_token()

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> StravaClient:
        """Factory depuis variables d'environnement.

        Lit ``STRAVA_CLIENT_ID``, ``STRAVA_CLIENT_SECRET``,
        ``STRAVA_REFRESH_TOKEN``.

        Raises:
            EnvironmentError: Si une variable est manquante.
        """
        missing = [
            v
            for v in (
                "STRAVA_CLIENT_ID",
                "STRAVA_CLIENT_SECRET",
                "STRAVA_REFRESH_TOKEN",
            )
            if not os.environ.get(v)
        ]
        if missing:
            raise EnvironmentError(
                f"Variables d'environnement manquantes : {', '.join(missing)}"
            )
        return cls(
            client_id=os.environ["STRAVA_CLIENT_ID"],
            client_secret=os.environ["STRAVA_CLIENT_SECRET"],
            refresh_token=os.environ["STRAVA_REFRESH_TOKEN"],
        )

    # ── OAuth2 ───────────────────────────────────────────────────────────────

    def _refresh_access_token(self) -> None:
        """Renouvelle l'access token via le refresh token."""
        import requests  # noqa: PLC0415

        _logger.info("Renouvellement du token Strava...")
        response = requests.post(
            _TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access_token"]
        # Strava peut retourner un nouveau refresh token
        if data.get("refresh_token") and data["refresh_token"] != self._refresh_token:
            self._refresh_token = data["refresh_token"]
            _logger.debug("Refresh token mis à jour.")
        _logger.success("✅ Token Strava renouvelé.")

    # ── Requêtes ─────────────────────────────────────────────────────────────

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Effectue une requête GET sur l'API Strava.

        Gère automatiquement :
        - Renouvellement du token (401)
        - Rate limiting (429) avec attente de 15 min ou backoff exponentiel

        Args:
            endpoint: Chemin relatif, ex: ``"/athlete"``
            params:   Paramètres de requête optionnels

        Returns:
            Données JSON désérialisées.

        Raises:
            RateLimitExceededException: Si les quotas journaliers sont épuisés.
        """
        import requests  # noqa: PLC0415

        url = f"{_BASE_URL}{endpoint}"
        headers = {"Authorization": f"Bearer {self._access_token}"}

        for attempt in range(self._max_retries + 1):
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 401:
                _logger.warning("Token expiré, renouvellement...")
                self._refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                continue

            if response.status_code == 429:
                if attempt >= self._max_retries:
                    raise RateLimitExceededException(
                        "Rate limit atteint après tous les retries. Réessayez dans 15 min."
                    )
                self._handle_rate_limit(response, attempt)
                continue

            self._log_rate_usage(response)
            response.raise_for_status()
            return response.json()

        raise RateLimitExceededException("Rate limit atteint après tous les retries.")

    def get_paginated(
        self,
        endpoint: str,
        per_page: int = 200,
        start_page: int = 1,
        extra_params: dict[str, Any] | None = None,
        page_callback: Any = None,
    ) -> list[dict[str, Any]]:
        """Parcourt toutes les pages d'un endpoint paginé.

        S'arrête quand la page retourne une liste vide.
        Applique une pause de ``_PAGE_PAUSE_S`` secondes entre chaque page.

        Args:
            endpoint:      Chemin relatif, ex: ``"/athlete/activities"``
            per_page:      Nombre d'éléments par page (max 200 pour Strava).
            start_page:    Page de départ (reprise sur crash).
            extra_params:  Paramètres additionnels à passer à chaque requête.
            page_callback: Callable(page, items) appelé après chaque page
                           (pour la sauvegarde intermédiaire ou le suivi d'état).

        Returns:
            Liste complète de tous les items récupérés depuis ``start_page``.

        Raises:
            RateLimitExceededException: Si les quotas sont épuisés.
        """
        all_items: list[dict[str, Any]] = []
        page = start_page

        while True:
            _logger.info("📄 Page %d (per_page=%d)...", page, per_page)
            params = {"page": page, "per_page": per_page, **(extra_params or {})}
            items = self.get(endpoint, params=params)

            if not items:
                _logger.info(
                    "✅ Plus d'éléments — pagination terminée (page %d).", page
                )
                break

            all_items.extend(items)
            _logger.info(
                "   → %d éléments récupérés (total courant : %d)",
                len(items),
                len(all_items),
            )

            if page_callback is not None:
                page_callback(page, items)

            page += 1
            time.sleep(_PAGE_PAUSE_S)

        return all_items

    # ── Helpers internes ─────────────────────────────────────────────────────

    def _handle_rate_limit(self, response: Any, attempt: int) -> None:
        """Gère les réponses 429 en attendant le délai approprié."""
        usage = response.headers.get("X-RateLimit-Usage", "")
        limit = response.headers.get("X-RateLimit-Limit", "")

        if usage and limit:
            _, usage_daily = map(int, usage.split(","))
            _, limit_daily = map(int, limit.split(","))
            if usage_daily >= limit_daily:
                raise RateLimitExceededException(
                    f"Quota journalier atteint ({usage_daily}/{limit_daily}). Réessayez demain."
                )
            wait = 15 * 60  # 15 min pour la fenêtre glissante
            _logger.warning("⏳ Rate limit 15 min atteint. Attente %ds...", wait)
            time.sleep(wait)
        else:
            wait = 60 * (2**attempt)  # backoff exponentiel
            _logger.warning(
                "⏳ Rate limit 429. Attente %ds (tentative %d/%d)...",
                wait,
                attempt + 1,
                self._max_retries,
            )
            time.sleep(wait)

    def _log_rate_usage(self, response: Any) -> None:
        """Log l'utilisation des quotas si les headers sont présents."""
        limit_header = response.headers.get("X-RateLimit-Limit")
        usage_header = response.headers.get("X-RateLimit-Usage")
        if limit_header and usage_header:
            lim_15m, lim_day = map(int, limit_header.split(","))
            use_15m, use_day = map(int, usage_header.split(","))
            _logger.debug(
                "API usage — 15min: %d/%d, daily: %d/%d",
                use_15m,
                lim_15m,
                use_day,
                lim_day,
            )
            if use_15m >= lim_15m * 0.8:
                _logger.warning(
                    "⚠️  Approche de la limite 15 min : %d/%d", use_15m, lim_15m
                )
