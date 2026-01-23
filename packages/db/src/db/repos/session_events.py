from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from db.conn import to_json, transaction


def append_event(
    session_id: int,
    step: int,
    user_input: str | None,
    choice_id: str | None,
    llm_json: dict[str, Any] | None,
    deltas_json: dict[str, Any] | None,
) -> str:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO session_events (
                    session_id,
                    step,
                    user_input,
                    choice_id,
                    llm_json,
                    deltas_json
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id, step) DO NOTHING
                RETURNING id;
                """,
                (
                    session_id,
                    step,
                    user_input,
                    choice_id,
                    to_json(llm_json),
                    to_json(deltas_json),
                ),
            )
            row = cur.fetchone()
            return "inserted" if row else "duplicate"


def exists_for_step(session_id: int, step: int) -> bool:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM session_events
                WHERE session_id = %s AND step = %s
                LIMIT 1;
                """,
                (session_id, step),
            )
            return cur.fetchone() is not None


def exists_for_fingerprint(session_id: int, fingerprint: str) -> bool:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM session_events
                WHERE session_id = %s
                  AND llm_json ->> 'turn_fingerprint' = %s
                LIMIT 1;
                """,
                (session_id, fingerprint),
            )
            return cur.fetchone() is not None
