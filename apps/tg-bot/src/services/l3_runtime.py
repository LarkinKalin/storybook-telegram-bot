from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Literal

from db.conn import transaction
from db.repos import session_events, sessions
from packages.engine.src.engine_v0_1 import apply_turn, init_state_v01
from src.services.content_stub import build_content_step
from src.keyboards.l3 import build_l3_keyboard
from src.services.story_runtime import StepView, render_step

TurnStatus = Literal["accepted", "duplicate", "stale"]


@dataclass
class L3TurnResult:
    status: TurnStatus
    step_view: StepView | None
    session_id: int
    step: int
    theme_id: str | None
    final_id: str | None


def _fingerprint(
    session_id: int,
    step0: int,
    kind: str,
    payload: str,
    source_message_id: int,
) -> str:
    raw = f"{session_id}:{step0}:{kind}:{payload}:{source_message_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def apply_l3_turn(
    *,
    tg_id: int,
    sid8: str,
    st2: int,
    turn: Dict[str, Any],
    source_message_id: int,
) -> L3TurnResult | None:
    with transaction() as conn:
        session_row = sessions.get_by_tg_id_sid8_for_update(conn, tg_id=tg_id, sid8=sid8)
        if not session_row:
            return None
        if int(session_row["step"]) != st2:
            return L3TurnResult(
                status="stale",
                step_view=None,
                session_id=int(session_row["id"]),
                step=int(session_row["step"]),
                theme_id=session_row.get("theme_id"),
                final_id=None,
            )

        params = session_row.get("params_json") or {}
        if not isinstance(params, dict) or params.get("v") != "0.1":
            state = init_state_v01(session_row.get("max_steps", 8))
            sessions.update_params_json_in_tx(conn, session_row["id"], state)
        else:
            state = params
        content = build_content_step(session_row["theme_id"], state["step0"], state)
        turn_kind = turn.get("kind", "")
        payload = turn.get("choice_id") or turn.get("text") or ""
        fingerprint = _fingerprint(
            session_row["id"], state["step0"], turn_kind, payload, source_message_id
        )
        event_id = session_events.insert_event(
            conn,
            session_id=session_row["id"],
            step=state["step0"],
            user_input=turn.get("text"),
            choice_id=turn.get("choice_id"),
            llm_json={"turn_fingerprint": fingerprint, "turn": turn},
            deltas_json=None,
        )
        if event_id is None:
            existing_event = session_events.get_by_step(
                conn,
                session_id=session_row["id"],
                step=state["step0"],
            )
            final_id = None
            if existing_event:
                llm_json = existing_event.get("llm_json") or {}
                if isinstance(llm_json, dict):
                    step_log = llm_json.get("engine_step_log") or {}
                    if isinstance(step_log, dict):
                        final_id = step_log.get("final_id")
            if final_id:
                final_text = (
                    f"Финал {final_id}.\n"
                    f"Спасибо за игру! Можно начать новую сказку."
                )
                final_keyboard = build_l3_keyboard(
                    [],
                    allow_free_text=False,
                    sid8=session_row["sid8"],
                    step=state["step0"],
                )
                step_view = StepView(
                    text=final_text,
                    keyboard=final_keyboard,
                    final_id=final_id,
                )
            else:
                step_view = render_step(session_row, state=state)
            return L3TurnResult(
                status="duplicate",
                step_view=step_view,
                session_id=int(session_row["id"]),
                step=int(session_row["step"]),
                theme_id=session_row.get("theme_id"),
                final_id=final_id or step_view.final_id,
            )

        new_state, step_log = apply_turn(state, turn, content)
        llm_json = {
            "engine_step_log": step_log,
            "turn_fingerprint": fingerprint,
            "turn": turn,
        }
        deltas_json = {"applied_deltas": step_log["applied_deltas"]}
        session_events.update_event_payload(
            conn,
            event_id=event_id,
            llm_json=llm_json,
            deltas_json=deltas_json,
        )
        sessions.update_params_json_in_tx(conn, session_row["id"], new_state)
        sessions.update_step_in_tx(conn, session_row["id"], new_state["step0"])

        if step_log["final_id"]:
            sessions.finish_with_final_in_tx(
                conn,
                session_row["id"],
                step_log["final_id"],
                step_log["final_meta"] or {},
            )
            final_text = (
                f"Финал {step_log['final_id']}.\n"
                f"Спасибо за игру! Можно начать новую сказку."
            )
            final_keyboard = build_l3_keyboard(
                [],
                allow_free_text=False,
                sid8=session_row["sid8"],
                step=new_state["step0"],
            )
            step_view = StepView(
                text=final_text,
                keyboard=final_keyboard,
                final_id=step_log["final_id"],
            )
            return L3TurnResult(
                status="accepted",
                step_view=step_view,
                session_id=int(session_row["id"]),
                step=int(new_state["step0"]),
                theme_id=session_row.get("theme_id"),
                final_id=step_log["final_id"],
            )

        step_view = render_step({**session_row, "params_json": new_state}, state=new_state)
        return L3TurnResult(
            status="accepted",
            step_view=step_view,
            session_id=int(session_row["id"]),
            step=int(new_state["step0"]),
            theme_id=session_row.get("theme_id"),
            final_id=step_view.final_id,
        )
