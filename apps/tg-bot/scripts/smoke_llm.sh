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
  "mock:ok"
  "mock:invalid_json"
)

for mode in "${modes[@]}"; do
  IFS=":" read -r provider mock_mode <<<"${mode}"
  echo "==> Restarting tg-bot with LLM_PROVIDER=${provider} LLM_MOCK_MODE=${mock_mode}"
  LLM_PROVIDER="${provider}" LLM_MOCK_MODE="${mock_mode}" \
    docker compose -f "${COMPOSE_FILE}" up -d --build tg-bot

  echo "LLM env inside container:"
  docker compose -f "${COMPOSE_FILE}" exec -T tg-bot env | grep '^LLM_' || true

  echo "Подсказка: нажми A/B/C в Telegram"
  sleep 3

  echo "==> Recent LLM logs"
  docker compose -f "${COMPOSE_FILE}" logs --since 1m tg-bot \
    | grep -E 'llm\.(adapter|validator|fallback)' || true
  echo ""
done
