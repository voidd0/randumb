#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

docker compose config >/tmp/voiddo_rescue_compose_config.txt
python3 -m py_compile apps/api/app/*.py apps/worker/worker/*.py
PYTHONPATH="$ROOT/apps/api" python3 -m pytest -q apps/api/tests

echo "ok"
