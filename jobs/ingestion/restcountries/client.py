"""
RestCountriesClient — Connecteur HTTP pour REST Countries API v3.1.

Adapté depuis ``_archives/import_countries.py`` (commande de gestion Django).
La logique de fetch, parsing et normalisation est extraite en client pur
sans aucune dépendance Django.

Variables d'environnement :
    RESTCOUNTRIES_BASE_URL        : URL de base (défaut : https://restcountries.com/v3.1)
    RESTCOUNTRIES_INDEPENDENT_ONLY: "true" → pays indépendants seulement (défaut : false)
    RESTCOUNTRIES_TIMEOUT         : Timeout HTTP en secondes (défaut : 30)

Dépendances : ``requests`` (opt-in via extra ``[http]``)
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any

from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.ingestion.restcountries.client")

_DEFAULT_BASE_URL = "https://restcountries.com/v3.1"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# ── Helpers de conversion ────────────────────────────────────────────────


def _safe_str(value: Any) -> str:
    """Retourne une chaîne vide si la valeur est None."""
    return "" if value is None else str(value).strip()


def _safe_decimal(value: Any) -> Decimal | None:
    """Convertit en Decimal ; retourne None si impossible."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    """Convertit en int ; retourne None si impossible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ── Normalisation d'un enregistrement brut ──────────────────────────────


def parse_country(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise un enregistrement brut de l'API REST Countries.

    Adapté depuis la méthode ``handle()`` de la commande Django
    ``import_countries.py``.  Retourne un dict Python pur — aucune
    dépendance Django (pas de ``Model``, pas d'ORM).

    Args:
        raw: Dict brut retourné par l'API REST Countries v3.1.

    Returns:
        Dict normalisé avec types Python natifs (str, int, Decimal, list, dict).

    Raises:
        ValueError: Si le code ISO Alpha-2 est absent (champ obligatoire).
    """
    iso_alpha2 = _safe_str(raw.get("cca2"))
    if not iso_alpha2:
        raise ValueError("Code ISO Alpha-2 (cca2) manquant dans l'enregistrement")

    # ── Codes ISO ──────────────────────────────────────────────────────
    iso_alpha3 = _safe_str(raw.get("cca3"))
    iso_numeric = _safe_str(raw.get("ccn3"))

    # ── Noms ──────────────────────────────────────────────────────────
    name_data: dict[str, Any] = raw.get("name", {})
    name_common_en = _safe_str(name_data.get("common"))
    name_official_en = _safe_str(name_data.get("official"))

    translations: dict[str, Any] = raw.get("translations", {})
    fra = translations.get("fra", {})
    name_common_fr = _safe_str(fra.get("common"))
    name_official_fr = _safe_str(fra.get("official"))

    native_name_data: dict[str, Any] = name_data.get("nativeName", {})
    name_native = ""
    if native_name_data:
        first_native = next(iter(native_name_data.values()), {})
        name_native = _safe_str(first_native.get("common", ""))

    # ── Géographie ────────────────────────────────────────────────────
    region = _safe_str(raw.get("region"))
    subregion = _safe_str(raw.get("subregion"))
    capitals: list[str] = raw.get("capital", []) or []
    landlocked: bool = raw.get("landlocked", False)
    borders: list[str] = raw.get("borders", []) or []
    continents: list[str] = raw.get("continents", []) or []

    latlng: list[Any] = raw.get("latlng", []) or []
    latitude = _safe_decimal(latlng[0] if len(latlng) > 0 else None)
    longitude = _safe_decimal(latlng[1] if len(latlng) > 1 else None)
    area_km2 = _safe_decimal(raw.get("area"))

    # ── Population ────────────────────────────────────────────────────
    population = _safe_int(raw.get("population"))

    # ── Devises ───────────────────────────────────────────────────────
    currencies_data: dict[str, Any] = raw.get("currencies", {}) or {}
    currency_code = ""
    currency_name = ""
    currency_symbol = ""
    if currencies_data:
        currency_code = next(iter(currencies_data))
        currency_info = currencies_data[currency_code]
        currency_name = _safe_str(currency_info.get("name"))
        currency_symbol = _safe_str(currency_info.get("symbol"))

    # ── Langues ───────────────────────────────────────────────────────
    languages: dict[str, str] = raw.get("languages", {}) or {}
    official_languages: list[str] = list(languages.values())

    # ── Symboles ──────────────────────────────────────────────────────
    flag_emoji = _safe_str(raw.get("flag"))
    flags: dict[str, Any] = raw.get("flags", {}) or {}
    flag_svg_url = _safe_str(flags.get("svg"))
    flag_png_url = _safe_str(flags.get("png"))

    coat_of_arms: dict[str, Any] = raw.get("coatOfArms", {}) or {}
    coat_of_arms_svg_url = _safe_str(coat_of_arms.get("svg"))
    coat_of_arms_png_url = _safe_str(coat_of_arms.get("png"))

    # ── Internet & téléphonie ─────────────────────────────────────────
    tld: list[str] = raw.get("tld", []) or []
    idd: dict[str, Any] = raw.get("idd", {}) or {}
    calling_code_root = _safe_str(idd.get("root"))
    calling_code_suffixes: list[str] = idd.get("suffixes", []) or []

    # ── Fuseaux horaires ──────────────────────────────────────────────
    timezones: list[str] = raw.get("timezones", []) or []

    # ── Statut ────────────────────────────────────────────────────────
    independent: bool = raw.get("independent", False)
    un_member: bool = raw.get("unMember", False)
    status = _safe_str(raw.get("status"))

    # ── Divers ────────────────────────────────────────────────────────
    maps: dict[str, Any] = raw.get("maps", {}) or {}
    google_maps_url = _safe_str(maps.get("googleMaps"))
    openstreetmap_url = _safe_str(maps.get("openStreetMaps"))
    start_of_week = _safe_str(raw.get("startOfWeek"))
    car_data: dict[str, Any] = raw.get("car", {}) or {}
    car_side = _safe_str(car_data.get("side"))

    return {
        # Identifiants
        "iso_alpha2": iso_alpha2,
        "iso_alpha3": iso_alpha3,
        "iso_numeric": iso_numeric,
        # Noms
        "name_common_en": name_common_en,
        "name_official_en": name_official_en,
        "name_common_fr": name_common_fr,
        "name_official_fr": name_official_fr,
        "name_native": name_native,
        # Région
        "region": region,
        "subregion": subregion,
        # Géographie
        "capitals": capitals,
        "latitude": str(latitude) if latitude is not None else None,
        "longitude": str(longitude) if longitude is not None else None,
        "area_km2": str(area_km2) if area_km2 is not None else None,
        "landlocked": landlocked,
        "borders": borders,
        "continents": continents,
        "population": population,
        # Devises
        "currencies": currencies_data,
        "currency_code": currency_code,
        "currency_name": currency_name,
        "currency_symbol": currency_symbol,
        # Langues
        "languages": languages,
        "official_languages": official_languages,
        # Symboles
        "flag_emoji": flag_emoji,
        "flag_svg_url": flag_svg_url,
        "flag_png_url": flag_png_url,
        "coat_of_arms_svg_url": coat_of_arms_svg_url,
        "coat_of_arms_png_url": coat_of_arms_png_url,
        # Internet & téléphonie
        "tld": tld,
        "calling_code_root": calling_code_root,
        "calling_code_suffixes": calling_code_suffixes,
        # Fuseaux horaires
        "timezones": timezones,
        # Statut
        "independent": independent,
        "un_member": un_member,
        "status": status,
        # Divers
        "google_maps_url": google_maps_url,
        "openstreetmap_url": openstreetmap_url,
        "start_of_week": start_of_week,
        "car_side": car_side,
        # Méta
        "source_api": "REST Countries API v3.1",
        "raw_data": raw,
    }


# ── Client ───────────────────────────────────────────────────────────────


class RestCountriesClient:
    """Client HTTP pour REST Countries API v3.1.

    Args:
        base_url: URL de base de l'API.
        independent_only: Si ``True``, ne charge que les pays indépendants.
        timeout: Timeout HTTP en secondes.
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        independent_only: bool = False,
        timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._independent_only = independent_only
        self._timeout = timeout

    @classmethod
    def from_env(cls) -> RestCountriesClient:
        """Factory depuis variables d'environnement."""
        return cls(
            base_url=os.environ.get("RESTCOUNTRIES_BASE_URL", _DEFAULT_BASE_URL),
            independent_only=os.environ.get(
                "RESTCOUNTRIES_INDEPENDENT_ONLY", "false"
            ).lower()
            == "true",
            timeout=int(os.environ.get("RESTCOUNTRIES_TIMEOUT", "30")),
        )

    # ── Fetch ─────────────────────────────────────────────────────────

    def fetch_raw(self) -> list[dict[str, Any]]:
        """Appelle l'API et retourne les données brutes (listes de dicts JSON).

        Effectue une ou deux requêtes selon ``independent_only`` :
        - ``independent?status=true`` — pays indépendants (toujours)
        - ``independent?status=false`` — territoires non-indépendants (si ``independent_only=False``)

        Returns:
            Liste brute de dicts JSON (non normalisés).

        Raises:
            RuntimeError: Si aucune donnée n'est récupérée.
            ImportError: Si ``requests`` n'est pas installé.
        """
        try:
            import requests  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "Le package 'requests' est requis pour RestCountriesClient. "
                "Installez-le avec : pip install requests"
            ) from exc

        endpoints = [f"{self._base_url}/independent?status=true"]
        if not self._independent_only:
            endpoints.append(f"{self._base_url}/independent?status=false")

        all_raw: list[dict[str, Any]] = []

        for url in endpoints:
            _logger.info("Appel API : %s", url)
            try:
                response = requests.get(url, headers=_HEADERS, timeout=self._timeout)
                response.raise_for_status()
                batch: list[dict[str, Any]] = response.json()
                _logger.info("%d pays récupérés depuis %s", len(batch), url)
                all_raw.extend(batch)
            except requests.exceptions.RequestException as exc:
                if self._independent_only:
                    raise RuntimeError(f"Erreur API REST Countries : {exc}") from exc
                _logger.warning(
                    "Erreur sur %s (non fatal, endpoint optionnel) : %s", url, exc
                )

        if not all_raw:
            raise RuntimeError(
                "Aucune donnée récupérée depuis l'API REST Countries. "
                "Vérifiez la connectivité réseau ou RESTCOUNTRIES_BASE_URL."
            )

        _logger.info("Total brut : %d enregistrements", len(all_raw))
        return all_raw

    def fetch_normalized(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Fetch + normalisation + dédoublonnage par ``cca2``.

        Returns:
            Tuple ``(pays_normalisés, erreurs)`` où chaque erreur est un dict
            ``{"index": int, "cca2": str, "error": str}``.
        """
        raw_list = self.fetch_raw()

        normalized: dict[str, dict[str, Any]] = {}  # cca2 → record (dédoublonnage)
        errors: list[dict[str, Any]] = []

        for i, raw in enumerate(raw_list):
            try:
                record = parse_country(raw)
                cca2 = record["iso_alpha2"]
                if cca2 in normalized:
                    _logger.debug("Doublon ignoré : %s (index %d)", cca2, i)
                    continue
                normalized[cca2] = record
            except (ValueError, KeyError) as exc:
                errors.append(
                    {
                        "index": i,
                        "cca2": raw.get("cca2", "?"),
                        "error": str(exc),
                    }
                )
                _logger.warning("Erreur parsing pays index %d : %s", i, exc)

        _logger.info(
            "Normalisation terminée : %d pays valides, %d erreurs",
            len(normalized),
            len(errors),
        )
        return list(normalized.values()), errors
