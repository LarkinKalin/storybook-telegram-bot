import json
from pathlib import Path

from packages.llm.src.openrouter_provider import OpenRouterProvider


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_openrouter_payload_schema(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return DummyResponse(
            {"choices": [{"message": {"content": {"text": "ok", "recap_short": "recap", "choices": []}}}]}
        )

    monkeypatch.setenv("OPENROUTER_MODEL_TEXT", "moonshotai/kimi-k2.5")
    monkeypatch.setenv("OPENROUTER_TIMEOUT_S", "12")
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS_STEP", "64")
    monkeypatch.setenv("OPENROUTER_RESPONSE_FORMAT", "json_schema")
    monkeypatch.setenv("OPENROUTER_RESPONSE_HEALING", "1")
    repo_root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("SKAZKA_CONTENT_DIR", str(repo_root / "content"))
    monkeypatch.setattr("packages.llm.src.openrouter_provider.requests.post", fake_post)

    provider = OpenRouterProvider("key")
    provider.generate({"expected_type": "story_step", "story_request": {"text": "hi"}})

    payload = captured["json"]
    assert payload["response_format"]["type"] == "json_schema"
    schema = payload["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["recap_short"]["type"] == "string"
    assert schema["properties"]["choices"]["maxItems"] == 3
    assert {"id": "response-healing"} in payload["plugins"]
    assert payload["messages"][0]["role"] == "system"
    assert "ДУГА НА 8 ШАГОВ" in payload["messages"][0]["content"]
    assert "400–800" in payload["messages"][0]["content"]
    assert provider.last_prompt_source.startswith("file:")
    assert provider.last_prompt_path.endswith("content/prompts/story_step/default.txt")


def test_openrouter_content_dict(monkeypatch):
    payload = {"choices": [{"message": {"content": {"text": "step", "choices": []}}}]}

    def fake_post(*_args, **_kwargs):
        return DummyResponse(payload)

    monkeypatch.setattr("packages.llm.src.openrouter_provider.requests.post", fake_post)
    provider = OpenRouterProvider("key")
    result = provider.generate({"expected_type": "story_step"})
    assert json.loads(result)["text"] == "step"


def test_openrouter_content_string_json(monkeypatch):
    payload = {"choices": [{"message": {"content": "{\"text\": \"final\"}"}}]}

    def fake_post(*_args, **_kwargs):
        return DummyResponse(payload)

    monkeypatch.setattr("packages.llm.src.openrouter_provider.requests.post", fake_post)
    provider = OpenRouterProvider("key")
    result = provider.generate({"expected_type": "story_final"})
    assert json.loads(result)["text"] == "final"


def test_openrouter_content_string_invalid(monkeypatch):
    payload = {"choices": [{"message": {"content": "not-json"}}]}

    def fake_post(*_args, **_kwargs):
        return DummyResponse(payload)

    monkeypatch.setattr("packages.llm.src.openrouter_provider.requests.post", fake_post)
    provider = OpenRouterProvider("key")
    result = provider.generate({"expected_type": "story_final"})
    assert result == "not-json"
