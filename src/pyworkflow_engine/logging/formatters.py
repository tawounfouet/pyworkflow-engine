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
import os
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

# ── Couleurs ANSI par niveau de log ──────────────────────────────────────────
# Inspiré des conventions Loguru / database_logger.py
_LEVEL_COLORS: dict[str, str] = {
    "DEBUG": "\033[94m",     # Bleu ciel
    "INFO": "\033[36m",      # Cyan
    "WARNING": "\033[33m",   # Jaune
    "ERROR": "\033[31m",     # Rouge
    "CRITICAL": "\033[91m",  # Rouge vif
}
_RESET = "\033[0m"
_DIM = "\033[90m"  # Gris pour le timestamp


def _supports_color(stream: Any = None) -> bool:
    """Détecte si le terminal supporte les couleurs ANSI."""
    if stream is None:
        stream = sys.stderr
    if not hasattr(stream, "isatty"):
        return False
    if not stream.isatty():
        return False
    # Windows: les couleurs ANSI sont supportées depuis Windows 10 1607+
    # via VirtualTerminalLevel ou les terminaux modernes (Windows Terminal, VS Code)
    if sys.platform == "win32":
        return os.environ.get("TERM_PROGRAM") == "vscode" or os.environ.get(
            "WT_SESSION"
        ) is not None or os.environ.get("ANSICON") is not None or True
    return True


class StructuredFormatter(logging.Formatter):
    """Format console lisible avec contexte structuré et couleurs ANSI.

    Produit des lignes comme :
        2026-03-11 20:42:17 | INFO | engine.facade | Workflow started
          job_id=abc-123

    Les couleurs sont activées automatiquement quand le terminal les supporte,
    ou peuvent être forcées via le paramètre ``colorize``.

    Args:
        extra_fields: Champs additionnels inclus dans chaque log entry.
        colorize: Force les couleurs on/off. None = auto-détection.
    """

    def __init__(
        self,
        extra_fields: dict[str, Any] | None = None,
        colorize: bool | None = None,
    ) -> None:
        super().__init__()
        self._extra_fields = extra_fields or {}
        self._colorize = colorize if colorize is not None else _supports_color()

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(
            record.created, tz=UTC
        ).strftime("%Y-%m-%d %H:%M:%S")

        # Nom court : enlever le prefix "pyworkflow_engine."
        name = record.name.removeprefix("pyworkflow_engine.")

        level = record.levelname

        # Couleur selon le niveau
        if self._colorize:
            color = _LEVEL_COLORS.get(record.levelname, "")
            line = (
                f"{_DIM}{timestamp}{_RESET} | "
                f"{color}{level}{_RESET} | "
                f"{name} | {color}{record.getMessage()}{_RESET}"
            )
        else:
            line = f"{timestamp} | {level} | {name} | {record.getMessage()}"

        parts = [line]

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
                record.created, tz=UTC
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
