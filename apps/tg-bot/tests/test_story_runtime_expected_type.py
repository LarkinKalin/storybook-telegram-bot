import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "apps" / "tg-bot"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.services.story_runtime import expected_type_for_step  # noqa: E402


def test_expected_type_for_step_non_final():
    assert expected_type_for_step(0, 3) == "story_step"
    assert expected_type_for_step(1, 3) == "story_step"


def test_expected_type_for_step_final():
    assert expected_type_for_step(2, 3) == "story_final"
    assert expected_type_for_step(7, 8) == "story_final"
