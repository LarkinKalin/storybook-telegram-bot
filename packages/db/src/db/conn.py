from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection
from psycopg_pool import ConnectionPool

_DB_URL_ENV = "DB_URL"
_pool: ConnectionPool | None = None


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


@contextmanager
def get_conn() -> Iterator[Connection]:
    with get_pool().connection() as conn:
        yield conn


@contextmanager
def transaction() -> Iterator[Connection]:
    with get_conn() as conn:
        with conn.transaction():
            yield conn
