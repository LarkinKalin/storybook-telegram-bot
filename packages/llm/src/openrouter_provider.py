from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import requests


class OpenRouterProvider:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key is required")
        self._api_key = api_key
        self._endpoint = "https://openrouter.ai/api/v1/chat/completions"
        self._model = os.getenv("OPENROUTER_MODEL_TEXT", "moonshotai/kimi-k2.5").strip()

    def generate(self, step_ctx: Dict[str, Any]) -> str:
        expected_type = step_ctx.get("expected_type")
        max_tokens = self._resolve_max_tokens(expected_type)
        timeout_s = self._resolve_timeout()
        messages = self._resolve_messages(step_ctx)

        payload = {
            "model": self._model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        http_referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
        if http_referer:
            headers["HTTP-Referer"] = http_referer
        app_title = os.getenv("OPENROUTER_APP_TITLE", "").strip()
        if app_title:
            headers["X-Title"] = app_title

        try:
            response = requests.post(
                self._endpoint,
                headers=headers,
                json=payload,
                timeout=timeout_s,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise TimeoutError("openrouter timeout") from exc
        except requests.exceptions.HTTPError:
            raise

        payload = response.json()
        content = (
            payload.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )
        if not isinstance(content, str):
            raise ValueError("openrouter response missing content")
        return content

    def _resolve_messages(self, step_ctx: Dict[str, Any]) -> List[Dict[str, str]]:
        messages = step_ctx.get("messages")
        if isinstance(messages, list) and messages:
            return messages

        story_request = step_ctx.get("story_request")
        if isinstance(story_request, dict):
            user_content: str = json.dumps(story_request, ensure_ascii=False)
        else:
            user_content = "" if story_request is None else str(story_request)
        return [
            {
                "role": "system",
                "content": "Верни только JSON. Без markdown. Без пояснений.",
            },
            {"role": "user", "content": user_content},
        ]

    def _resolve_max_tokens(self, expected_type: Any) -> int | None:
        if expected_type == "story_step":
            raw = os.getenv("OPENROUTER_MAX_TOKENS_STEP", "")
        else:
            raw = os.getenv("OPENROUTER_MAX_TOKENS_FINAL", "")
        raw = raw.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _resolve_timeout(self) -> float:
        raw = os.getenv("OPENROUTER_TIMEOUT_S", "30").strip()
        if not raw:
            return 30.0
        try:
            return float(raw)
        except ValueError:
            return 30.0
