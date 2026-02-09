from __future__ import annotations

import base64
import hashlib
import os
from typing import Any, Dict, Tuple

import requests


class MissingOpenRouterKeyError(ValueError):
    pass


_SIM_FAIL_USED = False


def generate_t2i(prompt: str) -> Tuple[bytes, str, int | None, int | None, str]:
    return _generate_image(prompt=prompt, reference_bytes=None, reference_mime=None)


def generate_i2i(
    prompt: str,
    reference_bytes: bytes,
    reference_mime: str,
) -> Tuple[bytes, str, int | None, int | None, str]:
    return _generate_image(
        prompt=prompt,
        reference_bytes=reference_bytes,
        reference_mime=reference_mime,
    )


def _generate_image(
    *,
    prompt: str,
    reference_bytes: bytes | None,
    reference_mime: str | None,
) -> Tuple[bytes, str, int | None, int | None, str]:
    api_key = _get_api_key()
    endpoint = "https://openrouter.ai/api/v1/chat/completions"
    model = os.getenv("OPENROUTER_MODEL_IMAGE", "black-forest-labs/flux.2-pro").strip()
    timeout_s = _resolve_timeout()
    prompt = _clamp_prompt(prompt)
    _maybe_simulate_failure()

    messages = [_build_prompt_message(prompt, reference_bytes, reference_mime)]
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "extra_body": {"modalities": ["image", "text"]},
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    http_referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    app_title = os.getenv("OPENROUTER_APP_TITLE", "").strip()
    if app_title:
        headers["X-Title"] = app_title

    response = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=timeout_s,
    )
    response.raise_for_status()
    payload = response.json()
    image_bytes, mime = _extract_image(payload)
    width, height = _extract_dimensions(image_bytes, mime)
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    return image_bytes, mime, width, height, sha256


def _get_api_key() -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise MissingOpenRouterKeyError("OpenRouter API key is required")
    return api_key


def _resolve_timeout() -> float:
    raw = os.getenv("OPENROUTER_IMAGE_TIMEOUT_SEC", "").strip()
    if not raw:
        raw = os.getenv("OPENROUTER_IMAGE_TIMEOUT_S", "90").strip()
    if not raw:
        return 90.0
    try:
        return float(raw)
    except ValueError:
        return 90.0


def _clamp_prompt(prompt: str) -> str:
    raw = os.getenv("OPENROUTER_IMAGE_PROMPT_MAX_LEN", "1200").strip()
    try:
        limit = max(200, int(raw))
    except ValueError:
        limit = 1200
    if len(prompt) <= limit:
        return prompt
    return prompt[:limit].rstrip()


def _maybe_simulate_failure() -> None:
    global _SIM_FAIL_USED
    if _SIM_FAIL_USED:
        return
    if os.getenv("SKAZKA_IMAGE_PROVIDER_SIM_FAIL", "0").strip() not in {"1", "true", "yes", "on"}:
        return
    _SIM_FAIL_USED = True
    raise RuntimeError("simulated image provider failure")


def _build_prompt_message(
    prompt: str,
    reference_bytes: bytes | None,
    reference_mime: str | None,
) -> Dict[str, Any]:
    if reference_bytes is None:
        return {"role": "user", "content": prompt}
    if reference_mime is None:
        reference_mime = "image/png"
    data_url = _to_data_url(reference_bytes, reference_mime)
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
    }


def _to_data_url(image_bytes: bytes, mime: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_image(payload: Dict[str, Any]) -> Tuple[bytes, str]:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("openrouter image response missing choices")
    message = choices[0].get("message") or {}
    images = message.get("images") or []
    if not images:
        raise ValueError("openrouter image response missing images")
    image_url = images[0].get("image_url") or {}
    data_url = image_url.get("url")
    if not isinstance(data_url, str):
        raise ValueError("openrouter image response missing image url")
    return _parse_data_url(data_url)


def _parse_data_url(data_url: str) -> Tuple[bytes, str]:
    if not data_url.startswith("data:"):
        raise ValueError("unexpected image url format")
    header, _, data = data_url.partition(",")
    if not data:
        raise ValueError("invalid data url")
    mime_part = header[5:]
    mime = mime_part.split(";")[0] or "application/octet-stream"
    try:
        decoded = base64.b64decode(data)
    except base64.binascii.Error as exc:
        raise ValueError("invalid base64 data") from exc
    return decoded, mime


def _extract_dimensions(image_bytes: bytes, mime: str) -> Tuple[int | None, int | None]:
    if mime != "image/png":
        return None, None
    return _parse_png_dimensions(image_bytes)


def _parse_png_dimensions(image_bytes: bytes) -> Tuple[int | None, int | None]:
    signature = b"\x89PNG\r\n\x1a\n"
    if not image_bytes.startswith(signature):
        return None, None
    if len(image_bytes) < 24:
        return None, None
    ihdr_offset = 8
    if image_bytes[ihdr_offset + 4:ihdr_offset + 8] != b"IHDR":
        return None, None
    width = int.from_bytes(image_bytes[ihdr_offset + 8:ihdr_offset + 12], "big")
    height = int.from_bytes(image_bytes[ihdr_offset + 12:ihdr_offset + 16], "big")
    if width <= 0 or height <= 0:
        return None, None
    return width, height
