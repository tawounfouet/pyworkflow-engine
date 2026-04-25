# Auto-registration of email connectors.
# Each import triggers the @connector decorator which registers the class.

from pyconnectors.connectors.email import (
    smtp,
    imap,
    pop3,
)  # stdlib only — always available

try:
    from pyconnectors.connectors.email import gmail
except ImportError:
    pass

try:
    from pyconnectors.connectors.email import outlook
except ImportError:
    pass

try:
    from pyconnectors.connectors.email import yahoo
except ImportError:
    pass

try:
    from pyconnectors.connectors.email import resend
except ImportError:
    pass

try:
    from pyconnectors.connectors.email import brevo
except ImportError:
    pass

try:
    from pyconnectors.connectors.email import mailchimp
except ImportError:
    pass

try:
    from pyconnectors.connectors.email import mailersend
except ImportError:
    pass

try:
    from pyconnectors.connectors.email import mailgun
except ImportError:
    pass

try:
    from pyconnectors.connectors.email import ses
except ImportError:
    pass
