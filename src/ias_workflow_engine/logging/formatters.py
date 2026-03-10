"""
Formatters — formatage structuré des logs, zero dépendance.

Deux formatters stdlib :
- ``StructuredFormatter`` : format lisible humain pour la console
- ``JSONFormatter`` : format JSON machine-parseable pour fichier / collecteur

Ces formatters enrichissent chaque log avec des champs contextuels
(timestamp ISO, level, logger name, extra fields) sans nécessiter structlog.
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Format console lisible avec contexte structuré.

    Produit des lignes comme :
        2026-03-10T14:30:00Z [INFO] core.engine — Workflow started job_id=abc-123

    Args:
        extra_fields: Champs additionnels inclus dans chaque log entry.
    """

    def __init__(self, extra_fields: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._extra_fields = extra_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()

        # Nom court : enlever le prefix "ias_workflow_engine."
        name = record.name.removeprefix("ias_workflow_engine.")

        parts = [
            f"{timestamp} [{record.levelname:<8}] {name} — {record.getMessage()}",
        ]

        # Ajouter les extra fields (du record + de la config)
        extras = {**self._extra_fields}
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_KEYS and not key.startswith("_"):
                extras[key] = value

        if extras:
            extras_str = " ".join(f"{k}={v}" for k, v in extras.items())
            parts.append(f"  {extras_str}")

        # Exception info
        if record.exc_info and record.exc_info[1] is not None:
            parts.append(self.formatException(record.exc_info))

        return "\n".join(parts)


class JSONFormatter(logging.Formatter):
    """Format JSON structuré pour fichiers et collecteurs de logs.

    Produit des lignes JSON comme :
        {"timestamp": "2026-03-10T14:30:00+00:00", "level": "INFO", ...}

    Chaque ligne est un objet JSON valide (JSON Lines / NDJSON).

    Args:
        extra_fields: Champs additionnels inclus dans chaque log entry.
    """

    def __init__(self, extra_fields: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._extra_fields = extra_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Extra fields (config-level)
        log_entry.update(self._extra_fields)

        # Extra fields (record-level, passés via `extra={}`)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_KEYS and not key.startswith("_"):
                log_entry[key] = _safe_serialize(value)

        # Exception info
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Stack info
        if record.stack_info:
            log_entry["stack_info"] = record.stack_info

        return json.dumps(log_entry, default=str, ensure_ascii=False)


def _safe_serialize(value: Any) -> Any:
    """Sérialise une valeur pour JSON de manière sûre."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_serialize(v) for k, v in value.items()}
    return str(value)


# Clés standard d'un LogRecord — on les exclut des extras
_STANDARD_LOG_RECORD_KEYS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "process",
        "processName",
        "message",
        "taskName",
    }
)
