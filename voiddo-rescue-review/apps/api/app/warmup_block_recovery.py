from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import email_provider, json_safe, recipient_hash, warmup_pre_send_gate


RECOVERABLE_STATUSES = {
    "blocked_recent_bounce",
    "blocked_recent_rate_limit",
    "blocked_mail_qa",
    "blocked_paused",
}

SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _count_for_local_day(local_date) -> int:
    tz = ZoneInfo("Asia/Jerusalem")
    start = datetime.combine(local_date, time.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    row = fetch_one(
        """
        SELECT count(*) AS count
        FROM warmup_schedule
        WHERE status = 'scheduled'
          AND scheduled_for >= %s
          AND scheduled_for < %s
        """,
        (start, end),
    )
    return int(row["count"] or 0) if row else 0


def _next_recovery_slot(original) -> datetime:
    tz = ZoneInfo("Asia/Jerusalem")
    now_local = datetime.now(tz)
    original_local = original.astimezone(tz) if original else now_local
    if original_local > now_local + timedelta(hours=1):
        return original_local.astimezone(timezone.utc)

    slots = [time(10, 15), time(16, 15)]
    for day_offset in range(0, 21):
        local_date = (now_local + timedelta(days=day_offset)).date()
        if _count_for_local_day(local_date) >= 2:
            continue
        for slot in slots:
            candidate = datetime.combine(local_date, slot, tzinfo=tz)
            if candidate > now_local + timedelta(hours=2):
                return candidate.astimezone(timezone.utc)
    return (now_local + timedelta(days=1)).astimezone(timezone.utc)


def warmup_block_recovery_snapshot(limit: int = 50) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 50), 200))
    rows = fetch_all(
        """
        SELECT id, recipient_email, sender_mailbox, day_number, scheduled_for, status, result_json
        FROM warmup_schedule
        WHERE status = ANY(%s)
        ORDER BY updated_at DESC, scheduled_for ASC
        LIMIT %s
        """,
        (list(RECOVERABLE_STATUSES), safe_limit),
    )
    candidates = []
    recoverable_count = 0
    for row in rows:
        gate = warmup_pre_send_gate(dict(row))
        recoverable = bool(gate.get("allowed"))
        recoverable_count += 1 if recoverable else 0
        candidates.append(
            {
                "schedule_id": str(row["id"]),
                "status": row["status"],
                "day_number": int(row["day_number"] or 0),
                "recipient_hash": recipient_hash(row["recipient_email"]),
                "provider": email_provider(row["recipient_email"]),
                "sender_mailbox": row["sender_mailbox"],
                "recoverable": recoverable,
                "gate_status": gate.get("status"),
                "scheduled_for": row["scheduled_for"].isoformat() if row.get("scheduled_for") else None,
            }
        )
    return json_safe(
        {
            "status": "recoverable_rows_found" if recoverable_count else ("blocked_rows_found" if rows else "idle"),
            "candidate_count": len(candidates),
            "recoverable_count": recoverable_count,
            "candidates": candidates,
            **SAFE_FLAGS,
        }
    )


def recover_blocked_warmup_slots(limit: int = 25, apply: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    rows = fetch_all(
        """
        SELECT id, recipient_email, sender_mailbox, day_number, scheduled_for, status, result_json
        FROM warmup_schedule
        WHERE status = ANY(%s)
        ORDER BY updated_at ASC, scheduled_for ASC
        LIMIT %s
        """,
        (list(RECOVERABLE_STATUSES), safe_limit),
    )
    recovered = []
    still_blocked = []
    for row in rows:
        gate = warmup_pre_send_gate(dict(row))
        if not gate.get("allowed"):
            still_blocked.append(
                {
                    "schedule_id": str(row["id"]),
                    "status": row["status"],
                    "gate_status": gate.get("status"),
                    "recipient_hash": recipient_hash(row["recipient_email"]),
                    "provider": email_provider(row["recipient_email"]),
                }
            )
            continue
        new_time = _next_recovery_slot(row.get("scheduled_for"))
        item = {
            "schedule_id": str(row["id"]),
            "old_status": row["status"],
            "new_status": "scheduled",
            "old_scheduled_for": row["scheduled_for"].isoformat() if row.get("scheduled_for") else None,
            "new_scheduled_for": new_time.isoformat(),
            "recipient_hash": recipient_hash(row["recipient_email"]),
            "provider": email_provider(row["recipient_email"]),
            **SAFE_FLAGS,
        }
        if apply:
            execute(
                """
                UPDATE warmup_schedule
                SET status = 'scheduled',
                    scheduled_for = %s,
                    result_json = COALESCE(result_json, '{}'::jsonb) || %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    new_time,
                    Jsonb(
                        {
                            "warmup_block_recovery": {
                                "old_status": row["status"],
                                "new_scheduled_for": new_time.isoformat(),
                                "send_mail": False,
                                "live_outreach_allowed": False,
                            }
                        }
                    ),
                    row["id"],
                ),
            )
        recovered.append(item)

    status = "applied" if apply and recovered else ("planned" if recovered else ("blocked" if rows else "idle"))
    result = json_safe(
        {
            "status": status,
            "applied": bool(apply),
            "inspected_count": len(rows),
            "recovered_count": len(recovered),
            "still_blocked_count": len(still_blocked),
            "recovered": recovered,
            "still_blocked": still_blocked,
            **SAFE_FLAGS,
        }
    )
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('warmup.block_recovery', %s, %s, %s)
        """,
        (
            "info" if recovered else "warning",
            "Warmup blocked-slot recovery evaluated",
            Jsonb(result),
        ),
    )
    return result
