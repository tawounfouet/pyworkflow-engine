# Auto-registration of auth connectors.
try:
    from pyconnectors.connectors.auth import jwt_auth
except ImportError:
    pass

try:
    from pyconnectors.connectors.auth import oauth2
except ImportError:
    pass

try:
    from pyconnectors.connectors.auth import oidc
except ImportError:
    pass

try:
    from pyconnectors.connectors.auth import saml
except ImportError:
    pass
