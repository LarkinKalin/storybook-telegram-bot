from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from db.conn import transaction
from db.repos import session_events, sessions

L3Outcome = Literal["accepted", "duplicate", "stale", "invalid"]


@dataclass
class L3ApplyPayload:
    new_state: dict[str, Any]
    llm_json: dict[str, Any] | None
    deltas_json: dict[str, Any] | None
    step_result_json: dict[str, Any] | None
    meta_json: dict[str, Any] | None
    finish_status: str | None
    final_id: str | None
    final_meta: dict[str, Any] | None


@dataclass
class L3ApplyResult:
    outcome: L3Outcome
    session_row: dict[str, Any]
    step: int
    event: dict[str, Any] | None
    payload: L3ApplyPayload | None


def apply_l3_turn_atomic(
    *,
    tg_id: int,
    sid8: str,
    expected_step: int,
    step: int,
    user_input: str | None,
    choice_id: str | None,
    is_valid: Callable[[dict[str, Any]], bool] | None = None,
    apply_fn: Callable[[dict[str, Any]], L3ApplyPayload],
) -> L3ApplyResult | None:
    with transaction() as conn:
        session_row = sessions.get_by_tg_id_sid8_for_update(conn, tg_id=tg_id, sid8=sid8)
        if not session_row:
            return None
        if int(session_row["step"]) != expected_step:
            return L3ApplyResult(
                outcome="stale",
                session_row=session_row,
                step=int(session_row["step"]),
                event=None,
                payload=None,
            )

        if is_valid is not None and not is_valid(session_row):
            return L3ApplyResult(
                outcome="invalid",
                session_row=session_row,
                step=int(session_row["step"]),
                event=None,
                payload=None,
            )

        event_id = session_events.insert_event(
            conn,
            session_id=session_row["id"],
            step=step,
            step0=step,
            user_input=user_input,
            choice_id=choice_id,
            llm_json=None,
            deltas_json=None,
            outcome="accepted",
            step_result_json=None,
            meta_json=None,
        )
        if event_id is None:
            existing_event = session_events.get_by_step(
                conn,
                session_id=session_row["id"],
                step=step,
            )
            return L3ApplyResult(
                outcome="duplicate",
                session_row=session_row,
                step=step,
                event=existing_event,
                payload=None,
            )

        payload = apply_fn(session_row)
        session_events.update_event_payload(
            conn,
            event_id=event_id,
            llm_json=payload.llm_json,
            deltas_json=payload.deltas_json,
            outcome="accepted",
            step_result_json=payload.step_result_json,
            meta_json=payload.meta_json,
        )
        sessions.update_params_json_in_tx(conn, session_row["id"], payload.new_state)
        sessions.update_step_in_tx(conn, session_row["id"], payload.new_state["step0"])

        if payload.final_id:
            sessions.finish_with_final_in_tx(
                conn,
                session_row["id"],
                payload.final_id,
                payload.final_meta or {},
            )
        elif payload.finish_status:
            sessions.finish_in_tx(conn, session_row["id"], status=payload.finish_status)

        return L3ApplyResult(
            outcome="accepted",
            session_row=session_row,
            step=int(payload.new_state["step0"]),
            event=None,
            payload=payload,
        )
