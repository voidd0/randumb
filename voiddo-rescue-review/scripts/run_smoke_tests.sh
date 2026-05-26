#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

docker compose config >/tmp/voiddo_rescue_compose_config.txt
docker compose exec -T api sh -lc 'python -m py_compile app/*.py'
docker compose exec -T worker sh -lc 'python -m py_compile worker/*.py'
docker compose exec -T api python -m pytest -q

echo "ok"
