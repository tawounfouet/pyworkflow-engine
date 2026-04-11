"""
Tests pour le module config.
"""

from __future__ import annotations

import pytest

from pyworkflow_engine.config import (
    EngineConfig,
    ExecutorConfig,
    LoggingConfig,
    WorkflowConfig,
)
from pyworkflow_engine.facade import WorkflowEngine


class TestConfigClasses:
    def test_engine_config_defaults(self):
        cfg = EngineConfig()
        assert cfg.max_retries == 0
        assert cfg.retry_delay_seconds == 1.0
        assert cfg.default_timeout_seconds is None
        assert cfg.parallel is False
        assert cfg.max_workers is None
        assert cfg.pool_size_valid is None

    def test_engine_config_validation(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            EngineConfig(max_retries=-1)
        with pytest.raises(ValueError, match="must be >= 0"):
            EngineConfig(retry_delay_seconds=-0.5)
        with pytest.raises(ValueError, match="must be >= 1"):
            EngineConfig(max_workers=0)

    def test_executor_config_defaults(self):
        cfg = ExecutorConfig()
        assert cfg.strategy == "local"
        assert cfg.pool_size == 4
        assert cfg.max_workers is None
        assert cfg.effective_workers == 4

    def test_executor_config_validation(self):
        with pytest.raises(ValueError, match="must be one of"):
            ExecutorConfig(strategy="invalid_strategy")
        with pytest.raises(ValueError, match="must be >= 1"):
            ExecutorConfig(pool_size=0)
        with pytest.raises(ValueError, match="must be >= 1"):
            ExecutorConfig(max_workers=0)

    def test_executor_config_effective_workers(self):
        cfg = ExecutorConfig(pool_size=4, max_workers=8)
        assert cfg.effective_workers == 8

    def test_logging_config_validation(self):
        with pytest.raises(ValueError, match="must be one of"):
            LoggingConfig(level="INVALID")
        with pytest.raises(ValueError, match="must be one of"):
            LoggingConfig(format="xml")


class TestWorkflowEngineConfigIntegration:
    def test_engine_init_with_direct_params(self):
        """Test la rétrocompatibilité des paramètres directs."""
        engine = WorkflowEngine(parallel=True, max_workers=5)
        assert engine._runner.__class__.__name__ == "ParallelRunner"
        # Le max_workers est bien passé au __init__ de ParallelRunner
        # Pas d'accès direct facile, mais on vérifie le type du runner

    def test_engine_init_with_config(self):
        """Test l'initialisation via WorkflowConfig."""
        cfg = WorkflowConfig(
            engine=EngineConfig(parallel=True, max_workers=3)
        )
        engine = WorkflowEngine(config=cfg)
        assert engine._config is cfg
        assert engine._runner.__class__.__name__ == "ParallelRunner"

    def test_config_overrides_direct_params(self):
        """Test que la config prend le dessus sur les paramètres directs."""
        cfg = WorkflowConfig(
            engine=EngineConfig(parallel=False)
        )
        engine = WorkflowEngine(config=cfg, parallel=True)
        assert engine._runner.__class__.__name__ == "WorkflowRunner"  # Séquentiel car config gagne
