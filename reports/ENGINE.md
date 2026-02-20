# ENGINE

Факт-лог по движку.

- 2026-01-23 | TG.4.1.01 | DONE | Engine v0.1 (pure library) в `packages/engine`: модели, `apply_turn`, `pick_final`, milestones, детерминированные логи, pytest. Команда тестов: `python -m pytest -q packages/engine/tests`.
- 2026-01-23 | TG.4.1.02 | DONE | Engine v0.1: обработка classifier_result для free-text (confidence/safety/tags), neutral_reason low_confidence/safety_unclear, clamping для классификатора.

- 2026-02-20 | TG.LLM.CLASSIFIER.MILESTONES.ONECALL.V1 | DONE | Milestone voting extended for free_text: on milestone step with non-neutral classifier outcome, vote is derived from `intent_trait` when `confidence >= 0.70` and trait in t1..t5, else vote=none; added positive/negative tests in `packages/engine/tests/test_engine_v0_1.py`.
- 2026-02-20 | TG.L3.RUNTIME.INVALID.FREETEXT.RESULTBUG.V1 | DONE | Runtime crash fix documented: early invalid free_text return no longer references undefined `result`; `max_steps=None` in invalid payload branch.
