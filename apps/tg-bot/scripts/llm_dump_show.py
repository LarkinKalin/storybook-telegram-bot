from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _resolve_dump_dir() -> Path:
    raw = os.getenv("LLM_DEBUG_DUMP_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path("var") / "llm_dumps"


def _latest_dump(dump_dir: Path) -> Path | None:
    if not dump_dir.exists():
        return None
    files = sorted(dump_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _preview_content(content: object, full: bool) -> str:
    if isinstance(content, str):
        return content if full else content[:600]
    return json.dumps(content, ensure_ascii=False, indent=2) if full else str(content)[:600]


def main() -> int:
    parser = argparse.ArgumentParser(description="Show latest LLM debug dump")
    parser.add_argument("--full", action="store_true", help="Show full message content")
    args = parser.parse_args()

    dump_dir = _resolve_dump_dir()
    latest = _latest_dump(dump_dir)
    if latest is None:
        print(f"No dumps found in {dump_dir}")
        return 1

    payload = json.loads(latest.read_text(encoding="utf-8"))
    request = payload.get("request") or {}
    response_format = request.get("response_format")
    print(f"file: {latest}")
    print(f"model: {request.get('model')}")
    print(f"temperature: {request.get('temperature')}")
    print(f"max_tokens: {request.get('max_tokens')}")
    print(f"response_format: {response_format}")
    context = payload.get("context") or {}
    print(
        f"context: step={context.get('step')} total_steps={context.get('total_steps')} "
        f"last_choice={context.get('last_choice')} recaps_count={context.get('recaps_count')}"
    )

    messages = request.get("messages") or []
    print(f"messages: {len(messages)}")
    for idx, message in enumerate(messages):
        role = message.get("role")
        content = message.get("content")
        print(f"\n#{idx} role={role}")
        print(_preview_content(content, args.full))

    parsed_json = payload.get("parsed_json") or {}
    print("\nparsed_json.text:")
    print(_preview_content(parsed_json.get("text"), args.full))
    if parsed_json.get("recap_short"):
        print("\nparsed_json.recap_short:")
        print(_preview_content(parsed_json.get("recap_short"), args.full))

    choices = parsed_json.get("choices") or []
    if isinstance(choices, list):
        print("\nparsed_json.choices:")
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            print(f"- {choice.get('choice_id')}: {choice.get('label')}")

    usage = payload.get("usage") or {}
    print("\nusage:")
    print(
        f"prompt_tokens={usage.get('prompt_tokens')} "
        f"completion_tokens={usage.get('completion_tokens')} "
        f"total_tokens={usage.get('total_tokens')} "
        f"cost={usage.get('cost')}"
    )
    engine_input = payload.get("engine_input")
    engine_output = payload.get("engine_output")
    if engine_input is not None:
        print("\nengine_input:")
        print(_preview_content(engine_input, args.full))
    if engine_output is not None:
        print("\nengine_output:")
        print(_preview_content(engine_output, args.full))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
