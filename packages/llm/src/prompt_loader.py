from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptLoadResult:
    text: str
    source: str
    path: str


class PromptNotFoundError(FileNotFoundError):
    def __init__(self, paths: list[Path]) -> None:
        self.paths = paths
        searched = "\n".join(str(path) for path in paths)
        super().__init__(f"prompt files not found, tried:\n{searched}")


def load_system_prompt(expected_type: str, theme_id: str | None) -> str:
    result = load_system_prompt_with_source(expected_type, theme_id)
    return result.text


def load_system_prompt_with_source(
    expected_type: str, theme_id: str | None
) -> PromptLoadResult:
    prompt_paths = _build_prompt_paths(expected_type, theme_id)
    for path in prompt_paths:
        try:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return PromptLoadResult(text=text, source="file", path=str(path))
    raise PromptNotFoundError(prompt_paths)


def _build_prompt_paths(expected_type: str, theme_id: str | None) -> list[Path]:
    base_dir = _resolve_prompt_base_dir()
    expected_dir = "story_final" if expected_type == "story_final" else "story_step"
    candidates: list[Path] = []
    if theme_id:
        candidates.append(base_dir / expected_dir / f"{theme_id}.txt")
    candidates.append(base_dir / expected_dir / "default.txt")
    candidates.append(base_dir / "default.txt")
    legacy_default = Path("content/prompts/default.txt")
    if legacy_default not in candidates:
        candidates.append(legacy_default)
    return candidates


def _resolve_prompt_base_dir() -> Path:
    content_dir = os.getenv("SKAZKA_CONTENT_DIR", "").strip()
    if content_dir:
        return Path(content_dir) / "prompts"
    prompts_dir = os.getenv("PROMPTS_DIR", "").strip()
    if prompts_dir:
        return Path(prompts_dir)
    return Path("/app/content/prompts")
