"""Streamlit integration for PyConnectors."""
from __future__ import annotations

from typing import Any, Optional

from pyconnectors.config.base import ConnectorConfig
from pyconnectors.models.result import ConnectorResult
from pyconnectors.services.factory import ConnectorFactory

try:
    import streamlit as st
except ImportError:
    st = None


def get_connector(name: str, config_dict: Optional[dict] = None) -> Any:
    """
    Create a cached connector instance for use in Streamlit apps.

    Wraps ConnectorFactory.create() with st.cache_resource so the connector
    is only instantiated once per session.

    Usage::

        conn = get_connector("db.pg", {"host": "localhost"})
        result = conn.safe_execute(query="SELECT 1")
    """
    if st is None:
        raise ImportError(
            "Streamlit is not installed. Install it with: pip install streamlit"
        )

    config = ConnectorConfig.from_dict(config_dict or {})

    @st.cache_resource
    def _create() -> Any:
        return ConnectorFactory.create(name, config=config)

    return _create()


def run_connector(
    name: str,
    config_dict: Optional[dict] = None,
    **kwargs: Any,
) -> ConnectorResult:
    """
    Execute a connector and display results in Streamlit.

    Shows a spinner while executing and renders errors via st.error().
    """
    if st is None:
        raise ImportError(
            "Streamlit is not installed. Install it with: pip install streamlit"
        )

    config = ConnectorConfig.from_dict(config_dict or {})
    factory = ConnectorFactory()

    with st.spinner(f"Running {name}…"):
        result = factory.execute(name, config, **kwargs)

    if not result.success:
        st.error(f"Connector error: {result.error}")

    return result
