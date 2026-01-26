from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from db.repos import sessions
from packages.engine.src.engine_v0_1 import init_state_v01
from src.keyboards.l3 import build_final_keyboard, build_l3_keyboard
from src.services.content_stub import build_content_step


@dataclass
class StepView:
    text: str
    keyboard: object
    final_id: Optional[str] = None


def build_final_step_result(final_id: str | None) -> Dict:
    if final_id:
        final_text = (
            f"Финал {final_id}.\n"
            "Спасибо за игру! Можно начать новую сказку."
        )
    else:
        final_text = "Сказка завершена. Можно начать новую."
    return {
        "text": final_text,
        "choices": [],
        "allow_free_text": False,
        "final_id": final_id,
    }


def ensure_engine_state(session_row: Dict) -> Dict:
    params = session_row.get("params_json") or {}
    if not isinstance(params, dict) or params.get("v") != "0.1":
        state = init_state_v01(session_row.get("max_steps", 8))
        sessions.update_params_json(session_row["id"], state)
        return state
    return params


def build_step_result(session_row: Dict, state: Dict | None = None) -> Dict:
    state = state or ensure_engine_state(session_row)
    if state["step0"] >= state["n"] - 1:
        return build_final_step_result(final_id=None)
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
    return {
        "text": "\n".join(text_lines),
        "choices": keyboard_choices,
        "allow_free_text": state["free_text_allowed_after"],
        "final_id": None,
    }


def step_result_to_view(step_result: Dict, sid8: str, step: int) -> StepView:
    text = step_result.get("text") or ""
    final_id = step_result.get("final_id")
    choices = step_result.get("choices") or []
    allow_free_text = bool(step_result.get("allow_free_text"))
    if final_id or not choices:
        keyboard = build_final_keyboard()
    else:
        keyboard = build_l3_keyboard(
            choices,
            allow_free_text=allow_free_text,
            sid8=sid8,
            step=step,
        )
    return StepView(text=text, keyboard=keyboard, final_id=final_id)


def render_current_step(session_row: Dict) -> StepView:
    state = ensure_engine_state(session_row)
    step_result = build_step_result(session_row, state=state)
    return step_result_to_view(step_result, sid8=session_row["sid8"], step=state["step0"])


def render_step(session_row: Dict, state: Dict | None = None) -> StepView:
    state = state or ensure_engine_state(session_row)
    step_result = build_step_result(session_row, state=state)
    return step_result_to_view(step_result, sid8=session_row["sid8"], step=state["step0"])
