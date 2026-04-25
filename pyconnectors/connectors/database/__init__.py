# Auto-registration of database connectors.
from pyconnectors.connectors.database import sqlite  # stdlib only

try:
    from pyconnectors.connectors.database import postgresql
except ImportError:
    pass

try:
    from pyconnectors.connectors.database import mysql
except ImportError:
    pass

try:
    from pyconnectors.connectors.database import mongodb
except ImportError:
    pass

try:
    from pyconnectors.connectors.database import redis
except ImportError:
    pass
