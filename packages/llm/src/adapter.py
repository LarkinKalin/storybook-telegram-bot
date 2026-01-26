from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from packages.llm.src.fallbacks import build_fallback
from packages.llm.src.mock_provider import MockProvider
from packages.llm.src.validator import validate_response

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    expected_type: str
    raw_text: str
    parsed_json: Optional[Dict[str, Any]]
    used_fallback: bool
    skipped: bool
    error_class: Optional[str]
    error_reason: Optional[str]


def _normalize_provider() -> str:
    raw = os.getenv("LLM_PROVIDER", "off").strip().lower()
    if not raw:
        raw = "off"
    if raw not in {"off", "mock"}:
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
            used_fallback=False,
            skipped=True,
            error_class=None,
            error_reason=None,
        )

    mock_mode = _normalize_mock_mode()
    mock_provider = MockProvider(mode=mock_mode)
    return _generate_with_provider(
        provider_name="mock",
        provider=mock_provider,
        expected_type=expected_type,
        step_ctx=step_ctx,
    )


def _generate_with_provider(
    *,
    provider_name: str,
    provider: MockProvider,
    expected_type: str,
    step_ctx: Dict[str, Any],
) -> LLMResult:
    last_error_class: Optional[str] = None
    last_error_reason: Optional[str] = None
    last_raw_text = ""

    attempt = 1
    while True:
        try:
            last_raw_text = provider.generate(step_ctx)
        except Exception as exc:  # noqa: BLE001
            last_error_class = type(exc).__name__
            last_error_reason = "timeout" if isinstance(exc, TimeoutError) else "exception"
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
        return LLMResult(
            expected_type=expected_type,
            raw_text=last_raw_text,
            parsed_json=parsed_json,
            used_fallback=False,
            skipped=False,
            error_class=None,
            error_reason=None,
        )

    fallback_json = build_fallback(expected_type)
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
        used_fallback=True,
        skipped=False,
        error_class=last_error_class,
        error_reason=last_error_reason,
    )
