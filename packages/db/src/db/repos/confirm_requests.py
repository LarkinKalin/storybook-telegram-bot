from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from db.conn import to_json, transaction
from db.repos import users

_DEFAULT_KIND = "GENERIC"


def _ensure_user_id(tg_id: int) -> int:
    user = users.get_or_create_by_tg_id(tg_id)
    return int(user["id"])


def create(
    tg_id: int,
    rid8: str,
    payload: dict[str, Any] | None = None,
    ttl_sec: int = 600,
) -> None:
    user_id = _ensure_user_id(tg_id)
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO confirm_requests (
                    user_id,
                    tg_id,
                    rid8,
                    kind,
                    payload_json,
                    expires_at
                )
                VALUES (%s, %s, %s, %s, %s, now() + (%s * interval '1 second'))
                ON CONFLICT (rid8) DO NOTHING;
                """,
                (user_id, tg_id, rid8, _DEFAULT_KIND, to_json(payload), ttl_sec),
            )


def get(tg_id: int, rid8: str) -> dict[str, Any] | None:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM confirm_requests
                WHERE tg_id = %s AND rid8 = %s;
                """,
                (tg_id, rid8),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def consume(tg_id: int, rid8: str) -> bool:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE confirm_requests
                SET status = 'USED', result = 'YES', used_at = now()
                WHERE tg_id = %s
                  AND rid8 = %s
                  AND status = 'PENDING'
                  AND expires_at > now();
                """,
                (tg_id, rid8),
            )
            return cur.rowcount > 0
