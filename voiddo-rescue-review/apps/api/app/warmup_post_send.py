from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import json_safe, set_runtime_control


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}

BLOCKING_SIGNALS = {"bounce", "dsn", "smtp_rate_limit", "spam_signal", "auth_failure", "tls_failure", "dkim_failure", "dmarc_failure"}


def _sent_warmup_rows(limit: int) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
          ws.id,
          ws.sender_mailbox,
          ws.day_number,
          ws.sent_at,
          ws.result_json,
          ee.payload_json->>'recipient_hash' AS recipient_hash,
          ee.message_id AS event_message_id
        FROM warmup_schedule ws
        LEFT JOIN email_events ee
          ON ee.event_type = 'warmup_sent'
         AND ee.payload_json->>'schedule_id' = ws.id::text
        WHERE ws.status = 'sent'
          AND ws.sent_at IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM warmup_post_send_checks wpsc
            WHERE wpsc.result_json->'checked_schedule_ids' ? ws.id::text
          )
        ORDER BY ws.sent_at ASC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 100)),),
    )


def _signals_for(row: dict[str, Any]) -> list[dict[str, Any]]:
    result_json = row.get("result_json") if isinstance(row.get("result_json"), dict) else {}
    message_id = result_json.get("message_id") or row.get("event_message_id")
    recipient_hash = row.get("recipient_hash")
    rows = fetch_all(
        """
        SELECT signal_type, severity, source, mailbox, provider, message_id, raw_summary, created_at
        FROM mail_signals
        WHERE created_at >= %s
          AND (
            (%s::text IS NOT NULL AND message_id = %s)
            OR (%s::text IS NOT NULL AND recipient_hash = %s)
            OR signal_type = ANY(%s)
          )
        ORDER BY created_at DESC
        LIMIT 25
        """,
        (row["sent_at"], message_id, message_id, recipient_hash, recipient_hash, list(BLOCKING_SIGNALS)),
    )
    return [
        {
            "signal_type": item["signal_type"],
            "severity": item["severity"],
            "source": item["source"],
            "mailbox": item["mailbox"],
            "provider": item["provider"],
            "message_id": item["message_id"],
            "raw_summary": (item["raw_summary"] or "")[:160],
            "created_at": item["created_at"].isoformat() if item.get("created_at") else None,
        }
        for item in rows
    ]


def observe_warmup_post_send(limit: int = 10, pause_on_blocker: bool = True) -> dict[str, Any]:
    rows = _sent_warmup_rows(limit)
    observations: list[dict[str, Any]] = []
    blocked = 0
    checked_schedule_ids: dict[str, bool] = {}
    for row in rows:
        signals = _signals_for(row)
        blocking = [signal for signal in signals if signal["signal_type"] in BLOCKING_SIGNALS]
        if blocking:
            blocked += 1
        schedule_id = str(row["id"])
        checked_schedule_ids[schedule_id] = True
        observations.append(
            {
                "schedule_id": schedule_id,
                "sender_mailbox": row["sender_mailbox"],
                "day_number": int(row["day_number"] or 0),
                "sent_at": row["sent_at"].isoformat() if row.get("sent_at") else None,
                "recipient_hash_present": bool(row.get("recipient_hash")),
                "signal_count": len(signals),
                "blocking_signal_count": len(blocking),
                "signals": signals,
            }
        )

    paused = False
    if blocked and pause_on_blocker:
        set_runtime_control("pause_warmup", True, "warmup_post_send_observer", "blocking post-send mail signal")
        paused = True

    status = "idle_no_sent_warmup" if not rows else ("paused_warmup_on_signal" if paused else "observed_clean")
    result = json_safe(
        {
            "status": status,
            "checked_count": len(rows),
            "clean_count": len(rows) - blocked,
            "blocked_count": blocked,
            "paused_warmup": paused,
            "checked_schedule_ids": checked_schedule_ids,
            "observations": observations,
            **SAFE_FLAGS,
        }
    )
    row = execute(
        """
        INSERT INTO warmup_post_send_checks(
          status, checked_count, clean_count, blocked_count, paused_warmup, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (result["status"], result["checked_count"], result["clean_count"], result["blocked_count"], result["paused_warmup"], Jsonb(result)),
    )
    result["check_id"] = str(row["id"])
    result["created_at"] = row["created_at"].isoformat()
    return result


def latest_warmup_post_send_checks(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, checked_count, clean_count, blocked_count, paused_warmup,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM warmup_post_send_checks
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 100)),),
    )
    return {
        "count": len(rows),
        "history": [
            {
                "id": str(row["id"]),
                "status": row["status"],
                "checked_count": int(row["checked_count"] or 0),
                "clean_count": int(row["clean_count"] or 0),
                "blocked_count": int(row["blocked_count"] or 0),
                "paused_warmup": bool(row["paused_warmup"]),
                "send_mail": bool(row["send_mail"]),
                "smtp_called": bool(row["smtp_called"]),
                "live_outreach_allowed": bool(row["live_outreach_allowed"]),
                "raw_recipient_addresses_included": bool(row["raw_recipient_addresses_included"]),
                "secrets_included": bool(row["secrets_included"]),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ],
        **SAFE_FLAGS,
    }
