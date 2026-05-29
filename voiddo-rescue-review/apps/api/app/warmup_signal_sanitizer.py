from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import email_provider, json_safe, recipient_hash


BLOCKING_SIGNAL_TYPES = ("bounce", "dsn", "spam_signal")
SCHEDULE_STATUSES_TO_QUARANTINE = (
    "scheduled",
    "blocked_recent_bounce",
    "blocked_recent_rate_limit",
    "blocked_mail_qa",
    "blocked_paused",
    "failed",
)
SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def warmup_signal_sanitizer(window_hours: int = 168, limit: int = 200, apply: bool = True, source: str = "") -> dict[str, Any]:
    """Quarantine approved warmup recipients that match blocking mail signals.

    The database has raw owner-approved warmup addresses because SMTP needs them,
    but this function only returns hashes/providers. It never sends mail and it
    never tries to shorten the clean-window after a bounce.
    """
    hours = max(1, min(int(window_hours or 168), 720))
    safe_limit = max(1, min(int(limit or 200), 1000))
    signals = [
        dict(row)
        for row in fetch_all(
            """
            SELECT DISTINCT recipient_hash, signal_type, provider
            FROM mail_signals
            WHERE signal_type = ANY(%s)
              AND COALESCE(recipient_hash, '') <> ''
              AND created_at >= now() - (%s || ' hours')::interval
              AND (%s = '' OR source = %s)
            ORDER BY recipient_hash
            LIMIT %s
            """,
            (list(BLOCKING_SIGNAL_TYPES), hours, source, source, safe_limit),
        )
    ]
    signal_hashes = {str(row["recipient_hash"]) for row in signals if row.get("recipient_hash")}
    recipients = [
        dict(row)
        for row in fetch_all(
            """
            SELECT id, email, mailbox, status, approved
            FROM warmup_recipients
            WHERE approved
              AND status = 'approved_test_pool'
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (safe_limit,),
        )
    ]

    matched = [row for row in recipients if recipient_hash(row["email"]) in signal_hashes]
    quarantined_count = 0
    suppression_upserts = 0
    schedule_quarantined_count = 0
    samples: list[dict[str, Any]] = []

    for row in matched:
        hashed = recipient_hash(row["email"])
        provider = email_provider(row["email"])
        if apply:
            execute(
                """
                INSERT INTO suppression_list(email, reason, source)
                SELECT %s, 'warmup_blocking_mail_signal', 'warmup_signal_sanitizer'
                WHERE NOT EXISTS (
                  SELECT 1
                  FROM suppression_list
                  WHERE lower(email) = lower(%s)
                )
                """,
                (row["email"], row["email"]),
            )
            suppression_upserts += 1
            updated = execute(
                """
                UPDATE warmup_recipients
                SET approved = false,
                    status = 'suppressed_mail_signal',
                    notes = 'quarantined_by_warmup_signal_sanitizer'
                WHERE id = %s
                RETURNING id
                """,
                (row["id"],),
            )
            quarantined_count += 1 if updated else 0
            schedule_rows = fetch_all(
                """
                UPDATE warmup_schedule
                SET status = 'skipped_suppressed',
                    result_json = COALESCE(result_json, '{}'::jsonb) || %s::jsonb,
                    updated_at = now()
                WHERE lower(recipient_email) = lower(%s)
                  AND status = ANY(%s)
                RETURNING id
                """,
                (
                    Jsonb(
                        {
                            "warmup_signal_sanitizer": {
                                "recipient_hash": hashed,
                                "provider": provider,
                                "reason": "blocking_mail_signal",
                                "send_mail": False,
                                "live_outreach_allowed": False,
                            }
                        }
                    ),
                    row["email"],
                    list(SCHEDULE_STATUSES_TO_QUARANTINE),
                ),
            )
            schedule_quarantined_count += len(schedule_rows)
        samples.append(
            {
                "recipient_hash": hashed,
                "provider": provider,
                "mailbox": row["mailbox"],
                "old_status": row["status"],
            }
        )

    result = json_safe(
        {
            "status": "applied" if apply else "preview",
            "window_hours": hours,
            "source_filtered": bool(source),
            "signal_hash_count": len(signal_hashes),
            "approved_recipient_count": len(recipients),
            "matched_recipient_count": len(matched),
            "quarantined_recipient_count": quarantined_count,
            "suppression_upsert_attempts": suppression_upserts,
            "schedule_quarantined_count": schedule_quarantined_count,
            "samples": samples[:20],
            **SAFE_FLAGS,
        }
    )
    if apply:
        execute(
            """
            INSERT INTO system_events(type, severity, message, payload_json)
            VALUES ('warmup.signal_sanitizer', %s, 'Warmup signal sanitizer evaluated', %s)
            """,
            ("warning" if matched else "info", Jsonb(result)),
        )
    return result
