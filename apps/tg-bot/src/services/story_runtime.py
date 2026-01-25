from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from db.repos import sessions
from packages.engine.src.engine_v0_1 import init_state_v01
from src.keyboards.l3 import build_l3_keyboard
from src.services.content_stub import build_content_step


@dataclass
class StepView:
    text: str
    keyboard: object
    final_id: Optional[str] = None


def ensure_engine_state(session_row: Dict) -> Dict:
    params = session_row.get("params_json") or {}
    if not isinstance(params, dict) or params.get("v") != "0.1":
        state = init_state_v01(session_row.get("max_steps", 8))
        sessions.update_params_json(session_row["id"], state)
        return state
    return params


def render_step(session_row: Dict, state: Dict | None = None) -> StepView:
    state = state or ensure_engine_state(session_row)
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
        keyboard_choices,
        allow_free_text=state["free_text_allowed_after"],
        sid8=session_row["sid8"],
        step=state["step0"],
    )
    return StepView(text="\n".join(text_lines), keyboard=keyboard)
