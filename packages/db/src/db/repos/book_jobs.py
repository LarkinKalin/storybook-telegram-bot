from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from db.conn import transaction


def get_by_session_kind(session_id: int, kind: str = "book_v1") -> dict[str, Any] | None:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM book_jobs
                WHERE session_id = %s AND kind = %s
                LIMIT 1;
                """,
                (session_id, kind),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def upsert_status(
    session_id: int,
    *,
    kind: str = "book_v1",
    status: str,
    result_pdf_asset_id: int | None = None,
    script_json_asset_id: int | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO book_jobs (
                    session_id,
                    kind,
                    status,
                    result_pdf_asset_id,
                    script_json_asset_id,
                    error_message,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (session_id, kind) DO UPDATE
                SET
                    status = EXCLUDED.status,
                    result_pdf_asset_id = COALESCE(EXCLUDED.result_pdf_asset_id, book_jobs.result_pdf_asset_id),
                    script_json_asset_id = COALESCE(EXCLUDED.script_json_asset_id, book_jobs.script_json_asset_id),
                    error_message = EXCLUDED.error_message,
                    updated_at = now()
                RETURNING *;
                """,
                (
                    session_id,
                    kind,
                    status,
                    result_pdf_asset_id,
                    script_json_asset_id,
                    error_message,
                ),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("failed to upsert book job")
            return dict(row)
