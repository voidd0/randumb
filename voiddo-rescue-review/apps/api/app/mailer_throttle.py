from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_one
from .p0 import recent_mail_signal_count


def throttle_decision(scope: str, scope_key: str, min_delay_seconds: int = 600) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM mail_throttle_state WHERE scope = %s AND scope_key = %s", (scope, scope_key))
    now = datetime.now(timezone.utc)
    checks = {
        "scope": scope,
        "scope_key": scope_key,
        "min_delay_seconds": min_delay_seconds,
        "recent_bounce_or_dsn_count": recent_mail_signal_count(["bounce", "dsn"], 24),
        "recent_rate_limit_count": recent_mail_signal_count(["smtp_rate_limit"], 24),
    }
    if checks["recent_bounce_or_dsn_count"] > 0:
        return {"allowed": False, "reason": "recent_bounce_or_dsn", "checks": checks}
    if checks["recent_rate_limit_count"] > 0:
        return {"allowed": False, "reason": "recent_rate_limit", "checks": checks}
    if row and row.get("backoff_until") and row["backoff_until"] > now:
        return {"allowed": False, "reason": "backoff_active", "checks": {**checks, "backoff_until": row["backoff_until"]}}
    if row and row.get("last_sent_at"):
        elapsed = (now - row["last_sent_at"]).total_seconds()
        if elapsed < min_delay_seconds:
            return {"allowed": False, "reason": "min_delay", "checks": {**checks, "elapsed_seconds": elapsed}}
    return {"allowed": True, "reason": "allowed", "checks": checks}


def record_throttle_send(scope: str, scope_key: str, reason: str = "sent") -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO mail_throttle_state(scope, scope_key, last_sent_at, sent_last_hour, sent_today, reason)
        VALUES (%s, %s, now(), 1, 1, %s)
        ON CONFLICT (scope, scope_key) DO UPDATE
          SET last_sent_at = now(),
              sent_last_hour = mail_throttle_state.sent_last_hour + 1,
              sent_today = mail_throttle_state.sent_today + 1,
              reason = EXCLUDED.reason,
              updated_at = now()
        RETURNING *
        """,
        (scope, scope_key, reason),
    )
    return dict(row)
