from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .campaign_preview_quality import campaign_preview_quality_pack
from .campaign_preview_reviews import campaign_preview_review_summary
from .campaign_preflight_status import PREFLIGHT_FRESH_MINUTES, latest_campaign_preflight_status
from .db import execute, fetch_all, fetch_one
from .mailer_action_queue import process_mailer_action_queue
from .mailer_control_room import mailer_digest_trend_guard, mailer_policy_score
from .p0 import json_safe, transport_gate_status


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}

EXPECTED_TRANSPORT_BLOCKS = {"outreach_dry_run_enabled", "live_outreach_not_approved"}


def _campaign_ids(limit: int, campaign_id: str | None = None) -> list[str]:
    if campaign_id:
        row = fetch_one("SELECT id FROM campaigns WHERE id = %s", (campaign_id,))
        return [str(row["id"])] if row else []
    rows = fetch_all(
        """
        SELECT c.id
        FROM campaigns c
        JOIN campaign_leads cl ON cl.campaign_id = c.id AND cl.status = 'preview'
        WHERE c.status IN ('preview_ready', 'draft')
        GROUP BY c.id
        ORDER BY max(cl.updated_at) DESC, c.updated_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 20), 100)),),
    )
    return [str(row["id"]) for row in rows]


def _record_inline_trend_guard(trend: dict[str, Any]) -> None:
    execute(
        """
        INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at)
        VALUES ('mailer_digest_trend_guard_agent', 'completed', %s, now(), now())
        """,
        (Jsonb(trend),),
    )


def campaign_preflight(campaign_id: str, limit: int = 20) -> dict[str, Any]:
    quality = campaign_preview_quality_pack(campaign_id, limit)
    reviews = campaign_preview_review_summary(campaign_id)
    policy = mailer_policy_score()
    policy_repair = None
    policy_blockers = policy.get("blockers") or []
    if policy.get("decision") == "NO_SEND_BLOCKED_REPAIR" and (
        "current_mailer_action_queue_not_empty" in policy_blockers or "trend_guard_not_pass" in policy_blockers
    ):
        queued = int(((policy.get("queue_hygiene") or {}).get("mailer_action_queue_rows") or 0))
        if queued <= 20:
            processed = process_mailer_action_queue(limit=queued) if queued > 0 else {"processed_count": 0}
            trend = mailer_digest_trend_guard()
            _record_inline_trend_guard(trend)
            policy = mailer_policy_score()
            policy_repair = {
                "attempted": True,
                "processed_count": int(processed.get("processed_count") or 0),
                "trend_decision": trend.get("decision"),
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
            }
    transport = transport_gate_status({"email": "redacted@example.test", "body": "Unsubscribe: https://go.rescue.voiddo.com/unsubscribe/preview"})

    blockers: list[str] = []
    if quality["status"] != "PASS_PREVIEW_QUALITY":
        blockers.append("preview_quality_not_pass")
    if int(quality.get("ready_count") or 0) <= 0:
        blockers.append("no_ready_preview_rows")
    if int(reviews.get("usable_preview_count") or 0) <= 0 and int(reviews.get("checked_count") or 0) > 0:
        blockers.append("preview_reviews_no_usable_rows")
    if int(reviews.get("held_count") or 0) > 0 and int(reviews.get("usable_preview_count") or 0) <= 0:
        blockers.append("preview_rows_held_for_review")
    if int(policy.get("score") or 0) < 90 or policy.get("decision") != "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW":
        blockers.append("mailer_policy_not_ready")
    if transport.get("allowed"):
        blockers.append("transport_unexpectedly_allows_live_send")
    if transport.get("reason") not in EXPECTED_TRANSPORT_BLOCKS:
        blockers.append("transport_unexpected_block_reason")

    decision = "PASS_NO_SEND_PREFLIGHT" if not blockers else "FAIL_BLOCK_LAUNCH"
    result = json_safe(
        {
            "campaign_id": campaign_id,
            "status": "completed",
            "decision": decision,
            "checked_count": int(quality.get("checked_count") or 0),
            "ready_count": int(quality.get("ready_count") or 0),
            "blockers": blockers,
            "blocker_count": len(blockers),
            "quality_status": quality.get("status"),
            "quality_blockers_by_code": quality.get("blockers_by_code", {}),
            "preview_review_summary": reviews,
            "mailer_policy_score": int(policy.get("score") or 0),
            "mailer_policy_decision": policy.get("decision"),
            "mailer_policy_repair": policy_repair,
            "transport_allowed": bool(transport.get("allowed")),
            "transport_reason": transport.get("reason"),
            **SAFE_FLAGS,
        }
    )
    row = execute(
        """
        INSERT INTO campaign_preflight_runs(
          campaign_id, status, decision, checked_count, ready_count, blocker_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (
            campaign_id,
            result["status"],
            result["decision"],
            result["checked_count"],
            result["ready_count"],
            result["blocker_count"],
            Jsonb(result),
        ),
    )
    result["run_id"] = str(row["id"])
    result["created_at"] = row["created_at"].isoformat()
    return result


def campaign_preflight_batch(limit: int = 20, campaign_id: str | None = None) -> dict[str, Any]:
    ids = _campaign_ids(limit, campaign_id)
    runs = [campaign_preflight(item, limit=20) for item in ids]
    passed = len([item for item in runs if item["decision"] == "PASS_NO_SEND_PREFLIGHT"])
    return {
        "status": "completed" if runs else "idle_no_campaigns",
        "campaign_count": len(runs),
        "passed_count": passed,
        "failed_count": len(runs) - passed,
        "runs": runs,
        **SAFE_FLAGS,
    }

def latest_campaign_preflight_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, campaign_id, status, decision, checked_count, ready_count, blocker_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM campaign_preflight_runs
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
                "campaign_id": str(row["campaign_id"]) if row.get("campaign_id") else None,
                "status": row["status"],
                "decision": row["decision"],
                "checked_count": int(row["checked_count"] or 0),
                "ready_count": int(row["ready_count"] or 0),
                "blocker_count": int(row["blocker_count"] or 0),
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


def campaign_preflight_orphan_hygiene(limit: int = 100, apply: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 500))
    rows = fetch_all(
        """
        SELECT id, decision, blocker_count, created_at
        FROM campaign_preflight_runs
        WHERE campaign_id IS NULL
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    ids = [str(row["id"]) for row in rows]
    deleted_count = 0
    if apply and ids:
        execute("DELETE FROM campaign_preflight_runs WHERE id = ANY(%s::uuid[])", (ids,))
        deleted_count = len(ids)
    return {
        "status": "clean" if not rows else ("cleaned" if apply else "orphans_found"),
        "orphan_count": len(rows),
        "deleted_count": deleted_count,
        "sample": [
            {
                "id": str(row["id"]),
                "decision": row["decision"],
                "blocker_count": int(row["blocker_count"] or 0),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows[:10]
        ],
        **SAFE_FLAGS,
    }
