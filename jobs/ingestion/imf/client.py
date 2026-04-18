"""
IMFClient — Connecteur HTTP pour l'API IMF DataMapper v1.

Adapté depuis ``_archives/imf_v2.py``.
Zéro dépendance externe — utilise uniquement ``urllib`` de la stdlib.

Variables d'environnement :
    IMF_BASE_URL    : URL de base (défaut : https://www.imf.org/external/datamapper/api/v1)
    IMF_TIMEOUT     : Timeout HTTP en secondes (défaut : 60)
    IMF_INDICATORS  : Codes séparés par virgule (défaut : 6 indicateurs macro)
    IMF_YEAR_FROM   : Année de début incluse (défaut : 2000)
    IMF_YEAR_TO     : Année de fin incluse (défaut : année en cours)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.ingestion.imf.client")

_DEFAULT_BASE_URL = "https://www.imf.org/external/datamapper/api/v1"
_DEFAULT_TIMEOUT = 60
_HEADERS = {
    "Accept": "application/json",
    # Note : ne pas envoyer de User-Agent personnalisé — le WAF de l'IMF bloque
    # tout UA non-standard.  ``urllib`` envoie « Python-urllib/3.x » par défaut,
    # ce qui est accepté.
}

# Indicateurs macroéconomiques clés par défaut
DEFAULT_INDICATORS = [
    "NGDP_RPCH",  # Croissance du PIB réel (%)
    "PCPIPCH",  # Inflation, prix à la consommation (%)
    "LUR",  # Taux de chômage (% population active)
    "BCA_NGDPD",  # Solde courant (% du PIB)
    "GGXCNL_NGDP",  # Solde budgétaire net (% du PIB)
    "GGXWDG_NGDP",  # Dette publique brute (% du PIB)
]


# ── Dataclass résultat ───────────────────────────────────────────────────


@dataclass
class IMFRecord:
    """Un enregistrement normalisé issu de l'API IMF DataMapper."""

    indicator: str
    indicator_label: str
    country: str  # code ISO 3 lettres (ex : "FRA")
    country_label: str
    year: int
    value: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "indicator": self.indicator,
            "indicator_label": self.indicator_label,
            "country": self.country,
            "country_label": self.country_label,
            "year": self.year,
            "value": self.value,
        }


# ── Client ───────────────────────────────────────────────────────────────


@dataclass
class IMFClient:
    """Client HTTP pour l'API IMF DataMapper v1.

    Args:
        base_url:   URL de base de l'API.
        timeout:    Timeout HTTP en secondes.
        indicators: Codes indicateurs à extraire.
        year_from:  Année de début incluse. ``None`` = pas de filtre.
        year_to:    Année de fin incluse. ``None`` = pas de filtre.

    Examples:
        >>> client = IMFClient.from_env()
        >>> meta = client.fetch_indicators_meta()
        >>> "NGDP_RPCH" in meta
        True
    """

    base_url: str = _DEFAULT_BASE_URL
    timeout: int = _DEFAULT_TIMEOUT
    indicators: list[str] = field(default_factory=lambda: list(DEFAULT_INDICATORS))
    year_from: int | None = 2000
    year_to: int | None = None

    # ── Factory ───────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> IMFClient:
        """Construit un client depuis les variables d'environnement."""
        from datetime import UTC, datetime  # noqa: PLC0415

        raw_indicators = os.environ.get("IMF_INDICATORS", "").strip()
        indicators = (
            [i.strip() for i in raw_indicators.split(",") if i.strip()]
            if raw_indicators
            else list(DEFAULT_INDICATORS)
        )

        year_from_raw = os.environ.get("IMF_YEAR_FROM", "2000").strip()
        year_to_raw = os.environ.get("IMF_YEAR_TO", "").strip()

        return cls(
            base_url=os.environ.get("IMF_BASE_URL", _DEFAULT_BASE_URL).rstrip("/"),
            timeout=int(os.environ.get("IMF_TIMEOUT", str(_DEFAULT_TIMEOUT))),
            indicators=indicators,
            year_from=int(year_from_raw) if year_from_raw else None,
            year_to=int(year_to_raw) if year_to_raw else datetime.now(tz=UTC).year,
        )

    # ── HTTP ──────────────────────────────────────────────────────────

    def _get(self, path: str) -> Any:
        """Effectue un GET HTTP et retourne le JSON parsé.

        Args:
            path: Chemin relatif à ``base_url`` (ex. ``"indicators"``).

        Raises:
            RuntimeError: Sur erreur HTTP (4xx/5xx) ou réseau.
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        req = urllib.request.Request(url, headers=_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"IMF API HTTP {exc.code} — {url}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"IMF API réseau — {url} : {exc.reason}") from exc

    # ── Métadonnées ───────────────────────────────────────────────────

    def fetch_indicators_meta(self) -> dict[str, str]:
        """Retourne ``{code: label}`` pour tous les indicateurs disponibles.

        Returns:
            Dict de tous les codes indicateurs avec leur libellé.
        """
        _logger.info("Fetch métadonnées indicateurs — %s/indicators", self.base_url)
        data = self._get("indicators")
        meta = {k: v.get("label", k) for k, v in data.get("indicators", {}).items()}
        _logger.info("%d indicateurs disponibles", len(meta))
        return meta

    def fetch_countries_meta(self) -> dict[str, str]:
        """Retourne ``{iso3: label}`` pour tous les pays disponibles.

        Returns:
            Dict de tous les codes ISO 3 lettres avec le nom du pays.
        """
        _logger.info("Fetch métadonnées pays — %s/countries", self.base_url)
        data = self._get("countries")
        meta = {k: v.get("label", k) for k, v in data.get("countries", {}).items()}
        _logger.info("%d pays disponibles", len(meta))
        return meta

    def fetch_regions_meta(self) -> dict[str, str]:
        """Retourne ``{code: label}`` pour toutes les régions géographiques.

        Returns:
            Dict de tous les codes région avec leur libellé.
        """
        _logger.info("Fetch métadonnées régions — %s/regions", self.base_url)
        data = self._get("regions")
        meta = {k: v.get("label", k) for k, v in data.get("regions", {}).items()}
        _logger.info("%d régions disponibles", len(meta))
        return meta

    def fetch_groups_meta(self) -> dict[str, str]:
        """Retourne ``{code: label}`` pour tous les groupes analytiques.

        Returns:
            Dict de tous les codes groupe avec leur libellé.
        """
        _logger.info("Fetch métadonnées groupes — %s/groups", self.base_url)
        data = self._get("groups")
        meta = {k: v.get("label", k) for k, v in data.get("groups", {}).items()}
        _logger.info("%d groupes disponibles", len(meta))
        return meta

    def fetch_metadata_catalog(self) -> dict[str, dict[str, str]]:
        """Récupère les 4 ressources de référence en un seul appel.

        Effectue 4 requêtes séquentielles :
        ``/indicators``, ``/countries``, ``/regions``, ``/groups``.

        Returns:
            ``{"indicators": {...}, "countries": {...},
               "regions": {...}, "groups": {...}}``
        """
        return {
            "indicators": self.fetch_indicators_meta(),
            "countries": self.fetch_countries_meta(),
            "regions": self.fetch_regions_meta(),
            "groups": self.fetch_groups_meta(),
        }

    # ── Données ───────────────────────────────────────────────────────

    def fetch_raw_indicator(self, indicator: str) -> dict[str, dict[str, Any]]:
        """Retourne les données brutes pour un indicateur (tous pays).

        Args:
            indicator: Code indicateur (ex. ``"NGDP_RPCH"``).

        Returns:
            Dict ``{iso3: {year_str: value}}``

        Raises:
            RuntimeError: Sur erreur HTTP ou réseau.
        """
        _logger.debug("Fetch indicateur : %s", indicator)
        data = self._get(indicator)
        return data.get("values", {}).get(indicator, {})

    def fetch_normalized(
        self,
        indicators_meta: dict[str, str],
        countries_meta: dict[str, str],
    ) -> list[IMFRecord]:
        """Récupère et normalise tous les indicateurs configurés.

        Itère sur ``self.indicators``, appelle ``fetch_raw_indicator()``
        pour chacun et construit des ``IMFRecord`` filtrés par
        ``year_from`` / ``year_to``.

        Args:
            indicators_meta: ``{code: label}`` depuis ``fetch_indicators_meta()``.
            countries_meta:  ``{iso3: label}`` depuis ``fetch_countries_meta()``.

        Returns:
            Liste de ``IMFRecord`` normalisés, filtrés par année.
        """
        records: list[IMFRecord] = []

        for indicator_code in self.indicators:
            label = indicators_meta.get(indicator_code, indicator_code)
            try:
                raw = self.fetch_raw_indicator(indicator_code)
            except RuntimeError as exc:
                _logger.warning("Indicateur %s ignoré : %s", indicator_code, exc)
                continue

            for country_iso3, years_data in raw.items():
                country_label = countries_meta.get(country_iso3, country_iso3)
                for year_str, value in years_data.items():
                    try:
                        year = int(year_str)
                    except ValueError:
                        continue
                    if self.year_from and year < self.year_from:
                        continue
                    if self.year_to and year > self.year_to:
                        continue
                    records.append(
                        IMFRecord(
                            indicator=indicator_code,
                            indicator_label=label,
                            country=country_iso3,
                            country_label=country_label,
                            year=year,
                            value=float(value) if value is not None else None,
                        )
                    )

        return records
