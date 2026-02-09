from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from db.conn import transaction


def insert_session_image(
    session_id: int,
    step_ui: int,
    asset_id: int | None,
    role: str,
    reference_asset_id: int | None,
    image_model: str,
    prompt: str,
) -> int | None:
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
                ON CONFLICT (session_id, step_ui, role) DO UPDATE
                SET
                    asset_id = COALESCE(EXCLUDED.asset_id, session_images.asset_id),
                    reference_asset_id = COALESCE(EXCLUDED.reference_asset_id, session_images.reference_asset_id),
                    image_model = EXCLUDED.image_model,
                    prompt = EXCLUDED.prompt
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
            return int(row["id"]) if row else None


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


def get_reference_asset_id(session_id: int) -> int | None:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT asset_id
                FROM session_images
                WHERE session_id = %s AND role = 'reference'
                ORDER BY id
                LIMIT 1;
                """,
                (session_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return int(row["asset_id"])


def get_step_image_asset_id(session_id: int, step_ui: int) -> int | None:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT asset_id
                FROM session_images
                WHERE session_id = %s AND role = 'step_image' AND step_ui = %s
                ORDER BY id
                LIMIT 1;
                """,
                (session_id, step_ui),
            )
            row = cur.fetchone()
            if not row:
                return None
            return int(row["asset_id"])
