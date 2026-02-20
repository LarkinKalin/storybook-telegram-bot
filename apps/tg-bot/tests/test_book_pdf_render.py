import io
import sys
from pathlib import Path

import pytest

PdfReader = pytest.importorskip("pypdf").PdfReader

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "apps" / "tg-bot"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.services import book_runtime as br  # noqa: E402


@pytest.mark.skipif(br.canvas is None, reason="reportlab unavailable")
def test_book_pdf_has_8_pages_and_image_xobject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pil = pytest.importorskip("PIL.Image")
    img = tmp_path / "p.png"
    pil.new("RGB", (8, 8), (120, 80, 200)).save(img, format="PNG")

    def fake_get_by_id(asset_id: int):
        return {"id": asset_id, "storage_key": "book/test.png"}

    monkeypatch.setattr(br.assets, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(br, "_resolve_storage_path", lambda _k: img)

    script = {
        "title": "Тест",
        "pages": [
            {"page_no": i, "heading": f"Страница {i}", "text": "Текст страницы", "image_prompt": "Prompt"}
            for i in range(1, 9)
        ],
    }
    pdf_bytes = br._build_book_pdf_bytes(script, child_name="Дружок", image_assets=[1] * 8)

    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 8

    page = reader.pages[1]
    resources = page["/Resources"]
    xobj = resources.get("/XObject")
    assert xobj is not None
    assert len(xobj.keys()) >= 1
