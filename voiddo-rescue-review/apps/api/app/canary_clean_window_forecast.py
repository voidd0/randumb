from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_one
from .p0 import json_safe, mail_signal_summary, runtime_control_enabled


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


BLOCKING_SIGNALS = (
    "bounce",
    "dsn",
    "smtp_rate_limit",
    "spam_signal",
    "auth_failure",
    "tls_failure",
    "dkim_failure",
    "dmarc_failure",
)


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def canary_clean_window_forecast(window_hours: int = 24, store: bool = True) -> dict[str, Any]:
    hours = max(1, min(int(window_hours or 24), 168))
    row = fetch_one(
        """
        SELECT now() AS now_at,
               max(created_at) AS last_signal_at,
               count(*) AS signal_count
        FROM mail_signals
        WHERE signal_type = ANY(%s)
          AND created_at >= now() - (%s || ' hours')::interval
        """,
        (list(BLOCKING_SIGNALS), hours),
    ) or {}
    now_at = row.get("now_at") or datetime.now(timezone.utc)
    last_signal_at = row.get("last_signal_at")
    signal_count = int(row.get("signal_count") or 0)
    eligible_after = last_signal_at + timedelta(hours=hours) if last_signal_at else now_at
    seconds_remaining = max(0, int((eligible_after - now_at).total_seconds())) if last_signal_at else 0
    summary = mail_signal_summary(hours)
    queued = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'") or {}
    sent = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'sent'") or {}
    bounced = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'bounced'") or {}
    clean = signal_count == 0
    pause_outreach = runtime_control_enabled("pause_outreach")
    if clean and pause_outreach:
        next_action = "run_canary_resume_plan_apply_true"
    elif clean:
        next_action = "worker_may_continue_queued_canary_under_spacing"
    else:
        next_action = "wait_until_eligible_after_then_rerun_mail_qa_and_resume_plan"

    result = json_safe(
        {
            "status": "clean" if clean else "waiting_clean_window",
            "window_hours": hours,
            "now_at": _iso(now_at),
            "last_signal_at": _iso(last_signal_at),
            "eligible_after": _iso(eligible_after),
            "seconds_remaining": seconds_remaining,
            "signal_count": signal_count,
            "signal_counts": {
                "bounce_or_dsn": int(summary.get("bounce_or_dsn_count", 0) or 0),
                "rate_limit": int(summary.get("rate_limit_count", 0) or 0),
                "spam": int(summary.get("spam_signal_count", 0) or 0),
                "mail_auth_failure": int(summary.get("mail_auth_failure_count", 0) or 0),
            },
            "pause_outreach": pause_outreach,
            "queued_count": int(queued.get("count") or 0),
            "smtp_sent_count": int(sent.get("count") or 0),
            "bounced_count": int(bounced.get("count") or 0),
            "next_action": next_action,
            **SAFE_FLAGS,
        }
    )
    if store:
        execute(
            """
            INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at)
            VALUES ('canary_clean_window_forecast_agent', %s, %s, now(), now())
            """,
            ("completed" if clean else "blocked", Jsonb(result)),
        )
    return result

