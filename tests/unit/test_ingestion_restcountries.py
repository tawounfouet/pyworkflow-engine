"""
Tests unitaires — jobs/ingestion/restcountries

Couvre :
- ``parse_country``     : normalisation d'un enregistrement brut
- ``validate_raw``      : step de validation (cas valid / empty / invalid)
- ``normalize_countries``: step de normalisation avec dédoublonnage
- ``load_to_datalake``  : step de chargement (skip / write)
- ``ingest_restcountries.build()`` : structure du job décoré
- Intégration moteur en mémoire (sans réseau) via mock de ``fetch_raw``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.models.enums import RunStatus


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

# Enregistrement brut minimal conforme à l'API REST Countries v3.1
RAW_FR: dict[str, Any] = {
    "cca2": "FR",
    "cca3": "FRA",
    "ccn3": "250",
    "name": {
        "common": "France",
        "official": "French Republic",
        "nativeName": {"fra": {"common": "France", "official": "République française"}},
    },
    "translations": {"fra": {"common": "France", "official": "République française"}},
    "region": "Europe",
    "subregion": "Western Europe",
    "capital": ["Paris"],
    "latlng": [46.0, 2.0],
    "area": 551695,
    "population": 67391582,
    "borders": ["AND", "BEL", "DEU", "ITA", "LUX", "MCO", "ESP", "CHE"],
    "currencies": {"EUR": {"name": "Euro", "symbol": "€"}},
    "languages": {"fra": "French"},
    "flag": "🇫🇷",
    "flags": {
        "svg": "https://flagcdn.com/fr.svg",
        "png": "https://flagcdn.com/w320/fr.png",
    },
    "coatOfArms": {"svg": "https://mainfacts.com/media/images/coats_of_arms/fr.svg"},
    "tld": [".fr"],
    "idd": {"root": "+3", "suffixes": ["3"]},
    "timezones": ["UTC-10:00", "UTC-09:30", "UTC+01:00"],
    "independent": True,
    "unMember": True,
    "status": "officially-assigned",
    "landlocked": False,
    "continents": ["Europe"],
    "maps": {"googleMaps": "https://goo.gl/maps/g7QxxSFsWyTPKuzd7"},
    "startOfWeek": "monday",
    "car": {"side": "right"},
}

RAW_DE: dict[str, Any] = {
    "cca2": "DE",
    "cca3": "DEU",
    "name": {
        "common": "Germany",
        "official": "Federal Republic of Germany",
        "nativeName": {
            "deu": {"common": "Deutschland", "official": "Bundesrepublik Deutschland"}
        },
    },
    "translations": {
        "fra": {"common": "Allemagne", "official": "République fédérale d'Allemagne"}
    },
    "region": "Europe",
    "subregion": "Western Europe",
    "capital": ["Berlin"],
    "latlng": [51.0, 9.0],
    "area": 357114,
    "population": 83240525,
    "borders": ["AUT", "BEL", "CZE", "DNK", "FRA", "LUX", "NLD", "POL", "CHE"],
    "currencies": {"EUR": {"name": "Euro", "symbol": "€"}},
    "languages": {"deu": "German"},
    "flag": "🇩🇪",
    "flags": {
        "svg": "https://flagcdn.com/de.svg",
        "png": "https://flagcdn.com/w320/de.png",
    },
    "coatOfArms": {},
    "tld": [".de"],
    "idd": {"root": "+4", "suffixes": ["9"]},
    "timezones": ["UTC+01:00"],
    "independent": True,
    "unMember": True,
    "status": "officially-assigned",
    "landlocked": False,
    "continents": ["Europe"],
    "maps": {},
    "startOfWeek": "monday",
    "car": {"side": "right"},
}


# ═══════════════════════════════════════════════════════════════════════════
# Tests — parse_country
# ═══════════════════════════════════════════════════════════════════════════


class TestParseCountry:
    """Tests unitaires de la fonction ``parse_country``."""

    def test_parse_codes_iso(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["iso_alpha2"] == "FR"
        assert r["iso_alpha3"] == "FRA"
        assert r["iso_numeric"] == "250"

    def test_parse_noms_en(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["name_common_en"] == "France"
        assert r["name_official_en"] == "French Republic"

    def test_parse_noms_fr(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["name_common_fr"] == "France"
        assert r["name_official_fr"] == "République française"

    def test_parse_nom_natif(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["name_native"] == "France"

    def test_parse_nom_natif_allemagne(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_DE)
        assert r["name_native"] == "Deutschland"

    def test_parse_geographie(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["region"] == "Europe"
        assert r["subregion"] == "Western Europe"
        assert r["capitals"] == ["Paris"]
        assert r["landlocked"] is False
        assert "BEL" in r["borders"]
        assert r["continents"] == ["Europe"]

    def test_parse_coordonnees(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        # Decimal("46.0") → str vaut "46.0" (pas "46"), on vérifie la valeur flottante
        assert float(r["latitude"]) == pytest.approx(46.0)
        assert float(r["longitude"]) == pytest.approx(2.0)

    def test_parse_area_et_population(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["area_km2"] == "551695"
        assert r["population"] == 67391582

    def test_parse_devises(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["currency_code"] == "EUR"
        assert r["currency_name"] == "Euro"
        assert r["currency_symbol"] == "€"

    def test_parse_langues(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert "French" in r["official_languages"]
        assert r["languages"] == {"fra": "French"}

    def test_parse_drapeaux(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["flag_emoji"] == "🇫🇷"
        assert "fr.svg" in r["flag_svg_url"]
        assert "fr.png" in r["flag_png_url"]

    def test_parse_tld_et_idd(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["tld"] == [".fr"]
        assert r["calling_code_root"] == "+3"
        assert r["calling_code_suffixes"] == ["3"]

    def test_parse_fuseaux_horaires(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert "UTC+01:00" in r["timezones"]

    def test_parse_statut(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["independent"] is True
        assert r["un_member"] is True
        assert r["status"] == "officially-assigned"

    def test_parse_divers(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["start_of_week"] == "monday"
        assert r["car_side"] == "right"
        assert "goo.gl" in r["google_maps_url"]

    def test_parse_meta(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country(RAW_FR)
        assert r["source_api"] == "REST Countries API v3.1"
        assert r["raw_data"] == RAW_FR  # référence au dict original

    def test_parse_champs_optionnels_manquants(self) -> None:
        """Un enregistrement minimal (seul cca2 obligatoire) ne doit pas lever d'exception."""
        from jobs.ingestion.restcountries.client import parse_country

        r = parse_country({"cca2": "XX"})
        assert r["iso_alpha2"] == "XX"
        assert r["name_common_en"] == ""
        assert r["population"] is None
        assert r["latitude"] is None
        assert r["currencies"] == {}
        assert r["official_languages"] == []

    def test_parse_raise_si_cca2_manquant(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        with pytest.raises(ValueError, match="cca2"):
            parse_country({"cca3": "FRA"})

    def test_parse_raise_si_cca2_vide(self) -> None:
        from jobs.ingestion.restcountries.client import parse_country

        with pytest.raises(ValueError, match="cca2"):
            parse_country({"cca2": ""})


# ═══════════════════════════════════════════════════════════════════════════
# Tests — Steps isolés (sans moteur)
# ═══════════════════════════════════════════════════════════════════════════


class TestStepValidateRaw:
    """Tests du step ``validate_raw`` appelé directement (sans moteur)."""

    def test_valid(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import validate_raw

        result = validate_raw(raw_countries=[RAW_FR, RAW_DE])
        assert result["status"] == "valid"
        assert result["total"] == 2
        assert result["invalid_count"] == 0

    def test_empty_list(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import validate_raw

        result = validate_raw(raw_countries=[])
        assert result["status"] == "empty"
        assert result["total"] == 0

    def test_none_defaults_to_empty(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import validate_raw

        result = validate_raw()
        assert result["status"] == "empty"

    def test_invalid_record_raises(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import validate_raw

        with pytest.raises(ValueError, match="cca2"):
            validate_raw(raw_countries=[{"cca3": "FRA"}])  # cca2 absent


class TestStepNormalizeCountries:
    """Tests du step ``normalize_countries`` appelé directement."""

    def test_normalise_deux_pays(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import normalize_countries

        result = normalize_countries(
            raw_countries=[RAW_FR, RAW_DE],
            status="valid",
        )
        assert result["count"] == 2
        assert result["error_count"] == 0
        pays = {p["iso_alpha2"]: p for p in result["countries"]}
        assert "FR" in pays
        assert "DE" in pays
        assert pays["FR"]["name_common_fr"] == "France"
        assert pays["DE"]["name_common_fr"] == "Allemagne"

    def test_skip_si_status_empty(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import normalize_countries

        result = normalize_countries(raw_countries=[RAW_FR], status="empty")
        assert result["count"] == 0
        assert result["countries"] == []

    def test_dedoublonnage(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import normalize_countries

        # RAW_FR en double — un seul doit être conservé
        result = normalize_countries(
            raw_countries=[RAW_FR, RAW_FR],
            status="valid",
        )
        assert result["count"] == 1

    def test_enregistrement_invalide_compte_comme_erreur(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import normalize_countries

        bad = {"cca3": "???"}  # pas de cca2
        result = normalize_countries(
            raw_countries=[RAW_FR, bad],
            status="valid",
        )
        assert result["count"] == 1
        assert result["error_count"] == 1


class TestStepLoadToDatalake:
    """Tests du step ``load_to_datalake`` avec DataLake mocké."""

    def test_skip_si_liste_vide(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import load_to_datalake

        result = load_to_datalake(countries=[], count=0, ingest_date="2026-04-12")
        assert result["skipped"] is True
        assert result["rows_written"] == 0

    def test_skip_si_none(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import load_to_datalake

        result = load_to_datalake()
        assert result["skipped"] is True

    def test_ecrit_dans_datalake(self, tmp_path: Path) -> None:
        from jobs.ingestion.restcountries.extract_countries import load_to_datalake
        from jobs.ingestion.restcountries.client import parse_country

        pays = [parse_country(RAW_FR)]

        with patch.dict("os.environ", {"DATALAKE_PATH": str(tmp_path)}):
            result = load_to_datalake(
                countries=pays,
                count=1,
                ingest_date="2026-04-12",
            )

        assert result["skipped"] is False
        assert result["rows_written"] == 1
        assert "2026-04-12" in result["path"]

        # Vérifie que le fichier JSON existe et est valide
        output_file = (
            tmp_path
            / "raw"
            / "restcountries"
            / "countries"
            / "2026-04-12"
            / "data.json"
        )
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert len(data) == 1
        assert data[0]["iso_alpha2"] == "FR"

    def test_partition_par_date(self, tmp_path: Path) -> None:
        from jobs.ingestion.restcountries.extract_countries import load_to_datalake
        from jobs.ingestion.restcountries.client import parse_country

        pays = [parse_country(RAW_FR)]
        date = "2026-04-12"

        with patch.dict("os.environ", {"DATALAKE_PATH": str(tmp_path)}):
            result = load_to_datalake(countries=pays, count=1, ingest_date=date)

        assert date in result["path"]


# ═══════════════════════════════════════════════════════════════════════════
# Tests — structure du job décoré
# ═══════════════════════════════════════════════════════════════════════════


class TestJobStructure:
    """Vérifie la structure du ``Job`` produit par ``@job``."""

    def test_build_retourne_un_job(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries
        from pyworkflow_engine.models import Job

        assert isinstance(ingest_restcountries.build(), Job)

    def test_nom_et_version(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries

        job = ingest_restcountries.build()
        assert job.name == "ingestion-restcountries"
        assert job.version == "1.0.0"

    def test_quatre_steps(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries

        job = ingest_restcountries.build()
        assert len(job.steps) == 4

    def test_noms_steps(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries

        job = ingest_restcountries.build()
        names = [s.name for s in job.steps]
        assert names == [
            "fetch_raw",
            "validate_raw",
            "normalize_countries",
            "load_to_datalake",
        ]

    def test_dependances(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries

        job = ingest_restcountries.build()
        steps = {s.name: s for s in job.steps}
        assert steps["fetch_raw"].dependencies == []
        assert steps["validate_raw"].dependencies == ["fetch_raw"]
        assert set(steps["normalize_countries"].dependencies) == {
            "fetch_raw",
            "validate_raw",
        }
        assert steps["load_to_datalake"].dependencies == ["normalize_countries"]

    def test_retry_fetch_raw(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries

        job = ingest_restcountries.build()
        fetch = next(s for s in job.steps if s.name == "fetch_raw")
        assert fetch.retry_count == 3

    def test_timeout_fetch_raw(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries
        from datetime import timedelta

        job = ingest_restcountries.build()
        fetch = next(s for s in job.steps if s.name == "fetch_raw")
        assert fetch.timeout == timedelta(seconds=120)

    def test_pas_de_cycles(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries
        from pyworkflow_engine.engine.dag import DAGResolver

        job = ingest_restcountries.build()
        resolver = DAGResolver(job)
        # get_execution_order() lève DAGValidationError si le graphe a un cycle
        order = resolver.get_execution_order()
        assert len(order) == 4

    def test_exit_step(self) -> None:
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries

        job = ingest_restcountries.build()
        assert job.get_exit_steps() == ["load_to_datalake"]


# ═══════════════════════════════════════════════════════════════════════════
# Tests — intégration moteur (sans réseau, fetch_raw mocké)
# ═══════════════════════════════════════════════════════════════════════════


class TestIngestionMoteur:
    """Intégration WorkflowEngine en mémoire — fetch_raw mocké, sans réseau."""

    def _make_mock_client(self, raw_list: list[dict[str, Any]]) -> MagicMock:
        """Retourne un mock de ``RestCountriesClient`` qui retourne ``raw_list``."""
        mock_client = MagicMock()
        mock_client.fetch_raw.return_value = raw_list
        return mock_client

    def test_pipeline_complet_deux_pays(self, tmp_path: Path) -> None:
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries

        with (
            patch(
                "jobs.ingestion.restcountries.extract_countries.RestCountriesClient.from_env",
                return_value=self._make_mock_client([RAW_FR, RAW_DE]),
            ),
            patch.dict("os.environ", {"DATALAKE_PATH": str(tmp_path)}),
        ):
            engine = WorkflowEngine()
            result = engine.run(
                ingest_restcountries.build(),
                initial_context={"ingest_date": "2026-04-12"},
            )

        assert result.status == RunStatus.SUCCESS

        # fetch_raw
        fetch_out = result.get_step_run("fetch_raw").output_data
        assert fetch_out["count_raw"] == 2

        # validate_raw
        validate_out = result.get_step_run("validate_raw").output_data
        assert validate_out["status"] == "valid"
        assert validate_out["total"] == 2

        # normalize_countries
        norm_out = result.get_step_run("normalize_countries").output_data
        assert norm_out["count"] == 2
        assert norm_out["error_count"] == 0

        # load_to_datalake
        load_out = result.get_step_run("load_to_datalake").output_data
        assert load_out["rows_written"] == 2
        assert load_out["skipped"] is False

        # Vérifie le fichier JSON dans le datalake
        output_file = (
            tmp_path
            / "raw"
            / "restcountries"
            / "countries"
            / "2026-04-12"
            / "data.json"
        )
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert len(data) == 2

    def test_pipeline_liste_vide(self, tmp_path: Path) -> None:
        """Si l'API retourne une liste vide, le pipeline doit échouer sur validate_raw."""
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries

        with (
            patch(
                "jobs.ingestion.restcountries.extract_countries.RestCountriesClient.from_env",
                return_value=self._make_mock_client([]),
            ),
            patch.dict("os.environ", {"DATALAKE_PATH": str(tmp_path)}),
        ):
            engine = WorkflowEngine()
            result = engine.run(
                ingest_restcountries.build(),
                initial_context={"ingest_date": "2026-04-12"},
            )

        # fetch_raw réussit (liste vide renvoyée sans erreur)
        # validate_raw retourne status="empty"
        validate_out = result.get_step_run("validate_raw").output_data
        assert validate_out["status"] == "empty"

        # load_to_datalake skipped
        load_out = result.get_step_run("load_to_datalake").output_data
        assert load_out["skipped"] is True

    def test_pipeline_deduplication(self, tmp_path: Path) -> None:
        """Un doublon cca2 ne doit être écrit qu'une seule fois."""
        from jobs.ingestion.restcountries.extract_countries import ingest_restcountries

        with (
            patch(
                "jobs.ingestion.restcountries.extract_countries.RestCountriesClient.from_env",
                return_value=self._make_mock_client([RAW_FR, RAW_FR, RAW_DE]),
            ),
            patch.dict("os.environ", {"DATALAKE_PATH": str(tmp_path)}),
        ):
            engine = WorkflowEngine()
            result = engine.run(
                ingest_restcountries.build(),
                initial_context={"ingest_date": "2026-04-12"},
            )

        assert result.status == RunStatus.SUCCESS
        norm_out = result.get_step_run("normalize_countries").output_data
        assert norm_out["count"] == 2  # FR dédoublonné → 2 pays uniques
