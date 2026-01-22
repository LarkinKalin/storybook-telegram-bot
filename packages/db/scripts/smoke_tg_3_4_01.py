from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from db.repos import session_events, sessions, users  # noqa: E402


def main() -> int:
    if not os.getenv("DB_URL"):
        print("DB_URL is not set")
        return 1

    print("Smoke TG.3.4.01 starting...")
    user = users.get_or_create_by_tg_id(123456789, tg_username="smoke_test")
    user_id = int(user["id"])
    print(f"User ready: id={user_id}")

    session = sessions.create_new_active(user_id, theme_id="smoke", meta={"max_steps": 1})
    session_id = int(session["id"])
    print(f"Session created: id={session_id}")

    active = sessions.get_active(user_id)
    print(f"Active session found: {active is not None}")

    status_first = session_events.append_event(
        session_id,
        step=1,
        user_input="hello",
        choice_id=None,
        llm_json={"narration": "test"},
        deltas_json=None,
    )
    status_second = session_events.append_event(
        session_id,
        step=1,
        user_input="hello again",
        choice_id=None,
        llm_json={"narration": "test"},
        deltas_json=None,
    )
    print(f"Event insert statuses: {status_first}, {status_second}")

    sessions.finish(session_id, status="FINISHED")
    active_after = sessions.get_active(user_id)
    print(f"Active session after finish: {active_after is None}")

    print("Smoke TG.3.4.01 completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
