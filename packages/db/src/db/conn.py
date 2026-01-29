from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection, OperationalError
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

_DB_URL_ENV = "DB_URL"
_pool: ConnectionPool | None = None
logger = logging.getLogger(__name__)


class DBUnavailable(RuntimeError):
    pass


def _get_db_url() -> str:
    db_url = os.getenv(_DB_URL_ENV)
    if not db_url:
        raise RuntimeError(f"{_DB_URL_ENV} is not set")
    return db_url


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(conninfo=_get_db_url(), min_size=1, max_size=5, open=True)
    return _pool


def to_json(value: object | None) -> Json | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return Json(value)
    return Json(value)


@contextmanager
def get_conn() -> Iterator[Connection]:
    try:
        with get_pool().connection() as conn:
            yield conn
    except OperationalError as exc:
        logger.exception("DB connection failed", exc_info=True)
        _reset_pool()
        raise DBUnavailable("DB connection failed") from exc


@contextmanager
def transaction() -> Iterator[Connection]:
    try:
        with get_conn() as conn:
            with conn.transaction():
                yield conn
    except OperationalError as exc:
        logger.exception("DB transaction failed", exc_info=True)
        _reset_pool()
        raise DBUnavailable("DB transaction failed") from exc


def _reset_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
