import os
import threading
from time import time_ns

import pytest

from db.conn import get_conn
from db.repos import l3_turns, session_events, sessions, users


def test_apply_l3_turn_atomic_duplicate_under_concurrency() -> None:
    if not os.getenv("DB_URL"):
        pytest.skip("DB_URL not set")
    tg_id = int(time_ns() % 1_000_000_000)
    user = users.get_or_create_by_tg_id(tg_id, display_name="concurrency_test")
    session_row = sessions.create_new_active(
        user_id=user["id"],
        theme_id="test",
        player_name="tester",
        meta={"max_steps": 2, "v": "0.1"},
    )
    sid8 = session_row["sid8"]
    expected_step = 0
    step_result_json = {
        "text": "Шаг 1/2.\nТестовый шаг.\n\nВыбор:\nA",
        "choices": [{"choice_id": "a", "label": "A"}],
        "allow_free_text": False,
        "final_id": None,
    }

    barrier = threading.Barrier(2)
    results: list[l3_turns.L3ApplyResult | None] = []

    def apply_fn(session_row: dict) -> l3_turns.L3ApplyPayload:
        return l3_turns.L3ApplyPayload(
            new_state={
                "v": "0.1",
                "step0": 1,
                "n": 2,
                "free_text_allowed_after": 0,
            },
            llm_json={"engine_step_log": {"applied_deltas": []}},
            deltas_json={"applied_deltas": []},
            step_result_json=step_result_json,
            meta_json={"turn_fingerprint": "test"},
            finish_status=None,
            final_id=None,
            final_meta=None,
        )

    def worker() -> None:
        barrier.wait()
        result = l3_turns.apply_l3_turn_atomic(
            tg_id=tg_id,
            sid8=sid8,
            expected_step=expected_step,
            step=expected_step,
            user_input="A",
            choice_id="a",
            apply_fn=apply_fn,
        )
        results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    outcomes = sorted(result.outcome for result in results if result)
    assert outcomes == ["accepted", "duplicate"]

    duplicate_result = next(result for result in results if result and result.outcome == "duplicate")
    assert duplicate_result.event
    assert duplicate_result.event["step_result_json"] == step_result_json

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)
                FROM session_events
                WHERE session_id = %s AND step = %s;
                """,
                (session_row["id"], expected_step),
            )
            assert cur.fetchone()[0] == 1
