from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import json_safe, recipient_hash


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def outreach_queue_suppression_hygiene(limit: int = 100, apply: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 500))
    rows = [
        dict(row)
        for row in fetch_all(
            """
            SELECT DISTINCT ON (om.id)
                   om.id AS outreach_message_id,
                   om.lead_id,
                   lower(split_part(COALESCE(l.email, ''), '@', 2)) AS recipient_domain,
                   CASE
                     WHEN s.email IS NOT NULL THEN 'email_suppressed'
                     WHEN s.domain IS NOT NULL THEN 'domain_suppressed'
                     ELSE 'suppressed'
                   END AS reason
            FROM outreach_messages om
            JOIN leads l ON l.id = om.lead_id
            JOIN suppression_list s
              ON lower(s.email) = lower(l.email)
              OR lower(COALESCE(s.domain, '')) = lower(split_part(COALESCE(l.email, ''), '@', 2))
            WHERE om.status = 'queued'
            ORDER BY om.id, s.created_at DESC
            LIMIT %s
            """,
            (safe_limit,),
        )
    ]
    blocked = 0
    if apply and rows:
        ids = [str(row["outreach_message_id"]) for row in rows]
        execute(
            """
            UPDATE outreach_messages
            SET status = 'transport_blocked'
            WHERE id = ANY(%s::uuid[])
              AND status = 'queued'
            """,
            (ids,),
        )
        for row in rows:
            execute(
                """
                INSERT INTO email_events(outreach_message_id, event_type, payload_json)
                VALUES (%s, 'outreach_queue_suppression_block', %s)
                """,
                (
                    row["outreach_message_id"],
                    Jsonb(
                        {
                            "reason": row["reason"],
                            "recipient_domain_hash": recipient_hash(row.get("recipient_domain") or ""),
                            "send_mail": False,
                            "live_outreach_allowed": False,
                        }
                    ),
                ),
            )
        blocked = len(rows)
    result = json_safe(
        {
            "status": "blocked_rows_found" if rows else "clean",
            "apply": bool(apply),
            "checked_limit": safe_limit,
            "matched_count": len(rows),
            "blocked_count": blocked,
            "sample": [
                {
                    "outreach_message_id": str(row["outreach_message_id"]),
                    "reason": row["reason"],
                    "recipient_domain_hash": recipient_hash(row.get("recipient_domain") or ""),
                }
                for row in rows[:20]
            ],
            **SAFE_FLAGS,
        }
    )
    execute(
        """
        INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at)
        VALUES ('outreach_queue_suppression_hygiene_agent', %s, %s, now(), now())
        """,
        ("blocked" if rows else "completed", Jsonb(result)),
    )
    return result
