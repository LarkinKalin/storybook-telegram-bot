import asyncio

from src.services import image_delivery


class DummyBot:
    def __init__(self) -> None:
        self.sent = []

    async def send_photo(self, *, chat_id, photo, caption, reply_to_message_id):  # noqa: ANN001
        self.sent.append(
            {
                "chat_id": chat_id,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
                "filename": photo.filename,
            }
        )


def test_reference_image_created(monkeypatch):
    captured = {}

    def fake_t2i(_prompt):
        return (b"img", "image/png", 10, 10, "sha")

    def fake_store_asset(*, image_bytes, mime, width, height, sha256=None):
        captured["stored"] = {
            "bytes": image_bytes,
            "mime": mime,
            "width": width,
            "height": height,
            "sha256": sha256,
        }
        return 123, "images/ref.png"

    def fake_insert_session_image(**kwargs):
        captured["insert"] = kwargs
        return 1

    monkeypatch.setattr(image_delivery, "_resolve_retries", lambda: 0)
    monkeypatch.setattr(image_delivery, "generate_t2i", fake_t2i)
    monkeypatch.setattr(image_delivery, "_store_asset", fake_store_asset)
    monkeypatch.setattr(image_delivery.session_images, "get_reference_asset_id", lambda _sid: None)
    monkeypatch.setattr(image_delivery.session_images, "insert_session_image", fake_insert_session_image)

    bot = DummyBot()
    asyncio.run(
        image_delivery._generate_and_send_image(
            bot=bot,
            chat_id=1,
            step_message_id=10,
            session_id=42,
            step_ui=1,
            story_step_ui=1,
            total_steps=8,
            prompt="scene",
            theme_id="robot_world",
            image_scene_brief="Детская книжная иллюстрация про роботов.",
        )
    )

    assert captured["insert"]["role"] == "step_image"
    assert captured["insert"]["step_ui"] == 1
    assert "иллюстрация" in captured["insert"]["prompt"]
    assert bot.sent


def test_step_image_uses_reference(monkeypatch):
    captured = {}

    def fake_i2i(_prompt, _bytes, _mime):
        return (b"img", "image/png", 10, 10, "sha")

    def fake_store_asset(*, image_bytes, mime, width, height, sha256=None):
        captured["stored"] = {
            "bytes": image_bytes,
            "mime": mime,
            "width": width,
            "height": height,
            "sha256": sha256,
        }
        return 456, "images/step.png"

    def fake_insert_session_image(**kwargs):
        captured["insert"] = kwargs
        return 1

    monkeypatch.setattr(image_delivery, "_resolve_retries", lambda: 0)
    monkeypatch.setattr(image_delivery, "generate_i2i", fake_i2i)
    monkeypatch.setattr(image_delivery, "_store_asset", fake_store_asset)
    monkeypatch.setattr(image_delivery.session_images, "get_reference_asset_id", lambda _sid: 999)
    monkeypatch.setattr(
        image_delivery, "_load_reference", lambda _asset_id: image_delivery.ReferencePayload(b"r", "image/png")
    )
    monkeypatch.setattr(image_delivery.session_images, "insert_session_image", fake_insert_session_image)

    bot = DummyBot()
    asyncio.run(
        image_delivery._generate_and_send_image(
            bot=bot,
            chat_id=1,
            step_message_id=10,
            session_id=42,
            step_ui=4,
            story_step_ui=4,
            total_steps=8,
            prompt="scene text",
            theme_id=None,
            image_scene_brief="Детская книжная иллюстрация по сцене.",
        )
    )

    assert captured["insert"]["role"] == "step_image"
    assert captured["insert"]["reference_asset_id"] == 999
    assert "иллюстрация" in captured["insert"]["prompt"]
    assert bot.sent


def test_step_image_without_reference(monkeypatch):
    captured = {}

    def fake_t2i(_prompt):
        return (b"img", "image/png", 10, 10, "sha")

    def fake_store_asset(*, image_bytes, mime, width, height, sha256=None):
        captured["stored"] = {
            "bytes": image_bytes,
            "mime": mime,
            "width": width,
            "height": height,
            "sha256": sha256,
        }
        return 789, "images/step_no_ref.png"

    def fake_insert_session_image(**kwargs):
        captured["insert"] = kwargs
        return 1

    monkeypatch.setattr(image_delivery, "_resolve_retries", lambda: 0)
    monkeypatch.setattr(image_delivery, "generate_t2i", fake_t2i)
    monkeypatch.setattr(image_delivery, "_store_asset", fake_store_asset)
    monkeypatch.setattr(image_delivery.session_images, "get_reference_asset_id", lambda _sid: None)
    monkeypatch.setattr(image_delivery.session_images, "insert_session_image", fake_insert_session_image)

    bot = DummyBot()
    asyncio.run(
        image_delivery._generate_and_send_image(
            bot=bot,
            chat_id=1,
            step_message_id=10,
            session_id=42,
            step_ui=4,
            story_step_ui=4,
            total_steps=8,
            prompt="scene text",
            theme_id=None,
            image_scene_brief="Детская книжная иллюстрация по сцене.",
        )
    )

    assert captured["insert"]["role"] == "step_image"
    assert captured["insert"]["reference_asset_id"] is None
    assert bot.sent


def test_image_steps_with_story_step_ui():
    schedule = image_delivery.ImageSchedule(story_step_ui=1, total_steps=8, has_image_scene_brief=True)
    assert schedule.needs_image is True
    schedule = image_delivery.ImageSchedule(story_step_ui=2, total_steps=8, has_image_scene_brief=True)
    assert schedule.needs_image is False


def test_image_steps_plan_for_totals():
    assert image_delivery.image_steps(8) == {1, 4, 8}
    assert image_delivery.image_steps(10) == {1, 4, 8}
    assert image_delivery.image_steps(12) == {1, 5, 9}


def test_story_step_ui_mapping():
    assert image_delivery.resolve_story_step_ui(0) == 1
    assert image_delivery.resolve_story_step_ui(3) == 4
