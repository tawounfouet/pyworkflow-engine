"""
Adapter Snowflake — pip install pyworkflow-engine[snowflake]

Handler ``logging.Handler`` stdlib pour persister les logs dans Snowflake.
S'intègre nativement dans le pipeline logging du core sans changer l'API.

Usage :
    from pyworkflow_engine.adapters.snowflake import SnowflakeLogHandler

    handler = SnowflakeLogHandler(
        connection_factory=my_snowflake_connection,
        database="MONITORING_DB",
        schema="LOGS_SCHEMA",
        table="WORKFLOW_LOGS",
    )
    logger = logging.getLogger("pyworkflow_engine")
    logger.addHandler(handler)

Note : Inspiré du pattern ``SnowflakeDestination`` de database_logger.py,
       mais re-conçu comme un ``logging.Handler`` stdlib standard.
"""

from .handler import SnowflakeLogHandler

__all__ = ["SnowflakeLogHandler"]
