from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error as url_error

import requests

from packages.llm.src.fallbacks import build_fallback
from packages.llm.src.mock_provider import MockProvider
from packages.llm.src.openrouter_provider import OpenRouterProvider
from packages.llm.src.validator import validate_response

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    expected_type: str
    raw_text: str
    parsed_json: Optional[Dict[str, Any]]
    usage: Optional[Dict[str, Any]]
    used_fallback: bool
    skipped: bool
    error_class: Optional[str]
    error_reason: Optional[str]


def _normalize_provider() -> str:
    raw = os.getenv("LLM_PROVIDER", "off").strip().lower()
    if not raw:
        raw = "off"
    if raw not in {"off", "mock", "openrouter"}:
        logger.warning("llm.adapter unknown provider=%s fallback=off", raw)
        return "off"
    return raw


def _normalize_mock_mode() -> str:
    raw = os.getenv("LLM_MOCK_MODE", "ok").strip().lower()
    if not raw:
        raw = "ok"
    base = raw
    if raw.endswith("_once") or raw.endswith("_always"):
        base = raw.rsplit("_", 1)[0]
    if base not in {
        "ok",
        "ok_step_3",
        "ok_step_2",
        "ok_step_1",
        "ok_step_0",
        "ok_final",
        "invalid_json",
        "schema_invalid",
        "timeout",
        "type_mismatch",
    }:
        logger.warning("llm.adapter unknown mock_mode=%s fallback=ok", raw)
        return "ok"
    return raw


def generate(step_ctx: Dict[str, Any]) -> LLMResult:
    expected_type = str(step_ctx.get("expected_type") or "")
    provider = _normalize_provider()
    if provider == "off":
        logger.info("llm.adapter provider=off skipped=true")
        return LLMResult(
            expected_type=expected_type,
            raw_text="",
            parsed_json=None,
            usage=None,
            used_fallback=False,
            skipped=True,
            error_class=None,
            error_reason=None,
        )

    if provider == "mock":
        mock_mode = _normalize_mock_mode()
        mock_provider = MockProvider(mode=mock_mode)
        return _generate_with_provider(
            provider_name="mock",
            provider=mock_provider,
            expected_type=expected_type,
            step_ctx=step_ctx,
        )
    if provider == "openrouter":
        from packages.llm.src.openrouter_provider import (
            MissingOpenRouterKeyError,
            OpenRouterProvider,
        )

        try:
            openrouter_provider = OpenRouterProvider.from_env()
        except MissingOpenRouterKeyError:
            logger.info("llm.adapter provider=openrouter skipped=true reason=missing_key")
            return LLMResult(
                expected_type=expected_type,
                raw_text="",
                parsed_json=None,
                usage=None,
                used_fallback=False,
                skipped=True,
                error_class=None,
                error_reason="missing_key",
            )
        return _generate_with_provider(
            provider_name="openrouter",
            provider=openrouter_provider,
            expected_type=expected_type,
            step_ctx=step_ctx,
        )
    logger.warning("llm.adapter unknown provider=%s fallback=off", provider)
    return LLMResult(
        expected_type=expected_type,
        raw_text="",
        parsed_json=None,
        usage=None,
        used_fallback=False,
        skipped=True,
        error_class=None,
        error_reason=None,
    )


def _generate_with_provider(
    *,
    provider_name: str,
    provider: Any,
    expected_type: str,
    step_ctx: Dict[str, Any],
) -> LLMResult:
    last_error_class: Optional[str] = None
    last_error_reason: Optional[str] = None
    last_raw_text = ""
    last_usage: Dict[str, Any] | None = None
    last_finish_reason: str | None = None
    last_native_finish_reason: str | None = None
    last_request_payload: Dict[str, Any] | None = None
    last_response_payload: Dict[str, Any] | None = None

    attempt = 1
    while True:
        try:
            last_raw_text = provider.generate(step_ctx)
            last_request_payload = getattr(provider, "last_request_payload", None)
            last_response_payload = getattr(provider, "last_response_payload", None)
            last_usage = getattr(provider, "last_usage", None)
            last_finish_reason = getattr(provider, "last_finish_reason", None)
            last_native_finish_reason = getattr(provider, "last_native_finish_reason", None)
        except Exception as exc:  # noqa: BLE001
            last_error_class = type(exc).__name__
            if isinstance(exc, TimeoutError):
                last_error_reason = "timeout"
            elif isinstance(exc, url_error.HTTPError):
                last_error_reason = f"provider_http_{exc.code}"
            elif isinstance(exc, requests.exceptions.HTTPError):
                status_code = getattr(exc.response, "status_code", None)
                if status_code is None:
                    last_error_reason = "provider_http_unknown"
                else:
                    last_error_reason = f"provider_http_{status_code}"
            else:
                last_error_reason = "exception"
            logger.info(
                "llm.adapter provider=%s expected=%s attempt=%s outcome=error",
                provider_name,
                expected_type,
                attempt,
            )
            if attempt == 1:
                attempt = 2
                continue
            break

        parsed_json, error_reason = validate_response(last_raw_text, expected_type)
        if error_reason:
            last_error_class = "validation_error"
            last_error_reason = error_reason
            logger.info(
                "llm.validator expected=%s outcome=%s",
                expected_type,
                error_reason,
            )
            logger.info(
                "llm.adapter provider=%s expected=%s attempt=%s outcome=error",
                provider_name,
                expected_type,
                attempt,
            )
            if attempt == 1:
                attempt = 2
                continue
            break

        logger.info(
            "llm.adapter provider=%s expected=%s attempt=%s outcome=ok",
            provider_name,
            expected_type,
            attempt,
        )
        _dump_debug(
            step_ctx=step_ctx,
            provider_name=provider_name,
            expected_type=expected_type,
            raw_text=last_raw_text,
            usage=last_usage,
            error_reason=None,
            finish_reason=last_finish_reason,
            native_finish_reason=last_native_finish_reason,
            request=last_request_payload,
            response=last_response_payload,
            parsed_json=parsed_json,
            engine_input=step_ctx.get("engine_input"),
            engine_output=step_ctx.get("engine_output"),
        )
        return LLMResult(
            expected_type=expected_type,
            raw_text=last_raw_text,
            parsed_json=parsed_json,
            usage=last_usage,
            used_fallback=False,
            skipped=False,
            error_class=None,
            error_reason=None,
        )

    fallback_json = build_fallback(expected_type)
    _dump_debug(
        step_ctx=step_ctx,
        provider_name=provider_name,
        expected_type=expected_type,
        raw_text=last_raw_text,
        usage=last_usage,
        error_reason=last_error_reason,
        finish_reason=last_finish_reason,
        native_finish_reason=last_native_finish_reason,
        request=last_request_payload,
        response=last_response_payload,
        parsed_json=fallback_json,
        engine_input=step_ctx.get("engine_input"),
        engine_output=step_ctx.get("engine_output"),
    )
    reason = last_error_reason or "unknown"
    logger.info(
        "llm.fallback expected=%s reason=%s",
        expected_type,
        reason,
    )
    return LLMResult(
        expected_type=expected_type,
        raw_text=last_raw_text,
        parsed_json=fallback_json,
        usage=last_usage,
        used_fallback=True,
        skipped=False,
        error_class=last_error_class,
        error_reason=last_error_reason,
    )


def _dump_debug(
    *,
    step_ctx: Dict[str, Any],
    provider_name: str,
    expected_type: str,
    raw_text: str,
    usage: Dict[str, Any] | None,
    error_reason: str | None,
    finish_reason: str | None,
    native_finish_reason: str | None,
    request: Dict[str, Any] | None = None,
    response: Dict[str, Any] | None = None,
    parsed_json: Dict[str, Any] | None = None,
    engine_input: Dict[str, Any] | None = None,
    engine_output: Dict[str, Any] | None = None,
) -> None:
    dump_dir = os.getenv("LLM_DEBUG_DUMP_DIR", "").strip()
    if not dump_dir:
        return
    try:
        os.makedirs(dump_dir, exist_ok=True)
        req_id = step_ctx.get("req_id") or "unknown"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{req_id}_{provider_name}_{expected_type}_{timestamp}.json"
        path = os.path.join(dump_dir, filename)
        payload = {
            "req_id": req_id,
            "provider": provider_name,
            "expected_type": expected_type,
            "request": request,
            "response": response,
            "engine_input": engine_input,
            "engine_output": engine_output,
            "error_reason": error_reason,
            "raw_text": raw_text,
            "parsed_json": parsed_json,
            "usage": usage,
            "finish_reason": finish_reason,
            "native_finish_reason": native_finish_reason,
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except OSError:
        return
