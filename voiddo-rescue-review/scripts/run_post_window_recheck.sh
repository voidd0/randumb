#!/usr/bin/env bash
set -euo pipefail

cd /opt/voiddo-rescue

exec 9>/tmp/voiddo-rescue-post-window-recheck.lock
if ! flock -n 9; then
  echo '{"status":"skipped","reason":"already_running","live_outreach_allowed":false,"sends_started":false}'
  exit 0
fi

docker compose exec -T api python -m app.post_window_recheck_runner
