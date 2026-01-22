from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from db.conn import transaction


def create_invoice(
    user_id: int,
    invoice_id: str,
    amount: int,
    kind: str,
    period_yyyymm: str | None,
    status: str = "PENDING",
) -> None:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO payments (
                    user_id,
                    invoice_id,
                    amount,
                    kind,
                    period_yyyymm,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (invoice_id) DO NOTHING;
                """,
                (user_id, invoice_id, amount, kind, period_yyyymm, status),
            )


def mark_confirmed(
    invoice_id: str,
    tx_hash: str,
    confirmed_at: int | None = None,
) -> None:
    with transaction() as conn:
        with conn.cursor() as cur:
            if confirmed_at is None:
                cur.execute(
                    """
                    UPDATE payments
                    SET status = 'CONFIRMED', tx_hash = %s, updated_at = now()
                    WHERE invoice_id = %s;
                    """,
                    (tx_hash, invoice_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE payments
                    SET
                        status = 'CONFIRMED',
                        tx_hash = %s,
                        updated_at = to_timestamp(%s)
                    WHERE invoice_id = %s;
                    """,
                    (tx_hash, confirmed_at, invoice_id),
                )


def list_pending(limit: int = 50) -> list[dict[str, Any]]:
    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM payments
                WHERE status = 'PENDING'
                ORDER BY created_at ASC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [dict(row) for row in rows]
