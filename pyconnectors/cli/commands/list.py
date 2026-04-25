import typer
from rich.console import Console
from rich.table import Table

from pyconnectors.adapters.registry.memory import _default_registry

app = typer.Typer()
console = Console()

# We need to import the connectors so they are registered
# In a real app we might load them dynamically or have an entry point based plugin system
# For now, let's just make sure the subpackages are imported
import pyconnectors.connectors.auth.jwt_auth  # noqa
import pyconnectors.connectors.auth.oauth2  # noqa
import pyconnectors.connectors.auth.oidc  # noqa
import pyconnectors.connectors.auth.saml  # noqa
import pyconnectors.connectors.database.mongodb  # noqa
import pyconnectors.connectors.database.mysql  # noqa
import pyconnectors.connectors.database.postgresql  # noqa
import pyconnectors.connectors.database.redis  # noqa
import pyconnectors.connectors.database.sqlite  # noqa
import pyconnectors.connectors.email.brevo  # noqa
import pyconnectors.connectors.email.gmail  # noqa
import pyconnectors.connectors.email.imap  # noqa
import pyconnectors.connectors.email.mailchimp  # noqa
import pyconnectors.connectors.email.mailersend  # noqa
import pyconnectors.connectors.email.mailgun  # noqa
import pyconnectors.connectors.email.outlook  # noqa
import pyconnectors.connectors.email.pop3  # noqa
import pyconnectors.connectors.email.resend  # noqa
import pyconnectors.connectors.email.ses  # noqa
import pyconnectors.connectors.email.smtp  # noqa
import pyconnectors.connectors.email.yahoo  # noqa
import pyconnectors.connectors.http.oauth2  # noqa
import pyconnectors.connectors.http.rest  # noqa
import pyconnectors.connectors.apps.fitness.strava  # noqa
import pyconnectors.connectors.apps.payment.paypal  # noqa
import pyconnectors.connectors.apps.payment.stripe_api  # noqa
import pyconnectors.connectors.apps.social.facebook  # noqa
import pyconnectors.connectors.apps.social.instagram  # noqa
import pyconnectors.connectors.apps.social.linkedin  # noqa
import pyconnectors.connectors.apps.social.slack  # noqa
import pyconnectors.connectors.apps.social.tiktok  # noqa
import pyconnectors.connectors.apps.social.twitter  # noqa
import pyconnectors.connectors.apps.social.whatsapp  # noqa
import pyconnectors.connectors.storage.azure.adls  # noqa
import pyconnectors.connectors.storage.azure.azure_blob  # noqa
import pyconnectors.connectors.storage.media.cloudinary  # noqa
import pyconnectors.connectors.storage.s3.digitalocean  # noqa
import pyconnectors.connectors.storage.gcp.gcs  # noqa
import pyconnectors.connectors.storage.s3.hetzner  # noqa
import pyconnectors.connectors.storage.s3.minio  # noqa
import pyconnectors.connectors.storage.s3.ovh  # noqa
import pyconnectors.connectors.storage.s3.s3  # noqa


@app.callback(invoke_without_command=True)
def main() -> None:
    """List all available connectors."""
    connectors = _default_registry.list_connectors()

    if not connectors:
        console.print("[yellow]No connectors found.[/yellow]")
        return

    table = Table(title="Available Connectors")
    table.add_column("Name", style="cyan")
    table.add_column("Class", style="magenta")
    table.add_column("Description", style="white")

    for name, cls in sorted(connectors.items()):
        doc = (cls.__doc__ or "").strip().splitlines()[0].strip() if cls.__doc__ else ""
        table.add_row(name, cls.__name__, doc)

    console.print(table)
