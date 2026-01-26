import pytest

from packages.llm.src.adapter import generate


@pytest.mark.parametrize(
    "mode,expected_len",
    [
        ("ok_step_3", 3),
        ("ok_step_2", 2),
        ("ok_step_1", 1),
        ("ok_step_0", 0),
    ],
)
def test_ok_step_variants(monkeypatch, mode, expected_len):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_MODE", mode)
    result = generate({"expected_type": "story_step", "req_id": "req-ok"})
    assert result.used_fallback is False
    assert result.parsed_json is not None
    assert len(result.parsed_json.get("choices", [])) == expected_len


def test_ok_final(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_MODE", "ok_final")
    result = generate({"expected_type": "story_final", "req_id": "req-final"})
    assert result.used_fallback is False
    assert result.parsed_json is not None
    assert isinstance(result.parsed_json.get("text"), str)
    assert "choices" not in result.parsed_json


@pytest.mark.parametrize(
    "mode,expected_reason",
    [
        ("invalid_json_always", "invalid_json"),
        ("schema_invalid_always", "schema_invalid"),
        ("type_mismatch_always", "type_mismatch"),
        ("timeout_always", "timeout"),
    ],
)
def test_broken_modes_fallback(monkeypatch, mode, expected_reason):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_MODE", mode)
    result = generate({"expected_type": "story_step", "req_id": "req-bad"})
    assert result.used_fallback is True
    assert result.parsed_json is not None
    assert result.error_reason == expected_reason


def test_retry_recovers_after_invalid_json_once(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_MODE", "invalid_json_once")
    result = generate({"expected_type": "story_step", "req_id": "req-retry"})
    assert result.used_fallback is False
    assert result.parsed_json is not None
