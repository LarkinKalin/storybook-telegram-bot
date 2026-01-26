## MVP Stack
- Python 3.11
- aiogram
- Postgres
- Docker Compose v2
- Secrets: /etc/skazka/skazka.env
- LOG_LEVEL: optional env (default INFO) for tg-bot logging

## TG.4.2.01 smoke check (no Telegram required)
Run from repo root with DB_URL pointing at Postgres:

```bash
PYTHONPATH=apps/tg-bot:packages/db/src TG_ID=999000 python apps/tg-bot/scripts/tg_4_2_01_smoke.py
```

## Dev/test dependencies
Install dev dependencies (including psycopg for DB tests):

```bash
python -m pip install -r requirements-dev.txt
```

This creates a session, applies three turns (A/B/C), and prints the resulting
`sessions.params_json`, `sessions.ending_id`, and `session_events` rows.

Run inside the container:

```bash
docker compose -f infra/docker/docker-compose.yml exec tg-bot \
  sh -lc "TG_ID=999000 python /app/apps/tg-bot/scripts/tg_4_2_01_smoke.py"
```

## Docker compose note
The tg-bot service does not bind-mount source code; after code changes run:

```bash
docker compose -f infra/docker/docker-compose.yml build tg-bot
docker compose -f infra/docker/docker-compose.yml up -d
```

## Документация (Source of Truth)
Главный вход: `docs/canon/INDEX.md` (порядок чтения, приоритеты, канон).
