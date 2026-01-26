from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import psycopg

logger = logging.getLogger(__name__)
_ADVISORY_LOCK_ID = 812345


def _migration_files(migrations_dir: Path) -> Iterable[Path]:
    return sorted(migrations_dir.glob("*.sql"))


def apply_pending(db_url: str, migrations_dir: str) -> None:
    migrations_path = Path(migrations_dir)
    if not migrations_path.exists():
        raise RuntimeError(f"Migrations directory not found: {migrations_dir}")

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s);", (_ADVISORY_LOCK_ID,))
            conn.commit()
        try:
            _ensure_schema_migrations(conn)
            applied = _load_applied(conn)
            for migration in _migration_files(migrations_path):
                if migration.name in applied:
                    continue
                _apply_one(conn, migration)
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s);", (_ADVISORY_LOCK_ID,))
                conn.commit()


def _ensure_schema_migrations(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            );
            """
        )
        conn.commit()


def _load_applied(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM schema_migrations;")
        rows = cur.fetchall()
    return {row[0] for row in rows}


def _apply_one(conn: psycopg.Connection, migration: Path) -> None:
    logger.info("applying migration=%s", migration.name)
    sql = migration.read_text(encoding="utf-8")
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (name) VALUES (%s);",
                (migration.name,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.error("failed migration=%s", migration.name, exc_info=True)
        raise
    logger.info("applied migration=%s", migration.name)
