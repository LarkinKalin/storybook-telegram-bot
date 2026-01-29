from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from db.conn import transaction


def insert_session_image(
    session_id: int,
    step_ui: int,
    asset_id: int,
    role: str,
    reference_asset_id: int | None,
    image_model: str,
    prompt: str,
) -> int:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO session_images (
                    session_id,
                    step_ui,
                    asset_id,
                    role,
                    reference_asset_id,
                    image_model,
                    prompt
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    session_id,
                    step_ui,
                    asset_id,
                    role,
                    reference_asset_id,
                    image_model,
                    prompt,
                ),
            )
            row = cur.fetchone()
            return int(row["id"])


def list_session_images(session_id: int) -> list[dict[str, Any]]:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM session_images
                WHERE session_id = %s
                ORDER BY id;
                """,
                (session_id,),
            )
            return [dict(row) for row in cur.fetchall()]
