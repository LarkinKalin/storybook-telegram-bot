import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "apps" / "tg-bot"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.keyboards.l3 import build_l3_keyboard  # noqa: E402


def _choices(count: int) -> list[dict]:
    labels = [
        ("A", "A"),
        ("B", "B"),
        ("C", "C"),
    ]
    return [
        {"choice_id": choice_id, "label": label}
        for choice_id, label in labels[:count]
    ]


def _first_row_count(markup) -> int:
    if not markup.inline_keyboard:
        return 0
    return len(markup.inline_keyboard[0])


def test_keyboard_choices_len_three():
    markup = build_l3_keyboard(_choices(3), allow_free_text=True, sid8="sid", step=1)
    assert _first_row_count(markup) == 3


def test_keyboard_choices_len_two():
    markup = build_l3_keyboard(_choices(2), allow_free_text=True, sid8="sid", step=1)
    assert _first_row_count(markup) == 2


def test_keyboard_choices_len_one():
    markup = build_l3_keyboard(_choices(1), allow_free_text=True, sid8="sid", step=1)
    assert _first_row_count(markup) == 1


def test_keyboard_choices_len_zero():
    markup = build_l3_keyboard(_choices(0), allow_free_text=True, sid8="sid", step=1)
    assert _first_row_count(markup) == 1
    assert markup.inline_keyboard[0][0].text == "✍️ Свой вариант"
