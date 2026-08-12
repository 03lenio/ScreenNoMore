# ScreenNoMore

ScreenNoMore is a self-hosted attention budget enforced through NextDNS. It
observes DNS activity for configured services, counts unique minutes of allowed
usage in a rolling window, blocks a service when its allowance is reached, and
restores access after its cooldown.

## Policy

For each service, ScreenNoMore counts a minute once when at least one allowed
DNS query matches one of that service's domains. Duplicate queries and blocked
queries do not add usage. Only activity inside
`OBSERVING_LAST_LOGS_FROM_MINUTES` and after the most recent cooldown reset is
counted.

When `limit_minutes` is reached, ScreenNoMore enables the matching NextDNS
parental-control service. If NextDNS does not know that service ID, its domains
are used as denylist fallbacks. After `block_duration_minutes`, the service is
unblocked and its usage is reset.

## Run with Docker Compose

1. Copy `.env.example` to `.env`.
2. Add the API key from the bottom of the NextDNS account page and the target
   profile ID.
3. Start the worker:

```sh
docker compose up --build -d
docker compose ps
docker compose logs -f app
```

Stop it intentionally with `docker compose down`. The `unless-stopped` restart
policy restarts it after crashes and Docker daemon restarts.

The Compose service is healthy after a complete observation cycle succeeds.
Repeated cycle failures cause the worker to exit so Docker can restart it.

## Configuration

| Variable | Purpose | Default in Compose |
| --- | --- | --- |
| `NEXTDNS_API_KEY` | NextDNS API authentication | Required in `.env` |
| `NEXTDNS_PROFILE_ID` | Profile to observe and update | Required in `.env` |
| `OBSERVING_INTERVAL` | Seconds between successful cycles | `30` |
| `OBSERVING_LAST_LOGS_FROM_MINUTES` | Rolling usage window | `40` |
| `MAX_LOG_PAGES` | Pagination safety cap per cycle | `20` |
| `MAX_CONSECUTIVE_FAILURES` | Failures before process restart | `5` |
| `HEALTH_MAX_AGE_SECONDS` | Minimum accepted heartbeat age | `90` |
| `DATABASE_CONFIG_PATH` | SQLite database path | `/data/screennomore.db` |
| `SERVICES_CONFIG_PATH` | First-run service seed file | Included seed JSON |

`NEXTDNS_API_KEY` stays server-side. Do not commit `.env` or expose it to a
future browser client.

## Services and persistence

The bundled `services.json` is read only once to seed a fresh database. After
that, SQLite is authoritative: database edits and deletions survive restarts.
Each service stores a display name, a NextDNS service ID, monitored domains, an
allowance, and a cooldown.

Runtime data is stored in `./data` by Compose. Back it up before upgrading:

```sh
docker compose down
cp data/screennomore.db data/screennomore.db.backup
docker compose up -d
```

Startup applies the small additive schema migration needed by this prototype.

## Focused checks

The regression checks use Python's standard library:

```sh
python -m unittest discover -s tests -v
```

They cover usage accounting, pagination, cooldown persistence, one-time
seeding, remote failure consistency, and the worker failure threshold.

# Outlook and TODOs

- In the future there should be a small frontend to view usage and reset cooldowns. For now, use `sqlite3` or
  `DB Browser for SQLite` to inspect the database.
- Additionally, `services.json` should be removed in the future, and the database should be the only source of truth. 
  - The frontend should then allow adding and removing services.
- There should be a gitlab pipeline for building and publishing the docker image.
- Code quality and test coverage should be improved, especially for the NextDNS API client.
- The NextDNS API client should be moved into its own module, exposing profiles as first-class objects, and the worker should be refactored to use this interface.