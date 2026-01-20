from __future__ import annotations

from typing import Literal

ReadMode = Literal["kid", "adult"]

_read_mode_by_user: dict[int, ReadMode] = {}


def get_read_mode(tg_id: int) -> ReadMode:
    return _read_mode_by_user.get(tg_id, "kid")


def set_read_mode(tg_id: int, mode: ReadMode) -> None:
    _read_mode_by_user[tg_id] = mode
