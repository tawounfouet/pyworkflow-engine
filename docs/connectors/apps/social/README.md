# Social Connectors

Interact with major social network APIs. All connectors use stdlib `urllib` — no external HTTP clients required. All use `safe_execute()` — never raises, always returns `ConnectorResult`.

| Connector | Key | Auth | Dependencies |
|---|---|---|---|
| [Facebook](facebook.md) | `social.facebook` | `access_token` | stdlib |
| [Instagram](instagram.md) | `social.instagram` | `access_token` | stdlib |
| [LinkedIn](linkedin.md) | `social.linkedin` | `access_token` | stdlib |
| [Slack](slack.md) | `social.slack` | `webhook_url` | stdlib |
| [TikTok](tiktok.md) | `social.tiktok` | `access_token` | stdlib |
| [Twitter / X](twitter.md) | `social.twitter` | `bearer_token` | stdlib |
| [WhatsApp](whatsapp.md) | `social.whatsapp` | `access_token` + `phone_number_id` | stdlib |
