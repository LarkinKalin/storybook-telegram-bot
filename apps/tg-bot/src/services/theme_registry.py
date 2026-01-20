from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

_THEME_ID_RE = re.compile(r"^[a-z0-9_-]{1,16}$")


class ThemeRegistry:
    def __init__(self, content_dir: Path) -> None:
        self._content_dir = content_dir
        self._themes: list[dict[str, Any]] = []
        self._themes_by_id: dict[str, dict[str, Any]] = {}
        self._style_ids: set[str] = set()
        self._tag_vocab: set[str] = set()
        self._loaded = False

    def load_all(self) -> None:
        tag_vocab = self._load_json(self._content_dir / "tag_vocab.json")
        styles = self._load_json(self._content_dir / "styles.json")
        themes = self._load_json(self._content_dir / "themes.json")

        self._tag_vocab = self._validate_tag_vocab(tag_vocab)
        self._style_ids = self._validate_styles(styles)
        self._themes = self._validate_themes(themes)
        self._themes_by_id = {theme["id"]: theme for theme in self._themes}
        self._loaded = True

    def list_themes(self) -> list[dict[str, Any]]:
        self._ensure_loaded()
        return list(self._themes)

    def get_theme(self, theme_id: str) -> dict[str, Any] | None:
        self._ensure_loaded()
        return self._themes_by_id.get(theme_id)

    def page(self, page_index: int, page_size: int = 10) -> tuple[list[dict[str, Any]], int, int]:
        self._ensure_loaded()
        if page_size <= 0:
            raise ValueError("page_size must be positive")

        total = len(self._themes)
        if total == 0:
            return [], 0, 0

        page_count = math.ceil(total / page_size)
        page_index = max(0, min(page_index, page_count - 1))

        start = page_index * page_size
        end = start + page_size
        return self._themes[start:end], page_index, page_count

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("ThemeRegistry is not loaded. Call load_all() on startup.")

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Missing content file: {path}")
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid JSON root in {path}")
        return data

    def _validate_tag_vocab(self, data: dict[str, Any]) -> set[str]:
        tags = data.get("tags")
        if not isinstance(tags, list) or not tags:
            raise ValueError("Tag vocab must contain non-empty tags list")
        normalized: set[str] = set()
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("Tag vocab contains empty tag")
            normalized.add(tag)
        return normalized

    def _validate_styles(self, data: dict[str, Any]) -> set[str]:
        styles = data.get("styles")
        if not isinstance(styles, list) or not styles:
            raise ValueError("Styles must contain non-empty styles list")
        style_ids: set[str] = set()
        for style in styles:
            if not isinstance(style, dict):
                raise ValueError("Style entry must be object")
            style_id = style.get("style_id")
            style_tag = style.get("style_tag")
            if not isinstance(style_id, str) or not style_id.strip():
                raise ValueError("Style id is empty")
            if not isinstance(style_tag, str) or not style_tag.strip():
                raise ValueError("Style tag is empty")
            style_ids.add(style_id)
        return style_ids

    def _validate_themes(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        themes = data.get("themes")
        if themes is None:
            raise ValueError("Themes file must contain themes")
        if not isinstance(themes, list):
            raise ValueError("Themes must be a list")

        validated: list[dict[str, Any]] = []
        for theme in themes:
            if not isinstance(theme, dict):
                raise ValueError("Theme entry must be object")
            theme_id = theme.get("id")
            title = theme.get("title")
            subtitle = theme.get("subtitle")
            tags = theme.get("tags")
            style_default = theme.get("style_default")
            style_tag = theme.get("style_tag")
            starter_brief = theme.get("starter_brief")

            if not isinstance(theme_id, str) or not _THEME_ID_RE.match(theme_id):
                raise ValueError(f"Theme id invalid: {theme_id}")
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"Theme title is empty for {theme_id}")
            if not isinstance(subtitle, str) or not subtitle.strip():
                raise ValueError(f"Theme subtitle is empty for {theme_id}")
            if not isinstance(style_default, str) or not style_default.strip():
                raise ValueError(f"Theme style_default is empty for {theme_id}")
            if style_default not in self._style_ids:
                raise ValueError(f"Unknown style_default {style_default} for {theme_id}")
            if not isinstance(style_tag, str) or not style_tag.strip():
                raise ValueError(f"Theme style_tag is empty for {theme_id}")
            if not isinstance(starter_brief, str) or not starter_brief.strip():
                raise ValueError(f"Theme starter_brief is empty for {theme_id}")

            if not isinstance(tags, list):
                raise ValueError(f"Theme tags must be list for {theme_id}")
            if not (4 <= len(tags) <= 6):
                raise ValueError(f"Theme tags count must be 4..6 for {theme_id}")
            for tag in tags:
                if not isinstance(tag, str) or tag not in self._tag_vocab:
                    raise ValueError(f"Unknown tag {tag} for {theme_id}")

            validated.append(theme)
        return validated


_repo_root = Path(__file__).resolve().parents[4]
registry = ThemeRegistry(_repo_root / "content")
