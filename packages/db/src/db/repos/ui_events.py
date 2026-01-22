from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from db.conn import transaction


def insert_idempotent(
    session_id: int,
    step: int,
    kind: str,
    content_hash: str,
    payload: dict[str, Any] | None = None,
) -> str:
    del payload
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO ui_events (
                    session_id,
                    step,
                    kind,
                    content_hash,
                    state,
                    pending_since
                )
                VALUES (%s, %s, %s, %s, 'PENDING', now())
                ON CONFLICT (session_id, step, kind, content_hash) DO NOTHING
                RETURNING id;
                """,
                (session_id, step, kind, content_hash),
            )
            row = cur.fetchone()
            return "inserted" if row else "duplicate"
