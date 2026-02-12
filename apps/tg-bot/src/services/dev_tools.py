from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from psycopg.rows import dict_row

from db.conn import transaction
from db.repos import l3_turns, session_events, sessions, users
from packages.engine.src.engine_v0_1 import init_state_v01
from src.services.runtime_sessions import Session, get_session

logger = logging.getLogger(__name__)

_DEMO_THEME_ID = "dev_book_demo"
_DEMO_PLAYER_NAME = "dev_book_demo"
_CONTENT_ROOT = Path(os.getenv("SKAZKA_CONTENT_DIR", "/app/content"))
_DEV_BOOK_FIXTURE_PATH = _CONTENT_ROOT / "fixtures" / "dev_book_8_steps.json"


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
    if not admins:
        return False
    return tg_id in admins


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


def fast_forward_to_final(tg_id: int) -> tuple[bool, str]:
    session = get_session(tg_id)
    if session is None:
        return False, "Нет активной сессии. Сначала начни или подключи /dev_use_session <sid8>."

    final_step0 = max(0, int(session.max_steps) - 1)
    sid8 = session.sid8
    if int(session.step) < final_step0:
        ok, msg = _fast_forward_session(tg_id, sid8, session.max_steps, session.step, to_step=final_step0)
        if not ok:
            return ok, msg

    refreshed = get_session(tg_id)
    if refreshed is None:
        return False, "Не удалось обновить активную сессию после fast-forward."

    final_id = f"dev_final_{uuid4().hex[:8]}"

    def _apply_final(session_row: dict):
        state = _ensure_session_engine_state(session_row)
        new_state = dict(state)
        new_state["step0"] = final_step0
        return l3_turns.L3ApplyPayload(
            new_state=new_state,
            llm_json={"dev_finish": True},
            deltas_json={"dev_finish": True},
            step_result_json={
                "step_index": final_step0 + 1,
                "text": "[DEV] Finished",
                "narration_text": "[DEV] Finished",
                "choices": [],
                "protocol_choices": [],
                "chosen_choice_id": None,
                "story_step_json": {"text": "[DEV] Finished", "choices": []},
                "final_id": final_id,
                "allow_free_text": False,
            },
            meta_json={"dev_finish": True, "final_id": final_id},
            finish_status="FINISHED",
            final_id=final_id,
            final_meta={"dev_finish": True},
        )

    result = l3_turns.apply_l3_turn_atomic(
        tg_id=tg_id,
        sid8=sid8,
        expected_step=final_step0,
        step=final_step0,
        user_input="[DEV_FINISH]",
        choice_id="dev_finish",
        base_meta_json={"dev_finish": True},
        apply_fn=_apply_final,
    )
    if result is None:
        return False, "Сессия не найдена для dev_finish."
    if result.outcome not in {"accepted", "duplicate"}:
        return False, f"dev_finish остановлен: {result.outcome}."

    if result.outcome == "duplicate":
        with transaction() as conn:
            row = sessions.get_by_tg_id_sid8_for_update(conn, tg_id=tg_id, sid8=sid8)
            if not row:
                return False, "Сессия не найдена при обновлении финала."
            event = session_events.get_by_step(conn, session_id=int(row["id"]), step=final_step0)
            if event:
                payload = event.get("step_result_json") if isinstance(event.get("step_result_json"), dict) else {}
                payload = dict(payload)
                payload["final_id"] = final_id
                payload.setdefault("text", "[DEV] Finished")
                payload.setdefault("choices", [])
                session_events.update_event_payload(
                    conn,
                    event_id=int(event["id"]),
                    llm_json=event.get("llm_json") if isinstance(event.get("llm_json"), dict) else {"dev_finish": True},
                    deltas_json=event.get("deltas_json") if isinstance(event.get("deltas_json"), dict) else {"dev_finish": True},
                    outcome="accepted",
                    step_result_json=payload,
                    meta_json={"dev_finish": True, "final_id": final_id},
                )
            sessions.finish_with_final_in_tx(conn, int(row["id"]), final_id, {"dev_finish": True})

    return True, f"Финал проставлен. final_id={final_id}, step={final_step0 + 1}."


def _load_dev_book_fixture() -> dict[str, Any]:
    if _DEV_BOOK_FIXTURE_PATH.exists():
        payload = json.loads(_DEV_BOOK_FIXTURE_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    steps = [
        {
            "step_index": i,
            "text": f"[DEV_FIXTURE] Шаг {i}",
            "choices": [{"id": "a", "text": "Вариант A"}],
            "chosen_choice_id": "a",
        }
        for i in range(1, 9)
    ]
    return {"title": "Тестовая книжка", "child_name": "дружок", "steps": steps}


def create_dev_book_session_from_fixture(tg_id: int) -> Session:
    fixture = _load_dev_book_fixture()
    user = users.get_or_create_by_tg_id(tg_id)
    user_id = int(user["id"])
    row = sessions.create_new_active(
        user_id,
        theme_id="test_book",
        player_name="dev_book_fixture",
        meta={"max_steps": 8},
    )
    session = _to_session(row)
    steps = fixture.get("steps") if isinstance(fixture.get("steps"), list) else []
    for idx in range(8):
        source = steps[idx] if idx < len(steps) and isinstance(steps[idx], dict) else {}
        step_text = source.get("text") if isinstance(source.get("text"), str) else f"[DEV_FIXTURE] Шаг {idx+1}"
        raw_choices = source.get("choices") if isinstance(source.get("choices"), list) else []
        protocol_choices: list[dict[str, str]] = []
        for choice in raw_choices:
            if not isinstance(choice, dict):
                continue
            cid = choice.get("id") or choice.get("choice_id")
            ctext = choice.get("text") or choice.get("label")
            if isinstance(cid, str) and isinstance(ctext, str):
                protocol_choices.append({"id": cid, "text": ctext})
        if not protocol_choices:
            protocol_choices = [{"id": "a", "text": "Вариант A"}]
        chosen_choice_id = source.get("chosen_choice_id") if isinstance(source.get("chosen_choice_id"), str) else protocol_choices[0]["id"]
        step_payload = {
            "step_index": idx + 1,
            "narration_text": step_text,
            "text": step_text,
            "protocol_choices": protocol_choices,
            "choices": [{"choice_id": c["id"], "label": c["text"]} for c in protocol_choices],
            "chosen_choice_id": chosen_choice_id,
            "story_step_json": {"text": step_text, "choices": [{"id": c["id"], "text": c["text"]} for c in protocol_choices]},
            "allow_free_text": False,
            "final_id": "dev_fixture_final" if idx == 7 else None,
        }
        session_events.append_event(
            session_id=session.id,
            step=idx,
            step0=idx,
            user_input="[DEV_FIXTURE]",
            choice_id=chosen_choice_id,
            llm_json={"dev_fixture": True},
            deltas_json={"dev_fixture": True},
            outcome="accepted",
            step_result_json=step_payload,
            meta_json={"dev_fixture": True},
        )
    sessions.update_step(session.id, 7)
    refreshed = activate_session_for_user(tg_id, session.sid8)
    return refreshed or session
