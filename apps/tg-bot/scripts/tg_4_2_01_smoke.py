from __future__ import annotations

import os

from db.conn import transaction
from db.repos import sessions, users
from src.services.runtime_sessions import start_session
from src.services.story_runtime import advance_turn


def _print_db_state(session_id: int) -> None:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT params_json, ending_id, step
                FROM sessions
                WHERE id = %s;
                """,
                (session_id,),
            )
            row = cur.fetchone()
            print("session:", row)
            cur.execute(
                """
                SELECT step, choice_id, user_input, llm_json, deltas_json
                FROM session_events
                WHERE session_id = %s
                ORDER BY step ASC;
                """,
                (session_id,),
            )
            events = cur.fetchall()
            print("events:", events)


def main() -> None:
    tg_id = int(os.getenv("TG_ID", "999000"))
    users.get_or_create_by_tg_id(tg_id)
    session = start_session(tg_id, theme_id="stub", max_steps=8)
    session_id = session.id
    user_row = users.get_or_create_by_tg_id(tg_id)
    active = sessions.get_active(user_row["id"])
    if not active:
        raise RuntimeError("No active session created")
    session_row = dict(active)
    for idx, choice_id in enumerate(["A", "B", "C"], start=1):
        view = advance_turn(
            session_row,
            {"kind": "choice", "choice_id": choice_id},
            source_message_id=1000 + idx,
        )
        if view is None:
            print("duplicate turn ignored")
            break
        if view.final_id:
            print("final_id:", view.final_id)
            break
        refreshed = sessions.get_active(user_row["id"])
        if not refreshed:
            break
        session_row = dict(refreshed)
    _print_db_state(session_id)


if __name__ == "__main__":
    main()
