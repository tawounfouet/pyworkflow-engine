# Strava (`fitness.strava`)

Connect to the [Strava v3 API](https://developers.strava.com/docs/reference/) to fetch athlete profiles, activity history, stats, clubs, and routes.

**Requires:** Nothing (uses stdlib `urllib` only)

---

## Authentication

The connector supports two modes, depending on the use case:

### Mode 1 — Static access token (scripts / development)

```python
ConnectorConfig(params={"access_token": "<your_token>"})
```

Obtain a token from [strava.com/settings/api](https://www.strava.com/settings/api).
Tokens expire after ~6 hours — use Mode 2 for production.

### Mode 2 — OAuth2 refresh token (production — recommended)

```python
ConnectorConfig(params={
    "client_id":     "<STRAVA_CLIENT_ID>",
    "client_secret": "<STRAVA_CLIENT_SECRET>",
    "refresh_token": "<STRAVA_REFRESH_TOKEN>",
})
```

The connector automatically fetches a fresh access token on init and renews it on every 401 response. The refresh token is rotated in-memory if Strava returns a new one.

Follow the [Strava OAuth2 flow](https://developers.strava.com/docs/authentication/) to generate the initial refresh token. Use `setup_auth.py` from your project to bootstrap it.

### Configuration reference

| Key | Required | Description |
|---|---|---|
| `access_token` | Mode 1 | Short-lived OAuth2 access token |
| `client_id` | Mode 2 | Strava application Client ID |
| `client_secret` | Mode 2 | Strava application Client Secret |
| `refresh_token` | Mode 2 | OAuth2 refresh token |
| `max_retries` | No | Max retries on 401/429 (default: `3`) |

---

## `execute()` — single request

```python
execute(endpoint: str, data: dict | None = None, method: str = "GET") -> dict
```

Returns `{"status": int, "data": dict | list}` on success, or `{"status": int, "error": ...}` on HTTP errors.

- **GET** — `data` is converted to query-string parameters.
- **POST / PUT** — `data` is serialised as a JSON body.

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"access_token": "your_strava_token"})
strava = ConnectorFactory.create("fitness.strava", config=config)

# Athlete profile
result = strava.safe_execute("athlete")
print(result.data["firstname"], result.data["lastname"])

# Recent activities (query params)
result = strava.safe_execute("athlete/activities", data={"per_page": 5})
for act in result.data:
    print(act["name"], act["sport_type"])

# Create an activity (POST)
result = strava.safe_execute(
    "activities",
    data={
        "name": "Evening Run",
        "type": "Run",
        "sport_type": "Run",
        "start_date_local": "2026-04-13T18:30:00Z",
        "elapsed_time": 3600,
        "distance": 10000,
    },
    method="POST",
)
print(result.data["id"])
```

---

## `get_paginated()` — full history

Iterates all pages automatically and applies a 2-second pause between requests to respect Strava's rate limits.

```python
get_paginated(
    endpoint: str,
    per_page: int = 200,
    start_page: int = 1,
    extra_params: dict | None = None,
    page_callback: Callable[[int, list], None] | None = None,
) -> list[dict]
```

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "client_id":     "...",
    "client_secret": "...",
    "refresh_token": "...",
})
strava = ConnectorFactory.create("fitness.strava", config=config)

# Fetch entire activity history
activities = strava.execute_raw_paginated(  # or call .get_paginated() directly
    "athlete/activities",
    per_page=200,
    page_callback=lambda page, items: print(f"Page {page}: {len(items)} activities"),
)
print(f"Total: {len(activities)} activities")

# Fetch only activities from a specific day (after/before timestamps)
import datetime, zoneinfo
day = datetime.date(2026, 4, 13)
tz  = datetime.timezone.utc
after  = int(datetime.datetime(day.year, day.month, day.day, tzinfo=tz).timestamp())
before = after + 86400

daily = strava.get_paginated(
    "athlete/activities",
    per_page=50,
    extra_params={"after": after, "before": before},
)
print(daily)
```

> `get_paginated()` is called directly on the connector instance (not via `safe_execute`). Wrap it manually in a try/except if you need error handling.

---

## `test_connection()`

Performs a lightweight `GET /athlete` to validate credentials.

```python
ok, message = strava.test_connection()
# ok=True  → "Connected as John Doe (id=12345)"
# ok=False → "Strava connection failed: Authorization Error"
```

---

## Rate limits

Strava enforces **200 requests / 15 minutes** and **2 000 requests / day**.

The connector handles this transparently:

| Situation | Behaviour |
|---|---|
| 429 — 15-min window | Waits 15 minutes, then retries |
| 429 — daily quota exhausted | Raises `RuntimeError` immediately |
| 429 — no rate-limit headers | Exponential back-off (60 s, 120 s, 240 s…) |
| Approaching 80 % of 15-min limit | `warnings.warn(...)` |
| Approaching 90 % of daily limit | `warnings.warn(...)` |

---

## Common endpoints

| Entity | Endpoint | Notes |
|---|---|---|
| Athlete profile | `GET /athlete` | — |
| Athlete stats | `GET /athletes/{id}/stats` | Requires athlete ID |
| Activity list | `GET /athlete/activities` | Paginated; supports `after`/`before` |
| Single activity | `GET /activities/{id}` | — |
| Clubs | `GET /athlete/clubs` | — |
| Routes | `GET /athletes/{id}/routes` | Requires athlete ID |
| Create activity | `POST /activities` | — |

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, flow, configure, ConnectorConfig

configure("fitness.strava", ConnectorConfig(params={
    "client_id":     "...",
    "client_secret": "...",
    "refresh_token": "...",
}))

@connect("fitness.strava")
def fetch_athlete(conn):
    return conn.execute("athlete")

@connect("fitness.strava")
def fetch_stats(conn, athlete_id: int):
    return conn.execute(f"athletes/{athlete_id}/stats")

@flow(name="strava-daily-snapshot")
def daily_snapshot():
    profile = fetch_athlete()
    if not profile.success:
        return profile
    stats = fetch_stats(athlete_id=profile.data["id"])
    return {
        "athlete": profile.data,
        "stats":   stats.data,
    }

result = daily_snapshot()
print(result.success)
print(result.metadata["flow"])   # "strava-daily-snapshot"
print(result.duration)
```

---

## Environment variables

```bash
# .env
STRAVA_CLIENT_ID=12345
STRAVA_CLIENT_SECRET=abc...
STRAVA_REFRESH_TOKEN=def...
```

```python
import os
from dotenv import load_dotenv
from pyconnectors import ConnectorFactory, ConnectorConfig

load_dotenv()

config = ConnectorConfig(params={
    "client_id":     os.environ["STRAVA_CLIENT_ID"],
    "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
    "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
})
strava = ConnectorFactory.create("fitness.strava", config=config)
```
