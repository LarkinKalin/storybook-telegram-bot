import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "apps" / "tg-bot"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.services.book_runtime import _required_story_step_indexes  # noqa: E402


def test_required_story_steps_allow_final_as_separate_outcome() -> None:
    assert _required_story_step_indexes(8) == [1, 2, 3, 4, 5, 6, 7]


def test_required_story_steps_minimum() -> None:
    assert _required_story_step_indexes(1) == [1]
