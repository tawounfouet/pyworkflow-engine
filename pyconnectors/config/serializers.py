"""
config/serializers.py — functions to serialize ConnectorConfig instances.

Secrets are excluded by default; pass ``include_secrets=True`` to override.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict


def to_dict(config: Any, include_secrets: bool = False) -> Dict[str, Any]:
    """Serialize a ConnectorConfig to a plain dictionary."""
    data = asdict(config)
    if not include_secrets:
        data.pop("secrets", None)
    for k, v in data.items():
        if isinstance(v, Enum):
            data[k] = v.value
        elif isinstance(v, datetime):
            data[k] = v.isoformat()
    return data


def to_json(
    config: Any,
    path: str | Path,
    include_secrets: bool = False,
    indent: int = 2,
) -> None:
    """Save a ConnectorConfig to a JSON file."""
    data = to_dict(config, include_secrets=include_secrets)
    with open(path, "w") as f:
        json.dump(data, f, indent=indent, default=str)


def to_json_string(config: Any, include_secrets: bool = False) -> str:
    """Serialize a ConnectorConfig to a JSON string."""
    data = to_dict(config, include_secrets=include_secrets)
    return json.dumps(data, indent=2, default=str)
