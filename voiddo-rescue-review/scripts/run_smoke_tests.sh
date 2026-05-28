#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

docker compose config >/tmp/voiddo_rescue_compose_config.txt
docker compose exec -T api sh -lc 'python -m py_compile app/*.py'
docker compose exec -T worker sh -lc 'python -m py_compile worker/*.py'
docker compose exec -T api python - <<'PY'
from pathlib import Path
import subprocess
import sys

tests = sorted(f"tests/{path.name}" for path in Path("tests").glob("test_*.py"))
batch_size = 8
for index in range(0, len(tests), batch_size):
    batch = tests[index:index + batch_size]
    print(f"smoke pytest batch {index // batch_size + 1}: {len(batch)} files", flush=True)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", *batch])
    if result.returncode:
        raise SystemExit(result.returncode)
print(f"smoke pytest segmented ok: {len(tests)} files", flush=True)
PY

echo "ok"
