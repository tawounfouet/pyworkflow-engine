"""
Tests unitaires — jobs/ingestion/imf

Couvre :
- ``IMFClient``        : factory, _get (mocké), fetch_*_meta, fetch_raw_indicator,
                         fetch_normalized — filtres années, valeurs null
- ``fetch_metadata``   : step isolé
- ``fetch_raw_data``   : step isolé — succès, indicateur ignoré, tout vide
- ``validate_raw``     : cas valid / empty / indicateurs partiellement vides
- ``normalize_records``: filtre années, valeurs null, skip si empty
- ``load_to_datalake`` : skip liste vide, écriture fichier, partition par date
- ``ingest_imf.build()``: structure du job décoré (5 steps, dépendances, retry, timeout)
- Intégration moteur en mémoire (sans réseau) via mocks
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.models.enums import RunStatus

# ── Fixtures ─────────────────────────────────────────────────────────────

INDICATORS_META = {
    "NGDP_RPCH": "GDP, constant prices",
    "PCPIPCH": "Inflation, average consumer prices",
    "LUR": "Unemployment rate",
}

COUNTRIES_META = {
    "FRA": "France",
    "USA": "United States",
    "DEU": "Germany",
}

# Données brutes simulant la réponse de /{INDICATOR}
RAW_NGDP: dict[str, dict[str, Any]] = {
    "FRA": {"2020": -7.9, "2021": 6.8, "2022": 2.5},
    "USA": {"2020": -2.8, "2021": 5.9, "2022": 2.1},
}
RAW_PCPIPCH: dict[str, dict[str, Any]] = {
    "FRA": {"2020": 0.5, "2021": 1.6, "2022": 5.2},
    "USA": {"2020": 1.2, "2021": 4.7, "2022": 8.0},
}
RAW_LUR: dict[str, dict[str, Any]] = {
    "FRA": {"2020": 8.0, "2021": 7.9, "2022": 7.3},
    "DEU": {"2020": 3.8, "2021": 3.6, "2022": 3.0},
    "USA": {"2020": 8.1, "2021": 5.4, "2022": None},  # valeur null
}

# raw_data tel que retourné par fetch_raw_data
FULL_RAW_DATA = {
    "NGDP_RPCH": RAW_NGDP,
    "PCPIPCH": RAW_PCPIPCH,
    "LUR": RAW_LUR,
}


# ═══════════════════════════════════════════════════════════════════════════
# IMFClient — tests unitaires
# ═══════════════════════════════════════════════════════════════════════════


class TestIMFClientFromEnv:
    def test_valeurs_par_defaut(self) -> None:
        from jobs.ingestion.imf.client import IMFClient, DEFAULT_INDICATORS

        with patch.dict("os.environ", {}, clear=False):
            for var in [
                "IMF_BASE_URL",
                "IMF_TIMEOUT",
                "IMF_INDICATORS",
                "IMF_YEAR_FROM",
                "IMF_YEAR_TO",
            ]:
                os.environ.pop(var, None)
            client = IMFClient.from_env()

        assert client.base_url == "https://www.imf.org/external/datamapper/api/v1"
        assert client.timeout == 60
        assert client.indicators == DEFAULT_INDICATORS
        assert client.year_from == 2000

    def test_surcharge_via_env(self) -> None:
        from jobs.ingestion.imf.client import IMFClient

        with patch.dict(
            "os.environ",
            {
                "IMF_BASE_URL": "http://localhost:9000",
                "IMF_TIMEOUT": "30",
                "IMF_INDICATORS": "NGDP_RPCH,LUR",
                "IMF_YEAR_FROM": "2015",
                "IMF_YEAR_TO": "2023",
            },
        ):
            client = IMFClient.from_env()

        assert client.base_url == "http://localhost:9000"
        assert client.timeout == 30
        assert client.indicators == ["NGDP_RPCH", "LUR"]
        assert client.year_from == 2015
        assert client.year_to == 2023

    def test_indicators_vide_utilise_defaut(self) -> None:
        from jobs.ingestion.imf.client import IMFClient, DEFAULT_INDICATORS

        with patch.dict("os.environ", {"IMF_INDICATORS": ""}):
            client = IMFClient.from_env()

        assert client.indicators == DEFAULT_INDICATORS


import os  # noqa: E402 (besoin pour les tests os.environ.pop)


class TestIMFClientGet:
    def _make_client(self) -> Any:
        from jobs.ingestion.imf.client import IMFClient

        return IMFClient(base_url="http://mock", timeout=5, indicators=["NGDP_RPCH"])

    def test_get_succes(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client._get("indicators")
        assert result == {"ok": True}

    def test_get_http_error_leve_runtime(self) -> None:
        import urllib.error  # noqa: PLC0415

        client = self._make_client()
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                "http://mock/indicators", 404, "Not Found", {}, None  # type: ignore[arg-type]
            ),
        ):
            with pytest.raises(RuntimeError, match="404"):
                client._get("indicators")

    def test_get_url_error_leve_runtime(self) -> None:
        import urllib.error  # noqa: PLC0415

        client = self._make_client()
        with patch(
            "urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")
        ):
            with pytest.raises(RuntimeError, match="réseau"):
                client._get("indicators")


class TestIMFClientFetchMeta:
    def _mock_get(self, client: Any, return_value: dict[str, Any]) -> Any:
        return patch.object(client, "_get", return_value=return_value)

    def test_fetch_indicators_meta(self) -> None:
        from jobs.ingestion.imf.client import IMFClient

        client = IMFClient()
        payload = {
            "indicators": {
                "NGDP_RPCH": {"label": "GDP"},
                "LUR": {"label": "Unemployment"},
            }
        }
        with self._mock_get(client, payload):
            meta = client.fetch_indicators_meta()
        assert meta == {"NGDP_RPCH": "GDP", "LUR": "Unemployment"}

    def test_fetch_countries_meta(self) -> None:
        from jobs.ingestion.imf.client import IMFClient

        client = IMFClient()
        payload = {
            "countries": {"FRA": {"label": "France"}, "USA": {"label": "United States"}}
        }
        with self._mock_get(client, payload):
            meta = client.fetch_countries_meta()
        assert meta == {"FRA": "France", "USA": "United States"}

    def test_fetch_indicators_meta_champ_label_absent(self) -> None:
        from jobs.ingestion.imf.client import IMFClient

        client = IMFClient()
        payload = {"indicators": {"NGDP_RPCH": {}}}  # pas de "label"
        with self._mock_get(client, payload):
            meta = client.fetch_indicators_meta()
        assert meta["NGDP_RPCH"] == "NGDP_RPCH"  # code utilisé comme fallback


class TestIMFClientFetchRawIndicator:
    def test_retourne_dict_pays_annees(self) -> None:
        from jobs.ingestion.imf.client import IMFClient

        client = IMFClient()
        payload = {"values": {"NGDP_RPCH": RAW_NGDP}}
        with patch.object(client, "_get", return_value=payload):
            result = client.fetch_raw_indicator("NGDP_RPCH")
        assert result == RAW_NGDP

    def test_indicateur_absent_retourne_vide(self) -> None:
        from jobs.ingestion.imf.client import IMFClient

        client = IMFClient()
        payload = {"values": {}}
        with patch.object(client, "_get", return_value=payload):
            result = client.fetch_raw_indicator("INCONNU")
        assert result == {}


class TestIMFClientFetchNormalized:
    def test_filtre_years(self) -> None:
        from jobs.ingestion.imf.client import IMFClient

        client = IMFClient(indicators=["NGDP_RPCH"], year_from=2021, year_to=2021)
        with patch.object(client, "fetch_raw_indicator", return_value=RAW_NGDP):
            records = client.fetch_normalized(INDICATORS_META, COUNTRIES_META)
        years = {r.year for r in records}
        assert years == {2021}

    def test_valeur_null_conservee(self) -> None:
        from jobs.ingestion.imf.client import IMFClient

        client = IMFClient(indicators=["LUR"], year_from=2022, year_to=2022)
        with patch.object(client, "fetch_raw_indicator", return_value=RAW_LUR):
            records = client.fetch_normalized(INDICATORS_META, COUNTRIES_META)
        usa_record = next((r for r in records if r.country == "USA"), None)
        assert usa_record is not None
        assert usa_record.value is None

    def test_label_pays_inconnu_utilise_code(self) -> None:
        from jobs.ingestion.imf.client import IMFClient

        client = IMFClient(indicators=["NGDP_RPCH"], year_from=2020, year_to=2020)
        raw = {"XYZ": {"2020": 1.0}}  # pays inconnu dans countries_meta
        with patch.object(client, "fetch_raw_indicator", return_value=raw):
            records = client.fetch_normalized(INDICATORS_META, {})
        assert records[0].country_label == "XYZ"

    def test_indicateur_en_erreur_ignore(self) -> None:
        from jobs.ingestion.imf.client import IMFClient

        client = IMFClient(indicators=["NGDP_RPCH"], year_from=2020, year_to=2022)
        with patch.object(
            client, "fetch_raw_indicator", side_effect=RuntimeError("404")
        ):
            records = client.fetch_normalized(INDICATORS_META, COUNTRIES_META)
        assert records == []

    def test_to_dict(self) -> None:
        from jobs.ingestion.imf.client import IMFRecord

        r = IMFRecord("NGDP_RPCH", "GDP", "FRA", "France", 2022, 2.5)
        d = r.to_dict()
        assert d["indicator"] == "NGDP_RPCH"
        assert d["country"] == "FRA"
        assert d["year"] == 2022
        assert d["value"] == 2.5


# ═══════════════════════════════════════════════════════════════════════════
# Steps isolés
# ═══════════════════════════════════════════════════════════════════════════


class TestStepFetchMetadata:
    def test_retourne_meta(self) -> None:
        from jobs.ingestion.imf.extract_imf import fetch_metadata
        from jobs.ingestion.imf.client import IMFClient

        mock_client = MagicMock()
        mock_client.fetch_indicators_meta.return_value = INDICATORS_META
        mock_client.fetch_countries_meta.return_value = COUNTRIES_META

        with patch.object(IMFClient, "from_env", return_value=mock_client):
            result = fetch_metadata()

        assert result["indicators_meta"] == INDICATORS_META
        assert result["countries_meta"] == COUNTRIES_META
        assert result["indicator_count"] == 3
        assert result["country_count"] == 3


class TestStepFetchRawData:
    def _mock_client(self) -> MagicMock:
        from jobs.ingestion.imf.client import IMFClient

        mock = MagicMock(spec=IMFClient)
        mock.indicators = ["NGDP_RPCH", "PCPIPCH"]
        mock.year_from = 2020
        mock.year_to = 2022

        def side_effect(code: str) -> dict:
            return {"NGDP_RPCH": RAW_NGDP, "PCPIPCH": RAW_PCPIPCH}.get(code, {})

        mock.fetch_raw_indicator.side_effect = side_effect
        return mock

    def test_retourne_raw_data(self) -> None:
        from jobs.ingestion.imf.extract_imf import fetch_raw_data
        from jobs.ingestion.imf.client import IMFClient

        with patch.object(IMFClient, "from_env", return_value=self._mock_client()):
            result = fetch_raw_data(
                indicators_meta=INDICATORS_META,
                countries_meta=COUNTRIES_META,
            )

        assert "NGDP_RPCH" in result["raw_data"]
        assert "PCPIPCH" in result["raw_data"]
        assert result["indicators_fetched"] == ["NGDP_RPCH", "PCPIPCH"]
        assert result["record_count_raw"] > 0

    def test_indicateur_en_erreur_ignore(self) -> None:
        from jobs.ingestion.imf.extract_imf import fetch_raw_data
        from jobs.ingestion.imf.client import IMFClient

        mock = self._mock_client()
        mock.fetch_raw_indicator.side_effect = RuntimeError("network error")

        with patch.object(IMFClient, "from_env", return_value=mock):
            result = fetch_raw_data()

        assert result["indicators_fetched"] == []
        assert result["record_count_raw"] == 0

    def test_tous_vides(self) -> None:
        from jobs.ingestion.imf.extract_imf import fetch_raw_data
        from jobs.ingestion.imf.client import IMFClient

        mock = self._mock_client()
        mock.fetch_raw_indicator.side_effect = (
            None  # clear side_effect so return_value is used
        )
        mock.fetch_raw_indicator.return_value = {}

        with patch.object(IMFClient, "from_env", return_value=mock):
            result = fetch_raw_data()

        assert result["record_count_raw"] == 0


class TestStepValidateRaw:
    def test_valid(self) -> None:
        from jobs.ingestion.imf.extract_imf import validate_raw

        result = validate_raw(
            raw_data=FULL_RAW_DATA,
            indicators_fetched=list(FULL_RAW_DATA.keys()),
            record_count_raw=100,
        )
        assert result["status"] == "valid"

    def test_empty_si_aucun_fetch(self) -> None:
        from jobs.ingestion.imf.extract_imf import validate_raw

        result = validate_raw(raw_data={}, indicators_fetched=[], record_count_raw=0)
        assert result["status"] == "empty"

    def test_empty_si_zero_points(self) -> None:
        from jobs.ingestion.imf.extract_imf import validate_raw

        result = validate_raw(
            raw_data={"NGDP_RPCH": {}},
            indicators_fetched=["NGDP_RPCH"],
            record_count_raw=0,
        )
        assert result["status"] == "empty"

    def test_indicateurs_partiellement_vides_dans_empty_indicators(self) -> None:
        from jobs.ingestion.imf.extract_imf import validate_raw

        result = validate_raw(
            raw_data={"NGDP_RPCH": RAW_NGDP, "LUR": {}},
            indicators_fetched=["NGDP_RPCH", "LUR"],
            record_count_raw=6,
        )
        assert result["status"] == "valid"
        assert "LUR" in result["empty_indicators"]

    def test_none_defaults(self) -> None:
        from jobs.ingestion.imf.extract_imf import validate_raw

        result = validate_raw()
        assert result["status"] == "empty"


class TestStepNormalizeRecords:
    def _mock_client(self, year_from: int = 2020, year_to: int = 2022) -> MagicMock:
        from jobs.ingestion.imf.client import IMFClient

        mock = MagicMock(spec=IMFClient)
        mock.year_from = year_from
        mock.year_to = year_to
        return mock

    def test_normalise_records(self) -> None:
        from jobs.ingestion.imf.extract_imf import normalize_records
        from jobs.ingestion.imf.client import IMFClient

        with patch.object(IMFClient, "from_env", return_value=self._mock_client()):
            result = normalize_records(
                raw_data={"NGDP_RPCH": RAW_NGDP},
                indicators_meta=INDICATORS_META,
                countries_meta=COUNTRIES_META,
                indicators_fetched=["NGDP_RPCH"],
                status="valid",
            )

        assert result["record_count"] > 0
        rec = result["records"][0]
        assert "indicator" in rec
        assert "country" in rec
        assert "year" in rec
        assert "value" in rec
        assert "indicator_label" in rec
        assert "country_label" in rec

    def test_skip_si_empty(self) -> None:
        from jobs.ingestion.imf.extract_imf import normalize_records
        from jobs.ingestion.imf.client import IMFClient

        with patch.object(IMFClient, "from_env", return_value=self._mock_client()):
            result = normalize_records(status="empty")

        assert result["records"] == []
        assert result["record_count"] == 0

    def test_filtre_annees(self) -> None:
        from jobs.ingestion.imf.extract_imf import normalize_records
        from jobs.ingestion.imf.client import IMFClient

        with patch.object(
            IMFClient, "from_env", return_value=self._mock_client(2022, 2022)
        ):
            result = normalize_records(
                raw_data={"NGDP_RPCH": RAW_NGDP},
                indicators_meta=INDICATORS_META,
                countries_meta=COUNTRIES_META,
                indicators_fetched=["NGDP_RPCH"],
                status="valid",
            )

        years = {r["year"] for r in result["records"]}
        assert years == {2022}

    def test_null_value_compte(self) -> None:
        from jobs.ingestion.imf.extract_imf import normalize_records
        from jobs.ingestion.imf.client import IMFClient

        with patch.object(
            IMFClient, "from_env", return_value=self._mock_client(2022, 2022)
        ):
            result = normalize_records(
                raw_data={"LUR": RAW_LUR},
                indicators_meta=INDICATORS_META,
                countries_meta=COUNTRIES_META,
                indicators_fetched=["LUR"],
                status="valid",
            )

        assert result["null_value_count"] == 1

    def test_label_pays_inconnu(self) -> None:
        from jobs.ingestion.imf.extract_imf import normalize_records
        from jobs.ingestion.imf.client import IMFClient

        raw = {"NGDP_RPCH": {"XYZ": {"2021": 1.0}}}
        with patch.object(
            IMFClient, "from_env", return_value=self._mock_client(2021, 2021)
        ):
            result = normalize_records(
                raw_data=raw,
                indicators_meta=INDICATORS_META,
                countries_meta={},
                indicators_fetched=["NGDP_RPCH"],
                status="valid",
            )
        assert result["records"][0]["country_label"] == "XYZ"


class TestStepLoadToDatalake:
    def test_skip_si_vide(self) -> None:
        from jobs.ingestion.imf.extract_imf import load_to_datalake

        result = load_to_datalake(records=[], record_count=0, ingest_date="2026-04-12")
        assert result["skipped"] is True
        assert result["rows_written"] == 0

    def test_skip_si_none(self) -> None:
        from jobs.ingestion.imf.extract_imf import load_to_datalake

        result = load_to_datalake()
        assert result["skipped"] is True

    def test_ecrit_dans_datalake(self, tmp_path: Path) -> None:
        from jobs.ingestion.imf.extract_imf import load_to_datalake

        records = [
            {"indicator": "NGDP_RPCH", "country": "FRA", "year": 2022, "value": 2.5}
        ]
        with patch.dict("os.environ", {"DATALAKE_PATH": str(tmp_path)}):
            result = load_to_datalake(
                records=records, record_count=1, ingest_date="2026-04-12"
            )

        assert result["skipped"] is False
        assert result["rows_written"] == 1
        assert "2026-04-12" in result["path"]

        output = tmp_path / "raw" / "imf" / "indicators" / "2026-04-12" / "data.json"
        assert output.exists()
        data = json.loads(output.read_text())
        assert data[0]["indicator"] == "NGDP_RPCH"

    def test_partition_dans_path(self, tmp_path: Path) -> None:
        from jobs.ingestion.imf.extract_imf import load_to_datalake

        records = [{"indicator": "LUR", "country": "DEU", "year": 2021, "value": 3.6}]
        with patch.dict("os.environ", {"DATALAKE_PATH": str(tmp_path)}):
            result = load_to_datalake(
                records=records, record_count=1, ingest_date="2025-10-01"
            )

        assert "2025-10-01" in result["path"]


# ═══════════════════════════════════════════════════════════════════════════
# Structure du job décoré
# ═══════════════════════════════════════════════════════════════════════════


class TestJobStructure:
    def test_build_retourne_un_job(self) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf
        from pyworkflow_engine.models import Job

        assert isinstance(ingest_imf.build(), Job)

    def test_nom_et_version(self) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf

        job = ingest_imf.build()
        assert job.name == "ingestion-imf"
        assert job.version == "1.0.0"

    def test_cinq_steps(self) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf

        assert len(ingest_imf.build().steps) == 5

    def test_noms_steps_dans_ordre(self) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf

        names = [s.name for s in ingest_imf.build().steps]
        assert names == [
            "fetch_metadata",
            "fetch_raw_data",
            "validate_raw",
            "normalize_records",
            "load_to_datalake",
        ]

    def test_dependances(self) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf

        steps = {s.name: s for s in ingest_imf.build().steps}
        assert steps["fetch_metadata"].dependencies == []
        assert steps["fetch_raw_data"].dependencies == ["fetch_metadata"]
        assert steps["validate_raw"].dependencies == ["fetch_raw_data"]
        assert set(steps["normalize_records"].dependencies) == {
            "fetch_raw_data",
            "fetch_metadata",
            "validate_raw",
        }
        assert steps["load_to_datalake"].dependencies == ["normalize_records"]

    def test_retry_fetch_raw_data(self) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf

        step = next(s for s in ingest_imf.build().steps if s.name == "fetch_raw_data")
        assert step.retry_count == 3

    def test_timeout_fetch_raw_data(self) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf
        from datetime import timedelta

        step = next(s for s in ingest_imf.build().steps if s.name == "fetch_raw_data")
        assert step.timeout == timedelta(seconds=600)

    def test_pas_de_cycles(self) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf
        from pyworkflow_engine.engine.dag import DAGResolver

        order = DAGResolver(ingest_imf.build()).get_execution_order()
        assert len(order) == 5

    def test_exit_step(self) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf

        assert ingest_imf.build().get_exit_steps() == ["load_to_datalake"]


# ═══════════════════════════════════════════════════════════════════════════
# Intégration moteur (sans réseau)
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_client(
    indicators: list[str] | None = None,
    raw_map: dict[str, Any] | None = None,
) -> MagicMock:
    from jobs.ingestion.imf.client import IMFClient

    mock = MagicMock(spec=IMFClient)
    mock.indicators = indicators or ["NGDP_RPCH", "PCPIPCH"]
    mock.year_from = 2020
    mock.year_to = 2022
    mock.fetch_indicators_meta.return_value = INDICATORS_META
    mock.fetch_countries_meta.return_value = COUNTRIES_META
    _raw = raw_map or {"NGDP_RPCH": RAW_NGDP, "PCPIPCH": RAW_PCPIPCH}
    mock.fetch_raw_indicator.side_effect = lambda code: _raw.get(code, {})
    return mock


class TestIngestionMoteur:
    def test_pipeline_complet(self, tmp_path: Path) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf
        from jobs.ingestion.imf.client import IMFClient

        with (
            patch.object(IMFClient, "from_env", return_value=_make_mock_client()),
            patch.dict("os.environ", {"DATALAKE_PATH": str(tmp_path)}),
        ):
            result = WorkflowEngine().run(
                ingest_imf.build(),
                initial_context={"ingest_date": "2026-04-12"},
            )

        assert result.status == RunStatus.SUCCESS

        assert result.get_step_run("fetch_metadata").output_data["indicator_count"] == 3
        assert result.get_step_run("validate_raw").output_data["status"] == "valid"

        norm = result.get_step_run("normalize_records").output_data
        assert norm["record_count"] > 0
        assert norm["null_value_count"] == 0

        load = result.get_step_run("load_to_datalake").output_data
        assert load["skipped"] is False
        assert load["rows_written"] > 0

        output = tmp_path / "raw" / "imf" / "indicators" / "2026-04-12" / "data.json"
        assert output.exists()
        data = json.loads(output.read_text())
        assert len(data) == load["rows_written"]

    def test_pipeline_tous_indicateurs_vides(self, tmp_path: Path) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf
        from jobs.ingestion.imf.client import IMFClient

        with (
            patch.object(
                IMFClient,
                "from_env",
                return_value=_make_mock_client(
                    raw_map={"NGDP_RPCH": {}, "PCPIPCH": {}}
                ),
            ),
            patch.dict("os.environ", {"DATALAKE_PATH": str(tmp_path)}),
        ):
            result = WorkflowEngine().run(
                ingest_imf.build(),
                initial_context={"ingest_date": "2026-04-12"},
            )

        assert result.get_step_run("validate_raw").output_data["status"] == "empty"
        assert result.get_step_run("load_to_datalake").output_data["skipped"] is True

    def test_pipeline_avec_valeurs_null(self, tmp_path: Path) -> None:
        from jobs.ingestion.imf.extract_imf import ingest_imf
        from jobs.ingestion.imf.client import IMFClient

        with (
            patch.object(
                IMFClient,
                "from_env",
                return_value=_make_mock_client(
                    indicators=["LUR"],
                    raw_map={"LUR": RAW_LUR},
                ),
            ),
            patch.dict("os.environ", {"DATALAKE_PATH": str(tmp_path)}),
        ):
            result = WorkflowEngine().run(
                ingest_imf.build(),
                initial_context={"ingest_date": "2026-04-12"},
            )

        assert result.status == RunStatus.SUCCESS
        norm = result.get_step_run("normalize_records").output_data
        assert norm["null_value_count"] == 1
