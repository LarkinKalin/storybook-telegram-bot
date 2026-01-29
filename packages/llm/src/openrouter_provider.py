from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import requests


class MissingOpenRouterKeyError(ValueError):
    pass


class OpenRouterProvider:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise MissingOpenRouterKeyError("OpenRouter API key is required")
        self._api_key = api_key
        self._endpoint = "https://openrouter.ai/api/v1/chat/completions"
        self._model = os.getenv("OPENROUTER_MODEL_TEXT", "moonshotai/kimi-k2.5").strip()
        self._model_final = os.getenv("OPENROUTER_MODEL_FINAL", "").strip()

    @classmethod
    def from_env(cls) -> "OpenRouterProvider":
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
        return cls(api_key)

    def generate(self, step_ctx: Dict[str, Any]) -> str:
        expected_type = step_ctx.get("expected_type")
        max_tokens = self._resolve_max_tokens(expected_type)
        timeout_s = self._resolve_timeout()
        messages = self._resolve_messages(step_ctx)
        response_format = self._build_response_format(expected_type)
        reasoning = self._resolve_reasoning()

        payload = {
            "model": self._resolve_model(expected_type),
            "messages": messages,
            "response_format": response_format,
            "temperature": 0.2,
        }
        if reasoning is not None:
            payload["reasoning"] = reasoning
        plugins = self._resolve_plugins()
        if plugins:
            payload["plugins"] = plugins
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
        self.last_usage = payload.get("usage")
        self.last_finish_reason = (
            payload.get("choices", [{}])[0].get("finish_reason")
        )
        self.last_native_finish_reason = (
            payload.get("choices", [{}])[0].get("native_finish_reason")
        )
        content = (
            payload.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )
        if isinstance(content, dict):
            return json.dumps(content, ensure_ascii=False)
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                return content
            return json.dumps(parsed, ensure_ascii=False)
        raise ValueError("openrouter response missing content")

    def _resolve_messages(self, step_ctx: Dict[str, Any]) -> List[Dict[str, str]]:
        messages = step_ctx.get("messages")
        if isinstance(messages, list) and messages:
            return messages

        story_request = step_ctx.get("story_request")
        if isinstance(story_request, dict):
            user_content: str = json.dumps(story_request, ensure_ascii=False)
        else:
            user_content = "" if story_request is None else str(story_request)
        system_prompt = "Верни только JSON. Без markdown. Без пояснений."
        if step_ctx.get("expected_type") == "story_final":
            system_prompt = (
                "Верни только JSON. Без markdown. Без пояснений. "
                "Финал должен быть кратким (1-3 предложения)."
            )
        return [
            {
                "role": "system",
                "content": system_prompt,
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
            raw = os.getenv("OPENROUTER_MAX_TOKENS_OUTPUT", "").strip()
        if not raw and expected_type == "story_final":
            raw = "3500"
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

    def _resolve_model(self, expected_type: Any) -> str:
        if expected_type == "story_final" and self._model_final:
            return self._model_final
        return self._model

    def _build_response_format(self, expected_type: Any) -> Dict[str, Any]:
        format_mode = os.getenv("OPENROUTER_RESPONSE_FORMAT", "json_object").strip().lower()
        if format_mode != "json_schema":
            return {"type": "json_object"}
        if expected_type == "story_step":
            schema = {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "properties": {
                                "choice_id": {"type": "string"},
                                "label": {"type": "string"},
                            },
                            "required": ["choice_id", "label"],
                            "additionalProperties": False,
                        },
                    },
                    "memory": {"type": ["object", "null"]},
                },
                "required": ["text", "choices"],
                "additionalProperties": False,
            }
            name = "story_step"
        else:
            schema = {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "image_prompt": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "maxItems": 0,
                        "items": {"type": "object"},
                    },
                    "memory": {"type": ["object", "null"]},
                },
                "required": ["text"],
                "additionalProperties": False,
            }
            name = "story_final"
        return {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "schema": schema,
                "strict": True,
            },
        }

    def _resolve_reasoning(self) -> Dict[str, Any] | None:
        mode = os.getenv("OPENROUTER_REASONING", "off").strip().lower()
        if not mode or mode == "off":
            return {"enabled": False}
        if mode in {"low", "medium", "high"}:
            return {"enabled": True, "effort": mode}
        return {"enabled": True}

    def _resolve_plugins(self) -> List[Dict[str, str]]:
        if os.getenv("OPENROUTER_RESPONSE_HEALING", "").strip() != "1":
            return []
        return [{"id": "response-healing"}]
