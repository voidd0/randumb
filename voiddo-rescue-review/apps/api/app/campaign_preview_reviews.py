from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import json_safe


ALLOWED_ACTIONS = {"approved", "held", "rejected"}


def normalize_preview_review_action(action: str) -> str:
    raw = (action or "").strip().lower()
    aliases = {
        "approve": "approved",
        "approved": "approved",
        "hold": "held",
        "held": "held",
        "reject": "rejected",
        "rejected": "rejected",
    }
    normalized = aliases.get(raw, raw)
    if normalized not in ALLOWED_ACTIONS:
        raise ValueError("unsupported_preview_review_action")
    return normalized


def review_campaign_preview(campaign_lead_id: str, action: str, reason: str = "", actor: str = "admin") -> dict[str, Any]:
    normalized = normalize_preview_review_action(action)
    row = fetch_one(
        """
        SELECT cl.id, cl.status, cl.score, c.id AS campaign_id, c.name AS campaign_name, b.domain, a.public_slug
        FROM campaign_leads cl
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN leads l ON l.id = cl.lead_id
        JOIN businesses b ON b.id = l.business_id
        LEFT JOIN audits a ON a.id = cl.audit_id
        WHERE cl.id = %s
        """,
        (campaign_lead_id,),
    )
    if not row:
        raise ValueError("campaign_preview_not_found")
    clean_reason = (reason or "").strip()[:280]
    result = {
        "campaign_lead_id": str(row["id"]),
        "campaign_id": str(row["campaign_id"]),
        "campaign_name": row["campaign_name"],
        "domain": row["domain"],
        "audit_slug": row["public_slug"],
        "preview_status": row["status"],
        "lead_score": int(row["score"] or 0),
        "action": normalized,
        "reason": clean_reason,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
    review = execute(
        """
        INSERT INTO campaign_preview_reviews(
          campaign_lead_id, action, reason, actor, result_json,
          send_mail, smtp_called, live_outreach_allowed, raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING *
        """,
        (campaign_lead_id, normalized, clean_reason, actor or "admin", Jsonb(result)),
    )
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('campaign_preview_review', 'info', %s, %s)
        """,
        (f"Campaign preview {normalized}", Jsonb(result)),
    )
    payload = dict(review)
    payload["result_json"] = result
    return json_safe(payload)


def latest_campaign_preview_reviews(limit: int = 25) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    rows = fetch_all(
        """
        SELECT r.id, r.campaign_lead_id, r.action, r.reason, r.actor, r.created_at,
               c.name AS campaign_name, b.domain, a.public_slug
        FROM campaign_preview_reviews r
        JOIN campaign_leads cl ON cl.id = r.campaign_lead_id
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN leads l ON l.id = cl.lead_id
        JOIN businesses b ON b.id = l.business_id
        LEFT JOIN audits a ON a.id = cl.audit_id
        ORDER BY r.created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    reviews = [
        {
            "id": str(row["id"]),
            "campaign_lead_id": str(row["campaign_lead_id"]),
            "action": row["action"],
            "reason": row["reason"],
            "actor": row["actor"],
            "campaign_name": row["campaign_name"],
            "domain": row["domain"],
            "audit_slug": row["public_slug"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return json_safe(
        {
            "status": "ready",
            "count": len(reviews),
            "reviews": reviews,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def campaign_preview_review_summary(campaign_id: str) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT cl.id AS campaign_lead_id, latest_review.action, latest_review.reason, latest_review.created_at
        FROM campaign_leads cl
        LEFT JOIN LATERAL (
          SELECT action, reason, created_at
          FROM campaign_preview_reviews
          WHERE campaign_lead_id = cl.id
          ORDER BY created_at DESC
          LIMIT 1
        ) latest_review ON true
        WHERE cl.campaign_id = %s
          AND cl.status = 'preview'
        """,
        (campaign_id,),
    )
    counts = {"approved": 0, "held": 0, "rejected": 0, "unreviewed": 0}
    latest = []
    for row in rows:
        action = row["action"] or "unreviewed"
        counts[action] = counts.get(action, 0) + 1
        latest.append(
            {
                "campaign_lead_id": str(row["campaign_lead_id"]),
                "action": action,
                "reason": row["reason"] or "",
                "created_at": row["created_at"],
            }
        )
    usable = counts["approved"] + counts["unreviewed"]
    return json_safe(
        {
            "campaign_id": campaign_id,
            "checked_count": len(rows),
            "approved_count": counts["approved"],
            "held_count": counts["held"],
            "rejected_count": counts["rejected"],
            "unreviewed_count": counts["unreviewed"],
            "usable_preview_count": usable,
            "decision": "BLOCKED_BY_REVIEW" if rows and usable <= 0 else "PASS_REVIEW_GATE",
            "latest_reviews": latest[:25],
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
