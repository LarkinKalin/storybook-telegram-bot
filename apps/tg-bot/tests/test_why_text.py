from __future__ import annotations

import hashlib
import logging

import pytest
import requests

from src.services import why_text


class DummyResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


def test_normalize_hash_stable() -> None:
    text = "  Почему ЁЖик???   "
    normalized = why_text._normalize_question(text)
    clamped = why_text._clamp_question(normalized)
    digest = hashlib.sha256(clamped.encode("utf-8")).hexdigest()
    assert normalized == "почему ежик?"
    assert digest == hashlib.sha256("почему ежик?".encode("utf-8")).hexdigest()


def test_log_does_not_include_question(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("WHY_DUMP_PATH", str(tmp_path / "dump.jsonl"))

    def fake_post(*_args, **_kwargs):
        return DummyResponse({"choices": [{"message": {"content": "Ответ"}}]})

    monkeypatch.setattr(why_text.requests, "post", fake_post)
    caplog.set_level(logging.INFO)
    question = "Секретный вопрос???"
    why_text.answer_why_text(question, "kid")
    assert question not in caplog.text


def test_qa_hit_skips_llm(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("WHY_DUMP_PATH", str(tmp_path / "dump.jsonl"))

    def fail_post(*_args, **_kwargs):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr(why_text.requests, "post", fail_post)
    result = why_text.answer_why_text("Почему небо голубое?", "kid")
    assert result.matched is True
    assert result.llm_called is False


def test_qa_miss_calls_llm(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("WHY_DUMP_PATH", str(tmp_path / "dump.jsonl"))
    called = {"count": 0}

    def fake_post(*_args, **_kwargs):
        called["count"] += 1
        return DummyResponse({"choices": [{"message": {"content": "Ответ"}}]})

    monkeypatch.setattr(why_text.requests, "post", fake_post)
    result = why_text.answer_why_text("Почему трава фиолетовая?", "kid")
    assert result.matched is False
    assert result.llm_called is True
    assert called["count"] == 1


def test_llm_timeout_retries_and_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("WHY_DUMP_PATH", str(tmp_path / "dump.jsonl"))
    calls = {"count": 0}

    def fake_post(*_args, **_kwargs):
        calls["count"] += 1
        raise requests.exceptions.Timeout("timeout")

    monkeypatch.setattr(why_text.requests, "post", fake_post)
    result = why_text.answer_why_text("Почему трава оранжевая?", "kid")
    assert calls["count"] == 2
    assert result.text == why_text._fallback_response()
    assert result.outcome == "fallback"
