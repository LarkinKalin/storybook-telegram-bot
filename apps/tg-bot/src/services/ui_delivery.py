from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from time import time
from typing import Literal

from aiogram.types import Message, ReplyKeyboardRemove

from db.repos import sessions, ui_events
from src.services.story_runtime import StepView

UiDecision = Literal["show", "skip"]


@dataclass
class UiAcquireResult:
    decision: UiDecision
    event_id: int | None


def _normalize_content(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`~]", "", text)
    return text.strip()


def content_hash(*, theme_id: str | None, text: str) -> str:
    base = f"{theme_id or 'none'}:{_normalize_content(text)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def acquire_step_event(
    *,
    session_id: int,
    step: int,
    kind: str,
    content_hash_value: str,
) -> UiAcquireResult:
    outcome = ui_events.acquire_event(
        session_id=session_id,
        step=step,
        kind=kind,
        content_hash=content_hash_value,
    )
    return UiAcquireResult(decision=outcome["decision"], event_id=outcome.get("event_id"))


async def deliver_step_view(
    *,
    message: Message,
    step_view: StepView,
    session_id: int,
    step: int,
    theme_id: str | None,
    kind: str = "recap_shown",
) -> bool:
    content_hash_value = content_hash(theme_id=theme_id, text=step_view.text)
    acquire = acquire_step_event(
        session_id=session_id,
        step=step,
        kind=kind,
        content_hash_value=content_hash_value,
    )
    if acquire.decision != "show" or acquire.event_id is None:
        return False

    try:
        sent_message = await message.answer("...", reply_markup=ReplyKeyboardRemove())
        step_message = sent_message
        try:
            await message.bot.edit_message_text(
                step_view.text,
                chat_id=sent_message.chat.id,
                message_id=sent_message.message_id,
                reply_markup=step_view.keyboard,
            )
        except Exception:
            try:
                await message.bot.delete_message(
                    chat_id=sent_message.chat.id,
                    message_id=sent_message.message_id,
                )
            except Exception:
                pass
            step_message = await message.answer(step_view.text, reply_markup=step_view.keyboard)
    except Exception:
        try:
            ui_events.mark_failed(acquire.event_id)
        except Exception:
            pass
        return False

    try:
        ui_events.mark_shown(acquire.event_id, step_message_id=step_message.message_id)
    except Exception:
        return True

    try:
        sessions.update_last_step(session_id, step_message.message_id, int(time()))
    except Exception:
        return True
    return True


def mark_delivery_failed(event_id: int) -> None:
    ui_events.mark_failed(event_id)
