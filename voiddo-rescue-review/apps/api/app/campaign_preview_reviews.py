from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .audit_strength import score_audit_strength
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


def auto_review_campaign_previews(limit: int = 25, apply: bool = True, campaign_id: str | None = None, reconsider_held: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    rows = fetch_all(
        """
        SELECT cl.id AS campaign_lead_id, cl.status, cl.score AS lead_score, cl.audit_id,
               c.id AS campaign_id, c.name AS campaign_name,
               l.status AS lead_status,
               b.domain, a.public_slug,
               latest_strength.final_score AS audit_strength_score,
               COALESCE(issue_counts.issue_count, 0) AS issue_count,
               COALESCE(issue_counts.critical_high_count, 0) AS critical_high_count,
               COALESCE(shot_counts.screenshot_count, 0) AS screenshot_count,
               latest_review.action AS latest_review_action,
               latest_review.actor AS latest_review_actor
        FROM campaign_leads cl
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN leads l ON l.id = cl.lead_id
        JOIN businesses b ON b.id = l.business_id
        LEFT JOIN audits a ON a.id = cl.audit_id
        LEFT JOIN LATERAL (
          SELECT final_score FROM audit_strength_scores WHERE audit_id = cl.audit_id ORDER BY created_at DESC LIMIT 1
        ) latest_strength ON true
        LEFT JOIN LATERAL (
          SELECT count(*) AS issue_count,
                 count(*) FILTER (WHERE severity IN ('critical', 'high')) AS critical_high_count
          FROM audit_issues
          WHERE audit_id = cl.audit_id
        ) issue_counts ON true
        LEFT JOIN LATERAL (
          SELECT count(*) AS screenshot_count
          FROM screenshots
          WHERE audit_id = cl.audit_id
        ) shot_counts ON true
        LEFT JOIN LATERAL (
          SELECT action, actor FROM campaign_preview_reviews WHERE campaign_lead_id = cl.id ORDER BY created_at DESC LIMIT 1
        ) latest_review ON true
        WHERE cl.status = 'preview'
          AND (
            latest_review.action IS NULL
            OR (%s AND latest_review.action = 'held' AND latest_review.actor = 'campaign_preview_self_review_agent')
          )
          AND (%s::uuid IS NULL OR c.id = %s::uuid)
        ORDER BY cl.score DESC NULLS LAST, cl.updated_at DESC NULLS LAST, cl.created_at DESC
        LIMIT %s
        """,
        (bool(reconsider_held), campaign_id, campaign_id, safe_limit),
    )
    decisions = []
    applied = 0
    for row in rows:
        lead_score = int(row["lead_score"] or 0)
        audit_strength = int(row["audit_strength_score"] or 0)
        if not audit_strength and row.get("audit_id"):
            audit_strength = int(score_audit_strength(str(row["audit_id"]))["final_score"])
        issue_count = int(row["issue_count"] or 0)
        critical_high_count = int(row["critical_high_count"] or 0)
        screenshot_count = int(row["screenshot_count"] or 0)
        domain = (row["domain"] or "").lower()
        lead_status = row["lead_status"] or ""
        action = "held"
        reason = "needs stronger evidence before preview approval"
        if lead_status in {"excluded_sensitive_target", "suppressed", "unsubscribed"} or domain.endswith(".example.test") or domain in {"example.com", "localhost"}:
            action = "rejected"
            reason = "suppressed, sensitive, or non-production target"
        elif not row.get("public_slug"):
            action = "held"
            reason = "missing public audit page"
        elif lead_score >= 80 and audit_strength >= 75:
            action = "approved"
            reason = "lead score and audit evidence meet no-send preview threshold"
        elif lead_score >= 75 and audit_strength >= 70 and issue_count >= 2 and critical_high_count >= 1 and screenshot_count >= 1:
            action = "approved"
            reason = "two specific public issues and screenshot evidence meet no-send preview threshold"
        elif lead_score >= 72 and audit_strength >= 77:
            action = "approved"
            reason = "specific public audit evidence meets no-send preview threshold"
        elif lead_score < 70 or audit_strength < 70:
            action = "held"
            reason = "lead or audit score below preview threshold"
        decision = {
            "campaign_lead_id": str(row["campaign_lead_id"]),
            "campaign_id": str(row["campaign_id"]),
            "domain": row["domain"],
            "lead_score": lead_score,
            "audit_strength_score": audit_strength,
            "issue_count": issue_count,
            "critical_high_count": critical_high_count,
            "screenshot_count": screenshot_count,
            "action": action,
            "reason": reason,
        }
        if apply:
            review_campaign_preview(str(row["campaign_lead_id"]), action, reason, "campaign_preview_self_review_agent")
            applied += 1
        decisions.append(decision)
    return json_safe(
        {
            "status": "completed" if decisions else "idle_no_unreviewed_previews",
            "campaign_id": campaign_id,
            "reconsider_held": bool(reconsider_held),
            "checked_count": len(decisions),
            "applied_count": applied,
            "approved_count": len([item for item in decisions if item["action"] == "approved"]),
            "held_count": len([item for item in decisions if item["action"] == "held"]),
            "rejected_count": len([item for item in decisions if item["action"] == "rejected"]),
            "decisions": decisions,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
