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
