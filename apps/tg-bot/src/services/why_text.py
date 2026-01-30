from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

from src.services.whyqa import WhyAnswer, whyqa

logger = logging.getLogger(__name__)

_DEFAULT_CLAMP_CHARS = 400
_DEFAULT_MAX_TOKENS = 400
_DEFAULT_TEMPERATURE = 0.65
_DEFAULT_TOP_P = 0.9
_DEFAULT_TIMEOUT_S = 15.0
_WHY_LLM_RETRY = 1

_OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODEL = "moonshotai/kimi-k2.5"

_REPEAT_PUNCT_RE = re.compile(r"([!?.,:;…])\1+")

_DEFAULT_DUMP_PATH = "apps/tg-bot/var/why_dumps/why_text_dump.jsonl"


@dataclass(frozen=True)
class WhyTextResult:
    text: str
    matched: bool
    matched_id: str | None
    score: int
    llm_called: bool
    outcome: str
    q_len: int
    q_hash: str


def answer_why_text(question: str, audience: str) -> WhyTextResult:
    normalized = _normalize_question(question)
    clamped = _clamp_question(normalized)
    q_len = len(clamped)
    q_hash = hashlib.sha256(clamped.encode("utf-8")).hexdigest()

    logger.info("why.q_received mode=why_text len=%s hash=%s", q_len, q_hash)

    qa_hit = False
    qa_id: str | None = None
    score = 0
    answer_text = ""

    try:
        answer = whyqa.answer(clamped, audience)
    except Exception as exc:  # noqa: BLE001
        logger.info("why.qa_load_error", exc_info=exc)
        answer = None

    if isinstance(answer, WhyAnswer) and answer.matched:
        qa_hit = True
        qa_id = answer.matched_id
        score = answer.score
        answer_text = answer.text
        logger.info("why.q_matched id=%s score=%s", qa_id, score)
        result = WhyTextResult(
            text=answer_text,
            matched=True,
            matched_id=qa_id,
            score=score,
            llm_called=False,
            outcome="ok",
            q_len=q_len,
            q_hash=q_hash,
        )
        _write_dump(result, qa_hit=qa_hit, model=None)
        return result

    logger.info("why.q_notfound")
    llm_text, outcome, llm_called = _call_llm(question=clamped)
    if llm_text:
        answer_text = llm_text
    else:
        answer_text = _fallback_response()
    result = WhyTextResult(
        text=answer_text,
        matched=False,
        matched_id=None,
        score=0,
        llm_called=llm_called,
        outcome=outcome,
        q_len=q_len,
        q_hash=q_hash,
    )
    _write_dump(result, qa_hit=qa_hit, model=_OPENROUTER_MODEL if llm_called else None)
    return result


def _normalize_question(text: str) -> str:
    cleaned = text.strip().lower().replace("ё", "е")
    cleaned = " ".join(cleaned.split())
    cleaned = _REPEAT_PUNCT_RE.sub(r"\1", cleaned)
    return cleaned.strip()


def _clamp_question(text: str) -> str:
    max_chars = _resolve_int("WHY_QUESTION_CLAMP_CHARS", _DEFAULT_CLAMP_CHARS)
    if max_chars <= 0:
        return ""
    return text[:max_chars]


def _fallback_response() -> str:
    return "Извини, я сейчас не могу ответить. Попробуй спросить иначе или попроси взрослого помочь."


@lru_cache(maxsize=None)
def _load_prompt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def _call_llm(*, question: str) -> tuple[str | None, str, bool]:
    api_key = _resolve_api_key()
    if not api_key:
        logger.info("why.llm_outcome outcome=fallback")
        return None, "fallback", False

    system_prompt, user_prompt = _build_prompts(question)
    timeout_s = _resolve_float("WHY_TIMEOUT_S", _DEFAULT_TIMEOUT_S)
    max_tokens = _resolve_int("WHY_MAX_TOKENS", _DEFAULT_MAX_TOKENS)
    temperature = _resolve_float("WHY_TEMPERATURE", _DEFAULT_TEMPERATURE)
    top_p = _resolve_float("WHY_TOP_P", _DEFAULT_TOP_P)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    http_referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    app_title = os.getenv("OPENROUTER_APP_TITLE", "").strip()
    if app_title:
        headers["X-Title"] = app_title

    payload = {
        "model": _OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "reasoning": {"enabled": False},
    }

    logger.info(
        "why.llm_called model=%s timeout_s=%s max_tokens=%s temperature=%s",
        _OPENROUTER_MODEL,
        timeout_s,
        max_tokens,
        temperature,
    )

    attempts = _WHY_LLM_RETRY + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.post(
                _OPENROUTER_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=timeout_s,
            )
            response.raise_for_status()
            content = _extract_content(response.json())
            if content and content.strip():
                logger.info("why.llm_outcome outcome=ok")
                return content.strip(), "ok", True
            last_error = ValueError("openrouter response empty")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        if attempt >= _WHY_LLM_RETRY:
            break
    if last_error:
        logger.info("why.llm_outcome outcome=fallback")
    return None, "fallback", True


def _extract_content(payload: dict[str, Any]) -> str | None:
    choice = payload.get("choices", [{}])[0]
    message = choice.get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return None


def _build_prompts(question: str) -> tuple[str, str]:
    prompt_dir = _prompt_dir()
    system_path = str(prompt_dir / "why_text_system_v1.txt")
    user_path = str(prompt_dir / "why_text_user_v1.txt")
    system_prompt = _load_prompt(system_path)
    user_template = _load_prompt(user_path)
    return system_prompt, user_template.format(question=question)


def _prompt_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "packages" / "llm" / "prompt_templates"


def _resolve_api_key() -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return api_key


def _resolve_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _resolve_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _write_dump(result: WhyTextResult, *, qa_hit: bool, model: str | None) -> None:
    dump_path = Path(os.getenv("WHY_DUMP_PATH", _DEFAULT_DUMP_PATH))
    try:
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "mode": "why_text",
            "q_len": result.q_len,
            "q_hash": result.q_hash,
            "qa_hit": qa_hit,
            "qa_id": result.matched_id,
            "score": result.score,
            "llm_called": result.llm_called,
            "model": model,
            "outcome": result.outcome,
            "resp_len": len(result.text),
            "response_text": result.text,
        }
        with dump_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return
