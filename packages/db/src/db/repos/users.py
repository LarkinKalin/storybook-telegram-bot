from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from db.conn import transaction


def get_or_create_by_tg_id(
    tg_id: int,
    tg_username: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    resolved_display_name = display_name or tg_username or f"user_{tg_id}"

    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO users (tg_id, display_name, tg_username)
                VALUES (%s, %s, %s)
                ON CONFLICT (tg_id)
                DO UPDATE SET
                    tg_username = COALESCE(EXCLUDED.tg_username, users.tg_username),
                    updated_at = now()
                RETURNING id, tg_id, display_name;
                """,
                (tg_id, resolved_display_name, tg_username),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("Failed to fetch user row")
            return dict(row)
