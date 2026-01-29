import hashlib
import os
from time import time_ns
from uuid import uuid4

import pytest

from db.conn import get_conn
from db.repos import assets, session_images, sessions, users


def _create_session() -> dict:
    tg_id = int(time_ns() % 1_000_000_000)
    user = users.get_or_create_by_tg_id(tg_id, display_name="assets_test")
    return sessions.create_new_active(
        user_id=user["id"],
        theme_id="test",
        player_name="tester",
        meta={"max_steps": 2, "v": "0.2"},
    )


def _create_asset(storage_key: str) -> int:
    sha256 = hashlib.sha256(f"{storage_key}:{uuid4()}".encode()).hexdigest()
    return assets.insert_asset(
        kind="image",
        storage_backend="fs",
        storage_key=storage_key,
        mime="image/png",
        bytes=123,
        sha256=sha256,
        width=10,
        height=20,
    )


def test_assets_session_images_tables_exist() -> None:
    if not os.getenv("DB_URL"):
        pytest.skip("DB_URL not set")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('assets', 'session_images');
                """
            )
            rows = {row[0] for row in cur.fetchall()}
    assert "assets" in rows
    assert "session_images" in rows


def test_session_images_unique_role_per_step() -> None:
    if not os.getenv("DB_URL"):
        pytest.skip("DB_URL not set")
    session_row = _create_session()
    asset_id = _create_asset("unique-role")
    session_images.insert_session_image(
        session_id=session_row["id"],
        step_ui=1,
        asset_id=asset_id,
        role="step_image",
        reference_asset_id=None,
        image_model="model",
        prompt="prompt",
    )
    duplicate_id = session_images.insert_session_image(
        session_id=session_row["id"],
        step_ui=1,
        asset_id=asset_id,
        role="step_image",
        reference_asset_id=None,
        image_model="model",
        prompt="prompt",
    )
    assert duplicate_id is None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)
                FROM session_images
                WHERE session_id = %s AND step_ui = %s AND role = %s;
                """,
                (session_row["id"], 1, "step_image"),
            )
            assert cur.fetchone()[0] == 1


def test_reference_only_step1_check() -> None:
    if not os.getenv("DB_URL"):
        pytest.skip("DB_URL not set")
    session_row = _create_session()
    asset_id = _create_asset("reference-only")
    with pytest.raises(Exception):
        session_images.insert_session_image(
            session_id=session_row["id"],
            step_ui=2,
            asset_id=asset_id,
            role="reference",
            reference_asset_id=None,
            image_model="model",
            prompt="prompt",
        )


def test_insert_and_list_session_images() -> None:
    if not os.getenv("DB_URL"):
        pytest.skip("DB_URL not set")
    session_row = _create_session()
    asset_id = _create_asset("list-session")
    session_image_id = session_images.insert_session_image(
        session_id=session_row["id"],
        step_ui=1,
        asset_id=asset_id,
        role="step_image",
        reference_asset_id=None,
        image_model="model",
        prompt="prompt",
    )
    rows = session_images.list_session_images(session_row["id"])
    assert [row["id"] for row in rows] == [session_image_id]
