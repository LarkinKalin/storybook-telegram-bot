from __future__ import annotations

import json
from typing import Any, Dict, Tuple


def validate_response(raw_text: str, expected_type: str) -> Tuple[Dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(parsed, dict):
        return None, "invalid_json"

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
        return False, "schema_invalid"
    if "choices" not in parsed:
        return False, "type_mismatch"
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
        return False, "schema_invalid"
    if "choices" in parsed:
        choices = parsed.get("choices")
        if choices is None:
            return True, ""
        if not isinstance(choices, list):
            return False, "schema_invalid"
        return False, "type_mismatch"
    return True, ""
