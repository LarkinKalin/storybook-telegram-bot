from packages.llm.src.adapter import generate


def test_generate_ok(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_MODE", "ok")
    result = generate({"expected_type": "story_step", "req_id": "req-1"})
    assert result.expected_type == "story_step"
    assert result.used_fallback is False
    assert result.parsed_json is not None
    assert result.parsed_json["text"]
    assert len(result.parsed_json["choices"]) == 3


def test_invalid_json_retry_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_MODE", "invalid_json_always")
    result = generate({"expected_type": "story_step", "req_id": "req-2"})
    assert result.used_fallback is True
    assert result.parsed_json is not None
    assert result.error_reason == "invalid_json"


def test_timeout_retry_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_MODE", "timeout_always")
    result = generate({"expected_type": "story_step", "req_id": "req-3"})
    assert result.used_fallback is True
    assert result.parsed_json is not None
    assert result.error_reason == "timeout"


def test_type_mismatch_retry_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_MODE", "type_mismatch_always")
    result = generate({"expected_type": "story_step", "req_id": "req-4"})
    assert result.used_fallback is True
    assert result.parsed_json is not None
    assert result.error_reason == "type_mismatch"
