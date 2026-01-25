from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row

from db.conn import transaction


def insert_idempotent(
    session_id: int,
    step: int,
    kind: str,
    content_hash: str,
    payload: dict[str, Any] | None = None,
) -> str:
    del payload
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO ui_events (
                    session_id,
                    step,
                    kind,
                    content_hash,
                    state,
                    pending_since
                )
                VALUES (%s, %s, %s, %s, 'PENDING', now())
                ON CONFLICT (session_id, step, kind)
                DO UPDATE SET content_hash = EXCLUDED.content_hash,
                              state = 'PENDING',
                              pending_since = now(),
                              updated_at = now()
                RETURNING id;
                """,
                (session_id, step, kind, content_hash),
            )
            row = cur.fetchone()
            return "inserted" if row else "duplicate"


def _backoff_seconds(fail_count: int) -> int:
    if fail_count <= 1:
        return 10
    if fail_count == 2:
        return 30
    return 120


def acquire_event(
    *,
    session_id: int,
    step: int,
    kind: str,
    content_hash: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM ui_events
                WHERE session_id = %s
                  AND step = %s
                  AND kind = %s
                FOR UPDATE;
                """,
                (session_id, step, kind),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    INSERT INTO ui_events (
                        session_id,
                        step,
                        kind,
                        content_hash,
                        state,
                        pending_since
                    )
                    VALUES (%s, %s, %s, %s, 'PENDING', now())
                    RETURNING id;
                    """,
                    (session_id, step, kind, content_hash),
                )
                inserted = cur.fetchone()
                return {"decision": "show", "event_id": int(inserted["id"])}

            state = row["state"]
            pending_since = row.get("pending_since")
            fail_count = int(row.get("fail_count") or 0)
            next_retry_at = row.get("next_retry_at")

            if state == "SHOWN":
                return {"decision": "skip", "event_id": int(row["id"])}

            if state == "PENDING":
                if pending_since and (now - pending_since) < timedelta(seconds=30):
                    return {"decision": "skip", "event_id": int(row["id"])}
                fail_count += 1
                retry_at = now + timedelta(seconds=_backoff_seconds(fail_count))
                cur.execute(
                    """
                    UPDATE ui_events
                    SET state = 'FAILED',
                        pending_since = NULL,
                        fail_count = %s,
                        next_retry_at = %s,
                        content_hash = %s,
                        updated_at = now()
                    WHERE id = %s;
                    """,
                    (fail_count, retry_at, content_hash, row["id"]),
                )
                state = "FAILED"
                next_retry_at = retry_at

            if state == "FAILED":
                if next_retry_at and next_retry_at > now:
                    return {"decision": "skip", "event_id": int(row["id"])}
                cur.execute(
                    """
                    UPDATE ui_events
                    SET state = 'PENDING',
                        pending_since = now(),
                        next_retry_at = NULL,
                        content_hash = %s,
                        updated_at = now()
                    WHERE id = %s;
                    """,
                    (content_hash, row["id"]),
                )
                return {"decision": "show", "event_id": int(row["id"])}

            return {"decision": "skip", "event_id": int(row["id"])}


def mark_shown(event_id: int, step_message_id: int | None = None) -> None:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ui_events
                SET state = 'SHOWN',
                    step_message_id = %s,
                    updated_at = now()
                WHERE id = %s;
                """,
                (step_message_id, event_id),
            )


def mark_failed(event_id: int) -> None:
    now = datetime.now(timezone.utc)
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT fail_count
                FROM ui_events
                WHERE id = %s
                FOR UPDATE;
                """,
                (event_id,),
            )
            row = cur.fetchone()
            if not row:
                return
            fail_count = int(row.get("fail_count") or 0) + 1
            retry_at = now + timedelta(seconds=_backoff_seconds(fail_count))
            cur.execute(
                """
                UPDATE ui_events
                SET state = 'FAILED',
                    fail_count = %s,
                    next_retry_at = %s,
                    updated_at = now()
                WHERE id = %s;
                """,
                (fail_count, retry_at, event_id),
            )
