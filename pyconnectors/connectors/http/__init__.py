# Auto-registration of http connectors.
from pyconnectors.connectors.http import rest

try:
    from pyconnectors.connectors.http import oauth2
except ImportError:
    pass
