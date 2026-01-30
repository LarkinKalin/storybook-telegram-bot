from packages.llm.src.validator import validate_response


def test_validator_json_parse_error():
    parsed, reason, detail = validate_response("{nope", "story_step")
    assert parsed is None
    assert reason == "json_parse_error"
    assert detail["response_preview"].startswith("{nope")


def test_validator_truncated_output():
    parsed, reason, detail = validate_response(
        "{\"text\": \"hi\", \"choices\": []", "story_final"
    )
    assert parsed is None
    assert reason == "truncated_output"
    assert "response_preview" in detail


def test_validator_invalid_json():
    parsed, reason, detail = validate_response("<<<not json>>>", "story_step")
    assert parsed is None
    assert reason == "invalid_json"
    assert detail["response_preview"].startswith("<<<not json>>>")


def test_validator_missing_required_fields():
    parsed, reason, detail = validate_response("{\"choices\": []}", "story_step")
    assert parsed is None
    assert reason == "missing_required_fields"
    assert "text" in detail["missing_fields"]


def test_validator_requires_recap_short():
    parsed, reason, detail = validate_response(
        "{\"text\": \"ok\", \"choices\": [{\"choice_id\": \"A\", \"label\": \"A\"}]}",
        "story_step",
    )
    assert parsed is None
    assert reason == "missing_required_fields"
    assert "recap_short" in detail["missing_fields"]


def test_validator_requires_recap_short():
    parsed, reason = validate_response(
        "{\"text\": \"ok\", \"choices\": [{\"choice_id\": \"A\", \"label\": \"A\"}]}",
        "story_step",
    )
    assert parsed is None
    assert reason == "missing_required_fields"


def test_validator_story_final_allows_empty_choices():
    parsed, reason, detail = validate_response(
        "{\"text\": \"ok\", \"choices\": []}", "story_final"
    )
    assert parsed is not None
    assert reason is None
    assert detail is None
