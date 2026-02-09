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
    story_step_ui: int
    total_steps: int
    has_image_scene_brief: bool = False

    @property
    def needs_image(self) -> bool:
        return self.has_image_scene_brief and self.story_step_ui in image_steps(self.total_steps)

    @property
    def image_mode(self) -> str:
        return "t2i" if self.story_step_ui == 1 else "i2i"


def image_steps(_total_steps: int) -> set[int]:
    if _total_steps in {8, 10}:
        return {1, 4, 8}
    if _total_steps == 12:
        return {1, 5, 9}
    midpoint = max(1, round(_total_steps / 2))
    return {1, midpoint, _total_steps}


def _step_images_enabled() -> bool:
    raw = os.getenv("SKAZKA_STEP_IMAGES", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def resolve_story_step_ui(engine_step: int) -> int:
    """Engine step is zero-based (step0); UI/story steps are 1-based."""
    return engine_step + 1


def _resolve_call_reason(*, enabled: bool, in_plan: bool, has_scene_brief: bool) -> str:
    if not enabled:
        return "feature_disabled"
    if not in_plan:
        return "step_not_in_plan"
    if not has_scene_brief:
        return "no_image_scene_brief"
    return "eligible_for_image"


def schedule_image_delivery(
    *,
    bot: Bot,
    chat_id: int,
    step_message_id: int,
    session_id: int,
    engine_step: int,
    step_ui: int,
    story_step_ui: int,
    total_steps: int,
    prompt: str,
    theme_id: str | None = None,
    image_scene_brief: str | None = None,
) -> None:
    enabled = _step_images_enabled()
    has_image_scene_brief = isinstance(image_scene_brief, str) and image_scene_brief.strip() != ""
    schedule = ImageSchedule(
        story_step_ui=story_step_ui,
        total_steps=total_steps,
        has_image_scene_brief=has_image_scene_brief,
    )
    in_plan = story_step_ui in image_steps(total_steps)
    reason = _resolve_call_reason(
        enabled=enabled,
        in_plan=in_plan,
        has_scene_brief=has_image_scene_brief,
    )
    logger.warning(
        "TG.7.4.01 called session_id=%s engine_step=%s step_ui=%s story_step_ui=%s steps_total=%s enabled=%s reason=%s",
        session_id,
        engine_step,
        step_ui,
        story_step_ui,
        total_steps,
        "true" if enabled else "false",
        reason,
    )
    if reason != "eligible_for_image":
        logger.warning(
            "TG.7.4.01 image_outcome outcome=skipped reason=%s session_id=%s step_ui=%s story_step_ui=%s",
            reason,
            session_id,
            step_ui,
            story_step_ui,
        )
        return
    image_model = os.getenv("OPENROUTER_MODEL_IMAGE", "black-forest-labs/flux.2-pro").strip()
    scheduled_id = session_images.insert_session_image(
        session_id=session_id,
        step_ui=story_step_ui,
        asset_id=None,
        role="step_image",
        reference_asset_id=None,
        image_model=image_model,
        prompt=image_scene_brief.strip() if isinstance(image_scene_brief, str) else prompt,
    )
    logger.warning(
        "TG.7.4.01 image_scheduled session_id=%s step_ui=%s story_step_ui=%s session_image_id=%s",
        session_id,
        step_ui,
        story_step_ui,
        scheduled_id,
    )
    asyncio.create_task(
        _generate_and_send_image(
            bot=bot,
            chat_id=chat_id,
            step_message_id=step_message_id,
            session_id=session_id,
            step_ui=step_ui,
            story_step_ui=story_step_ui,
            total_steps=total_steps,
            prompt=prompt,
            theme_id=theme_id,
            image_scene_brief=image_scene_brief,
        )
    )


async def _generate_and_send_image(
    *,
    bot: Bot,
    chat_id: int,
    step_message_id: int,
    session_id: int,
    step_ui: int,
    story_step_ui: int,
    total_steps: int,
    prompt: str,
    theme_id: str | None,
    image_scene_brief: str | None,
) -> None:
    has_image_scene_brief = isinstance(image_scene_brief, str) and image_scene_brief.strip() != ""
    schedule = ImageSchedule(
        story_step_ui=story_step_ui,
        total_steps=total_steps,
        has_image_scene_brief=has_image_scene_brief,
    )
    if not schedule.needs_image:
        return

    image_model = os.getenv("OPENROUTER_MODEL_IMAGE", "black-forest-labs/flux.2-pro").strip()
    retries = _resolve_retries()
    reference_asset_id = None
    reference_payload = None
    image_mode = schedule.image_mode
    if schedule.image_mode != "t2i":
        reference_asset_id = session_images.get_step_image_asset_id(session_id, step_ui=1)
        if reference_asset_id is not None:
            reference_payload = _load_reference(reference_asset_id)
        if reference_payload is None:
            logger.warning(
                "TG.7.4.01 image_outcome outcome=skipped reason=no_reference session_id=%s step_ui=%s story_step_ui=%s",
                session_id,
                step_ui,
                story_step_ui,
            )
            return

    prompt = _build_image_prompt(
        step_ui=story_step_ui,
        prompt=prompt,
        theme_id=theme_id,
        image_scene_brief=image_scene_brief,
    )
    for attempt in range(retries + 1):
        logger.warning(
            "TG.7.4.01 image_provider_called provider=openrouter mode=%s attempt=%s session_id=%s step_ui=%s story_step_ui=%s reference_asset_id=%s",
            image_mode,
            attempt,
            session_id,
            step_ui,
            story_step_ui,
            reference_asset_id,
        )
        logger.info(
            "TG.7.4.01 image_mode=%s attempt=%s session_id=%s step_ui=%s story_step_ui=%s reference_asset_id=%s",
            schedule.image_mode,
            attempt,
            session_id,
            step_ui,
            story_step_ui,
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
            role = "step_image"
            session_images.insert_session_image(
                session_id=session_id,
                step_ui=story_step_ui,
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
            logger.warning(
                "TG.7.4.01 image_outcome outcome=ok reason=provider_success attempt=%s session_id=%s step_ui=%s asset_id=%s reference_asset_id=%s",
                attempt,
                session_id,
                step_ui,
                asset_id,
                reference_asset_id,
            )
            logger.info(
                "TG.7.4.01 image.step_image created session_id=%s step_ui=%s asset_id=%s ref=%s",
                session_id,
                step_ui,
                asset_id,
                "yes" if reference_asset_id else "no",
            )
            return
        except MissingOpenRouterKeyError:
            logger.warning(
                "TG.7.4.01 image_outcome outcome=error reason=missing_api_key session_id=%s step_ui=%s",
                session_id,
                step_ui,
            )
            return
        except Exception as exc:  # noqa: BLE001
            reason = "simulated_failure" if "simulated image provider failure" in str(exc).lower() else "provider_error"
            logger.warning(
                "TG.7.4.01 image_outcome outcome=error reason=%s attempt=%s session_id=%s step_ui=%s",
                reason,
                attempt,
                session_id,
                step_ui,
                exc_info=exc,
            )
            if attempt >= retries:
                logger.warning(
                    "TG.7.4.01 image_outcome outcome=error reason=provider_error_final session_id=%s step_ui=%s",
                    session_id,
                    step_ui,
                    exc_info=exc,
                )
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


def _build_image_prompt(
    *,
    step_ui: int,
    prompt: str,
    theme_id: str | None,
    image_scene_brief: str | None,
) -> str:
    if isinstance(image_scene_brief, str) and image_scene_brief.strip():
        return image_scene_brief.strip()
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
        reference_asset_id = session_images.get_step_image_asset_id(session_id, step_ui=1)
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
