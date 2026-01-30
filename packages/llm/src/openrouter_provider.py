from __future__ import annotations

import json
import os
from pathlib import Path
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
        theme_id = step_ctx.get("theme_id")
        max_tokens = self._resolve_max_tokens(expected_type)
        timeout_s = self._resolve_timeout()
        theme_config = self._resolve_theme_config(theme_id)
        if not theme_config.system_prompt_step:
            theme_config = self._apply_default_prompt(theme_config)
        if theme_config.max_tokens_step is not None or theme_config.max_tokens_final is not None:
            max_tokens = self._resolve_theme_max_tokens(expected_type, theme_config, max_tokens)
        temperature = self._resolve_temperature(expected_type)
        if theme_config.temperature_step is not None or theme_config.temperature_final is not None:
            temperature = self._resolve_theme_temperature(expected_type, theme_config, temperature)
        messages = self._resolve_messages(step_ctx, theme_config)
        response_format = self._build_response_format(expected_type)
        reasoning = self._resolve_reasoning()

        payload = {
            "model": self._resolve_model(expected_type),
            "messages": messages,
            "response_format": response_format,
            "temperature": temperature,
        }
        if reasoning is not None:
            payload["reasoning"] = reasoning
        plugins = self._resolve_plugins()
        if plugins:
            payload["plugins"] = plugins
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        self.last_request_payload = payload
        self.last_request_messages = messages

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

        response_payload = response.json()
        self.last_response_payload = response_payload
        self.last_usage = response_payload.get("usage")
        self.last_finish_reason = (
            response_payload.get("choices", [{}])[0].get("finish_reason")
        )
        self.last_native_finish_reason = (
            response_payload.get("choices", [{}])[0].get("native_finish_reason")
        )
        content = (
            response_payload.get("choices", [{}])[0]
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

    def _resolve_messages(
        self, step_ctx: Dict[str, Any], theme_config: "_ThemeConfig"
    ) -> List[Dict[str, str]]:
        messages = step_ctx.get("messages")
        if isinstance(messages, list) and messages:
            return messages

        story_request = step_ctx.get("story_request")
        if isinstance(story_request, dict):
            user_content: str = json.dumps(story_request, ensure_ascii=False)
        else:
            user_content = "" if story_request is None else str(story_request)
        system_prompt = self._resolve_system_prompt(
            step_ctx.get("expected_type"),
            theme_config=theme_config,
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

    def _resolve_temperature(self, expected_type: Any) -> float:
        if expected_type == "story_final":
            raw = os.getenv("OPENROUTER_TEMPERATURE_FINAL", "").strip()
        else:
            raw = os.getenv("OPENROUTER_TEMPERATURE_STEP", "").strip()
        if not raw:
            raw = os.getenv("OPENROUTER_TEMPERATURE", "").strip()
        if not raw:
            raw = "0.5" if expected_type == "story_final" else "0.6"
        try:
            return float(raw)
        except ValueError:
            return 0.5

    def _resolve_system_prompt(
        self,
        expected_type: Any,
        *,
        theme_config: "_ThemeConfig",
    ) -> str:
        if expected_type == "story_final" and theme_config.system_prompt_final:
            return theme_config.system_prompt_final
        if expected_type != "story_final" and theme_config.system_prompt_step:
            return theme_config.system_prompt_step
        if expected_type == "story_final":
            override = os.getenv("OPENROUTER_SYSTEM_PROMPT_FINAL", "").strip()
            if override:
                return override
            return (
                "Ты пишешь финал детской сказки. Отвечай только одним JSON-объектом без markdown и "
                "без текста вне JSON. Вход: один JSON (story_request). Выход строго: "
                "{\"text\":\"...\"}. Текст на русском, 3–7 предложений или 500–900 символов. "
                "Уровень фантазирования: средний. Можно добавлять атмосферные детали, но не ломай факты "
                "из scene_text. Правила движка: история связная, выборы влияют на состояние, "
                "но числа и параметры игроку не показывай."
            )
        override = os.getenv("OPENROUTER_SYSTEM_PROMPT_STEP", "").strip()
        if override:
            return override
        return (
            "Ты пишешь следующий шаг детской сказки. Отвечай только одним JSON-объектом без markdown и "
            "без текста вне JSON. Вход: один JSON (story_request). Выход строго: "
            "{\"text\":\"...\",\"recap_short\":\"...\",\"choices\":[{\"choice_id\":\"A\",\"label\":\"...\"}]}. "
            "Текст на русском, 600–1200 символов. recap_short: 1–2 предложения, 120–240 символов, "
            "только факты текущего шага без новых сущностей. Уровень фантазирования: средний. "
            "Сохраняй choice_id строго как во входе (A/B/C), а label придумывай сам как действия "
            "персонажа (без слов «смелость/доброта/мудрость»). Избегай одинаковых штампов на каждом шаге, "
            "делай вариативные формулировки. Правила движка: в каждом шаге есть выбор A/B/C, "
            "выбор влияет на состояние по правилам движка, числа не раскрывай игроку."
        )

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
                    "recap_short": {"type": "string"},
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
                "required": ["text", "recap_short", "choices"],
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

    def _resolve_theme_max_tokens(
        self,
        expected_type: Any,
        theme_config: "_ThemeConfig",
        fallback: int | None,
    ) -> int | None:
        if expected_type == "story_final" and theme_config.max_tokens_final is not None:
            return theme_config.max_tokens_final
        if expected_type != "story_final" and theme_config.max_tokens_step is not None:
            return theme_config.max_tokens_step
        return fallback

    def _resolve_theme_temperature(
        self,
        expected_type: Any,
        theme_config: "_ThemeConfig",
        fallback: float,
    ) -> float:
        if expected_type == "story_final" and theme_config.temperature_final is not None:
            return theme_config.temperature_final
        if expected_type != "story_final" and theme_config.temperature_step is not None:
            return theme_config.temperature_step
        return fallback

    def _resolve_theme_config(self, theme_id: Any) -> "_ThemeConfig":
        if not isinstance(theme_id, str) or not theme_id:
            return _ThemeConfig()
        base_dir = Path(os.getenv("LLM_PROMPT_DIR", "content/prompts"))
        json_path = base_dir / f"{theme_id}.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except OSError:
                return _ThemeConfig()
            return _ThemeConfig.from_payload(data)
        txt_path = base_dir / f"{theme_id}.txt"
        if txt_path.exists():
            try:
                text = txt_path.read_text(encoding="utf-8").strip()
            except OSError:
                return _ThemeConfig()
            if text:
                return _ThemeConfig(system_prompt_step=text, system_prompt_final=text)
        return _ThemeConfig()

    def _apply_default_prompt(self, theme_config: "_ThemeConfig") -> "_ThemeConfig":
        base_dir = Path(os.getenv("LLM_PROMPT_DIR", "content/prompts"))
        default_path = base_dir / "default.txt"
        if not default_path.exists():
            return theme_config
        try:
            text = default_path.read_text(encoding="utf-8").strip()
        except OSError:
            return theme_config
        if not text:
            return theme_config
        return _ThemeConfig(
            system_prompt_step=text,
            system_prompt_final=theme_config.system_prompt_final or text,
            temperature_step=theme_config.temperature_step,
            temperature_final=theme_config.temperature_final,
            max_tokens_step=theme_config.max_tokens_step,
            max_tokens_final=theme_config.max_tokens_final,
        )


class _ThemeConfig:
    def __init__(
        self,
        *,
        system_prompt_step: str | None = None,
        system_prompt_final: str | None = None,
        temperature_step: float | None = None,
        temperature_final: float | None = None,
        max_tokens_step: int | None = None,
        max_tokens_final: int | None = None,
    ) -> None:
        self.system_prompt_step = system_prompt_step
        self.system_prompt_final = system_prompt_final
        self.temperature_step = temperature_step
        self.temperature_final = temperature_final
        self.max_tokens_step = max_tokens_step
        self.max_tokens_final = max_tokens_final

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "_ThemeConfig":
        return cls(
            system_prompt_step=_as_str(payload.get("system_prompt_step")),
            system_prompt_final=_as_str(payload.get("system_prompt_final")),
            temperature_step=_as_float(payload.get("temperature_step")),
            temperature_final=_as_float(payload.get("temperature_final")),
            max_tokens_step=_as_int(payload.get("max_tokens_step")),
            max_tokens_final=_as_int(payload.get("max_tokens_final")),
        )


def _as_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
