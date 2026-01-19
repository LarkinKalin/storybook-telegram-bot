from __future__ import annotations

_active: set[int] = set()


def has_active(tg_id: int) -> bool:
    return tg_id in _active


def set_active(tg_id: int, active: bool) -> None:
    if active:
        _active.add(tg_id)
    else:
        _active.discard(tg_id)
