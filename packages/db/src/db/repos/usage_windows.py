from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from db.conn import transaction

_ALLOWED_KINDS = {
    "messages_used": "messages_used",
    "sessions_started": "sessions_started",
}


def upsert_counter(
    user_id: int,
    kind: str,
    window_sec: int = 43200,
    delta: int = 1,
) -> dict[str, Any]:
    if kind not in _ALLOWED_KINDS:
        raise ValueError("kind must be messages_used or sessions_started")
    column = _ALLOWED_KINDS[kind]

    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM usage_windows
                WHERE user_id = %s
                  AND now() >= window_start
                  AND now() < window_end
                ORDER BY window_start DESC
                LIMIT 1
                FOR UPDATE;
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    f"""
                    UPDATE usage_windows
                    SET {column} = {column} + %s, updated_at = now()
                    WHERE id = %s
                    RETURNING *;
                    """,
                    (delta, row["id"]),
                )
                updated = cur.fetchone()
                return dict(updated)

            cur.execute(
                f"""
                INSERT INTO usage_windows (
                    user_id,
                    window_start,
                    window_end,
                    {column}
                )
                VALUES (%s, now(), now() + (%s * interval '1 second'), %s)
                RETURNING *;
                """,
                (user_id, window_sec, delta),
            )
            inserted = cur.fetchone()
            return dict(inserted)


def read_counters(user_id: int, window_sec: int = 43200) -> dict[str, Any]:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM usage_windows
                WHERE user_id = %s
                  AND now() >= window_start
                  AND now() < window_end
                ORDER BY window_start DESC
                LIMIT 1;
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                return dict(row)

    return {
        "user_id": user_id,
        "window_start": None,
        "window_end": None,
        "messages_used": 0,
        "sessions_started": 0,
        "blocked_until": None,
        "window_sec": window_sec,
    }
