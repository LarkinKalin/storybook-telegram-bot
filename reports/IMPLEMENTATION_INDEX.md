# IMPLEMENTATION_INDEX

Факт-лог по квестам (что реально сделано).

## Зоны
- TG_BOT.md — Telegram UX, команды, клавиатуры, сценарии.
- ENGINE.md — движок шагов, параметры, финалы.
- LLM_FILTERS.md — LLM контракт/промпты/валидатор + фильтры/rewrites.
- OPS_DB_TON.md — сервер/репо, БД, деплой, TON, обслуживание.

## Последние события
- 2026-01-17: TG.1.1.01..TG.1.1.04 — подготовка окружения и репо (см. OPS_DB_TON.md)
# IMPLEMENTATION_INDEX
Факт-лог по квестам. Ссылки на журналы зон.

- TG_BOT.md
- ENGINE.md
- LLM_FILTERS.md
- OPS_DB_TON.md
TG.2.2.01+TG.2.3.01 — runnable tg-bot in docker compose (/start OK) — 2026-01-19 — 7cdcc83,b03044e,b0f1ca1

2026-01-19 | TG.1.1.01 | ACCEPTED | Created system dirs /etc/skazka (750), /var/lib/skazka, /var/log/skazka, /var/backups/skazka (755)
2026-01-19 | TG.1.2.01 | ACCEPTED | Repo tree created at /srv/git/skazka (apps/packages/infra/scripts/tests/backups/reports); structure verified by tree -L 3
2026-01-19 | TG.1.3.01 | DONE | MVP Stack фиксирован в README (Python 3.11 + aiogram + Postgres + compose v2 + secrets /etc/skazka/skazka.env)
