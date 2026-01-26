from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Literal

from db.repos import l3_turns
from packages.engine.src.engine_v0_1 import apply_turn, init_state_v01
from src.services.content_stub import build_content_step
from src.services.story_runtime import (
    StepView,
    build_final_step_result,
    build_step_result,
    render_current_step,
    step_result_to_view,
)

TurnStatus = Literal["accepted", "duplicate", "stale", "invalid"]


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
    req_id: str | None = None,
) -> L3TurnResult | None:
    kind = turn.get("kind")
    if kind not in {"choice", "free_text"}:
        return L3TurnResult(
            status="invalid",
            step_view=None,
            session_id=0,
            step=st2,
            theme_id=None,
            final_id=None,
        )
    if kind == "choice" and not turn.get("choice_id"):
        return L3TurnResult(
            status="invalid",
            step_view=None,
            session_id=0,
            step=st2,
            theme_id=None,
            final_id=None,
        )
    if kind == "free_text" and not turn.get("text"):
        return L3TurnResult(
            status="invalid",
            step_view=None,
            session_id=0,
            step=st2,
            theme_id=None,
            final_id=None,
        )
    def _apply_in_tx(session_row: Dict[str, Any]) -> l3_turns.L3ApplyPayload:
        params = session_row.get("params_json") or {}
        if not isinstance(params, dict) or params.get("v") != "0.1":
            state = init_state_v01(session_row.get("max_steps", 8))
        else:
            state = params
        content = build_content_step(session_row["theme_id"], state["step0"], state)
        new_state, step_log = apply_turn(state, turn, content)
        turn_kind = turn.get("kind", "")
        payload_value = turn.get("choice_id") or turn.get("text") or ""
        fingerprint = _fingerprint(
            session_row["id"], state["step0"], turn_kind, payload_value, source_message_id
        )
        llm_json = {
            "engine_step_log": step_log,
            "turn_fingerprint": fingerprint,
            "turn": turn,
        }
        deltas_json = {"applied_deltas": step_log["applied_deltas"]}
        if step_log["final_id"]:
            step_result_json = build_final_step_result(
                step_log["final_id"],
                theme_id=session_row.get("theme_id"),
                req_id=req_id,
            )
        else:
            step_result_json = build_step_result(
                {**session_row, "params_json": new_state},
                state=new_state,
                req_id=req_id,
            )
        finish_status = None
        final_id = step_log["final_id"]
        final_meta = step_log["final_meta"] or {}
        if final_id is None and new_state["step0"] >= new_state["n"] - 1:
            finish_status = "FINISHED"
        meta_json = {
            "turn_fingerprint": fingerprint,
            "source_message_id": source_message_id,
            "req_id": req_id,
        }
        return l3_turns.L3ApplyPayload(
            new_state=new_state,
            llm_json=llm_json,
            deltas_json=deltas_json,
            step_result_json=step_result_json,
            meta_json=meta_json,
            finish_status=finish_status,
            final_id=final_id,
            final_meta=final_meta,
        )

    base_meta_json = {
        "req_id": req_id,
        "source_message_id": source_message_id,
    }
    result = l3_turns.apply_l3_turn_atomic(
        tg_id=tg_id,
        sid8=sid8,
        expected_step=st2,
        step=st2,
        user_input=turn.get("text"),
        choice_id=turn.get("choice_id"),
        base_meta_json=base_meta_json,
        apply_fn=_apply_in_tx,
    )
    if not result:
        return None
    if result.outcome == "stale":
        return L3TurnResult(
            status="stale",
            step_view=None,
            session_id=int(result.session_row["id"]),
            step=int(result.session_row["step"]),
            theme_id=result.session_row.get("theme_id"),
            final_id=None,
        )
    if result.outcome == "invalid":
        return L3TurnResult(
            status="invalid",
            step_view=None,
            session_id=int(result.session_row["id"]),
            step=int(result.session_row["step"]),
            theme_id=result.session_row.get("theme_id"),
            final_id=None,
        )
    if result.outcome == "duplicate":
        step_result_json = None
        if result.event:
            stored_step_result = result.event.get("step_result_json")
            if isinstance(stored_step_result, dict):
                step_result_json = stored_step_result
        if step_result_json:
            step_view = step_result_to_view(
                step_result_json,
                sid8=result.session_row["sid8"],
                step=st2,
            )
        else:
            step_view = render_current_step(result.session_row)
        final_id = step_view.final_id
        return L3TurnResult(
            status="duplicate",
            step_view=step_view,
            session_id=int(result.session_row["id"]),
            step=int(result.session_row["step"]),
            theme_id=result.session_row.get("theme_id"),
            final_id=final_id,
        )
    payload = result.payload
    step_view = step_result_to_view(
        payload.step_result_json or {},
        sid8=result.session_row["sid8"],
        step=int(payload.new_state["step0"]),
    )
    return L3TurnResult(
        status="accepted",
        step_view=step_view,
        session_id=int(result.session_row["id"]),
        step=int(payload.new_state["step0"]),
        theme_id=result.session_row.get("theme_id"),
        final_id=payload.final_id or step_view.final_id,
    )
