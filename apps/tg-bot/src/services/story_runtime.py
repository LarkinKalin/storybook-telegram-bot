from __future__ import annotations

from dataclasses import dataclass
import logging
from uuid import uuid4
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
    image_prompt: Optional[str] = None


def build_final_step_result(
    final_id: str | None,
    *,
    theme_id: str | None = None,
    req_id: str | None = None,
    child_name: str | None = None,
) -> Dict:
    raw = (child_name or "").strip()
    child_name_for_story = raw if raw else "дружок"
    logger.info(
        "llm.story_request child_name_present=%s child_name_len=%s",
        "true" if bool(raw) else "false",
        len(raw),
    )
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
        "child_profile": {"name": child_name_for_story},
        "story_request": {
            "expected_type": "story_final",
            "final_id": final_id,
            "theme_id": theme_id,
            "child_profile": {"name": child_name_for_story},
            "format": "Верни JSON формата {text}.",
        },
    }
    llm_result = llm_generate(step_ctx)
    if llm_result.parsed_json:
        llm_text = llm_result.parsed_json.get("text")
        if isinstance(llm_text, str) and llm_text.strip():
            final_text = llm_text
    resolved_child_name = (child_name or "").strip()
    child_name_for_story = resolved_child_name if resolved_child_name else "дружок"
    logger.info(
        "llm.story_request child_name_present=%s child_name_len=%s",
        "true" if bool(resolved_child_name) else "false",
        len(resolved_child_name),
    )
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
    req_id = _ensure_req_id(req_id)
    if state["step0"] >= state["n"] - 1:
        return build_final_step_result(
            final_id=None,
            theme_id=session_row.get("theme_id"),
            req_id=req_id,
            child_name=session_row.get("child_name"),
        )
    content = build_content_step(session_row["theme_id"], state["step0"], state)
    facts_json = session_row.get("facts_json") or {}
    recaps = facts_json.get("recaps") if isinstance(facts_json, dict) else None
    if not isinstance(recaps, list):
        recaps = []
    recaps = recaps[-5:]
    last_choice = facts_json.get("last_choice") if isinstance(facts_json, dict) else None
    choices = content["choices"]
    text_lines = [
        f"Шаг {state['step0'] + 1}/{state['n']}.",
        content["scene_text"],
    ]
    keyboard_choices = [
        {"choice_id": choice["choice_id"], "label": choice["choice_id"]} for choice in choices
    ]
    step_result = {
        "text": "\n".join(text_lines),
        "choices": keyboard_choices,
        "allow_free_text": state["free_text_allowed_after"],
        "final_id": None,
        "recap_short": _fallback_recap(content["scene_text"]),
        "choices_source": "stub",
        "image_prompt": None,
    }
    story_request = build_story_request(
        theme_id=session_row.get("theme_id"),
        state=state,
        content=content,
        recaps=recaps,
        last_choice=last_choice,
        child_name=session_row.get("child_name"),
    )
    step_ctx = {
        "expected_type": expected_type_for_step(state["step0"], state["n"]),
        "req_id": req_id,
        "theme_id": session_row.get("theme_id"),
        "step": state.get("step0"),
        "total_steps": state.get("n"),
        "allow_free_text": state.get("free_text_allowed_after"),
        "engine_input": state,
        "engine_output": facts_json.get("last_engine_output") if isinstance(facts_json, dict) else None,
        "last_choice": last_choice,
        "recaps_count": len(recaps),
        "story_request": story_request,
    }
    llm_result = llm_generate(step_ctx)
    if llm_result.parsed_json:
        llm_text = llm_result.parsed_json.get("text")
        if isinstance(llm_text, str) and llm_text.strip():
            step_result["text"] = llm_text
        recap_short = llm_result.parsed_json.get("recap_short")
        if isinstance(recap_short, str) and recap_short.strip():
            step_result["recap_short"] = recap_short.strip()
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
        image_prompt = llm_result.parsed_json.get("image_prompt")
        if isinstance(image_prompt, str) and image_prompt.strip():
            step_result["image_prompt"] = image_prompt.strip()
    else:
        fallback_choices = keyboard_choices[:2] if len(keyboard_choices) >= 2 else []
        step_result["choices"] = fallback_choices
        step_result["choices_source"] = "fallback"
    return step_result


def render_choices_block(choices: list[dict]) -> str:
    if not choices:
        return ""
    order = {"A": 0, "B": 1, "C": 2}

    def _sort_key(choice: dict) -> tuple[int, str]:
        choice_id = choice.get("choice_id")
        if isinstance(choice_id, str):
            return (order.get(choice_id.upper(), 99), choice_id)
        return (99, "")

    lines = ["Варианты:"]
    for choice in sorted(choices, key=_sort_key):
        choice_id = choice.get("choice_id")
        label = choice.get("label")
        if isinstance(choice_id, str) and isinstance(label, str):
            lines.append(f"{choice_id}) {label}")
    if len(lines) == 1:
        return ""
    lines.append("")
    lines.append("(Можно выбрать A/B/C кнопками или написать свой вариант.)")
    return "\n".join(lines)


def _fallback_recap(scene_text: str) -> str:
    recap = scene_text.strip().replace("\n", " ")
    if len(recap) > 220:
        recap = recap[:220].rstrip()
    return recap


def _ensure_req_id(req_id: str | None) -> str:
    if req_id:
        return req_id
    return uuid4().hex


def build_story_request(
    *,
    theme_id: str | None,
    state: Dict,
    content: Dict,
    recaps: list,
    last_choice: object,
    child_name: str | None = None,
) -> Dict:
    resolved_child_name = (child_name or "").strip()
    child_name_for_story = resolved_child_name if resolved_child_name else "дружок"
    logger.info(
        "llm.story_request child_name_present=%s child_name_len=%s",
        "true" if bool(resolved_child_name) else "false",
        len(resolved_child_name),
    )
    return {
        "expected_type": expected_type_for_step(state["step0"], state["n"]),
        "scene_text": content["scene_text"],
        "choices": [
            {"choice_id": choice["choice_id"], "label": choice["choice_id"]}
            for choice in content["choices"]
        ],
        "allow_free_text": state.get("free_text_allowed_after"),
        "step": state.get("step0"),
        "total_steps": state.get("n"),
        "theme_id": theme_id,
        "child_profile": {"name": child_name_for_story},
        "recaps": recaps,
        "last_choice": last_choice,
        "state": {
            "traits": state.get("traits"),
            "noise_streak": state.get("noise_streak"),
            "free_text_allowed_after": state.get("free_text_allowed_after"),
            "milestone_votes": state.get("milestone_votes"),
        },
        "format": "Верни JSON формата {text, recap_short, choices[], image_prompt?}.",
    }


def step_result_to_view(step_result: Dict, sid8: str, step: int) -> StepView:
    text = step_result.get("text") or ""
    final_id = step_result.get("final_id")
    image_prompt = step_result.get("image_prompt")
    choices = step_result.get("choices") or []
    allow_free_text = bool(step_result.get("allow_free_text"))
    choices_source = step_result.get("choices_source") or "unknown"
    if choices and not final_id:
        choices_block = render_choices_block(choices)
        if choices_block:
            text = f"{text}\n\n{choices_block}"
    if choices:
        preview_labels = []
        for choice in choices:
            choice_id = choice.get("choice_id")
            label = choice.get("label")
            if isinstance(choice_id, str) and isinstance(label, str):
                preview_labels.append(f"{choice_id}:{label[:60]}")
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
    return StepView(
        text=text,
        keyboard=keyboard,
        final_id=final_id,
        image_prompt=image_prompt if isinstance(image_prompt, str) else None,
    )


def render_current_step(session_row: Dict, req_id: str | None = None) -> StepView:
    state = ensure_engine_state(session_row)
    step_result = build_step_result(session_row, state=state, req_id=req_id)
    return step_result_to_view(step_result, sid8=session_row["sid8"], step=state["step0"])


def render_step(session_row: Dict, state: Dict | None = None, *, req_id: str | None = None) -> StepView:
    state = state or ensure_engine_state(session_row)
    step_result = build_step_result(session_row, state=state, req_id=req_id)
    return step_result_to_view(step_result, sid8=session_row["sid8"], step=state["step0"])
