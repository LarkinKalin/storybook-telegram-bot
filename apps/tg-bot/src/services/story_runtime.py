from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Optional

from db.repos import session_events, sessions
from packages.engine.src.engine_v0_1 import apply_turn, init_state_v01
from src.keyboards.l3 import build_l3_keyboard
from src.services.content_stub import build_content_step


@dataclass
class StepView:
    text: str
    keyboard: object
    final_id: Optional[str] = None


def _fingerprint(
    session_id: int,
    step0: int,
    kind: str,
    payload: str,
    source_message_id: int,
) -> str:
    raw = f"{session_id}:{step0}:{kind}:{payload}:{source_message_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ensure_engine_state(session_row: Dict) -> Dict:
    params = session_row.get("params_json") or {}
    if not isinstance(params, dict) or params.get("v") != "0.1":
        state = init_state_v01(session_row.get("max_steps", 8))
        sessions.update_params_json(session_row["id"], state)
        return state
    return params


def render_step(session_row: Dict) -> StepView:
    state = _ensure_engine_state(session_row)
    content = build_content_step(session_row["theme_id"], state["step0"], state)
    choices = content["choices"]
    text_lines = [
        f"Шаг {state['step0'] + 1}/{state['n']}.",
        content["scene_text"],
        "",
        "Выбор:",
        "\n".join(f"{choice['label']}" for choice in choices),
    ]
    keyboard_choices = [
        {"choice_id": choice["choice_id"], "label": choice["label"]} for choice in choices
    ]
    keyboard = build_l3_keyboard(
        keyboard_choices, allow_free_text=state["free_text_allowed_after"]
    )
    return StepView(text="\n".join(text_lines), keyboard=keyboard)


def advance_turn(
    session_row: Dict,
    turn: Dict,
    source_message_id: int,
) -> Optional[StepView]:
    state = _ensure_engine_state(session_row)
    content = build_content_step(session_row["theme_id"], state["step0"], state)
    turn_kind = turn.get("kind", "")
    payload = turn.get("choice_id") or turn.get("text") or ""
    fingerprint = _fingerprint(
        session_row["id"], state["step0"], turn_kind, payload, source_message_id
    )
    if session_events.exists_for_step(session_row["id"], state["step0"]):
        return None
    if session_events.exists_for_fingerprint(session_row["id"], fingerprint):
        return None

    new_state, step_log = apply_turn(state, turn, content)
    llm_json = {
        "engine_step_log": step_log,
        "turn_fingerprint": fingerprint,
        "turn": turn,
    }
    deltas_json = {"applied_deltas": step_log["applied_deltas"]}
    session_events.append_event(
        session_row["id"],
        step=state["step0"],
        user_input=turn.get("text"),
        choice_id=turn.get("choice_id"),
        llm_json=llm_json,
        deltas_json=deltas_json,
    )
    sessions.update_params_json(session_row["id"], new_state)
    sessions.update_step(session_row["id"], new_state["step0"])

    if step_log["final_id"]:
        sessions.finish_with_final(
            session_row["id"], step_log["final_id"], step_log["final_meta"] or {}
        )
        final_text = (
            f"Финал {step_log['final_id']}.\n"
            f"Спасибо за игру! Можно начать новую сказку."
        )
        final_keyboard = build_l3_keyboard([], allow_free_text=False)
        return StepView(text=final_text, keyboard=final_keyboard, final_id=step_log["final_id"])

    return render_step({**session_row, "params_json": new_state})
