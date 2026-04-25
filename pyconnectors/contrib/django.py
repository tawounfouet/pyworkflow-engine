"""Django integration for PyConnectors."""

from typing import Any

from pyconnectors.config.base import ConnectorConfig
from pyconnectors.services.factory import ConnectorFactory

try:
    from django.conf import settings
except ImportError:
    settings = None


def get_connector(name: str) -> Any:
    """
    Get a pre-configured connector based on Django settings.
    Requires `PYCONNECTORS` dict in Django settings.
    """
    if settings is None:
        raise ImportError("Django is not installed.")

    config_dict = getattr(settings, "PYCONNECTORS", {}).get(name, {})
    config = ConnectorConfig.from_dict(config_dict)

    return ConnectorFactory.create(name, config=config)
