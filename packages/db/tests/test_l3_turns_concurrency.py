import os
import socket
import subprocess
import threading
import time
import uuid
from time import time_ns

import psycopg

from typing import Callable

from db.conn import get_conn
from db.migrations_runner import apply_migrations
from db.repos import l3_turns, session_events, sessions, users


def test_apply_l3_turn_atomic_duplicate_under_concurrency() -> None:
    container_id = None
    if not os.getenv("DB_URL"):
        if _docker_available():
            container_id, db_url = _start_postgres_container()
            os.environ["DB_URL"] = db_url
        else:
            _run_in_memory_concurrency_test()
            return
    try:
        _wait_for_db_ready()
        apply_migrations()
        _run_concurrent_duplicate_test()
    finally:
        if container_id:
            subprocess.run(["docker", "rm", "-f", container_id], check=False)


def _run_concurrent_duplicate_test(
    *,
    assert_event_count: Callable[[int, int], None] | None = None,
) -> None:
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

    if assert_event_count is None:
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
    else:
        assert_event_count(session_row["id"], expected_step)


def _run_in_memory_concurrency_test() -> None:
    store = _InMemoryStore()
    original_transaction = l3_turns.transaction
    original_sessions = (
        sessions.create_new_active,
        sessions.get_by_tg_id_sid8_for_update,
        sessions.update_params_json_in_tx,
        sessions.update_step_in_tx,
        sessions.finish_with_final_in_tx,
        sessions.finish_in_tx,
    )
    original_events = (
        session_events.insert_event,
        session_events.get_by_step,
        session_events.update_event_payload,
    )
    original_users = users.get_or_create_by_tg_id
    try:
        l3_turns.transaction = store.transaction
        sessions.create_new_active = store.create_new_active
        sessions.get_by_tg_id_sid8_for_update = store.get_by_tg_id_sid8_for_update
        sessions.update_params_json_in_tx = store.update_params_json_in_tx
        sessions.update_step_in_tx = store.update_step_in_tx
        sessions.finish_with_final_in_tx = store.finish_with_final_in_tx
        sessions.finish_in_tx = store.finish_in_tx
        session_events.insert_event = store.insert_event
        session_events.get_by_step = store.get_by_step
        session_events.update_event_payload = store.update_event_payload
        users.get_or_create_by_tg_id = store.get_or_create_by_tg_id
        _run_concurrent_duplicate_test(assert_event_count=store.assert_event_count)
    finally:
        l3_turns.transaction = original_transaction
        (
            sessions.create_new_active,
            sessions.get_by_tg_id_sid8_for_update,
            sessions.update_params_json_in_tx,
            sessions.update_step_in_tx,
            sessions.finish_with_final_in_tx,
            sessions.finish_in_tx,
        ) = original_sessions
        (
            session_events.insert_event,
            session_events.get_by_step,
            session_events.update_event_payload,
        ) = original_events
        users.get_or_create_by_tg_id = original_users


class _InMemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._user_id = 1
        self._session_id = 1
        self._event_id = 1
        self._users: dict[int, dict] = {}
        self._sessions: dict[tuple[int, str], dict] = {}
        self._events: dict[tuple[int, int], dict] = {}

    def transaction(self):  # noqa: ANN001, ANN201 - matches contextmanager signature
        return _LockContext(self._lock)

    def get_or_create_by_tg_id(self, tg_id: int, **kwargs) -> dict:
        for row in self._users.values():
            if row["tg_id"] == tg_id:
                return row
        row = {"id": self._user_id, "tg_id": tg_id, "display_name": kwargs.get("display_name", "")}
        self._users[self._user_id] = row
        self._user_id += 1
        return row

    def create_new_active(self, user_id: int, theme_id: str, meta: dict, player_name: str | None = None) -> dict:
        sid8 = f"sid{self._session_id:04d}"
        row = {
            "id": self._session_id,
            "user_id": user_id,
            "tg_id": self._users[user_id]["tg_id"],
            "sid8": sid8,
            "status": "ACTIVE",
            "theme_id": theme_id,
            "step": 0,
            "max_steps": meta.get("max_steps", 1),
            "player_name": player_name or "tester",
            "params_json": meta,
        }
        self._sessions[(row["tg_id"], sid8)] = row
        self._session_id += 1
        return row

    def get_by_tg_id_sid8_for_update(self, _conn, tg_id: int, sid8: str) -> dict | None:
        return self._sessions.get((tg_id, sid8))

    def update_params_json_in_tx(self, _conn, session_id: int, params_json: dict) -> None:
        for row in self._sessions.values():
            if row["id"] == session_id:
                row["params_json"] = params_json
                return

    def update_step_in_tx(self, _conn, session_id: int, step: int) -> None:
        return

    def finish_with_final_in_tx(self, _conn, session_id: int, final_id: str, final_meta: dict) -> None:
        for row in self._sessions.values():
            if row["id"] == session_id:
                row["status"] = "FINISHED"
                row["ending_id"] = final_id
                row["facts_json"] = {"final_meta": final_meta}
                return

    def finish_in_tx(self, _conn, session_id: int, status: str = "FINISHED") -> None:
        for row in self._sessions.values():
            if row["id"] == session_id:
                row["status"] = status
                return

    def insert_event(
        self,
        _conn,
        session_id: int,
        step: int,
        step0: int | None,
        user_input: str | None,
        choice_id: str | None,
        llm_json: dict | None,
        deltas_json: dict | None,
        *,
        outcome: str | None = None,
        step_result_json: dict | None = None,
        meta_json: dict | None = None,
    ) -> int | None:
        key = (session_id, step)
        if key in self._events:
            return None
        event = {
            "id": self._event_id,
            "session_id": session_id,
            "step": step,
            "step0": step0,
            "user_input": user_input,
            "choice_id": choice_id,
            "llm_json": llm_json,
            "deltas_json": deltas_json,
            "outcome": outcome,
            "step_result_json": step_result_json,
            "meta_json": meta_json,
        }
        self._events[key] = event
        self._event_id += 1
        return event["id"]

    def get_by_step(self, _conn, session_id: int, step: int) -> dict | None:
        return self._events.get((session_id, step))

    def update_event_payload(
        self,
        _conn,
        event_id: int,
        llm_json: dict | None,
        deltas_json: dict | None,
        *,
        outcome: str | None = None,
        step_result_json: dict | None = None,
        meta_json: dict | None = None,
    ) -> None:
        for event in self._events.values():
            if event["id"] == event_id:
                event["llm_json"] = llm_json
                event["deltas_json"] = deltas_json
                event["outcome"] = outcome
                event["step_result_json"] = step_result_json
                event["meta_json"] = meta_json
                return

    def assert_event_count(self, session_id: int, step: int) -> None:
        count = 1 if (session_id, step) in self._events else 0
        assert count == 1


class _LockContext:
    def __init__(self, lock: threading.Lock) -> None:
        self._lock = lock

    def __enter__(self):  # noqa: ANN001, ANN201 - context protocol
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN201 - context protocol
        self._lock.release()
        return False


def _docker_available() -> bool:
    return subprocess.run(["which", "docker"], capture_output=True, text=True).returncode == 0


def _start_postgres_container() -> tuple[str, str]:
    port = _free_port()
    container_name = f"tg65-test-{uuid.uuid4().hex[:8]}"
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            "-e",
            "POSTGRES_DB=skazka",
            "-e",
            "POSTGRES_USER=skazka",
            "-e",
            "POSTGRES_PASSWORD=skazka",
            "-p",
            f"{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to start postgres: {result.stderr}")
    db_url = f"postgresql://skazka:skazka@localhost:{port}/skazka"
    return container_name, db_url


def _wait_for_db_ready(timeout_s: float = 10.0) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with psycopg.connect(os.environ["DB_URL"]):
                return
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError("Postgres did not become ready") from last_error


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
