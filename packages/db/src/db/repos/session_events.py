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
