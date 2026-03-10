"""
Tests pour le module logging — config, logger, formatters, handlers.

Tous ces tests utilisent uniquement la stdlib (zero dépendance externe).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from ias_workflow_engine.logging import (
    LoggingConfig,
    configure_logging,
    get_logger,
)
from ias_workflow_engine.logging.formatters import (
    JSONFormatter,
    StructuredFormatter,
)
from ias_workflow_engine.logging.handlers import (
    SQLiteLogHandler,
    create_queue_handler,
)
from ias_workflow_engine.logging.logger import (
    _ROOT_LOGGER_NAME,
    _cleanup,
    shutdown_logging,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_logging():
    """Nettoie le logging avant et après chaque test."""
    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def tmp_log_file(tmp_path: Path) -> Path:
    """Crée un chemin temporaire pour fichier de log."""
    return tmp_path / "test.log"


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Crée un chemin temporaire pour base SQLite."""
    return tmp_path / "test_logs.db"


# ── Tests LoggingConfig ──────────────────────────────────────────────────────


class TestLoggingConfig:
    """Tests pour la dataclass LoggingConfig."""

    def test_default_values(self):
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.json_output is False
        assert config.log_file is None
        assert config.log_file_max_bytes == 10 * 1024 * 1024
        assert config.log_file_backup_count == 5
        assert config.enable_queue is False
        assert config.extra_fields == {}
        assert config.propagate is False
        assert config.logger_name == "ias_workflow_engine"

    def test_custom_values(self):
        config = LoggingConfig(
            level="DEBUG",
            json_output=True,
            log_file="/tmp/test.log",
            enable_queue=True,
            extra_fields={"service": "test"},
        )
        assert config.level == "DEBUG"
        assert config.json_output is True
        assert config.log_file == "/tmp/test.log"
        assert config.enable_queue is True
        assert config.extra_fields == {"service": "test"}

    def test_frozen_immutability(self):
        config = LoggingConfig()
        with pytest.raises(AttributeError):
            config.level = "DEBUG"  # type: ignore[misc]

    def test_with_overrides(self):
        original = LoggingConfig(level="INFO", json_output=False)
        modified = original.with_overrides(level="DEBUG", json_output=True)
        assert original.level == "INFO"  # original unchanged
        assert modified.level == "DEBUG"
        assert modified.json_output is True

    def test_with_overrides_preserves_other_fields(self):
        original = LoggingConfig(
            level="WARNING",
            log_file="/tmp/app.log",
            extra_fields={"env": "prod"},
        )
        modified = original.with_overrides(level="ERROR")
        assert modified.log_file == "/tmp/app.log"
        assert modified.extra_fields == {"env": "prod"}
        assert modified.level == "ERROR"


# ── Tests get_logger ─────────────────────────────────────────────────────────


class TestGetLogger:
    """Tests pour la fonction get_logger."""

    def test_root_logger(self):
        logger = get_logger()
        assert logger.name == _ROOT_LOGGER_NAME

    def test_named_logger(self):
        logger = get_logger("core.engine")
        assert logger.name == f"{_ROOT_LOGGER_NAME}.core.engine"

    def test_named_logger_executors(self):
        logger = get_logger("executors.thread")
        assert logger.name == f"{_ROOT_LOGGER_NAME}.executors.thread"

    def test_null_handler_by_default(self):
        """La lib doit être silencieuse par défaut (PEP 282)."""
        root = get_logger()
        null_handlers = [h for h in root.handlers if isinstance(h, logging.NullHandler)]
        assert len(null_handlers) >= 1

    def test_logger_hierarchy(self):
        """Les loggers enfants héritent du logger parent."""
        parent = get_logger()
        child = get_logger("core.engine")
        assert child.parent is parent or child.parent.name == parent.name


# ── Tests configure_logging ──────────────────────────────────────────────────


class TestConfigureLogging:
    """Tests pour la fonction configure_logging."""

    def test_default_configuration(self):
        configure_logging()
        root = get_logger()
        assert root.level == logging.INFO
        # Should have NullHandler + StreamHandler
        non_null = [h for h in root.handlers if not isinstance(h, logging.NullHandler)]
        assert len(non_null) == 1
        assert isinstance(non_null[0], logging.StreamHandler)

    def test_debug_level(self):
        configure_logging(LoggingConfig(level="DEBUG"))
        root = get_logger()
        assert root.level == logging.DEBUG

    def test_json_output(self):
        configure_logging(LoggingConfig(json_output=True))
        root = get_logger()
        non_null = [h for h in root.handlers if not isinstance(h, logging.NullHandler)]
        assert isinstance(non_null[0].formatter, JSONFormatter)

    def test_structured_output(self):
        configure_logging(LoggingConfig(json_output=False))
        root = get_logger()
        non_null = [h for h in root.handlers if not isinstance(h, logging.NullHandler)]
        assert isinstance(non_null[0].formatter, StructuredFormatter)

    def test_file_handler(self, tmp_log_file: Path):
        configure_logging(LoggingConfig(log_file=str(tmp_log_file)))
        root = get_logger()
        file_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers) == 1

    def test_file_handler_writes(self, tmp_log_file: Path):
        configure_logging(LoggingConfig(log_file=str(tmp_log_file), level="DEBUG"))
        logger = get_logger("test")
        logger.info("hello file")
        # Force flush
        for h in logging.getLogger(_ROOT_LOGGER_NAME).handlers:
            h.flush()
        content = tmp_log_file.read_text()
        assert "hello file" in content

    def test_queue_handler(self):
        configure_logging(LoggingConfig(enable_queue=True))
        root = get_logger()
        queue_handlers = [
            h for h in root.handlers if isinstance(h, logging.handlers.QueueHandler)
        ]
        assert len(queue_handlers) == 1

    def test_idempotent_reconfiguration(self):
        """Un second appel nettoie avant de reconfigurer."""
        configure_logging(LoggingConfig(level="DEBUG"))
        configure_logging(LoggingConfig(level="WARNING"))
        root = get_logger()
        assert root.level == logging.WARNING
        non_null = [h for h in root.handlers if not isinstance(h, logging.NullHandler)]
        assert len(non_null) == 1  # pas d'accumulation

    def test_propagate_false_by_default(self):
        configure_logging()
        root = get_logger()
        assert root.propagate is False

    def test_propagate_true(self):
        configure_logging(LoggingConfig(propagate=True))
        root = get_logger()
        assert root.propagate is True

    def test_shutdown_logging(self):
        configure_logging()
        shutdown_logging()
        root = get_logger()
        non_null = [h for h in root.handlers if not isinstance(h, logging.NullHandler)]
        assert len(non_null) == 0


# ── Tests StructuredFormatter ────────────────────────────────────────────────


class TestStructuredFormatter:
    """Tests pour le StructuredFormatter."""

    def test_basic_format(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="ias_workflow_engine.core.engine",
            level=logging.INFO,
            pathname="engine.py",
            lineno=42,
            msg="Workflow started",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "[INFO    ]" in output
        assert "core.engine" in output
        assert "Workflow started" in output

    def test_extra_fields(self):
        formatter = StructuredFormatter(extra_fields={"service": "test"})
        record = logging.LogRecord(
            name="ias_workflow_engine.test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Warning msg",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "service=test" in output

    def test_record_extra_fields(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="ias_workflow_engine.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.job_id = "abc-123"  # type: ignore[attr-defined]
        output = formatter.format(record)
        assert "job_id=abc-123" in output

    def test_strips_root_prefix(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="ias_workflow_engine.executors.thread",
            level=logging.DEBUG,
            pathname="thread.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "executors.thread" in output
        assert "ias_workflow_engine.executors" not in output

    def test_exception_formatting(self):
        formatter = StructuredFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="ias_workflow_engine.test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        assert "ValueError" in output
        assert "boom" in output


# ── Tests JSONFormatter ──────────────────────────────────────────────────────


class TestJSONFormatter:
    """Tests pour le JSONFormatter."""

    def test_produces_valid_json(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="ias_workflow_engine.core",
            level=logging.INFO,
            pathname="core.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["message"] == "Test message"
        assert data["logger"] == "ias_workflow_engine.core"
        assert "timestamp" in data

    def test_extra_fields_in_json(self):
        formatter = JSONFormatter(extra_fields={"env": "prod", "version": "1.0"})
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["env"] == "prod"
        assert data["version"] == "1.0"

    def test_record_extras_in_json(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        record.job_id = "xyz-789"  # type: ignore[attr-defined]
        record.step_name = "fetch_data"  # type: ignore[attr-defined]
        output = formatter.format(record)
        data = json.loads(output)
        assert data["job_id"] == "xyz-789"
        assert data["step_name"] == "fetch_data"

    def test_exception_in_json(self):
        formatter = JSONFormatter()
        try:
            raise RuntimeError("critical failure")
        except RuntimeError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert data["exception"]["type"] == "RuntimeError"
        assert data["exception"]["message"] == "critical failure"
        assert isinstance(data["exception"]["traceback"], list)

    def test_timestamp_is_iso_format(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        # Should parse as valid ISO datetime
        datetime.fromisoformat(data["timestamp"])

    def test_safe_serialize_complex_types(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        record.complex_data = {"nested": [1, {"a": object()}]}  # type: ignore[attr-defined]
        output = formatter.format(record)
        # Should not raise, complex objects are str()-ified
        data = json.loads(output)
        assert "complex_data" in data


# ── Tests SQLiteLogHandler ───────────────────────────────────────────────────


class TestSQLiteLogHandler:
    """Tests pour le SQLiteLogHandler."""

    def test_creates_table(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path)
        # Table should exist
        cursor = handler._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workflow_logs'"
        )
        assert cursor.fetchone() is not None
        handler.close()

    def test_custom_table_name(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path, table_name="my_logs")
        cursor = handler._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='my_logs'"
        )
        assert cursor.fetchone() is not None
        handler.close()

    def test_emit_single_record(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path)
        record = logging.LogRecord(
            name="ias_workflow_engine.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test log message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        handler.flush()

        logs = handler.query_logs()
        assert len(logs) == 1
        assert logs[0]["message"] == "Test log message"
        assert logs[0]["level"] == "INFO"
        assert logs[0]["logger"] == "ias_workflow_engine.test"
        handler.close()

    def test_emit_with_extras(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path)
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="with extras",
            args=(),
            exc_info=None,
        )
        record.job_id = "abc-123"  # type: ignore[attr-defined]
        handler.emit(record)
        handler.flush()

        logs = handler.query_logs()
        assert len(logs) == 1
        extras = json.loads(logs[0]["extra"])
        assert extras["job_id"] == "abc-123"
        handler.close()

    def test_batch_mode(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path, batch_size=3)

        for i in range(2):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg=f"message {i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

        # Not flushed yet (batch_size=3, only 2 records)
        logs = handler.query_logs()
        assert len(logs) == 0

        # Third record triggers flush
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="message 2",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        logs = handler.query_logs()
        assert len(logs) == 3
        handler.close()

    def test_explicit_flush(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path, batch_size=100)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="buffered",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        handler.flush()

        logs = handler.query_logs()
        assert len(logs) == 1
        handler.close()

    def test_query_by_level(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path)

        for level, msg in [
            (logging.INFO, "info msg"),
            (logging.WARNING, "warn msg"),
            (logging.ERROR, "error msg"),
        ]:
            record = logging.LogRecord(
                name="test",
                level=level,
                pathname="test.py",
                lineno=1,
                msg=msg,
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        handler.flush()

        errors = handler.query_logs(level="ERROR")
        assert len(errors) == 1
        assert errors[0]["message"] == "error msg"
        handler.close()

    def test_query_by_logger_name(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path)

        for name in ["ias_workflow_engine.core", "ias_workflow_engine.executors"]:
            record = logging.LogRecord(
                name=name,
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg=f"from {name}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        handler.flush()

        core_logs = handler.query_logs(logger_name="core")
        assert len(core_logs) == 1
        assert "core" in core_logs[0]["logger"]
        handler.close()

    def test_query_since(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="recent",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        handler.flush()

        # Query with a past date should return the record
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        logs = handler.query_logs(since=past)
        assert len(logs) == 1

        # Query with a future date should return nothing
        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        logs = handler.query_logs(since=future)
        assert len(logs) == 0
        handler.close()

    def test_query_limit(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path)
        for i in range(10):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg=f"msg {i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        handler.flush()

        logs = handler.query_logs(limit=3)
        assert len(logs) == 3
        handler.close()

    def test_in_memory_db(self):
        handler = SQLiteLogHandler(db_path=":memory:")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="in memory",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        handler.flush()

        logs = handler.query_logs()
        assert len(logs) == 1
        handler.close()

    def test_close_flushes_buffer(self, tmp_db_path: Path):
        handler = SQLiteLogHandler(db_path=tmp_db_path, batch_size=100)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="will be flushed on close",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        # Before close, check with a separate connection
        import sqlite3

        handler.close()

        conn = sqlite3.connect(str(tmp_db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM workflow_logs")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1


# ── Tests create_queue_handler ───────────────────────────────────────────────


class TestCreateQueueHandler:
    """Tests pour le helper create_queue_handler."""

    def test_returns_handler_and_listener(self):
        console = logging.StreamHandler()
        q_handler, q_listener = create_queue_handler(console)
        assert isinstance(q_handler, logging.handlers.QueueHandler)
        assert isinstance(q_listener, logging.handlers.QueueListener)

    def test_queue_handler_works(self):
        """Les logs passent par la queue et arrivent au handler cible."""

        class CollectorHandler(logging.Handler):
            def __init__(self):
                super().__init__()
                self.records: list[logging.LogRecord] = []

            def emit(self, record: logging.LogRecord):
                self.records.append(record)

        collector = CollectorHandler()
        q_handler, q_listener = create_queue_handler(collector)
        q_listener.start()

        try:
            logger = logging.getLogger("test_queue_integration")
            logger.addHandler(q_handler)
            logger.setLevel(logging.DEBUG)
            logger.info("async message")

            # Give the listener thread time to process
            import time

            time.sleep(0.1)

            assert len(collector.records) >= 1
            assert collector.records[0].getMessage() == "async message"
        finally:
            q_listener.stop()
            logger.removeHandler(q_handler)


# ── Tests d'intégration logging ──────────────────────────────────────────────


class TestLoggingIntegration:
    """Tests d'intégration end-to-end du module logging."""

    def test_full_pipeline_console(self, capsys):
        """Configure → log → vérifie la sortie console."""
        configure_logging(LoggingConfig(level="DEBUG", json_output=False))
        logger = get_logger("integration.test")
        logger.info("hello from integration test")
        captured = capsys.readouterr()
        assert "hello from integration test" in captured.err

    def test_full_pipeline_json(self, capsys):
        """Configure JSON → log → vérifie le JSON valide."""
        configure_logging(LoggingConfig(level="DEBUG", json_output=True))
        logger = get_logger("integration.json")
        logger.warning("json test", extra={"step_id": "step-1"})
        captured = capsys.readouterr()
        data = json.loads(captured.err.strip())
        assert data["message"] == "json test"
        assert data["level"] == "WARNING"
        assert data["step_id"] == "step-1"

    def test_full_pipeline_file(self, tmp_log_file: Path):
        """Configure file → log → vérifie le fichier."""
        configure_logging(
            LoggingConfig(
                level="DEBUG",
                log_file=str(tmp_log_file),
                json_output=True,
            )
        )
        logger = get_logger("integration.file")
        logger.error("file test error")
        shutdown_logging()

        content = tmp_log_file.read_text().strip()
        assert content  # non-empty
        data = json.loads(content)
        assert data["message"] == "file test error"
        assert data["level"] == "ERROR"

    def test_full_pipeline_sqlite(self, tmp_db_path: Path):
        """Configure → log → vérifie dans SQLite."""
        configure_logging(LoggingConfig(level="DEBUG"))

        handler = SQLiteLogHandler(db_path=tmp_db_path)
        root = get_logger()
        root.addHandler(handler)

        logger = get_logger("integration.sqlite")
        logger.info("sqlite test", extra={"workflow_id": "wf-001"})

        handler.flush()
        logs = handler.query_logs()
        assert len(logs) >= 1
        assert any("sqlite test" in log["message"] for log in logs)

        handler.close()

    def test_full_pipeline_queue_with_sqlite(self, tmp_db_path: Path):
        """Queue async → SQLite handler."""
        import time

        sqlite_handler = SQLiteLogHandler(db_path=tmp_db_path)
        q_handler, q_listener = create_queue_handler(sqlite_handler)
        q_listener.start()

        try:
            logger = logging.getLogger("test_queue_sqlite")
            logger.addHandler(q_handler)
            logger.setLevel(logging.DEBUG)
            logger.info("async to sqlite")

            time.sleep(0.1)
            sqlite_handler.flush()

            logs = sqlite_handler.query_logs()
            assert len(logs) >= 1
            assert any("async to sqlite" in log["message"] for log in logs)
        finally:
            q_listener.stop()
            sqlite_handler.close()
            logger.removeHandler(q_handler)

    def test_extra_fields_propagate_through_hierarchy(self):
        """Les extra_fields de la config apparaissent dans les sous-loggers."""
        configure_logging(
            LoggingConfig(
                level="DEBUG",
                json_output=True,
                extra_fields={"service": "workflow-engine", "env": "test"},
            )
        )
        logger = get_logger("deep.nested.logger")

        # Capture the handler's formatter output
        root = get_logger()
        non_null = [h for h in root.handlers if not isinstance(h, logging.NullHandler)]
        assert len(non_null) >= 1

        formatter = non_null[0].formatter
        assert isinstance(formatter, JSONFormatter)

        record = logger.makeRecord(
            logger.name, logging.INFO, "test.py", 1, "test msg", (), None
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["service"] == "workflow-engine"
        assert data["env"] == "test"
