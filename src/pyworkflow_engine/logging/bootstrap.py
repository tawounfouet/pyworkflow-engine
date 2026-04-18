"""
Log bootstrapping helper.
"""
from __future__ import annotations

import logging as _stdlib_logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.config import WorkflowConfig

from pyworkflow_engine.logging.config import LoggingConfig as _LC
from pyworkflow_engine.logging.logger import configure_logging, get_logger


def configure_from_workflow_config(config: WorkflowConfig) -> None:
    """Configure le logging à partir d'un WorkflowConfig.
    
    Doit être appelé de manière explicite.
    """
    log_cfg = config.logging
    needs_setup = (
        log_cfg.level != "INFO"
        or log_cfg.format != "text"
        or log_cfg.log_dir is not None
        or log_cfg.log_to_db
    )
    
    if not needs_setup:
        return
        
    log_file: str | None = None
    if log_cfg.log_dir:
        log_dir = Path(log_cfg.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = str(log_dir / "pyworkflow.log")

    configure_logging(
        _LC(
            level=log_cfg.level,
            json_output=(log_cfg.format == "json"),
            log_file=log_file,
            log_file_max_bytes=log_cfg.log_file_max_mb * 1024 * 1024,
            log_file_backup_count=log_cfg.log_file_backup_count,
        )
    )

    if log_cfg.log_to_db and config.storage.db_path:
        from pyworkflow_engine.logging.handlers import SQLiteLogHandler  # noqa: PLC0415
        
        db_handler = SQLiteLogHandler(db_path=config.storage.db_path, batch_size=1)
        db_handler.setLevel(getattr(_stdlib_logging, log_cfg.level))
        _stdlib_logging.getLogger("pyworkflow_engine").addHandler(db_handler)
        get_logger().debug(
            "SQLiteLogHandler configuré depuis WorkflowConfig",
            extra={"db": config.storage.db_path, "table": "workflow_logs"},
        )
