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
        if mode == "schema_invalid":
            return self._build_schema_invalid(step_ctx)
        if mode == "type_mismatch":
            mismatched_type = "story_final" if expected_type == "story_step" else "story_step"
            return self._build_payload(mismatched_type, step_ctx)
        if mode == "ok_final":
            return self._build_payload("story_final", step_ctx)
        if mode.startswith("ok_step_"):
            count_str = mode.removeprefix("ok_step_")
            try:
                count = int(count_str)
            except ValueError:
                count = 3
            return self._build_step_payload(step_ctx, max(count, 0), expected_type=expected_type)
        if mode == "ok":
            if expected_type == "story_final":
                return self._build_payload("story_final", step_ctx)
            return self._build_step_payload(step_ctx, 3, expected_type=expected_type)
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
                "expected_type": expected_type,
            }
            return json.dumps(payload, ensure_ascii=False)

        return self._build_step_payload(step_ctx, 3, expected_type=expected_type)

    def _build_step_payload(
        self,
        step_ctx: Dict[str, Any],
        count: int,
        *,
        expected_type: str | None = None,
    ) -> str:
        step = step_ctx.get("step")
        total_steps = step_ctx.get("total_steps")
        header = "Новый шаг истории."
        if isinstance(step, int) and isinstance(total_steps, int):
            header = f"Шаг {step + 1}/{total_steps}."
        labels = [
            ("A", "A — Смелый путь"),
            ("B", "B — Осторожный путь"),
            ("C", "C — Необычный путь"),
        ]
        choices = [
            {"choice_id": choice_id, "label": label}
            for choice_id, label in labels[: max(0, min(count, 3))]
        ]
        payload = {
            "text": f"{header} Выберите действие героя:",
            "choices": choices,
            "memory": None,
            "expected_type": expected_type or step_ctx.get("expected_type"),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _build_schema_invalid(self, step_ctx: Dict[str, Any]) -> str:
        payload = {
            "text": "Неверный шаг.",
            "choices": [
                {"choice_id": "A", "label": "A — Раз"},
                {"choice_id": "B", "label": "B — Два"},
                {"choice_id": "C", "label": "C — Три"},
                {"choice_id": "D", "label": "D — Четыре"},
            ],
            "memory": None,
        }
        return json.dumps(payload, ensure_ascii=False)
