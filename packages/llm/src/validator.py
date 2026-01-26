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
        if not _validate_story_step(parsed):
            return None, "type_mismatch"
        return parsed, None
    if expected_type == "story_final":
        if not _validate_story_final(parsed):
            return None, "type_mismatch"
        return parsed, None
    return None, "type_mismatch"


def _validate_story_step(parsed: Dict[str, Any]) -> bool:
    text = parsed.get("text")
    if not isinstance(text, str) or not text.strip():
        return False
    choices = parsed.get("choices")
    if not isinstance(choices, list) or len(choices) < 3:
        return False
    choice_ids = []
    for choice in choices[:3]:
        if not isinstance(choice, dict):
            return False
        choice_id = choice.get("choice_id")
        label = choice.get("label") or choice.get("text")
        if not isinstance(choice_id, str) or not isinstance(label, str):
            return False
        choice_ids.append(choice_id)
    return set(choice_ids) >= {"A", "B", "C"}


def _validate_story_final(parsed: Dict[str, Any]) -> bool:
    text = parsed.get("text")
    return isinstance(text, str) and bool(text.strip())
