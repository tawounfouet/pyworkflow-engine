"""
config/loaders.py — functions to build ConnectorConfig from various sources.

These are the canonical constructors; ConnectorConfig.from_* are shim aliases
that delegate here for backward compatibility.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Type

from pyconnectors.models.enums import AuthMethod, ConnectorStatus
from pyconnectors.models.exceptions import ConnectorConfigurationError


def from_dict(
    data: Dict[str, Any],
    config_cls: Optional[type] = None,
) -> Any:
    """Load a ConnectorConfig (or subclass) from a plain dictionary."""
    if config_cls is None:
        from pyconnectors.config.base import ConnectorConfig
        config_cls = ConnectorConfig

    known_fields = {
        f.name
        for f in config_cls.__dataclass_fields__.values()
        if f.name != "params"
    }
    params: Dict[str, Any] = {}
    init_kwargs: Dict[str, Any] = {}

    for k, v in data.items():
        if k in known_fields:
            if k == "auth_method" and isinstance(v, str):
                v = AuthMethod(v)
            elif k == "status" and isinstance(v, str):
                v = ConnectorStatus(v)
            init_kwargs[k] = v
        else:
            params[k] = v

    if "params" in init_kwargs:
        existing = init_kwargs["params"]
        if isinstance(existing, dict):
            existing.update(params)
    elif params:
        init_kwargs["params"] = params

    return config_cls(**init_kwargs)


def from_json_file(filepath: str | Path, config_cls: Optional[type] = None) -> Any:
    """Load a ConnectorConfig from a JSON file."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise ConnectorConfigurationError(f"Configuration file not found: {filepath}")
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
        return from_dict(data, config_cls=config_cls)
    except json.JSONDecodeError as e:
        raise ConnectorConfigurationError(f"Invalid JSON configuration file: {e}")


def from_yaml_file(filepath: str | Path, config_cls: Optional[type] = None) -> Any:
    """Load a ConnectorConfig from a YAML file (requires PyYAML)."""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to load YAML config files. "
            "Install it with: pip install pyyaml"
        ) from exc

    filepath = Path(filepath)
    if not filepath.exists():
        raise ConnectorConfigurationError(f"Configuration file not found: {filepath}")
    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)
        return from_dict(data or {}, config_cls=config_cls)
    except yaml.YAMLError as e:
        raise ConnectorConfigurationError(f"Invalid YAML configuration file: {e}")


def from_env(prefix: str, config_cls: Optional[type] = None) -> Any:
    """
    Load a ConnectorConfig from environment variables with a given prefix.

    JSON-encoded values are supported for ``params``, ``secrets``, and ``tags``.
    """
    data: Dict[str, Any] = {}
    p = prefix.upper()

    for key, value in os.environ.items():
        if key.startswith(p):
            k = key[len(p):].lower()
            if k in ("params", "secrets", "tags"):
                try:
                    data[k] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    data[k] = value
            else:
                data[k] = value

    return from_dict(data, config_cls=config_cls)
