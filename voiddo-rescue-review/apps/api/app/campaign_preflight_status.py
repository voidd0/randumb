from __future__ import annotations

from typing import Any

from .db import fetch_one


SAFE_PREFLIGHT_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}

PREFLIGHT_FRESH_MINUTES = 120
PREFLIGHT_POLICY_VERSION = "20260529_mx_bounce_v1"


def latest_campaign_preflight_status(campaign_id: str | None, max_age_minutes: int = PREFLIGHT_FRESH_MINUTES) -> dict[str, Any]:
    if not campaign_id:
        return {
            "allowed": False,
            "reason": "campaign_preflight_campaign_id_missing",
            "decision": "MISSING",
            "fresh": False,
            **SAFE_PREFLIGHT_FLAGS,
        }
    row = fetch_one(
        """
        SELECT id, campaign_id, status, decision, checked_count, ready_count, blocker_count, created_at,
               COALESCE(result_json->>'policy_version', '') AS policy_version,
               created_at >= now() - (%s || ' minutes')::interval AS fresh
        FROM campaign_preflight_runs
        WHERE campaign_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (max(1, min(int(max_age_minutes or PREFLIGHT_FRESH_MINUTES), 1440)), campaign_id),
    )
    if not row:
        return {
            "allowed": False,
            "reason": "campaign_preflight_missing",
            "campaign_id": campaign_id,
            "decision": "MISSING",
            "fresh": False,
            **SAFE_PREFLIGHT_FLAGS,
        }
    policy_current = row["policy_version"] == PREFLIGHT_POLICY_VERSION
    allowed = row["decision"] == "PASS_NO_SEND_PREFLIGHT" and bool(row["fresh"]) and policy_current
    if allowed:
        reason = "campaign_preflight_pass"
    elif row["decision"] == "PASS_NO_SEND_PREFLIGHT" and not policy_current:
        reason = "campaign_preflight_policy_stale"
    elif row["decision"] == "PASS_NO_SEND_PREFLIGHT":
        reason = "campaign_preflight_stale"
    else:
        reason = "campaign_preflight_not_pass"
    return {
        "allowed": allowed,
        "reason": reason,
        "id": str(row["id"]),
        "campaign_id": str(row["campaign_id"]),
        "status": row["status"],
        "decision": row["decision"],
        "checked_count": int(row["checked_count"] or 0),
        "ready_count": int(row["ready_count"] or 0),
        "blocker_count": int(row["blocker_count"] or 0),
        "fresh": bool(row["fresh"]),
        "policy_version": row["policy_version"] or None,
        "required_policy_version": PREFLIGHT_POLICY_VERSION,
        "policy_current": policy_current,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        **SAFE_PREFLIGHT_FLAGS,
    }
