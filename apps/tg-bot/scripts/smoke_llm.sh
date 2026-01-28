#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/docker/docker-compose.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not available in PATH" >&2
  exit 1
fi

docker compose -f "${COMPOSE_FILE}" up -d tg-bot >/dev/null 2>&1

modes=(
  "off:"
  "mock:invalid_json_always"
  "openrouter:"
)

for mode in "${modes[@]}"; do
  IFS=":" read -r provider mock_mode <<<"${mode}"
  exec_env=(-e "LLM_PROVIDER=${provider}")
  if [[ -n "${mock_mode}" ]]; then
    exec_env+=(-e "LLM_MOCK_MODE=${mock_mode}")
  fi

  docker compose -f "${COMPOSE_FILE}" exec -T "${exec_env[@]}" tg-bot python - <<'PY'
import logging
import os
import re

from packages.llm.src import adapter


class AttemptTracker(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.max_attempt = 0

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "llm.adapter" not in message:
            return
        match = re.search(r"attempt=(\\d+)", message)
        if match:
            self.max_attempt = max(self.max_attempt, int(match.group(1)))


def build_step_ctx(expected_type: str):
    if expected_type == "story_step":
        return {
            "expected_type": expected_type,
            "req_id": "smoke-step",
            "story_request": {
                "rules": "Верни только JSON. Без markdown. Без пояснений.",
                "expected_type": expected_type,
                "scene_text": "Герой стоит у развилки дорог.",
                "choices": [
                    {"choice_id": "A", "label": "A — Налево"},
                    {"choice_id": "B", "label": "B — Направо"},
                ],
                "allow_free_text": False,
                "step": 0,
                "total_steps": 2,
                "theme_id": "smoke",
                "format": "Верни JSON формата {text, choices[]}.",
            },
        }
    return {
        "expected_type": expected_type,
        "req_id": "smoke-final",
        "story_request": {
            "rules": "Верни только JSON. Без markdown. Без пояснений.",
            "expected_type": expected_type,
            "final_id": "smoke",
            "theme_id": "smoke",
            "format": "Верни JSON формата {text}.",
        },
    }


def format_outcome(raw_text: str):
    if not raw_text:
        return "ok"
    snippet = raw_text.replace("\n", " ").strip()
    if len(snippet) > 80:
        snippet = snippet[:80] + "…"
    return f"ok({snippet})"


def run_expected(expected_type: str):
    tracker = AttemptTracker()
    tracker.setLevel(logging.INFO)
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(tracker)
    root_logger.setLevel(logging.INFO)

    provider_name = os.getenv("LLM_PROVIDER", "off").strip().lower()
    result = adapter.generate(build_step_ctx(expected_type))
    attempt = tracker.max_attempt
    if provider_name == "off":
        outcome = "skipped"
        reason = "skipped"
        attempt = 0
    elif result.used_fallback:
        outcome = "error"
        reason = result.error_reason or "unknown"
    else:
        outcome = format_outcome(result.raw_text)
        reason = result.error_reason or "none"
    print(
        f"provider={provider_name} expected={expected_type} "
        f"attempt={attempt} outcome={outcome} "
        f"used_fallback={str(result.used_fallback).lower()} reason={reason}"
    )


run_expected("story_step")
run_expected("story_final")
PY
done
