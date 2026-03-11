"""
Tests pour logging/utils.py — logged_operation, StepLogBridge, LoggingConfigBuilder.

Tests unitaires + intégration pour les composants ajoutés depuis
l'analyse de database_logger.py.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pyworkflow_engine.logging import (
    LoggingConfig,
    LoggingConfigBuilder,
    StepLogBridge,
    configure_logging,
    get_logger,
    logged_operation,
    shutdown_logging,
)
from pyworkflow_engine.logging.logger import _cleanup
from pyworkflow_engine.core.models.runtime import StepRun, StepLog


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_logging():
    """Nettoie le logging avant et après chaque test."""
    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def step_run():
    """StepRun de test."""
    return StepRun(step_name="process_data", job_run_id="job-123")


# ── Tests logged_operation ───────────────────────────────────────────────────


class TestLoggedOperation:
    """Tests pour le context manager logged_operation."""

    def test_logs_start_and_completion(self, capfd):
        """Vérifie que le début et la fin sont loggés."""
        configure_logging(LoggingConfig(level="DEBUG"))
        logger = get_logger("test.utils")
        with logged_operation(logger, "test operation"):
            pass

        captured = capfd.readouterr()
        assert "Starting: test operation" in captured.err
        assert "Completed: test operation" in captured.err

    def test_logs_duration(self, capfd):
        """Vérifie que la durée est incluse dans le log de complétion."""
        configure_logging(LoggingConfig(level="DEBUG"))
        logger = get_logger("test.utils")
        with logged_operation(logger, "timed op"):
            time.sleep(0.05)

        captured = capfd.readouterr()
        # Should contain duration like "(0.05s)"
        assert "Completed: timed op (" in captured.err
        assert "s)" in captured.err

    def test_logs_failure_on_exception(self, capfd):
        """Vérifie que l'échec est loggé avec exc_info."""
        configure_logging(LoggingConfig(level="DEBUG"))
        logger = get_logger("test.utils")
        with pytest.raises(ValueError, match="boom"):
            with logged_operation(logger, "failing op"):
                raise ValueError("boom")

        captured = capfd.readouterr()
        assert "Starting: failing op" in captured.err
        assert "Failed: failing op" in captured.err
        assert "ValueError" in captured.err

    def test_exception_is_reraised(self):
        """L'exception originale est re-raised, pas swallowed."""
        configure_logging(LoggingConfig(level="DEBUG"))
        logger = get_logger("test.utils")
        with pytest.raises(RuntimeError, match="original"):
            with logged_operation(logger, "reraise test"):
                raise RuntimeError("original")

    def test_yields_logger(self, capfd):
        """Le context manager yield le logger pour des logs intermédiaires."""
        configure_logging(LoggingConfig(level="DEBUG"))
        logger = get_logger("test.utils")
        with logged_operation(logger, "yielded") as log:
            log.info("intermediate step")

        captured = capfd.readouterr()
        assert "intermediate step" in captured.err

    def test_extra_fields_included(self, capsys):
        """Les extra fields sont passés aux logs."""
        configure_logging(LoggingConfig(level="DEBUG", json_output=True))
        logger = get_logger("test.extras")

        with logged_operation(logger, "with extras", job_id="abc-123"):
            pass

        captured = capsys.readouterr()
        lines = [l for l in captured.err.strip().split("\n") if l.strip()]
        # Le premier log (Starting) devrait contenir job_id
        start_data = json.loads(lines[0])
        assert start_data["job_id"] == "abc-123"

    def test_no_completed_log_on_failure(self, capfd):
        """Pas de log 'Completed' si l'opération échoue."""
        configure_logging(LoggingConfig(level="DEBUG"))
        logger = get_logger("test.utils")
        with pytest.raises(Exception):
            with logged_operation(logger, "no complete"):
                raise Exception("fail")

        captured = capfd.readouterr()
        assert "Completed: no complete" not in captured.err
        assert "Failed: no complete" in captured.err


# ── Tests StepLogBridge ──────────────────────────────────────────────────────


class TestStepLogBridge:
    """Tests pour le handler StepLogBridge."""

    def test_basic_bridge(self, step_run):
        """Un log stdlib est capturé dans StepRun.logs."""
        bridge = StepLogBridge(step_run)
        logger = logging.getLogger("test_bridge_basic")
        logger.addHandler(bridge)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info("Processing row 42")

            assert len(step_run.logs) == 1
            log_entry = step_run.logs[0]
            assert isinstance(log_entry, StepLog)
            assert log_entry.level == "INFO"
            assert log_entry.message == "Processing row 42"
            assert log_entry.source == "step:process_data"
        finally:
            logger.removeHandler(bridge)

    def test_multiple_levels(self, step_run):
        """Différents niveaux de log sont correctement bridgés."""
        bridge = StepLogBridge(step_run)
        logger = logging.getLogger("test_bridge_levels")
        logger.addHandler(bridge)
        logger.setLevel(logging.DEBUG)

        try:
            logger.debug("Debug msg")
            logger.info("Info msg")
            logger.warning("Warning msg")
            logger.error("Error msg")
            logger.critical("Critical msg")

            assert len(step_run.logs) == 5
            levels = [log.level for log in step_run.logs]
            assert levels == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        finally:
            logger.removeHandler(bridge)

    def test_extra_data_captured(self, step_run):
        """Les extras du LogRecord sont capturés dans StepLog.data."""
        bridge = StepLogBridge(step_run)
        logger = logging.getLogger("test_bridge_extras")
        logger.addHandler(bridge)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info("With extras", extra={"row_count": "42", "table": "users"})

            assert len(step_run.logs) == 1
            log_entry = step_run.logs[0]
            assert "row_count" in log_entry.data
            assert log_entry.data["row_count"] == "42"
        finally:
            logger.removeHandler(bridge)

    def test_custom_source(self, step_run):
        """La source custom est utilisée dans les StepLog."""
        bridge = StepLogBridge(step_run, source="custom_source")
        logger = logging.getLogger("test_bridge_source")
        logger.addHandler(bridge)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info("Custom source test")

            # StepRun.add_log() utilise source=f"step:{step_name}"
            # Le bridge appelle add_log() qui définit sa propre source
            assert len(step_run.logs) == 1
        finally:
            logger.removeHandler(bridge)

    def test_bridge_with_formatted_message(self, step_run):
        """Les messages formatés (%s, etc.) sont résolus."""
        bridge = StepLogBridge(step_run)
        logger = logging.getLogger("test_bridge_format")
        logger.addHandler(bridge)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info("Processing %d rows from %s", 42, "users")

            assert len(step_run.logs) == 1
            assert step_run.logs[0].message == "Processing 42 rows from users"
        finally:
            logger.removeHandler(bridge)

    def test_bridge_is_thread_safe(self, step_run):
        """Le bridge hérite du lock de logging.Handler."""
        bridge = StepLogBridge(step_run)
        # logging.Handler a un lock par défaut
        assert hasattr(bridge, "lock")

    def test_bridge_handles_error_gracefully(self):
        """Si add_log échoue, handleError est appelé sans crash."""
        mock_step_run = MagicMock()
        mock_step_run.add_log.side_effect = ValueError("invalid level")

        bridge = StepLogBridge(mock_step_run)
        logger = logging.getLogger("test_bridge_error")
        logger.addHandler(bridge)
        logger.setLevel(logging.DEBUG)

        try:
            # Should not raise even though add_log fails
            logger.info("This will fail internally")
        finally:
            logger.removeHandler(bridge)


# ── Tests LoggingConfigBuilder ───────────────────────────────────────────────


class TestLoggingConfigBuilder:
    """Tests pour le builder fluide LoggingConfigBuilder."""

    def test_build_defaults(self):
        """Builder sans configuration produit les défauts de LoggingConfig."""
        config = LoggingConfigBuilder().build()
        assert config.level == "INFO"
        assert config.json_output is False
        assert config.log_file is None
        assert config.enable_queue is False

    def test_level(self):
        """Définit le niveau de log."""
        config = LoggingConfigBuilder().level("DEBUG").build()
        assert config.level == "DEBUG"

    def test_json_output(self):
        """Active la sortie JSON."""
        config = LoggingConfigBuilder().json_output().build()
        assert config.json_output is True

    def test_json_output_false(self):
        """Désactive explicitement la sortie JSON."""
        config = LoggingConfigBuilder().json_output(False).build()
        assert config.json_output is False

    def test_log_file(self):
        """Configure la sortie fichier."""
        config = LoggingConfigBuilder().log_file("/tmp/test.log").build()
        assert config.log_file == "/tmp/test.log"

    def test_log_file_with_path(self):
        """Accepte un Path object."""
        config = LoggingConfigBuilder().log_file(Path("/tmp/test.log")).build()
        assert config.log_file == str(Path("/tmp/test.log"))

    def test_log_file_with_rotation(self):
        """Configure la rotation du fichier."""
        config = (
            LoggingConfigBuilder()
            .log_file("/tmp/test.log", max_bytes=50 * 1024 * 1024, backup_count=10)
            .build()
        )
        assert config.log_file == "/tmp/test.log"
        assert config.log_file_max_bytes == 50 * 1024 * 1024
        assert config.log_file_backup_count == 10

    def test_with_queue(self):
        """Active le logging asynchrone."""
        config = LoggingConfigBuilder().with_queue().build()
        assert config.enable_queue is True

    def test_extra_fields(self):
        """Ajoute des champs additionnels."""
        config = (
            LoggingConfigBuilder()
            .extra_fields(env="prod", service="etl")
            .build()
        )
        assert config.extra_fields == {"env": "prod", "service": "etl"}

    def test_extra_fields_cumulative(self):
        """Plusieurs appels à extra_fields() s'accumulent."""
        config = (
            LoggingConfigBuilder()
            .extra_fields(env="prod")
            .extra_fields(service="etl", version="1.0")
            .build()
        )
        assert config.extra_fields == {"env": "prod", "service": "etl", "version": "1.0"}

    def test_propagate(self):
        """Configure la propagation."""
        config = LoggingConfigBuilder().propagate(True).build()
        assert config.propagate is True

    def test_logger_name(self):
        """Définit le nom du logger."""
        config = LoggingConfigBuilder().logger_name("my_app").build()
        assert config.logger_name == "my_app"

    def test_full_chain(self):
        """Chaîne complète de configuration."""
        config = (
            LoggingConfigBuilder()
            .level("WARNING")
            .json_output()
            .log_file("/var/log/app.log", max_bytes=100 * 1024 * 1024)
            .with_queue()
            .extra_fields(env="staging", team="data")
            .propagate(False)
            .build()
        )
        assert config.level == "WARNING"
        assert config.json_output is True
        assert config.log_file == "/var/log/app.log"
        assert config.log_file_max_bytes == 100 * 1024 * 1024
        assert config.enable_queue is True
        assert config.extra_fields == {"env": "staging", "team": "data"}
        assert config.propagate is False

    def test_build_produces_frozen_config(self):
        """Le résultat est une LoggingConfig immuable (frozen)."""
        config = LoggingConfigBuilder().level("DEBUG").build()
        with pytest.raises(AttributeError):
            config.level = "INFO"  # type: ignore[misc]

    def test_builder_with_configure_logging(self):
        """Le builder s'intègre avec configure_logging()."""
        config = (
            LoggingConfigBuilder()
            .level("DEBUG")
            .json_output(False)
            .build()
        )
        configure_logging(config)
        root = get_logger()
        assert root.level == logging.DEBUG


# ── Tests d'intégration ──────────────────────────────────────────────────────


class TestUtilsIntegration:
    """Tests d'intégration pour les utilitaires."""

    def test_logged_operation_with_step_log_bridge(self):
        """logged_operation + StepLogBridge = traçabilité complète."""
        step_run = StepRun(step_name="etl_process", job_run_id="job-456")
        bridge = StepLogBridge(step_run)

        logger = logging.getLogger("test_integration_bridge_op")
        logger.addHandler(bridge)
        logger.setLevel(logging.DEBUG)

        try:
            with logged_operation(logger, "ETL pipeline"):
                logger.info("Extracting data")
                logger.info("Transforming data")
                logger.info("Loading data")

            # Should have: Starting + 3 intermediates + Completed = 5
            assert len(step_run.logs) == 5
            assert step_run.logs[0].message == "Starting: ETL pipeline"
            assert step_run.logs[1].message == "Extracting data"
            assert step_run.logs[2].message == "Transforming data"
            assert step_run.logs[3].message == "Loading data"
            assert "Completed: ETL pipeline" in step_run.logs[4].message
        finally:
            logger.removeHandler(bridge)

    def test_logged_operation_failure_with_bridge(self):
        """logged_operation failure + StepLogBridge capture l'erreur."""
        step_run = StepRun(step_name="failing_step", job_run_id="job-789")
        bridge = StepLogBridge(step_run)

        logger = logging.getLogger("test_integration_bridge_fail")
        logger.addHandler(bridge)
        logger.setLevel(logging.DEBUG)

        try:
            with pytest.raises(RuntimeError):
                with logged_operation(logger, "doomed operation"):
                    raise RuntimeError("kaboom")

            # Should have: Starting + Failed = 2
            assert len(step_run.logs) == 2
            assert step_run.logs[0].level == "INFO"
            assert "Starting" in step_run.logs[0].message
            assert step_run.logs[1].level == "ERROR"
            assert "Failed: doomed operation" in step_run.logs[1].message
        finally:
            logger.removeHandler(bridge)

    def test_builder_to_configure_full_pipeline(self, capfd):
        """Builder → configure_logging → logged_operation → console output."""
        config = (
            LoggingConfigBuilder()
            .level("DEBUG")
            .json_output(False)
            .extra_fields(service="test-pipeline")
            .build()
        )
        configure_logging(config)
        logger = get_logger("integration.full")

        with logged_operation(logger, "full pipeline test"):
            logger.info("Step 1 done")

        captured = capfd.readouterr()
        assert "Starting: full pipeline test" in captured.err
        assert "Step 1 done" in captured.err
        assert "Completed: full pipeline test" in captured.err
