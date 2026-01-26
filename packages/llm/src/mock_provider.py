from __future__ import annotations

import json
from typing import Any, Dict


class MockProvider:
    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self._once_used = False

    def _resolve_mode(self) -> str:
        if self.mode.endswith("_once"):
            base = self.mode.rsplit("_", 1)[0]
            if not self._once_used:
                self._once_used = True
                return base
            return "ok"
        if self.mode.endswith("_always"):
            return self.mode.rsplit("_", 1)[0]
        return self.mode

    def generate(self, step_ctx: Dict[str, Any]) -> str:
        mode = self._resolve_mode()
        expected_type = step_ctx.get("expected_type")

        if mode == "timeout":
            raise TimeoutError("mock timeout")
        if mode == "invalid_json":
            return "<<<not json>>>"
        if mode == "type_mismatch":
            mismatched_type = "story_final" if expected_type == "story_step" else "story_step"
            return self._build_payload(mismatched_type, step_ctx)
        return self._build_payload(expected_type, step_ctx)

    def _build_payload(self, expected_type: str | None, step_ctx: Dict[str, Any]) -> str:
        if expected_type == "story_final":
            text = "Финал истории. Спасибо за игру!"
            final_id = step_ctx.get("final_id")
            if final_id:
                text = f"Финал {final_id}. Спасибо за игру!"
            payload = {
                "text": text,
                "memory": None,
            }
            return json.dumps(payload, ensure_ascii=False)

        step = step_ctx.get("step")
        total_steps = step_ctx.get("total_steps")
        header = "Новый шаг истории."
        if isinstance(step, int) and isinstance(total_steps, int):
            header = f"Шаг {step + 1}/{total_steps}."
        payload = {
            "text": f"{header} Выберите действие героя:",
            "choices": [
                {"choice_id": "A", "label": "A — Смелый путь"},
                {"choice_id": "B", "label": "B — Осторожный путь"},
                {"choice_id": "C", "label": "C — Необычный путь"},
            ],
            "memory": None,
        }
        return json.dumps(payload, ensure_ascii=False)
