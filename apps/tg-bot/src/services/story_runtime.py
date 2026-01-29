from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Dict, Optional

from db.repos import sessions
from packages.engine.src.engine_v0_1 import init_state_v01
from packages.llm.src import generate as llm_generate
from src.keyboards.l3 import build_final_keyboard, build_l3_keyboard
from src.services.content_stub import build_content_step

logger = logging.getLogger(__name__)


@dataclass
class StepView:
    text: str
    keyboard: object
    final_id: Optional[str] = None


def build_final_step_result(
    final_id: str | None,
    *,
    theme_id: str | None = None,
    req_id: str | None = None,
) -> Dict:
    if final_id:
        final_text = (
            f"Финал {final_id}.\n"
            "Спасибо за игру! Можно начать новую сказку."
        )
    else:
        final_text = "Сказка завершена. Можно начать новую."
    step_ctx = {
        "expected_type": "story_final",
        "req_id": req_id,
        "final_id": final_id,
        "theme_id": theme_id,
        "story_request": {
            "expected_type": "story_final",
            "final_id": final_id,
            "theme_id": theme_id,
            "format": "Верни JSON формата {text}.",
        },
    }
    llm_result = llm_generate(step_ctx)
    if llm_result.parsed_json:
        llm_text = llm_result.parsed_json.get("text")
        if isinstance(llm_text, str) and llm_text.strip():
            final_text = llm_text
    return {
        "text": final_text,
        "choices": [],
        "allow_free_text": False,
        "final_id": final_id,
    }


def expected_type_for_step(step0: int, total_steps: int) -> str:
    if step0 >= total_steps - 1:
        return "story_final"
    return "story_step"


def ensure_engine_state(session_row: Dict) -> Dict:
    params = session_row.get("params_json") or {}
    if not isinstance(params, dict) or params.get("v") != "0.1":
        state = init_state_v01(session_row.get("max_steps", 8))
        sessions.update_params_json(session_row["id"], state)
        return state
    return params


def build_step_result(
    session_row: Dict,
    state: Dict | None = None,
    *,
    req_id: str | None = None,
) -> Dict:
    state = state or ensure_engine_state(session_row)
    if state["step0"] >= state["n"] - 1:
        return build_final_step_result(
            final_id=None,
            theme_id=session_row.get("theme_id"),
            req_id=req_id,
        )
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
    step_result = {
        "text": "\n".join(text_lines),
        "choices": keyboard_choices,
        "allow_free_text": state["free_text_allowed_after"],
        "final_id": None,
        "choices_source": "stub",
    }
    step_ctx = {
        "expected_type": expected_type_for_step(state["step0"], state["n"]),
        "req_id": req_id,
        "theme_id": session_row.get("theme_id"),
        "step": state.get("step0"),
        "total_steps": state.get("n"),
        "allow_free_text": state.get("free_text_allowed_after"),
        "story_request": {
            "expected_type": expected_type_for_step(state["step0"], state["n"]),
            "scene_text": content["scene_text"],
            "choices": [
                {"choice_id": choice["choice_id"], "label": choice["label"]}
                for choice in choices
            ],
            "allow_free_text": state.get("free_text_allowed_after"),
            "step": state.get("step0"),
            "total_steps": state.get("n"),
            "theme_id": session_row.get("theme_id"),
            "format": "Верни JSON формата {text, choices[]}.",
        },
    }
    llm_result = llm_generate(step_ctx)
    if llm_result.parsed_json:
        llm_text = llm_result.parsed_json.get("text")
        if isinstance(llm_text, str) and llm_text.strip():
            step_result["text"] = llm_text
        llm_choices = []
        parsed_choices = llm_result.parsed_json.get("choices", [])
        if isinstance(parsed_choices, list):
            for choice in parsed_choices:
                if not isinstance(choice, dict):
                    continue
                choice_id = choice.get("choice_id") or choice.get("id")
                label = choice.get("label") or choice.get("text")
                if isinstance(choice_id, str) and isinstance(label, str):
                    llm_choices.append({"choice_id": choice_id, "label": label})
        if llm_choices:
            step_result["choices"] = llm_choices
            step_result["choices_source"] = "llm"
        else:
            fallback_choices = keyboard_choices[:2] if len(keyboard_choices) >= 2 else []
            step_result["choices"] = fallback_choices
            step_result["choices_source"] = "fallback"
    else:
        fallback_choices = keyboard_choices[:2] if len(keyboard_choices) >= 2 else []
        step_result["choices"] = fallback_choices
        step_result["choices_source"] = "fallback"
    return step_result


def step_result_to_view(step_result: Dict, sid8: str, step: int) -> StepView:
    text = step_result.get("text") or ""
    final_id = step_result.get("final_id")
    choices = step_result.get("choices") or []
    allow_free_text = bool(step_result.get("allow_free_text"))
    choices_source = step_result.get("choices_source") or "unknown"
    if choices:
        preview_labels = []
        for choice in choices:
            label = choice.get("label")
            if isinstance(label, str):
                preview_labels.append(label[:60])
        logger.info(
            "tg.step_send step_ui=%s choices_len=%s choices_source=%s labels=%s",
            step + 1,
            len(choices),
            choices_source,
            preview_labels,
        )
    else:
        logger.info(
            "tg.step_send step_ui=%s choices_len=0 choices_source=%s",
            step + 1,
            choices_source,
        )
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
