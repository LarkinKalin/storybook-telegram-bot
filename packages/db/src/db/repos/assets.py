from __future__ import annotations

from psycopg.rows import dict_row

from db.conn import transaction


def insert_asset(
    kind: str,
    storage_backend: str,
    storage_key: str,
    mime: str,
    bytes: int,
    sha256: str,
    width: int | None = None,
    height: int | None = None,
) -> int:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO assets (
                    kind,
                    storage_backend,
                    storage_key,
                    mime,
                    bytes,
                    sha256,
                    width,
                    height
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    kind,
                    storage_backend,
                    storage_key,
                    mime,
                    bytes,
                    sha256,
                    width,
                    height,
                ),
            )
            row = cur.fetchone()
            return int(row["id"])
