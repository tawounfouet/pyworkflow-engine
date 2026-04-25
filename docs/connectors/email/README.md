# Email Connectors

Send and read emails via protocols, webmail wrappers, or transactional APIs. All connectors use `safe_execute()` — never raises, always returns `ConnectorResult`.

## Protocols

| Connector | Key | Description |
|---|---|---|
| [SMTP](smtp.md) | `email.smtp` | Send via any SMTP server |
| [IMAP](imap.md) | `email.imap` | Search and read emails |
| [POP3](pop3.md) | `email.pop3` | Fetch inbox stats |

## Webmail wrappers

| Connector | Key | Server |
|---|---|---|
| [Gmail](gmail.md) | `email.gmail` | `smtp.gmail.com:587` |
| [Outlook](outlook.md) | `email.outlook` | `smtp-mail.outlook.com:587` |
| [Yahoo](yahoo.md) | `email.yahoo` | `smtp.mail.yahoo.com:465` |

> For Gmail / Outlook / Yahoo with 2FA, generate an **App Password** from your account security settings.

## Transactional APIs

| Connector | Key | Dependencies |
|---|---|---|
| [Resend](resend.md) | `email.resend` | `uv pip install "pyconnectors[email]"` |
| [Brevo](brevo.md) | `email.brevo` | stdlib |
| [Mailchimp Transactional](mailchimp.md) | `email.mailchimp` | stdlib |
| [MailerSend](mailersend.md) | `email.mailersend` | stdlib |
| [Mailgun](mailgun.md) | `email.mailgun` | stdlib |
| [Amazon SES](ses.md) | `email.ses` | `uv pip install "pyconnectors[s3]"` (`boto3`) |
