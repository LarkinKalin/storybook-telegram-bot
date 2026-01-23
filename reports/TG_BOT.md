## 2026-01-19 — TG.2.1.01 — tg-bot runnable в Docker Compose (DONE)

Сделано:
- Добавлен минимальный tg-bot на aiogram (обрабатывает /start).
- Добавлены файлы контейнеризации:
  - /srv/git/skazka/apps/tg-bot/requirements.txt
  - /srv/git/skazka/apps/tg-bot/Dockerfile
  - /srv/git/skazka/apps/tg-bot/src/bot_app.py
- Обновлён compose:
  - /srv/git/skazka/infra/docker/docker-compose.yml
- Секреты вынесены из репозитория:
  - /srv/git/skazka/infra/docker/.env (не коммитим)
  - /etc/skazka/skazka.env остаётся вне репо (хранилище секретов)

Проверка:
- cd /srv/git/skazka/infra/docker
- docker-compose up -d --build
- docker-compose ps (tg-bot: Up)
- /start отвечает в Telegram

Результат: OK
2026-01-19 | TG.2.2.01+TG.2.3.01 | DONE | Runnable tg-bot (aiogram) in docker compose, /start отвечает; commits 7cdcc83,b03044e,b0f1ca1


2026-01-19 | TG.2.1.02 | DONE | L1 ReplyKeyboard: fixed labels, text==button treated as command; unknown text -> hint + L1
2026-01-19 | TG.2.1.02A | DONE | L1: slash aliases for all L1 buttons + prefix suggestions for partial slash input; BotFather commands configured (latin) for client-side autocomplete
2026-01-19 | TG.2.1.02A | DONE | L1: slash aliases for all L1 buttons + prefix suggestions for partial slash input; BotFather commands configured (latin) for client-side autocomplete

2026-01-19 | TG.2.1.03 | DONE | L2 topic picker: themes from json; inline buttons; callback t:<id>, pg2:<page>; page_size=10; empty-safe

2026-01-19 | TG.2.1.04.C | DONE | Добавлен режим “🧠 Почемучка” (WHY_TEXT) в L1, база why_qa.json, матчинг, fallback, inline-выход в меню; commit 8528dd5
Изменённые файлы:
- /srv/git/skazka/apps/tg-bot/src/bot_app.py
- /srv/git/skazka/apps/tg-bot/src/handlers/l1.py
- /srv/git/skazka/apps/tg-bot/src/handlers/why.py
- /srv/git/skazka/apps/tg-bot/src/keyboards/l1.py
- /srv/git/skazka/apps/tg-bot/src/keyboards/why.py
- /srv/git/skazka/apps/tg-bot/src/services/read_prefs.py
- /srv/git/skazka/apps/tg-bot/src/services/whyqa.py
- /srv/git/skazka/apps/tg-bot/src/data/why_qa.json
- /srv/git/skazka/apps/tg-bot/src/states.py
2026-01-19 | TG.2.1.04.C | FIX | whyqa data path uses src/data for container runtime; commit 0c3e83d
2026-01-19 | TG.2.1.04.D | DONE | WHY_TEXT UX: hide ReplyKeyboard on entry, inline ⬅ Назад (go:l1), return to L1; commit b21d33d
2026-01-20 | TG.2.1.04.D | DONE | Why-mode UX: remove L1 ReplyKeyboard on enter (ReplyKeyboardRemove), add inline back (go:l1) + callback handler; commits: 44f19e0, fabaa6a, d99dc87
Изменённые файлы:
- /srv/git/skazka/apps/tg-bot/src/handlers/l1.py
- /srv/git/skazka/apps/tg-bot/src/handlers/why.py
- /srv/git/skazka/apps/tg-bot/src/keyboards/why.py

2026-01-20 | TG.2.1.05 | DONE | Runtime sessions (ACTIVE/FINISHED/ABORTED), L3 inline-only step, resume/status/help/shop flows, theme pick gating by active session
2026-01-20 | TG.2.3.02A | DONE | L2 active-story confirm: add ⬅ Назад to return to theme list without changing session
2026-01-22 | TG.3.5.01 | DONE | TG bot uses Postgres for runtime sessions (1 ACTIVE enforced); resume/status/confirm read/write DB; survives restart
2026-01-23 | TG.4.2.01 | DONE | L3 inline runtime: engine apply_turn + params_json persistence + session_events step logs + final save (no LLM), anti-stale + fingerprint dedupe
