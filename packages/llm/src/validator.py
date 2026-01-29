from __future__ import annotations

import json
from typing import Any, Dict, Tuple


def validate_response(raw_text: str, expected_type: str) -> Tuple[Dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        if _looks_truncated(raw_text):
            return None, "truncated_output"
        if _looks_like_json(raw_text):
            return None, "json_parse_error"
        return None, "invalid_json"
    if not isinstance(parsed, dict):
        return None, "json_parse_error"

    type_hint = parsed.get("expected_type") or parsed.get("type")
    if isinstance(type_hint, str) and type_hint != expected_type:
        return None, "type_mismatch"

    if expected_type == "story_step":
        ok, reason = _validate_story_step(parsed)
        if not ok:
            return None, reason
        return parsed, None
    if expected_type == "story_final":
        ok, reason = _validate_story_final(parsed)
        if not ok:
            return None, reason
        return parsed, None
    return None, "type_mismatch"


def _validate_story_step(parsed: Dict[str, Any]) -> Tuple[bool, str]:
    text = parsed.get("text")
    if not isinstance(text, str) or not text.strip():
        return False, "missing_required_fields"
    if "choices" not in parsed:
        return False, "missing_required_fields"
    choices = parsed.get("choices")
    if not isinstance(choices, list):
        return False, "schema_invalid"
    if len(choices) > 3:
        return False, "schema_invalid"
    for choice in choices:
        if not isinstance(choice, dict):
            return False, "schema_invalid"
        choice_id = choice.get("choice_id")
        label = choice.get("label") or choice.get("text")
        if not isinstance(choice_id, str) or not isinstance(label, str):
            return False, "schema_invalid"
    return True, ""


def _validate_story_final(parsed: Dict[str, Any]) -> Tuple[bool, str]:
    text = parsed.get("text")
    if not isinstance(text, str) or not text.strip():
        return False, "missing_required_fields"
    image_prompt = parsed.get("image_prompt")
    if image_prompt is not None and not isinstance(image_prompt, str):
        return False, "schema_invalid"
    if "choices" in parsed:
        choices = parsed.get("choices")
        if choices is None:
            return True, ""
        if not isinstance(choices, list):
            return False, "schema_invalid"
        if len(choices) == 0:
            return True, ""
        return False, "schema_invalid"
    return True, ""


def _looks_truncated(raw_text: str) -> bool:
    stripped = raw_text.strip()
    if not stripped:
        return False
    if stripped[0] not in {"{", "["}:
        return False
    if len(stripped) < 20:
        return False
    if ":" not in stripped and "\"" not in stripped:
        return False
    in_string = False
    escape = False
    brace_balance = 0
    bracket_balance = 0
    for char in stripped:
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == "\"":
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            brace_balance += 1
        elif char == "}":
            brace_balance -= 1
        elif char == "[":
            bracket_balance += 1
        elif char == "]":
            bracket_balance -= 1
    if in_string:
        return True
    return brace_balance > 0 or bracket_balance > 0


def _looks_like_json(raw_text: str) -> bool:
    stripped = raw_text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")
