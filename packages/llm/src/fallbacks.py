from __future__ import annotations

from typing import Any, Dict


def build_fallback(expected_type: str) -> Dict[str, Any]:
    if expected_type == "story_final":
        return {
            "text": "История временно недоступна. Спасибо, что были с нами!",
            "memory": None,
        }
    return {
        "text": "Сцена временно недоступна. Выберите действие ниже.",
        "choices": [
            {"choice_id": "A", "label": "A — Продолжить"},
            {"choice_id": "B", "label": "B — Попробовать снова"},
            {"choice_id": "C", "label": "C — Завершить"},
        ],
        "memory": None,
    }
