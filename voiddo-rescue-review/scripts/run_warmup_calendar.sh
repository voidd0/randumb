#!/usr/bin/env bash
set -euo pipefail

cd /opt/voiddo-rescue
docker compose exec -T api python - <<'PY'
from app.p0 import run_warmup_calendar_due
print(run_warmup_calendar_due(limit=2))
PY
