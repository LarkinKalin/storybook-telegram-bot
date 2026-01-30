from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile

from db.repos import assets, session_images
from packages.llm.src.openrouter_image_provider import (
    MissingOpenRouterKeyError,
    generate_i2i,
    generate_t2i,
)

logger = logging.getLogger(__name__)

_ASSETS_ROOT_ENV = "ASSETS_ROOT"
_DEFAULT_ASSETS_ROOT = "/app/var/assets"
_ASSETS_IMAGE_DIR = "images"


@dataclass
class ImageSchedule:
    step_ui: int
    total_steps: int
    step0: int | None = None

    @property
    def needs_image(self) -> bool:
        if self.step0 is not None:
            return self.step0 in image_steps0(self.total_steps)
        return self.step_ui in image_steps(self.total_steps)

    @property
    def image_mode(self) -> str:
        return "t2i" if self.step_ui == 1 else "i2i"


def image_steps(total_steps: int) -> set[int]:
    if total_steps >= 12:
        return {1, 5, 9}
    if total_steps >= 8:
        return {1, 4, 8}
    return {1}


def image_steps0(total_steps: int) -> set[int]:
    if total_steps >= 12:
        return {0, 4, 8}
    if total_steps >= 8:
        return {0, 3, 7}
    return {0}


def schedule_image_delivery(
    *,
    bot: Bot,
    chat_id: int,
    step_message_id: int,
    session_id: int,
    step_ui: int,
    total_steps: int,
    prompt: str,
    theme_id: str | None = None,
    step0: int | None = None,
) -> None:
    schedule = ImageSchedule(step_ui=step_ui, total_steps=total_steps, step0=step0)
    logger.info(
        "TG.7.4.01 needs_image=%s session_id=%s step_ui=%s step0=%s total_steps=%s",
        schedule.needs_image,
        session_id,
        step_ui,
        step0,
        total_steps,
    )
    if not schedule.needs_image:
        return
    asyncio.create_task(
        _generate_and_send_image(
            bot=bot,
            chat_id=chat_id,
            step_message_id=step_message_id,
            session_id=session_id,
            step_ui=step_ui,
            total_steps=total_steps,
            prompt=prompt,
            theme_id=theme_id,
            step0=step0,
        )
    )


async def _generate_and_send_image(
    *,
    bot: Bot,
    chat_id: int,
    step_message_id: int,
    session_id: int,
    step_ui: int,
    total_steps: int,
    prompt: str,
    theme_id: str | None,
    step0: int | None,
) -> None:
    schedule = ImageSchedule(step_ui=step_ui, total_steps=total_steps, step0=step0)
    if not schedule.needs_image:
        return

    image_model = os.getenv("OPENROUTER_MODEL_IMAGE", "black-forest-labs/flux.2-pro").strip()
    retries = _resolve_retries()
    reference_asset_id = None
    reference_payload = None
    image_mode = schedule.image_mode
    if schedule.image_mode == "t2i":
        reference_asset_id = session_images.get_reference_asset_id(session_id)
        if reference_asset_id is not None:
            logger.info(
                "TG.7.4.01 image.reference exists session_id=%s step_ui=%s asset_id=%s",
                session_id,
                step_ui,
                reference_asset_id,
            )
            reference_payload = _load_reference(reference_asset_id)
            if reference_payload is not None:
                await _send_existing_image(
                    bot=bot,
                    chat_id=chat_id,
                    step_message_id=step_message_id,
                    image_bytes=reference_payload.bytes,
                    storage_key=_resolve_storage_key(reference_asset_id),
                )
                return
            logger.warning(
                "TG.7.4.01 image.reference missing_bytes session_id=%s step_ui=%s asset_id=%s",
                session_id,
                step_ui,
                reference_asset_id,
            )
            reference_asset_id = None
    else:
        reference_asset_id = session_images.get_reference_asset_id(session_id)
        if reference_asset_id is not None:
            reference_payload = _load_reference(reference_asset_id)
        if reference_payload is None:
            logger.warning(
                "TG.7.4.01 image.reference missing session_id=%s step_ui=%s",
                session_id,
                step_ui,
            )
            reference_asset_id = None
            image_mode = "t2i"

    prompt = _build_image_prompt(step_ui=step_ui, prompt=prompt, theme_id=theme_id)

    for attempt in range(retries + 1):
        logger.info(
            "TG.7.4.01 image_mode=%s attempt=%s session_id=%s step_ui=%s step0=%s reference_asset_id=%s",
            schedule.image_mode,
            attempt,
            session_id,
            step_ui,
            step0,
            reference_asset_id,
        )
        try:
            if image_mode == "t2i":
                image_bytes, mime, width, height, sha256 = generate_t2i(prompt)
            else:
                image_bytes, mime, width, height, sha256 = generate_i2i(
                    prompt,
                    reference_payload.bytes,
                    reference_payload.mime,
                )
            asset_id, storage_key = _store_asset(
                image_bytes=image_bytes,
                mime=mime,
                width=width,
                height=height,
                sha256=sha256,
            )
            role = "reference" if schedule.image_mode == "t2i" else "step_image"
            session_images.insert_session_image(
                session_id=session_id,
                step_ui=step_ui,
                asset_id=asset_id,
                role=role,
                reference_asset_id=reference_asset_id,
                image_model=image_model,
                prompt=prompt,
            )
            await bot.send_photo(
                chat_id=chat_id,
                photo=BufferedInputFile(image_bytes, filename=storage_key),
                caption="Иллюстрация",
                reply_to_message_id=step_message_id,
            )
            logger.info(
                "TG.7.4.01 image_outcome=ok session_id=%s step_ui=%s asset_id=%s reference_asset_id=%s",
                session_id,
                step_ui,
                asset_id,
                reference_asset_id,
            )
            if role == "reference":
                logger.info(
                    "TG.7.4.01 image.reference created session_id=%s step_ui=%s asset_id=%s",
                    session_id,
                    step_ui,
                    asset_id,
                )
            else:
                logger.info(
                    "TG.7.4.01 image.step_image created session_id=%s step_ui=%s asset_id=%s ref=%s",
                    session_id,
                    step_ui,
                    asset_id,
                    "yes" if reference_asset_id else "no",
                )
            return
        except MissingOpenRouterKeyError:
            logger.info(
                "TG.7.4.01 image_outcome=skipped reason=missing_api_key session_id=%s step_ui=%s",
                session_id,
                step_ui,
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "TG.7.4.01 image_outcome=error attempt=%s session_id=%s step_ui=%s reason=%s",
                attempt,
                session_id,
                step_ui,
                str(exc),
                exc_info=exc,
            )
            if attempt >= retries:
                return


@dataclass
class ReferencePayload:
    bytes: bytes
    mime: str


def _load_reference(asset_id: int) -> ReferencePayload | None:
    asset_row = assets.get_by_id(asset_id)
    if not asset_row:
        return None
    storage_key = asset_row.get("storage_key")
    if not isinstance(storage_key, str):
        return None
    mime = asset_row.get("mime")
    if not isinstance(mime, str):
        return None
    path = _resolve_storage_path(storage_key)
    if not path.exists():
        return None
    return ReferencePayload(bytes=path.read_bytes(), mime=mime)


async def _send_existing_image(
    *,
    bot: Bot,
    chat_id: int,
    step_message_id: int,
    image_bytes: bytes,
    storage_key: str,
) -> None:
    await bot.send_photo(
        chat_id=chat_id,
        photo=BufferedInputFile(image_bytes, filename=storage_key),
        caption="Иллюстрация",
        reply_to_message_id=step_message_id,
    )


def _resolve_storage_key(asset_id: int) -> str:
    asset_row = assets.get_by_id(asset_id)
    storage_key = asset_row.get("storage_key") if asset_row else None
    if isinstance(storage_key, str) and storage_key:
        return storage_key
    return f"{_ASSETS_IMAGE_DIR}/reference_{asset_id}.png"


def _build_reference_prompt(theme_id: str | None) -> str:
    theme_hint = theme_id or "универсальный стиль"
    return (
        "Детская книжная иллюстрация, единый стиль серии: "
        f"{theme_hint}. Без текста на изображении, без логотипов и водяных знаков, "
        "мягкие формы, чистый фон."
    )


def _build_step_prompt(scene_text: str) -> str:
    return (
        "Детская книжная иллюстрация по сцене: "
        f"{scene_text}. Без текста на изображении, без логотипов и водяных знаков."
    )


def _build_image_prompt(*, step_ui: int, prompt: str, theme_id: str | None) -> str:
    if step_ui == 1:
        return _build_reference_prompt(theme_id)
    return _build_step_prompt(prompt)


async def _wait_for_reference(
    session_id: int,
    *,
    attempts: int = 5,
    delay_s: float = 3.0,
) -> int | None:
    for idx in range(attempts):
        reference_asset_id = session_images.get_reference_asset_id(session_id)
        if reference_asset_id is not None:
            return reference_asset_id
        if idx < attempts - 1:
            await asyncio.sleep(delay_s)
    return None


def _resolve_retries() -> int:
    raw = os.getenv("IMAGE_RETRY", "1").strip()
    if not raw:
        return 1
    try:
        return max(0, int(raw))
    except ValueError:
        return 1


def _resolve_assets_root() -> Path:
    root = os.getenv(_ASSETS_ROOT_ENV, _DEFAULT_ASSETS_ROOT).strip()
    if not root:
        root = _DEFAULT_ASSETS_ROOT
    return Path(root)


def _resolve_storage_path(storage_key: str) -> Path:
    path = Path(storage_key)
    if path.is_absolute():
        return path
    return _resolve_assets_root() / storage_key


def _store_asset(
    *,
    image_bytes: bytes,
    mime: str,
    width: int | None,
    height: int | None,
    sha256: str | None = None,
) -> tuple[int, str]:
    digest = sha256 or hashlib.sha256(image_bytes).hexdigest()
    storage_key = f"{_ASSETS_IMAGE_DIR}/{digest}.png"
    path = _resolve_storage_path(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(image_bytes)
    asset_id = assets.insert_asset(
        kind="image",
        storage_backend="fs",
        storage_key=storage_key,
        mime=mime,
        bytes=len(image_bytes),
        sha256=digest,
        width=width,
        height=height,
    )
    return asset_id, storage_key
