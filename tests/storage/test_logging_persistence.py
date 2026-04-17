# filepath: tests/storage/test_logging_persistence.py
"""
Tests — Logging Persistence (ADR-018, décision 4).

Vérifie :
    - WorkflowLog CRUD via Repository
    - RepositoryLogHandler : emit, batch flush, corrélation
    - WorkflowLogQuery : filtres, pagination
    - Intégration UnifiedStorage.logs
"""

from __future__ import annotations

import logging
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

import pytest

from pyworkflow_engine.adapters.storage.repository import Repository
from pyworkflow_engine.adapters.storage.schema_generator import SchemaGenerator
from pyworkflow_engine.adapters.storage.unified import UnifiedStorage
from pyworkflow_engine.logging.handlers import RepositoryLogHandler
from pyworkflow_engine.models.logging.log_entry import WorkflowLog, WorkflowLogQuery
from pyworkflow_engine.ports.persistable import ModelRegistry


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_registry():
    """Sauvegarde et restaure le ModelRegistry autour de chaque test."""
    saved = ModelRegistry.get_all()
    yield
    ModelRegistry.clear()
    for model in saved.values():
        ModelRegistry.register(model)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    """Connexion SQLite in-memory avec table log_entries créée."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")

    meta = WorkflowLog.__table_meta__
    create_sql = SchemaGenerator.generate_create_table(meta)
    connection.execute(create_sql)
    for idx_sql in SchemaGenerator.generate_indexes(meta):
        connection.execute(idx_sql)
    connection.commit()
    return connection


@pytest.fixture()
def log_repo(conn: sqlite3.Connection) -> Repository[WorkflowLog]:
    """Repository[WorkflowLog] prêt à l'emploi."""
    return Repository(conn, WorkflowLog)


@pytest.fixture()
def storage() -> UnifiedStorage:
    """UnifiedStorage avec base SQLite temporaire, tables migrées."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_logs.db")
        s = UnifiedStorage(db_path)
        s.migrate()
        yield s
        s.close()


def _make_log(
    *,
    message: str = "Test log",
    level: str = "INFO",
    logger_name: str = "test.logger",
    **kwargs,
) -> WorkflowLog:
    """Helper pour créer un WorkflowLog avec des valeurs par défaut."""
    return WorkflowLog(
        id=str(uuid4()),
        message=message,
        level=level,
        logger_name=logger_name,
        **kwargs,
    )


# ══════════════════════════════════════════════════════════════════════════════
# WorkflowLog CRUD via Repository
# ══════════════════════════════════════════════════════════════════════════════


class TestWorkflowLogCRUD:
    """Tests CRUD de base pour WorkflowLog via Repository."""

    def test_create_and_get(self, log_repo: Repository[WorkflowLog]):
        """Créer un log et le relire par PK."""
        log = _make_log(message="Hello world", level="INFO")
        log_repo.create(log)

        found = log_repo.get(log.id)
        assert found is not None
        assert found.message == "Hello world"
        assert found.level == "INFO"
        assert found.logger_name == "test.logger"

    def test_create_with_correlation(self, log_repo: Repository[WorkflowLog]):
        """Créer un log avec tous les champs de corrélation."""
        log = _make_log(
            message="Correlated log",
            correlation_id="corr-001",
            job_run_id="job-123",
            step_run_id="step-456",
            execution_id="exec-789",
            pipeline_run_id="pipe-abc",
            agent_id="agent-def",
        )
        log_repo.create(log)

        found = log_repo.get(log.id)
        assert found is not None
        assert found.correlation_id == "corr-001"
        assert found.job_run_id == "job-123"
        assert found.step_run_id == "step-456"
        assert found.execution_id == "exec-789"
        assert found.pipeline_run_id == "pipe-abc"
        assert found.agent_id == "agent-def"

    def test_create_with_extra(self, log_repo: Repository[WorkflowLog]):
        """Créer un log avec des extras JSON."""
        log = _make_log(
            message="Extra log",
            extra={"custom_field": "value", "count": 42},
        )
        log_repo.create(log)

        found = log_repo.get(log.id)
        assert found is not None
        assert found.extra["custom_field"] == "value"
        assert found.extra["count"] == 42

    def test_create_with_exception(self, log_repo: Repository[WorkflowLog]):
        """Créer un log avec un traceback d'exception."""
        log = _make_log(
            message="Error occurred",
            level="ERROR",
            exception="Traceback (most recent call last):\n  File ...\nValueError: oops",
        )
        log_repo.create(log)

        found = log_repo.get(log.id)
        assert found is not None
        assert found.exception is not None
        assert "ValueError" in found.exception

    def test_create_with_technical_fields(self, log_repo: Repository[WorkflowLog]):
        """Créer un log avec module, func_name, line_no."""
        log = _make_log(
            module="my_module",
            func_name="my_function",
            line_no=42,
        )
        log_repo.create(log)

        found = log_repo.get(log.id)
        assert found is not None
        assert found.module == "my_module"
        assert found.func_name == "my_function"
        assert found.line_no == 42

    def test_filter_by_level(self, log_repo: Repository[WorkflowLog]):
        """Filtrer les logs par niveau."""
        log_repo.create(_make_log(level="INFO", message="info 1"))
        log_repo.create(_make_log(level="ERROR", message="error 1"))
        log_repo.create(_make_log(level="INFO", message="info 2"))
        log_repo.create(_make_log(level="WARNING", message="warn 1"))

        errors = log_repo.filter(level="ERROR")
        assert len(errors) == 1
        assert errors[0].message == "error 1"

        infos = log_repo.filter(level="INFO")
        assert len(infos) == 2

    def test_filter_by_correlation_id(self, log_repo: Repository[WorkflowLog]):
        """Filtrer les logs par correlation_id."""
        log_repo.create(_make_log(correlation_id="corr-A", message="a1"))
        log_repo.create(_make_log(correlation_id="corr-A", message="a2"))
        log_repo.create(_make_log(correlation_id="corr-B", message="b1"))

        results = log_repo.filter(correlation_id="corr-A")
        assert len(results) == 2
        assert all(r.correlation_id == "corr-A" for r in results)

    def test_filter_by_job_run_id(self, log_repo: Repository[WorkflowLog]):
        """Filtrer les logs par job_run_id."""
        log_repo.create(_make_log(job_run_id="job-1", message="j1"))
        log_repo.create(_make_log(job_run_id="job-2", message="j2"))

        results = log_repo.filter(job_run_id="job-1")
        assert len(results) == 1
        assert results[0].job_run_id == "job-1"

    def test_count(self, log_repo: Repository[WorkflowLog]):
        """Compter les logs."""
        log_repo.create(_make_log(level="INFO"))
        log_repo.create(_make_log(level="ERROR"))
        log_repo.create(_make_log(level="INFO"))

        assert log_repo.count() == 3
        assert log_repo.count(level="INFO") == 2
        assert log_repo.count(level="ERROR") == 1

    def test_delete(self, log_repo: Repository[WorkflowLog]):
        """Supprimer un log par PK."""
        log = _make_log()
        log_repo.create(log)
        assert log_repo.exists(log.id)

        log_repo.delete(log.id)
        assert not log_repo.exists(log.id)

    def test_all_ordered_by_timestamp(self, log_repo: Repository[WorkflowLog]):
        """Récupérer tous les logs triés par timestamp DESC."""
        now = datetime.now(UTC)
        log_repo.create(_make_log(message="old", timestamp=now - timedelta(hours=2)))
        log_repo.create(_make_log(message="new", timestamp=now))
        log_repo.create(_make_log(message="mid", timestamp=now - timedelta(hours=1)))

        results = log_repo.filter(order_by="-timestamp")
        assert len(results) == 3
        assert results[0].message == "new"
        assert results[1].message == "mid"
        assert results[2].message == "old"


# ══════════════════════════════════════════════════════════════════════════════
# RepositoryLogHandler
# ══════════════════════════════════════════════════════════════════════════════


class TestRepositoryLogHandler:
    """Tests pour le RepositoryLogHandler (ADR-018 D4)."""

    def test_emit_single_log(self, log_repo: Repository[WorkflowLog]):
        """emit() persiste immédiatement avec batch_size=1."""
        handler = RepositoryLogHandler(log_repo, batch_size=1)
        logger = logging.getLogger("test.emit_single")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info("Single log message")

            logs = log_repo.all()
            assert len(logs) == 1
            assert logs[0].message == "Single log message"
            assert logs[0].level == "INFO"
            assert logs[0].logger_name == "test.emit_single"
        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_emit_with_extra(self, log_repo: Repository[WorkflowLog]):
        """emit() extrait les extras du LogRecord."""
        handler = RepositoryLogHandler(log_repo, batch_size=1)
        logger = logging.getLogger("test.emit_extra")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info("With extras", extra={"custom_key": "custom_value"})

            logs = log_repo.all()
            assert len(logs) == 1
            assert "custom_key" in logs[0].extra
            assert logs[0].extra["custom_key"] == "custom_value"
        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_emit_extracts_correlation_fields(self, log_repo: Repository[WorkflowLog]):
        """emit() extrait les champs de corrélation dans les champs dédiés."""
        handler = RepositoryLogHandler(log_repo, batch_size=1)
        logger = logging.getLogger("test.emit_corr")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info(
                "Correlated",
                extra={
                    "job_run_id": "job-X",
                    "step_run_id": "step-Y",
                    "correlation_id": "corr-Z",
                    "custom_data": "hello",
                },
            )

            logs = log_repo.all()
            assert len(logs) == 1
            log = logs[0]
            # Corrélation dans les champs dédiés
            assert log.job_run_id == "job-X"
            assert log.step_run_id == "step-Y"
            assert log.correlation_id == "corr-Z"
            # Les extras non-corrélation restent dans extra
            assert "custom_data" in log.extra
            # Les corrélation ne sont PAS dupliqués dans extra
            assert "job_run_id" not in log.extra
            assert "step_run_id" not in log.extra
            assert "correlation_id" not in log.extra
        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_emit_with_exception(self, log_repo: Repository[WorkflowLog]):
        """emit() capture l'exception info."""
        handler = RepositoryLogHandler(log_repo, batch_size=1)
        logger = logging.getLogger("test.emit_exc")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            try:
                raise ValueError("test error")
            except ValueError:
                logger.exception("Something failed")

            logs = log_repo.all()
            assert len(logs) == 1
            assert logs[0].level == "ERROR"
            assert logs[0].exception is not None
            assert "test error" in logs[0].exception
        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_emit_captures_technical_fields(self, log_repo: Repository[WorkflowLog]):
        """emit() capture module, func_name, line_no."""
        handler = RepositoryLogHandler(log_repo, batch_size=1)
        logger = logging.getLogger("test.emit_tech")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info("Technical fields check")

            logs = log_repo.all()
            assert len(logs) == 1
            log = logs[0]
            assert log.module is not None
            assert log.func_name is not None
            assert log.line_no is not None
            assert log.line_no > 0
        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_batch_flush(self, log_repo: Repository[WorkflowLog]):
        """Avec batch_size > 1, les logs sont bufferisés puis flushés."""
        handler = RepositoryLogHandler(log_repo, batch_size=3)
        logger = logging.getLogger("test.batch")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            # 2 logs → pas encore flushé (batch_size=3)
            logger.info("Batch 1")
            logger.info("Batch 2")
            assert log_repo.count() == 0

            # 3e log → le buffer atteint batch_size → flush
            logger.info("Batch 3")
            assert log_repo.count() == 3

            # 1 log supplémentaire → bufferisé
            logger.info("Batch 4")
            assert log_repo.count() == 3

            # Flush explicite
            handler.flush()
            assert log_repo.count() == 4
        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_close_flushes_remaining(self, log_repo: Repository[WorkflowLog]):
        """close() flush le buffer restant."""
        handler = RepositoryLogHandler(log_repo, batch_size=10)
        logger = logging.getLogger("test.close_flush")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info("Before close 1")
            logger.info("Before close 2")
            assert log_repo.count() == 0

            handler.close()
            assert log_repo.count() == 2
        finally:
            logger.removeHandler(handler)

    def test_multiple_levels(self, log_repo: Repository[WorkflowLog]):
        """emit() gère tous les niveaux de log."""
        handler = RepositoryLogHandler(log_repo, batch_size=1)
        logger = logging.getLogger("test.levels")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            logger.debug("debug msg")
            logger.info("info msg")
            logger.warning("warning msg")
            logger.error("error msg")
            logger.critical("critical msg")

            logs = log_repo.all()
            assert len(logs) == 5
            levels = {log.level for log in logs}
            assert levels == {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        finally:
            logger.removeHandler(handler)
            handler.close()


# ══════════════════════════════════════════════════════════════════════════════
# WorkflowLogQuery
# ══════════════════════════════════════════════════════════════════════════════


class TestWorkflowLogQuery:
    """Tests pour WorkflowLogQuery (read-model DTO)."""

    def test_default_query(self):
        """Requête par défaut : limit=100, order_by=-timestamp."""
        query = WorkflowLogQuery()
        kwargs = query.to_filter_kwargs()
        assert kwargs["limit"] == 100
        assert kwargs["offset"] == 0
        assert kwargs["order_by"] == "-timestamp"

    def test_level_filter(self):
        """Filtre par level normalise en uppercase."""
        query = WorkflowLogQuery(level="error")
        kwargs = query.to_filter_kwargs()
        assert kwargs["level"] == "ERROR"

    def test_logger_name_like(self):
        """Filtre logger_name utilise LIKE."""
        query = WorkflowLogQuery(logger_name="engine")
        kwargs = query.to_filter_kwargs()
        assert kwargs["logger_name__like"] == "%engine%"

    def test_correlation_filters(self):
        """Tous les champs de corrélation sont transmis."""
        query = WorkflowLogQuery(
            correlation_id="corr-1",
            job_run_id="job-1",
            step_run_id="step-1",
            execution_id="exec-1",
            pipeline_run_id="pipe-1",
            agent_id="agent-1",
        )
        kwargs = query.to_filter_kwargs()
        assert kwargs["correlation_id"] == "corr-1"
        assert kwargs["job_run_id"] == "job-1"
        assert kwargs["step_run_id"] == "step-1"
        assert kwargs["execution_id"] == "exec-1"
        assert kwargs["pipeline_run_id"] == "pipe-1"
        assert kwargs["agent_id"] == "agent-1"

    def test_since_until_filters(self):
        """Filtre temporal since/until convertit en ISO."""
        since = datetime(2026, 4, 12, tzinfo=UTC)
        until = datetime(2026, 4, 13, tzinfo=UTC)
        query = WorkflowLogQuery(since=since, until=until)
        kwargs = query.to_filter_kwargs()
        assert kwargs["timestamp__gte"] == since.isoformat()
        assert kwargs["timestamp__lte"] == until.isoformat()

    def test_message_like(self):
        """Filtre message_like utilise LIKE."""
        query = WorkflowLogQuery(message_like="error")
        kwargs = query.to_filter_kwargs()
        assert kwargs["message__like"] == "%error%"

    def test_pagination(self):
        """Filtre pagination (limit, offset)."""
        query = WorkflowLogQuery(limit=25, offset=50)
        kwargs = query.to_filter_kwargs()
        assert kwargs["limit"] == 25
        assert kwargs["offset"] == 50

    def test_query_with_repository(self, log_repo: Repository[WorkflowLog]):
        """WorkflowLogQuery s'intègre avec Repository.filter()."""
        log_repo.create(_make_log(level="INFO", message="info log"))
        log_repo.create(_make_log(level="ERROR", message="error log"))
        log_repo.create(_make_log(level="ERROR", message="another error"))

        query = WorkflowLogQuery(level="ERROR")
        results = log_repo.filter(**query.to_filter_kwargs())
        assert len(results) == 2
        assert all(r.level == "ERROR" for r in results)

    def test_query_correlation_with_repository(self, log_repo: Repository[WorkflowLog]):
        """WorkflowLogQuery filtre par corrélation via Repository."""
        log_repo.create(_make_log(job_run_id="job-A", message="a1"))
        log_repo.create(_make_log(job_run_id="job-A", message="a2"))
        log_repo.create(_make_log(job_run_id="job-B", message="b1"))

        query = WorkflowLogQuery(job_run_id="job-A")
        results = log_repo.filter(**query.to_filter_kwargs())
        assert len(results) == 2


# ══════════════════════════════════════════════════════════════════════════════
# UnifiedStorage.logs integration
# ══════════════════════════════════════════════════════════════════════════════


class TestUnifiedStorageLogs:
    """Tests d'intégration pour UnifiedStorage.logs (ADR-018 D4)."""

    def test_logs_property_returns_repository(self, storage: UnifiedStorage):
        """storage.logs retourne un Repository[WorkflowLog]."""
        repo = storage.logs
        assert isinstance(repo, Repository)

    def test_log_entries_table_created(self, storage: UnifiedStorage):
        """migrate() crée la table log_entries."""
        tables = storage.get_table_names()
        assert "log_entries" in tables

    def test_crud_via_storage_logs(self, storage: UnifiedStorage):
        """CRUD complet via storage.logs."""
        log = _make_log(message="Via unified storage")
        storage.logs.create(log)

        found = storage.logs.get(log.id)
        assert found is not None
        assert found.message == "Via unified storage"

        assert storage.logs.count() == 1
        storage.logs.delete(log.id)
        assert storage.logs.count() == 0

    def test_handler_with_storage_logs(self, storage: UnifiedStorage):
        """RepositoryLogHandler fonctionne avec storage.logs."""
        handler = RepositoryLogHandler(storage.logs, batch_size=1)
        logger = logging.getLogger("test.storage_integration")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            logger.info("Integration test", extra={"job_run_id": "job-int-1"})

            logs = storage.logs.all()
            assert len(logs) == 1
            assert logs[0].message == "Integration test"
            assert logs[0].job_run_id == "job-int-1"
        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_health_check_includes_log_entries(self, storage: UnifiedStorage):
        """health_check() inclut la table log_entries."""
        health = storage.health_check()
        assert "log_entries" in health["tables"]
        assert "log_entries" in health["row_counts"]
