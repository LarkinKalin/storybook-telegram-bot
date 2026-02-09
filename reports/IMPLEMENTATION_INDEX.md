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
2026-01-19 | TG.2.1.02 | DONE | L1 home menu: fixed labels, label-first routing, unknown text hint+repeat; slash aliases + prefix suggestions; commits: 9ba4429, 1e6adc3, d8939cb

2026-01-19 | TG.2.1.03 | DONE | L2 topic picker: themes from json; inline buttons; callback t:<id>, pg2:<page>; page_size=10; empty-safe

2026-01-19 | TG.2.1.04.C | DONE | Why mode (WHY_TEXT) + L1 button + why_qa matching + fallback; commit 8528dd5
2026-01-19 | TG.2.1.04.C | FIX | whyqa data path uses src/data for container runtime; commit 0c3e83d
2026-01-19 | TG.2.1.04.D | DONE | Why UX polish: hide reply keyboard + go:l1 back button; commit b21d33d
2026-01-20 | TG.2.1.04.D | DONE | Why-mode UX: hide L1 keyboard + back button go:l1; commits 44f19e0,fabaa6a,d99dc87
2026-01-20 | TG.2.1.05 | DONE | Runtime sessions + L3 inline step + resume/status/help/shop screens + theme pick gating by active session
2026-01-20 | TG.2.3.02A | DONE | L2 active-story confirm: add ⬅ Назад to return to theme list without changing session
2026-01-22 | TG.3.2.01 | DONE | DB schema fixed via SQL migrations: users/sessions/session_events/payments/confirm_requests/usage_windows/ui_events (+ indexes/constraints)
2026-01-22 | TG.3.4.01 | DONE | DB access layer: repos for users/sessions/events/payments/confirm/ui_events/usage_windows (+ smoke check)
2026-01-22 | TG.3.5.01 | DONE | TG bot uses Postgres for runtime sessions (1 ACTIVE enforced); resume/status/confirm read/write DB; survives restart

## Canon (source of truth)
- docs/ENGINE_SPEC_v0_1.md — канон engine v0.1 (параметры, вехи, матрицы, финалы)

2026-01-23 | TG.4.1.01 | DONE | Engine v0.1 (pure library) in packages/engine + pytest setup
2026-01-23 | TG.4.1.02 | DONE | Engine v0.1 free-text classifier plumbing (confidence/safety neutral rules)
2026-01-23 | TG.4.2.01 | DONE | L3 runtime loop wired to Engine v0.1 + Postgres (params_json/session_events/final), inline-only without LLM
YYYY-MM-DD | TG.5.1.01 | DONE | LLM STORY_STEP contract v0.1 accepted (REV2 FINAL hardening++): engine independent, strict JSON-only IO, single-retry + exhausted policy, memory clamp, free_text-only guarantee, trace meta with sizes/retry_reason.
2026-01-25 | TG.6.4.01 | DONE | L3 step runtime: atomic facts + idempotency + ui_events delivery
2026-01-25 | TG.6.4.02 | DONE | L3 stale/invalid callback handling + ui_events dedup key
2026-01-25 | TG.6.4.06 | DONE | /resume idempotency: skip duplicate step delivery
2026-01-25 | TG.6.4.08 | DONE | L3 UX hardening: locked step UI + unified continue + free-text race guard
2026-01-25 | TG.6.4.09 | DONE | L3 UX hardening: lock after accept + resume idempotency + ending step final + global commands
2026-01-25 | TG.6.4.10 | DONE | Continue/Resume unification + idempotency guard + global commands
2026-01-26 | TG.6.5.01 | DONE | Atomic L3 + migrations runner + concurrency test
2026-01-27 | TG.7.1.01 | DONE | LLM adapter v0.1 (mock-first) + L3 integration behind flag
2026-01-28 | TG.7.2.01 | DONE | LLM mock matrix + contract validation tests + expected_type + choices.len UX
2026-01-28 | TG.7.3.01 | DONE | OpenRouter(Kimi) text provider v0.1 wired (secrets out of repo) + smoke step/final
2026-01-29 | TG.3.2.02 | DONE | DB v0.2 assets + session_images (no base64 in Postgres)
2026-01-30 | TG.7.5.01 | DONE | Why (Почемучка) v0.2: Q/A + LLM fallback (Kimi) + prompt pack + guardrails
2026-02-09 | TG.7.4.01.A | DONE | Image pipeline: invocation + scheduling proven
2026-02-09 | TG.7.4.02 | DONE | Image plan aligned to canonical story steps (8/10/12)
2026-02-09 | TG.7.4.04 | DONE | Flux image provider hardened (t2i+i2i reference chain)
