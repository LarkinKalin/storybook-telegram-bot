from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = REPO_ROOT / "apps" / "tg-bot"

sys.path.append(str(REPO_ROOT))
sys.path.append(str(DB_ROOT / "src"))
sys.path.append(str(BOT_ROOT))

from db.repos import assets, session_images, sessions, users  # noqa: E402
from src.services.image_delivery import image_steps  # noqa: E402


def _make_sha(label: str) -> str:
    return hashlib.sha256(f"{label}:{uuid4()}".encode()).hexdigest()


def _insert_asset(label: str) -> int:
    sha256 = _make_sha(label)
    return assets.insert_asset(
        kind="image",
        storage_backend="fs",
        storage_key=f"images/{sha256}.png",
        mime="image/png",
        bytes=123,
        sha256=sha256,
        width=10,
        height=20,
    )


def main() -> int:
    if not os.getenv("DB_URL"):
        print("DB_URL is not set")
        return 1

    print("Smoke TG.7.4.01 starting...")
    expected_steps = image_steps(10)
    if expected_steps != {1, 4, 8}:
        print(f"Unexpected image schedule: {expected_steps}")
        return 1

    user = users.get_or_create_by_tg_id(987654321, tg_username="smoke_image")
    session = sessions.create_new_active(user_id=user["id"], theme_id="smoke", meta={"max_steps": 10})
    session_id = int(session["id"])

    reference_asset_id = _insert_asset("reference")
    session_images.insert_session_image(
        session_id=session_id,
        step_ui=1,
        asset_id=reference_asset_id,
        role="reference",
        reference_asset_id=None,
        image_model="smoke",
        prompt="step 1",
    )

    step4_asset_id = _insert_asset("step4")
    session_images.insert_session_image(
        session_id=session_id,
        step_ui=4,
        asset_id=step4_asset_id,
        role="step_image",
        reference_asset_id=reference_asset_id,
        image_model="smoke",
        prompt="step 4",
    )

    step8_asset_id = _insert_asset("step8")
    session_images.insert_session_image(
        session_id=session_id,
        step_ui=8,
        asset_id=step8_asset_id,
        role="step_image",
        reference_asset_id=reference_asset_id,
        image_model="smoke",
        prompt="step 8",
    )

    rows = session_images.list_session_images(session_id)
    step4_row = next(row for row in rows if row["step_ui"] == 4)
    step8_row = next(row for row in rows if row["step_ui"] == 8)
    if step4_row["reference_asset_id"] != reference_asset_id:
        print("step4 reference asset mismatch")
        return 1
    if step8_row["reference_asset_id"] != reference_asset_id:
        print("step8 reference asset mismatch")
        return 1

    print("Smoke TG.7.4.01 completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
