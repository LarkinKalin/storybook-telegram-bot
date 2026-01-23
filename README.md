## MVP Stack
- Python 3.11
- aiogram
- Postgres
- Docker Compose v2
- Secrets: /etc/skazka/skazka.env

## TG.4.2.01 smoke check (no Telegram required)
Run from repo root with DB_URL pointing at Postgres:

```bash
PYTHONPATH=apps/tg-bot:packages/db/src TG_ID=999000 python apps/tg-bot/scripts/tg_4_2_01_smoke.py
```

This creates a session, applies three turns (A/B/C), and prints the resulting
`sessions.params_json`, `sessions.ending_id`, and `session_events` rows.

## Docker compose note
The tg-bot service does not bind-mount source code; after code changes run:

```bash
docker compose -f infra/docker/docker-compose.yml build tg-bot
docker compose -f infra/docker/docker-compose.yml up -d
```
