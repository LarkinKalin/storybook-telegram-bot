#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/infra/docker/docker-compose.yml"

docker compose -f "${COMPOSE_FILE}" up -d postgres

DB_URL="postgresql://skazka:skazka@localhost:5432/skazka"
export DB_URL

python -m pytest -q packages/db/tests/test_l3_turns_concurrency.py

docker compose -f "${COMPOSE_FILE}" down
