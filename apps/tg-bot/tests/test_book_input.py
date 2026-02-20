import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "apps" / "tg-bot"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.services import book_runtime as br  # noqa: E402


def test_build_book_input_enriches_chosen_choice_text(monkeypatch) -> None:
    monkeypatch.setattr(
        br,
        "_load_session_steps",
        lambda _sid: [
            {
                "step_index": 1,
                "narration_text": "Текст",
                "choices": [{"id": "a", "text": "Налево"}, {"id": "b", "text": "Направо"}],
                "chosen_choice_id": "b",
                "story_step_json": {},
            }
        ],
    )
    monkeypatch.setattr(br, "_pick_style_reference", lambda _sid: None)

    out = br.build_book_input({"id": 10, "theme_id": "forest", "child_name": "Мира"})
    step = out["steps"][0]
    assert step["chosen_choice_text"] == "Направо"

