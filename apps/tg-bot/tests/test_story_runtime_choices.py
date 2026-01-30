import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "apps" / "tg-bot"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from packages.engine.src.engine_v0_1 import init_state_v01  # noqa: E402
from src.services.story_runtime import build_step_result, step_result_to_view  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_MODE", "ok_step_2")


def test_step_result_uses_llm_choices() -> None:
    state = init_state_v01(3)
    session_row = {"theme_id": "test"}
    step_result = build_step_result(session_row, state=state, req_id="test")
    labels = [choice["label"] for choice in step_result["choices"]]
    assert step_result["choices_source"] == "llm"
    assert any("Повернуть к реке" in label for label in labels)
    view = step_result_to_view(step_result, sid8="sid", step=0)
    assert "Варианты:" in view.text
    assert "A)" in view.text
    banned = {"мудрость", "доброта", "смелость"}
    assert not any(any(word in label.lower() for word in banned) for label in labels)
