from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import json_safe, recipient_hash, set_runtime_control


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


def _count(query: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(query, params)
    return int((row or {}).get("count", 0) or 0)


def outreach_post_send_observer(window_hours: int = 24, apply_pause: bool = True) -> dict[str, Any]:
    hours = max(1, min(int(window_hours or 24), 168))
    sent_rows = fetch_all(
        """
        SELECT om.id, om.provider_message_id, om.sent_at, a.domain,
               lower(split_part(l.email, '@', 2)) AS recipient_domain
        FROM outreach_messages om
        JOIN leads l ON l.id = om.lead_id
        LEFT JOIN audits a ON a.id = om.audit_id
        WHERE om.status = 'sent'
          AND om.sent_at >= now() - (%s || ' hours')::interval
        ORDER BY om.sent_at DESC
        LIMIT 100
        """,
        (hours,),
    )
    signals = fetch_all(
        """
        SELECT signal_type, severity, source, mailbox, provider, message_id, created_at, raw_summary
        FROM mail_signals
        WHERE signal_type = ANY(%s)
          AND created_at >= now() - (%s || ' hours')::interval
        ORDER BY created_at DESC
        LIMIT 100
        """,
        (list(BLOCKING_SIGNALS), hours),
    )
    reply_count = _count(
        """
        SELECT count(*) AS count
        FROM inbox_threads
        WHERE updated_at >= now() - (%s || ' hours')::interval
        """,
        (hours,),
    )
    bounce_count = sum(1 for row in signals if row["signal_type"] in {"bounce", "dsn"})
    rate_count = sum(1 for row in signals if row["signal_type"] == "smtp_rate_limit")
    spam_count = sum(1 for row in signals if row["signal_type"] == "spam_signal")
    mail_auth_failure_count = sum(
        1
        for row in signals
        if row["signal_type"] in {"auth_failure", "tls_failure", "dkim_failure", "dmarc_failure"}
    )
    blockers = []
    if bounce_count:
        blockers.append("recent_bounce_or_dsn_after_send")
    if rate_count:
        blockers.append("recent_rate_limit_after_send")
    if spam_count:
        blockers.append("recent_spam_signal_after_send")
    if mail_auth_failure_count:
        blockers.append("recent_mail_auth_failure_after_send")

    pause_applied = False
    if blockers and apply_pause:
        set_runtime_control("pause_outreach", True, "outreach_post_send_observer", ",".join(blockers))
        pause_applied = True

    decision = "BLOCK_AND_PAUSE_OUTREACH" if blockers else "CLEAN_NO_POST_SEND_BLOCKERS"
    status = "blocked" if blockers else "clean"
    result = json_safe(
        {
            "status": status,
            "decision": decision,
            "window_hours": hours,
            "observed_sent_count": len(sent_rows),
            "reply_count": reply_count,
            "bounce_or_dsn_count": bounce_count,
            "rate_limit_count": rate_count,
            "spam_signal_count": spam_count,
            "mail_auth_failure_count": mail_auth_failure_count,
            "pause_outreach_applied": pause_applied,
            "blockers": blockers,
            "sent_message_sample": [
                {
                    "outreach_message_id": str(row["id"]),
                    "provider_message_id_present": bool(row.get("provider_message_id")),
                    "sent_at": row.get("sent_at"),
                    "domain": row.get("domain") or "",
                    "recipient_domain_hash": recipient_hash(row.get("recipient_domain") or ""),
                }
                for row in sent_rows[:10]
            ],
            "signal_sample": [
                {
                    "signal_type": row["signal_type"],
                    "severity": row["severity"],
                    "source": row["source"],
                    "mailbox": row["mailbox"],
                    "provider": row["provider"],
                    "message_id_present": bool(row.get("message_id")),
                    "created_at": row["created_at"],
                    "raw_summary": row.get("raw_summary", "")[:160],
                }
                for row in signals[:10]
            ],
            **SAFE_FLAGS,
        }
    )
    run = execute(
        """
        INSERT INTO outreach_post_send_observer_runs(
          status, decision, observed_sent_count, reply_count,
          bounce_or_dsn_count, rate_limit_count, spam_signal_count,
          pause_outreach_applied, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, status, decision, observed_sent_count, reply_count,
                  bounce_or_dsn_count, rate_limit_count, spam_signal_count,
                  pause_outreach_applied, created_at
        """,
        (
            status,
            decision,
            len(sent_rows),
            reply_count,
            bounce_count,
            rate_count,
            spam_count,
            pause_applied,
            Jsonb(result),
        ),
    )
    return json_safe({"run": dict(run), "result": result, **SAFE_FLAGS})


def latest_outreach_post_send_observer_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, decision, observed_sent_count, reply_count,
               bounce_or_dsn_count, rate_limit_count, spam_signal_count,
               pause_outreach_applied, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM outreach_post_send_observer_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 50)),),
    )
    return json_safe({"count": len(rows), "runs": [dict(row) for row in rows], **SAFE_FLAGS})
