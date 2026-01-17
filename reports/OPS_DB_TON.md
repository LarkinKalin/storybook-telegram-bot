## 2026-01-17 — TG.1.1.01..TG.1.1.04 — Подготовка окружения и репо (DONE)

Сделано:
- Созданы системные каталоги:
  - /etc/skazka
  - /var/backups/skazka
  - /var/lib/skazka
  - /var/log/skazka
- Создано дерево репозитория:
  - /srv/git/skazka/apps/tg-bot/src
  - /srv/git/skazka/packages/{engine,llm,filters,db,payments-ton}
  - /srv/git/skazka/infra/{docker,systemd}
  - /srv/git/skazka/backups
  - /srv/git/skazka/reports
- Созданы журналы реализации:
  - /srv/git/skazka/reports/IMPLEMENTATION_INDEX.md
  - /srv/git/skazka/reports/TG_BOT.md
  - /srv/git/skazka/reports/ENGINE.md
  - /srv/git/skazka/reports/LLM_FILTERS.md
  - /srv/git/skazka/reports/OPS_DB_TON.md
- Инициализирован git-репозиторий в /srv/git/skazka
- Создан root commit: 61db7f2 "init: skazka repo skeleton"
- Настроена git identity:
  - user.name = LarkinKalin
  - user.email = LarkinKalin@outlook.com

Проверка:
- tree -L 4 /srv/git/skazka
- git -C /srv/git/skazka log --oneline -n 3

Результат: OK
## TG.1.2.01 — Выбор способа запуска (MVP)

Дата: 2026-01-16

Принято решение использовать **Docker Compose** как основной способ запуска сервисов на этапе MVP.

Статус: DONE
