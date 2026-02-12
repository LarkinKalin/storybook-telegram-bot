from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from aiogram.types import BufferedInputFile

from db.repos import assets, book_jobs, session_images
from packages.llm.src.openrouter_image_provider import generate_i2i, generate_t2i
from src.services.image_delivery import _resolve_assets_root, _resolve_storage_path

logger = logging.getLogger(__name__)

_BOOK_SAMPLE_PATH = Path("/app/apps/tg-bot/assets/book_sample.pdf")
_BOOK_PROMPTS_DIR = Path("/app/content/prompts/book_rewrite")
_BOOK_PROMPT_KEY_ENV = "SKAZKA_BOOK_REWRITE_PROMPT_KEY"
_DEV_FIXTURE_PATH = Path("/app/content/fixtures/dev_book_8_steps.json")
_job_locks: dict[int, asyncio.Lock] = {}


def _session_lock(session_id: int) -> asyncio.Lock:
    lock = _job_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _job_locks[session_id] = lock
    return lock


def book_offer_text() -> str:
    return (
        "Хочешь превратить эту сказку в настоящую книжку?\n\n"
        "Соберу версию на 8 страниц с иллюстрациями в одном стиле и пришлю PDF прямо сюда."
    )


async def send_sample_pdf(message) -> None:
    if not _BOOK_SAMPLE_PATH.exists():
        await message.answer("Пока не нашёл образец PDF в контейнере. Попробуй позже 🙏")
        return
    data = _BOOK_SAMPLE_PATH.read_bytes()
    await message.answer_document(
        document=BufferedInputFile(data, filename="book_sample.pdf"),
        caption="Вот пример книжки ✨",
    )
    logger.info("book.sample sent")


async def run_dev_book_test_from_fixture(message, session_id: int) -> None:
    current = book_jobs.get_by_session_kind(session_id)
    if current and current.get("status") == "done" and current.get("result_pdf_asset_id"):
        await _send_existing_pdf(message, int(current["result_pdf_asset_id"]))
        return
    fixture = _load_dev_book_fixture()
    book_script = _build_book_script_from_fixture(fixture)
    script_asset_id = _store_json_asset(session_id, book_script)
    pdf_asset_id = _build_book_pdf(session_id, book_script)
    book_jobs.upsert_status(
        session_id,
        status="done",
        result_pdf_asset_id=pdf_asset_id,
        script_json_asset_id=script_asset_id,
        error_message=None,
    )
    await _send_existing_pdf(message, pdf_asset_id)


def _load_dev_book_fixture() -> dict[str, Any]:
    if _DEV_FIXTURE_PATH.exists():
        payload = json.loads(_DEV_FIXTURE_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    steps = [
        {
            "step_index": idx,
            "text": f"Тестовый шаг {idx}",
            "choices": [{"id": "a", "text": "Выбор A"}],
            "chosen_choice_id": "a",
        }
        for idx in range(1, 9)
    ]
    return {"title": "Тестовая книжка", "child_name": "Дружок", "steps": steps}


def _build_book_script_from_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    steps = fixture.get("steps") if isinstance(fixture.get("steps"), list) else []
    child_name = fixture.get("child_name") if isinstance(fixture.get("child_name"), str) else "Дружок"
    title = fixture.get("title") if isinstance(fixture.get("title"), str) else "Тестовая книжка"
    pages = []
    for idx in range(1, 9):
        step = steps[idx - 1] if idx - 1 < len(steps) and isinstance(steps[idx - 1], dict) else {}
        step_text = step.get("text") if isinstance(step.get("text"), str) else f"Тестовый шаг {idx}"
        pages.append({
            "page": idx,
            "text": f"{child_name}: {step_text}",
            "illustration_brief": f"Плейсхолдер-иллюстрация, страница {idx}.",
        })
    return _validate_book_script({
        "title": title,
        "pages": pages,
        "style_rules": "Плейсхолдерный стиль для dev-проверки PDF.",
    })


def build_book_input(session_row: dict[str, Any], theme_title: str | None = None) -> dict[str, Any]:
    events = _load_session_steps(session_row["id"])
    style_ref = _pick_style_reference(session_row["id"])
    child_name = (session_row.get("child_name") or "").strip()
    return {
        "session_id": session_row["id"],
        "theme_id": session_row.get("theme_id"),
        "theme_title": theme_title,
        "child_name": child_name or "дружок",
        "steps": events,
        "style_ref_asset_id": style_ref,
    }


def _load_session_steps(session_id: int) -> list[dict[str, Any]]:
    from db.conn import transaction
    from psycopg.rows import dict_row

    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT step, step_result_json, choice_id
                FROM session_events
                WHERE session_id = %s
                ORDER BY step ASC;
                """,
                (session_id,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    items: list[dict[str, Any]] = []
    for row in rows:
        sr = row.get("step_result_json") if isinstance(row.get("step_result_json"), dict) else {}
        items.append(
            {
                "step_index": int(sr.get("step_index") or int(row["step"]) + 1),
                "narration_text": _step_narration(sr),
                "choices": _step_choices_for_protocol(sr),
                "chosen_choice_id": sr.get("chosen_choice_id") or row.get("choice_id"),
                "story_step_json": sr.get("story_step_json") if isinstance(sr.get("story_step_json"), dict) else sr,
            }
        )
    return items


def _pick_style_reference(session_id: int) -> int | None:
    images = session_images.list_session_images(session_id)
    if not images:
        return None
    for row in images:
        if row.get("step_ui") == 1 and row.get("asset_id"):
            return int(row["asset_id"])
    for row in reversed(images):
        if row.get("asset_id"):
            return int(row["asset_id"])
    return None


def _book_prompt_key() -> str:
    key = os.getenv(_BOOK_PROMPT_KEY_ENV, "v1_default").strip()
    return key or "v1_default"


def _load_book_rewrite_prompt() -> str:
    key = _book_prompt_key()
    path = _BOOK_PROMPTS_DIR / f"{key}.md"
    if not path.exists():
        logger.warning("book.prompt missing key=%s fallback=v1_default", key)
        path = _BOOK_PROMPTS_DIR / "v1_default.md"
    if not path.exists():
        return "Сделай цельную детскую книжку на 8 страниц, JSON-only."
    return path.read_text(encoding="utf-8").strip()


def _validate_book_script(script: dict[str, Any]) -> dict[str, Any]:
    pages = script.get("pages") if isinstance(script.get("pages"), list) else []
    if len(pages) != 8:
        raise ValueError(f"book_script pages must be 8, got={len(pages)}")
    return script


def _step_choices_for_protocol(step_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(step_payload.get("protocol_choices"), list) and step_payload.get("protocol_choices"):
        normalized = []
        for item in step_payload.get("protocol_choices", []):
            if not isinstance(item, dict):
                continue
            cid = item.get("id")
            text = item.get("text")
            if isinstance(cid, str) and isinstance(text, str):
                normalized.append({"id": cid, "text": text})
        if normalized:
            return normalized
    choices = step_payload.get("choices") if isinstance(step_payload.get("choices"), list) else []
    normalized = []
    for item in choices:
        if not isinstance(item, dict):
            continue
        cid = item.get("choice_id") or item.get("id")
        text = item.get("label") or item.get("text")
        if isinstance(cid, str) and isinstance(text, str):
            normalized.append({"id": cid, "text": text})
    return normalized


def _step_narration(step_payload: dict[str, Any]) -> str:
    narration = step_payload.get("narration_text")
    if isinstance(narration, str) and narration.strip():
        return narration
    text = step_payload.get("text")
    if isinstance(text, str):
        return text
    return ""


def _build_book_script(book_input: dict[str, Any]) -> dict[str, Any]:
    rewrite_prompt = _load_book_rewrite_prompt()
    logger.info("book.rewrite prompt_key=%s", _book_prompt_key())
    child_name = book_input.get("child_name") or "дружок"
    source = [s.get("narration_text", "") for s in book_input.get("steps", []) if s.get("narration_text")]
    merged = " ".join(source)[:2400]
    pages = []
    for idx in range(1, 9):
        chunk = merged[(idx - 1) * 280 : idx * 280].strip() or "Новая сцена сказки."
        pages.append(
            {
                "page": idx,
                "text": f"{child_name} — {chunk}",
                "illustration_brief": f"Детская книжная иллюстрация. Страница {idx}. {chunk[:140]}",
            }
        )
    script = {
        "title": f"Книжка: {book_input.get('theme_title') or book_input.get('theme_id') or 'Сказка'}",
        "pages": pages,
        "style_rules": "Единый мягкий стиль детской книжной иллюстрации, тёплая палитра, без текста.",
        "rewrite_prompt_key": _book_prompt_key(),
        "rewrite_prompt_preview": rewrite_prompt[:200],
    }
    return _validate_book_script(script)


async def run_book_job(message, session_row: dict[str, Any], theme_title: str | None = None) -> None:
    lock = _session_lock(session_row["id"])
    async with lock:
        current = book_jobs.get_by_session_kind(session_row["id"])
        if current and current.get("status") == "done" and current.get("result_pdf_asset_id"):
            await _send_existing_pdf(message, int(current["result_pdf_asset_id"]))
            return
        if current and current.get("status") == "running":
            await message.answer("Уже собираю книжку, совсем скоро отправлю ✨")
            return

        logger.info("book.buy clicked session_id=%s", session_row["id"])
        book_jobs.upsert_status(session_row["id"], status="running", error_message=None)
        logger.info("book.job status=running session_id=%s", session_row["id"])

        try:
            book_input = build_book_input(session_row, theme_title=theme_title)
            logger.info("book.input built steps=%s has_style_ref=%s", len(book_input["steps"]), 1 if book_input.get("style_ref_asset_id") else 0)
            book_script = _build_book_script(book_input)
            logger.info("book.script ok pages=%s", len(book_script.get("pages", [])))
            script_asset_id = _store_json_asset(session_row["id"], book_script)
            image_assets = await _generate_book_images(book_script, book_input.get("style_ref_asset_id"))
            logger.info("book.images ok count=%s", len([a for a in image_assets if a]))
            pdf_asset_id = _build_book_pdf(session_row["id"], book_script)
            asset = assets.get_by_id(pdf_asset_id)
            logger.info("book.pdf ok size=%s path=%s", asset.get("bytes") if asset else None, asset.get("storage_key") if asset else None)
            book_jobs.upsert_status(
                session_row["id"],
                status="done",
                result_pdf_asset_id=pdf_asset_id,
                script_json_asset_id=script_asset_id,
                error_message=None,
            )
            logger.info("book.job status=done session_id=%s", session_row["id"])
            await _send_existing_pdf(message, pdf_asset_id)
            logger.info("book.send ok session_id=%s", session_row["id"])
        except Exception as exc:
            logger.exception("book.job failed session_id=%s", session_row["id"])
            book_jobs.upsert_status(session_row["id"], status="error", error_message=str(exc)[:500])
            await message.answer("Не удалось собрать книжку с первого раза. Нажми «📖 Купить книгу», чтобы повторить.")


async def _generate_book_images(book_script: dict[str, Any], style_ref_asset_id: int | None) -> list[int | None]:
    pages = book_script.get("pages") if isinstance(book_script.get("pages"), list) else []
    out: list[int | None] = []
    logger.info("book.images started pages=%s", len(pages))
    if os.getenv("SKAZKA_STEP_IMAGES", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        logger.info("book.images skipped reason=feature_disabled")
        return [None for _ in pages]
    ref_payload = _load_asset_payload(style_ref_asset_id) if style_ref_asset_id else None
    ref_bytes = ref_payload[0] if ref_payload else None
    ref_mime = ref_payload[1] if ref_payload else None
    for page in pages:
        page_no = page.get("page")
        prompt = f"{book_script.get('style_rules')}\n{page.get('illustration_brief')}"
        try:
            if ref_bytes and ref_mime:
                image_bytes, mime, width, height, sha = generate_i2i(prompt, ref_bytes, ref_mime)
            else:
                image_bytes, mime, width, height, sha = generate_t2i(prompt)
            asset_id, _ = _store_binary_asset("image", image_bytes, mime, sha, width=width, height=height)
            out.append(asset_id)
            logger.info("book.image ok page=%s asset_id=%s", page_no, asset_id)
        except Exception as exc:
            logger.warning("book.image error page=%s error=%s", page_no, exc)
            out.append(None)
    return out


def _build_book_pdf(session_id: int, book_script: dict[str, Any]) -> int:
    lines = [book_script.get("title") or "Сказка", ""]
    for page in book_script.get("pages", []):
        lines.append(f"Страница {page.get('page')}")
        lines.append(page.get("text") or "")
        lines.append("")
    pdf_bytes = _simple_pdf("\n".join(lines))
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    asset_id, _ = _store_binary_asset("pdf", pdf_bytes, "application/pdf", digest)
    return asset_id


def _simple_pdf(text: str) -> bytes:
    safe = text.replace("(", "[").replace(")", "]")
    stream = f"BT /F1 12 Tf 40 800 Td ({safe[:3000]}) Tj ET".encode("latin-1", "ignore")
    objs = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>endobj\n",
        b"4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
        b"5 0 obj<< /Length %d >>stream\n" % len(stream) + stream + b"\nendstream endobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode())
    return bytes(out)


def _store_json_asset(session_id: int, payload: dict[str, Any]) -> int:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    asset_id, _ = _store_binary_asset("json", data, "application/json", digest)
    return asset_id


def _store_binary_asset(
    kind: str,
    content: bytes,
    mime: str,
    sha256: str,
    *,
    width: int | None = None,
    height: int | None = None,
) -> tuple[int, str]:
    ext = "pdf" if kind == "pdf" else "json" if kind == "json" else "png"
    storage_key = f"book/{sha256}.{ext}"
    path = _resolve_storage_path(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content)
    existing = assets.get_by_sha256(sha256)
    if existing:
        return int(existing["id"]), str(existing["storage_key"])
    asset_id = assets.insert_asset(
        kind=kind,
        storage_backend="fs",
        storage_key=storage_key,
        mime=mime,
        bytes=len(content),
        sha256=sha256,
        width=width,
        height=height,
    )
    return asset_id, storage_key


def _load_asset_payload(asset_id: int | None) -> tuple[bytes, str] | None:
    if asset_id is None:
        return None
    row = assets.get_by_id(asset_id)
    if not row:
        return None
    path = _resolve_storage_path(row["storage_key"])
    if not path.exists():
        return None
    return path.read_bytes(), row.get("mime") or "image/png"


async def _send_existing_pdf(message, asset_id: int) -> None:
    row = assets.get_by_id(asset_id)
    if not row:
        await message.answer("PDF уже был собран, но файл не найден. Запусти сборку ещё раз.")
        return
    path = _resolve_storage_path(row["storage_key"])
    if not path.exists():
        await message.answer("PDF уже был собран, но файл не найден. Запусти сборку ещё раз.")
        return
    await message.answer_document(
        document=BufferedInputFile(path.read_bytes(), filename=path.name),
        caption="Готово! Вот твоя книжка 📘",
    )
