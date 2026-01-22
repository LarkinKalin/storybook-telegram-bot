from __future__ import annotations

import secrets
import string
from typing import Any

from psycopg.rows import dict_row

from db.conn import to_json, transaction

_ALLOWED_FINISH_STATUSES = {"FINISHED", "ABORTED"}
_SID8_ALPHABET = string.ascii_lowercase + string.digits


def _generate_sid8() -> str:
    return "".join(secrets.choice(_SID8_ALPHABET) for _ in range(8))


def get_active(user_id: int) -> dict[str, Any] | None:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM sessions
                WHERE user_id = %s AND status = 'ACTIVE'
                ORDER BY id DESC
                LIMIT 1;
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def create_new_active(
    user_id: int,
    theme_id: str | None = None,
    player_name: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = meta or {}
    max_steps = payload.get("max_steps", 1)
    if not isinstance(max_steps, int) or max_steps <= 0:
        max_steps = 1

    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tg_id, display_name
                FROM users
                WHERE id = %s;
                """,
                (user_id,),
            )
            user_row = cur.fetchone()
            if not user_row:
                raise ValueError(f"User {user_id} not found")

            cur.execute(
                """
                UPDATE sessions
                SET status = 'ABORTED', updated_at = now()
                WHERE user_id = %s AND status = 'ACTIVE';
                """,
                (user_id,),
            )

            resolved_player_name = player_name or user_row["display_name"]
            session_row = None
            while session_row is None:
                sid8 = _generate_sid8()
                cur.execute(
                    """
                    INSERT INTO sessions (
                        user_id,
                        tg_id,
                        sid8,
                        status,
                        theme_id,
                        step,
                        max_steps,
                        player_name,
                        params_json,
                        facts_json
                    )
                    VALUES (%s, %s, %s, 'ACTIVE', %s, 0, %s, %s, %s, '{}'::jsonb)
                    ON CONFLICT (sid8) DO NOTHING
                    RETURNING id, user_id, tg_id, sid8, status, theme_id, step, max_steps, player_name;
                    """,
                    (
                        user_id,
                        user_row["tg_id"],
                        sid8,
                        theme_id,
                        max_steps,
                        resolved_player_name,
                        to_json(payload),
                    ),
                )
                session_row = cur.fetchone()
            return dict(session_row)


def finish(session_id: int, status: str = "FINISHED") -> None:
    if status not in _ALLOWED_FINISH_STATUSES:
        raise ValueError("status must be FINISHED or ABORTED")

    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sessions
                SET status = %s, updated_at = now()
                WHERE id = %s;
                """,
                (status, session_id),
            )


def update_last_step(
    session_id: int,
    message_id: int | None,
    sent_at: int | None,
) -> None:
    with transaction() as conn:
        with conn.cursor() as cur:
            if sent_at is None:
                cur.execute(
                    """
                    UPDATE sessions
                    SET last_step_message_id = %s,
                        last_step_sent_at = NULL,
                        updated_at = now()
                    WHERE id = %s;
                    """,
                    (message_id, session_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE sessions
                    SET last_step_message_id = %s,
                        last_step_sent_at = to_timestamp(%s),
                        updated_at = now()
                    WHERE id = %s;
                    """,
                    (message_id, sent_at, session_id),
                )


def update_step(session_id: int, step: int) -> None:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sessions
                SET step = %s, updated_at = now()
                WHERE id = %s;
                """,
                (step, session_id),
            )
