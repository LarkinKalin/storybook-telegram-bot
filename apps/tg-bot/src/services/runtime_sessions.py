from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from db.repos import sessions, users

SessionStatus = Literal["ACTIVE", "FINISHED", "ABORTED"]


@dataclass
class Session:
    id: int
    tg_id: int
    status: SessionStatus
    theme_id: str | None
    step: int
    max_steps: int
    params_json: dict
    facts_json: dict
    ending_id: str | None
    last_step_message_id: int | None
    last_step_sent_at: int | None


def _to_epoch(value: datetime | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return int(value.timestamp())
    return int(value)


def _row_to_session(row: dict | None) -> Session | None:
    if not row:
        return None
    return Session(
        id=int(row["id"]),
        tg_id=int(row["tg_id"]),
        status=row["status"],
        theme_id=row["theme_id"],
        step=int(row.get("step", 0)),
        max_steps=int(row.get("max_steps", 1)),
        params_json=row.get("params_json") or {},
        facts_json=row.get("facts_json") or {},
        ending_id=row.get("ending_id"),
        last_step_message_id=row.get("last_step_message_id"),
        last_step_sent_at=_to_epoch(row.get("last_step_sent_at")),
    )


def _get_user_id(tg_id: int) -> int:
    user = users.get_or_create_by_tg_id(tg_id)
    return int(user["id"])


def get_session(tg_id: int) -> Session | None:
    user_id = _get_user_id(tg_id)
    row = sessions.get_active(user_id)
    return _row_to_session(row)


def has_active(tg_id: int) -> bool:
    return get_session(tg_id) is not None


def start_session(tg_id: int, theme_id: str | None, max_steps: int = 1) -> Session:
    user_id = _get_user_id(tg_id)
    row = sessions.create_new_active(user_id, theme_id, meta={"max_steps": max_steps})
    session = _row_to_session(row)
    if session is None:
        raise RuntimeError("Failed to start session")
    if not session.params_json or session.params_json.get("v") != "0.1":
        from packages.engine.src.engine_v0_1 import init_state_v01

        engine_state = init_state_v01(max_steps)
        sessions.update_params_json(session.id, engine_state)
    return session


def finish_session(tg_id: int) -> None:
    session = get_session(tg_id)
    if session:
        sessions.finish(session.id, status="FINISHED")


def abort_session(tg_id: int) -> None:
    session = get_session(tg_id)
    if session:
        sessions.finish(session.id, status="ABORTED")


def touch_last_step(tg_id: int, message_id: int, sent_at: int) -> None:
    session = get_session(tg_id)
    if not session:
        return
    sessions.update_last_step(session.id, message_id, sent_at)
