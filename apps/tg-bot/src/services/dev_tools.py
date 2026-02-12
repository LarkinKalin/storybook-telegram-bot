from __future__ import annotations

import logging
import os

from db.repos import l3_turns, sessions, users
from packages.engine.src.engine_v0_1 import init_state_v01
from src.services.runtime_sessions import Session, get_session

logger = logging.getLogger(__name__)


def dev_tools_enabled() -> bool:
    raw = os.getenv("SKAZKA_DEV_TOOLS", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _admin_ids() -> set[int]:
    raw = os.getenv("SKAZKA_DEV_ADMIN_TG_IDS", "").strip()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


def can_use_dev_tools(tg_id: int) -> bool:
    if not dev_tools_enabled():
        return False
    admins = _admin_ids()
    return tg_id in admins if admins else False


def activate_session_for_user(tg_id: int, sid8: str) -> Session | None:
    user = users.get_or_create_by_tg_id(tg_id)
    user_id = int(user["id"])
    row = sessions.activate_existing_session(user_id=user_id, tg_id=tg_id, sid8=sid8)
    if not row:
        return None
    return Session(
        id=int(row["id"]),
        tg_id=int(row["tg_id"]),
        sid8=str(row["sid8"]),
        status=row["status"],
        theme_id=row.get("theme_id"),
        step=int(row.get("step", 0)),
        max_steps=int(row.get("max_steps", 1)),
        params_json=row.get("params_json") or {},
        facts_json=row.get("facts_json") or {},
        ending_id=row.get("ending_id"),
        last_step_message_id=row.get("last_step_message_id"),
        last_step_sent_at=None,
        child_name=row.get("child_name"),
    )


def fast_forward_active_session(tg_id: int, to_step: int = 7) -> tuple[bool, str]:
    session = get_session(tg_id)
    if session is None:
        return False, "Нет активной сессии. Сначала начни или подключи /dev_use_session <sid8>."

    max_step0 = max(0, int(session.max_steps) - 1)
    to_step = max(0, min(int(to_step), max_step0))
    current = int(session.step)
    if current >= to_step:
        return True, f"Уже на шаге {current + 1} (step0={current})."

    logger.info(
        "dev.fast_forward started tg_id=%s sid8=%s from_step=%s to_step=%s",
        tg_id,
        session.sid8,
        current,
        to_step,
    )

    while current < to_step:
        step_before = current

        def _apply_fn(session_row: dict):
            params = session_row.get("params_json") or {}
            if not isinstance(params, dict) or params.get("v") != "0.1":
                params = init_state_v01(session_row.get("max_steps", 8))
            new_state = dict(params)
            new_state["step0"] = int(new_state.get("step0", step_before)) + 1

            step_result_json = {
                "step_index": step_before + 1,
                "narration_text": f"[DEV] Fast-forward step {step_before + 1}",
                "text": f"[DEV] Fast-forward step {step_before + 1}",
                "choices": [{"choice_id": "dev_ok", "label": "DEV OK"}],
                "protocol_choices": [{"id": "dev_ok", "text": "DEV OK"}],
                "chosen_choice_id": "dev_ok",
                "story_step_json": {
                    "text": f"[DEV] Fast-forward step {step_before + 1}",
                    "choices": [{"choice_id": "dev_ok", "label": "DEV OK"}],
                },
                "allow_free_text": False,
                "final_id": None,
                "recap_short": f"[DEV] Step {step_before + 1}",
            }

            return l3_turns.L3ApplyPayload(
                new_state=new_state,
                llm_json={"dev_fast_forward": True},
                deltas_json={"dev_fast_forward": True},
                step_result_json=step_result_json,
                meta_json={"dev_fast_forward": True},
                finish_status=None,
                final_id=None,
                final_meta=None,
            )

        result = l3_turns.apply_l3_turn_atomic(
            tg_id=tg_id,
            sid8=session.sid8,
            expected_step=step_before,
            step=step_before,
            user_input="[DEV_FF]",
            choice_id="dev_ok",
            base_meta_json={"dev_fast_forward": True},
            apply_fn=_apply_fn,
        )
        if result is None:
            return False, "Сессия не найдена при fast-forward."
        if result.outcome not in {"accepted", "duplicate"}:
            return False, f"Fast-forward остановлен: {result.outcome}."
        logger.info("dev.fast_forward step_written step=%s", step_before + 1)
        current = step_before + 1

    logger.info("dev.fast_forward ok new_step=%s", current)
    return True, f"Готово. Теперь активный шаг: {current + 1} (step0={current})."
