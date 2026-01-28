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
  "off:ok"
  "mock:invalid_json_always"
  "openrouter:ok"
)

for mode in "${modes[@]}"; do
  IFS=":" read -r provider mock_mode <<<"${mode}"
  exec_env=(-e "LLM_PROVIDER=${provider}" -e "LLM_MOCK_MODE=${mock_mode}")

  docker compose -f "${COMPOSE_FILE}" exec -T "${exec_env[@]}" tg-bot python - <<'PY'
import os

from packages.llm.src import adapter


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
    provider_name = os.getenv("LLM_PROVIDER", "off").strip().lower()
    try:
        result = adapter.generate(build_step_ctx(expected_type))
    except Exception as exc:  # noqa: BLE001
        outcome = "error"
        used_fallback = True
        attempt = 2
        reason = f"exception_{type(exc).__name__.lower()}"
    else:
        if provider_name == "off":
            outcome = "skipped"
            used_fallback = False
            reason = "skipped"
            attempt = 0
        elif result.used_fallback:
            outcome = "error"
            used_fallback = True
            reason = result.error_reason or "unknown"
            attempt = 2
        else:
            outcome = format_outcome(result.raw_text)
            used_fallback = False
            reason = result.error_reason or "none"
            attempt = 1

    print(
        f"provider={provider_name} expected={expected_type} "
        f"attempt={attempt} outcome={outcome} "
        f"used_fallback={str(used_fallback).lower()} reason={reason}"
    )


run_expected("story_step")
run_expected("story_final")
PY
done
