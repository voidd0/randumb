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


def _is_pause_gate_block(row: dict[str, Any]) -> bool:
    payload = row.get("payload_json") or {}
    checks = payload.get("checks", {}) if isinstance(payload, dict) else {}
    if row.get("block_reason") not in {"live_outreach_not_approved", "outreach_dry_run_enabled"}:
        return False
    return bool(
        checks.get("runtime_outreach_paused")
        or checks.get("outreach_paused")
        or checks.get("outreach_dry_run")
        or checks.get("first_live_send_flag") is False
    )


def _classify(row: dict[str, Any]) -> str:
    if row.get("is_suppressed"):
        return "keep_blocked_recipient_suppressed"
    if _is_pause_gate_block(row):
        return "requeue_pause_gate_block"
    reason = str(row.get("block_reason") or "unknown")
    if "preflight" in reason:
        return "keep_blocked_preflight"
    if reason in {"missing_unsubscribe", "missing_html_body", "recipient_suppressed"}:
        return f"keep_blocked_{reason}"
    return "keep_blocked_review_required"


def outreach_transport_block_hygiene(limit: int = 100, apply: bool = False) -> dict[str, Any]:
    """Recover rows incorrectly consumed by a pause gate.

    This is deliberately narrow: it only requeues transport-blocked outreach
    rows whose latest transport event shows a pause/dry-run/live-flag gate. It
    does not requeue suppressed, preflight-failed, malformed, or unknown rows.
    """
    safe_limit = max(1, min(int(limit or 100), 500))
    rows = [
        dict(row)
        for row in fetch_all(
            """
            WITH latest_event AS (
              SELECT DISTINCT ON (payload_json->>'message_id')
                     payload_json->>'message_id' AS message_id,
                     message AS block_reason,
                     payload_json,
                     created_at
              FROM system_events
              WHERE type = 'outreach.transport_blocked'
                AND payload_json ? 'message_id'
              ORDER BY payload_json->>'message_id', created_at DESC
            )
            SELECT om.id AS outreach_message_id,
                   lower(split_part(COALESCE(l.email, ''), '@', 2)) AS recipient_domain,
                   le.block_reason,
                   le.payload_json,
                   EXISTS (
                     SELECT 1
                     FROM suppression_list s
                     WHERE lower(s.email) = lower(l.email)
                        OR lower(COALESCE(s.domain, '')) = lower(split_part(COALESCE(l.email, ''), '@', 2))
                   ) AS is_suppressed
            FROM outreach_messages om
            LEFT JOIN leads l ON l.id = om.lead_id
            LEFT JOIN latest_event le ON le.message_id = om.id::text
            WHERE om.status = 'transport_blocked'
            ORDER BY om.created_at DESC
            LIMIT %s
            """,
            (safe_limit,),
        )
    ]
    classified = [{**row, "decision": _classify(row)} for row in rows]
    requeue_rows = [row for row in classified if row["decision"] == "requeue_pause_gate_block"]
    requeued = 0
    if apply and requeue_rows:
        ids = [str(row["outreach_message_id"]) for row in requeue_rows]
        execute(
            """
            UPDATE outreach_messages
            SET status = 'queued',
                send_after = GREATEST(COALESCE(send_after, now()), now() + interval '10 minutes')
            WHERE id = ANY(%s::uuid[])
              AND status = 'transport_blocked'
            """,
            (ids,),
        )
        requeued = len(requeue_rows)
        for row in requeue_rows:
            execute(
                """
                INSERT INTO system_events(type, severity, message, payload_json)
                VALUES ('outreach.transport_requeued_after_pause_block', 'info', %s, %s)
                """,
                (
                    "requeue_pause_gate_block",
                    Jsonb(
                        {
                            "message_id": str(row["outreach_message_id"]),
                            "recipient_domain_hash": recipient_hash(row.get("recipient_domain") or ""),
                            "previous_reason": row.get("block_reason") or "unknown",
                            **SAFE_FLAGS,
                        }
                    ),
                ),
            )
    keep_rows = [row for row in classified if row["decision"] != "requeue_pause_gate_block"]
    result = json_safe(
        {
            "status": "requeued" if requeued else ("review_required" if rows else "clean"),
            "apply": bool(apply),
            "checked_limit": safe_limit,
            "matched_count": len(rows),
            "requeue_candidate_count": len(requeue_rows),
            "requeued_count": requeued,
            "kept_blocked_count": len(keep_rows),
            "sample": [
                {
                    "outreach_message_id": str(row["outreach_message_id"]),
                    "decision": row["decision"],
                    "block_reason": row.get("block_reason") or "unknown",
                    "recipient_domain_hash": recipient_hash(row.get("recipient_domain") or ""),
                }
                for row in classified[:20]
            ],
            **SAFE_FLAGS,
        }
    )
    execute(
        """
        INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at)
        VALUES ('outreach_transport_block_hygiene_agent', %s, %s, now(), now())
        """,
        ("completed" if not keep_rows else "blocked", Jsonb(result)),
    )
    return result

