from __future__ import annotations

import logging
import os
from typing import Any

from psycopg.rows import dict_row

from db.conn import transaction
from db.repos import l3_turns, sessions, users
from packages.engine.src.engine_v0_1 import init_state_v01
from src.services.runtime_sessions import Session, get_session

logger = logging.getLogger(__name__)

_DEMO_THEME_ID = "dev_book_demo"
_DEMO_PLAYER_NAME = "dev_book_demo"


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
    return True if not admins else tg_id in admins


def _to_session(row: dict[str, Any]) -> Session:
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


def activate_session_for_user(tg_id: int, sid8: str) -> Session | None:
    user = users.get_or_create_by_tg_id(tg_id)
    user_id = int(user["id"])
    row = sessions.activate_existing_session(user_id=user_id, tg_id=tg_id, sid8=sid8)
    if not row:
        return None
    return _to_session(row)


def _ensure_session_engine_state(session_row: dict[str, Any]) -> dict[str, Any]:
    params = session_row.get("params_json") or {}
    if not isinstance(params, dict) or params.get("v") != "0.1":
        params = init_state_v01(session_row.get("max_steps", 8))
    return params


def _ff_step_payload(step_before: int, *, chosen_choice_id: str = "dev_ok") -> dict[str, Any]:
    return {
        "step_index": step_before + 1,
        "narration_text": f"[DEV] Fast-forward step {step_before + 1}",
        "text": f"[DEV] Fast-forward step {step_before + 1}",
        "choices": [{"choice_id": chosen_choice_id, "label": "DEV OK"}],
        "protocol_choices": [{"id": chosen_choice_id, "text": "DEV OK"}],
        "chosen_choice_id": chosen_choice_id,
        "story_step_json": {
            "text": f"[DEV] Fast-forward step {step_before + 1}",
            "choices": [{"choice_id": chosen_choice_id, "label": "DEV OK"}],
        },
        "allow_free_text": False,
        "final_id": None,
        "recap_short": f"[DEV] Step {step_before + 1}",
    }


def fast_forward_active_session(tg_id: int, to_step: int = 7) -> tuple[bool, str]:
    session = get_session(tg_id)
    if session is None:
        return False, "Нет активной сессии. Сначала начни или подключи /dev_use_session <sid8>."
    return _fast_forward_session(tg_id, session.sid8, session.max_steps, session.step, to_step=to_step)


def _fast_forward_session(
    tg_id: int,
    sid8: str,
    max_steps: int,
    current_step: int,
    *,
    to_step: int,
) -> tuple[bool, str]:
    max_step0 = max(0, int(max_steps) - 1)
    to_step = max(0, min(int(to_step), max_step0))
    current = int(current_step)
    if current >= to_step:
        return True, f"Уже на шаге {current + 1} (step0={current})."

    logger.info(
        "dev.fast_forward started tg_id=%s sid8=%s from_step=%s to_step=%s",
        tg_id,
        sid8,
        current,
        to_step,
    )

    while current < to_step:
        step_before = current

        def _apply_fn(session_row: dict):
            state = _ensure_session_engine_state(session_row)
            new_state = dict(state)
            new_state["step0"] = int(new_state.get("step0", step_before)) + 1
            return l3_turns.L3ApplyPayload(
                new_state=new_state,
                llm_json={"dev_fast_forward": True},
                deltas_json={"dev_fast_forward": True},
                step_result_json=_ff_step_payload(step_before),
                meta_json={"dev_fast_forward": True},
                finish_status=None,
                final_id=None,
                final_meta=None,
            )

        result = l3_turns.apply_l3_turn_atomic(
            tg_id=tg_id,
            sid8=sid8,
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


def ensure_demo_session_ready(tg_id: int) -> Session:
    user = users.get_or_create_by_tg_id(tg_id)
    user_id = int(user["id"])
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM sessions
                WHERE user_id = %s
                  AND tg_id = %s
                  AND theme_id = %s
                  AND player_name = %s
                ORDER BY id DESC
                LIMIT 1;
                """,
                (user_id, tg_id, _DEMO_THEME_ID, _DEMO_PLAYER_NAME),
            )
            existing = cur.fetchone()
    if existing:
        activated = sessions.activate_existing_session(user_id=user_id, tg_id=tg_id, sid8=existing["sid8"])
        row = activated or dict(existing)
    else:
        row = sessions.create_new_active(
            user_id,
            theme_id=_DEMO_THEME_ID,
            player_name=_DEMO_PLAYER_NAME,
            meta={"max_steps": 8},
        )
    session = _to_session(row)
    _fast_forward_session(tg_id, session.sid8, session.max_steps, session.step, to_step=7)
    refreshed = activate_session_for_user(tg_id, session.sid8)
    return refreshed or session
