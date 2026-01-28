#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/docker/docker-compose.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not available in PATH" >&2
  exit 1
fi

modes=(
  "off:ok"
  "mock:invalid_json_always"
  "openrouter:ok"
)

for mode in "${modes[@]}"; do
  IFS=":" read -r provider mock_mode <<<"${mode}"
  LLM_PROVIDER="${provider}" LLM_MOCK_MODE="${mock_mode}" \
    docker compose -f "${COMPOSE_FILE}" up -d --build tg-bot >/dev/null 2>&1

  docker compose -f "${COMPOSE_FILE}" exec -T tg-bot python - <<'PY'
import json
import logging
import os

from packages.llm.src import adapter
from packages.llm.src.mock_provider import MockProvider
from packages.llm.src.openrouter_provider import OpenRouterProvider


class CountingProvider:
    def __init__(self, provider):
        self.provider = provider
        self.attempts = 0

    def generate(self, step_ctx):
        self.attempts += 1
        return self.provider.generate(step_ctx)


def build_step_ctx(expected_type):
    if expected_type == "story_step":
        return {
            "expected_type": expected_type,
            "story_request": {
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
        "story_request": {
            "expected_type": expected_type,
            "final_id": "smoke",
            "theme_id": "smoke",
            "format": "Верни JSON формата {text}.",
        },
    }


def format_outcome(raw_text):
    if not raw_text:
        return "ok"
    snippet = raw_text.replace("\n", " ").strip()
    if len(snippet) > 80:
        snippet = snippet[:80] + "…"
    return f"ok({snippet})"


def run_expected(expected_type):
    provider_name = os.getenv("LLM_PROVIDER", "off").strip().lower()
    if provider_name == "off":
        result = adapter.generate(build_step_ctx(expected_type))
        print(
            f"provider={provider_name} expected={expected_type} attempt=0 "
            f"outcome=skipped used_fallback={str(result.used_fallback).lower()}"
        )
        return

    if provider_name == "mock":
        mock_mode = os.getenv("LLM_MOCK_MODE", "ok")
        provider = MockProvider(mode=mock_mode)
    elif provider_name == "openrouter":
        try:
            provider = OpenRouterProvider()
        except Exception:
            print(
                f"provider={provider_name} expected={expected_type} attempt=0 "
                "outcome=error used_fallback=false"
            )
            return
    else:
        print(
            f"provider={provider_name} expected={expected_type} attempt=0 "
            "outcome=unknown used_fallback=false"
        )
        return

    counting_provider = CountingProvider(provider)
    result = adapter._generate_with_provider(
        provider_name=provider_name,
        provider=counting_provider,
        expected_type=expected_type,
        step_ctx=build_step_ctx(expected_type),
    )
    outcome = "error" if result.used_fallback else format_outcome(result.raw_text)
    print(
        f"provider={provider_name} expected={expected_type} "
        f"attempt={counting_provider.attempts} outcome={outcome} "
        f"used_fallback={str(result.used_fallback).lower()}"
    )


logging.basicConfig(level=logging.ERROR)

run_expected("story_step")
run_expected("story_final")
PY
done
