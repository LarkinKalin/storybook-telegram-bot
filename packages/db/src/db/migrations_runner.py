from __future__ import annotations

from pathlib import Path
from typing import Iterable

from psycopg.rows import dict_row

from db.conn import transaction


def _migration_files(migrations_dir: Path) -> Iterable[Path]:
    return sorted(migrations_dir.glob("*.sql"))


def apply_migrations() -> None:
    migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
    if not migrations_dir.exists():
        return

    with transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                );
                """
            )
            cur.execute("SELECT name FROM schema_migrations;")
            applied = {row["name"] for row in cur.fetchall()}

            for migration in _migration_files(migrations_dir):
                if migration.name in applied:
                    continue
                sql = migration.read_text(encoding="utf-8")
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (name) VALUES (%s);",
                    (migration.name,),
                )
