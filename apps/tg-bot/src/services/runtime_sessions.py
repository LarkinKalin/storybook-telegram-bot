from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SessionStatus = Literal["ACTIVE", "FINISHED", "ABORTED"]


@dataclass
class Session:
    tg_id: int
    status: SessionStatus
    theme_id: str | None
    step: int
    max_steps: int
    last_step_message_id: int | None
    last_step_sent_at: int | None


_sessions: dict[int, Session] = {}


def get_session(tg_id: int) -> Session | None:
    return _sessions.get(tg_id)


def has_active(tg_id: int) -> bool:
    session = _sessions.get(tg_id)
    return session is not None and session.status == "ACTIVE"


def start_session(tg_id: int, theme_id: str | None, max_steps: int = 1) -> Session:
    session = Session(
        tg_id=tg_id,
        status="ACTIVE",
        theme_id=theme_id,
        step=0,
        max_steps=max_steps,
        last_step_message_id=None,
        last_step_sent_at=None,
    )
    _sessions[tg_id] = session
    return session


def finish_session(tg_id: int) -> None:
    session = _sessions.get(tg_id)
    if session:
        session.status = "FINISHED"


def abort_session(tg_id: int) -> None:
    session = _sessions.get(tg_id)
    if session:
        session.status = "ABORTED"


def touch_last_step(tg_id: int, message_id: int, sent_at: int) -> None:
    session = _sessions.get(tg_id)
    if not session:
        return
    session.last_step_message_id = message_id
    session.last_step_sent_at = sent_at
