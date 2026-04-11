"""
Connecteur Stripe — Accès à l'API Stripe pour l'extraction de données.

Ce client encapsule les appels à l'API Stripe. En mode dev/test,
il utilise un mock intégré pour éviter les appels réseau.

Variables d'environnement :
    STRIPE_API_KEY  : Clé API Stripe (sk_test_... ou sk_live_...)
    STRIPE_BASE_URL : URL de base (optionnel, pour les tests)
"""

from __future__ import annotations

import os
from typing import Any


class StripeClient:
    """Connecteur vers l'API Stripe."""

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url or "https://api.stripe.com"

    @classmethod
    def from_env(cls) -> StripeClient:
        """Factory depuis variables d'environnement."""
        api_key = os.environ.get("STRIPE_API_KEY", "")
        if not api_key:
            # Mode démo : retourne un client mock
            return cls(api_key="sk_test_demo", base_url="mock://")
        return cls(api_key=api_key)

    def list_charges(
        self,
        created_gte: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Récupère les paiements (charges) depuis Stripe.

        Args:
            created_gte: Date ISO à partir de laquelle récupérer (incluse).
            limit: Nombre maximum d'enregistrements.

        Returns:
            Liste de dictionnaires représentant les charges Stripe.
        """
        if self._base_url == "mock://":
            return self._mock_charges(created_gte, limit)

        # Implémentation réelle avec l'API Stripe
        try:
            import stripe  # noqa: PLC0415

            stripe.api_key = self._api_key
            params: dict[str, Any] = {"limit": limit}
            if created_gte:
                import datetime  # noqa: PLC0415

                dt = datetime.datetime.fromisoformat(created_gte)
                params["created"] = {"gte": int(dt.timestamp())}
            charges = stripe.Charge.list(**params)
            return [dict(c) for c in charges.data]
        except ImportError:
            # Fallback mock si le package stripe n'est pas installé
            return self._mock_charges(created_gte, limit)

    def list_subscriptions(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Récupère les abonnements depuis Stripe.

        Args:
            limit: Nombre maximum d'enregistrements.

        Returns:
            Liste de dictionnaires représentant les subscriptions.
        """
        if self._base_url == "mock://":
            return self._mock_subscriptions(limit)

        try:
            import stripe  # noqa: PLC0415

            stripe.api_key = self._api_key
            subs = stripe.Subscription.list(limit=limit)
            return [dict(s) for s in subs.data]
        except ImportError:
            return self._mock_subscriptions(limit)

    # ── Mock data (dev / tests) ──────────────────────────────────────

    @staticmethod
    def _mock_charges(
        created_gte: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Données de démonstration pour les charges."""
        return [
            {
                "id": "ch_mock_001",
                "amount": 2500,
                "currency": "eur",
                "status": "succeeded",
                "created": 1744329600,
                "description": "Paiement démo #1",
            },
            {
                "id": "ch_mock_002",
                "amount": 7500,
                "currency": "eur",
                "status": "succeeded",
                "created": 1744329700,
                "description": "Paiement démo #2",
            },
            {
                "id": "ch_mock_003",
                "amount": 1200,
                "currency": "usd",
                "status": "failed",
                "created": 1744329800,
                "description": "Paiement démo #3",
            },
        ][:limit]

    @staticmethod
    def _mock_subscriptions(limit: int = 100) -> list[dict[str, Any]]:
        """Données de démonstration pour les subscriptions."""
        return [
            {
                "id": "sub_mock_001",
                "customer": "cus_mock_001",
                "status": "active",
                "plan_amount": 2900,
                "currency": "eur",
                "current_period_start": 1744329600,
                "current_period_end": 1746921600,
            },
            {
                "id": "sub_mock_002",
                "customer": "cus_mock_002",
                "status": "canceled",
                "plan_amount": 4900,
                "currency": "eur",
                "current_period_start": 1741824000,
                "current_period_end": 1744329600,
            },
        ][:limit]
