from __future__ import annotations

from collections import Counter
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .economics import calculate_unit_economics
from .p0 import json_safe, recipient_hash


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}

CONTACT_MARKERS = ("contact", "form", "booking", "cta", "phone", "whatsapp", "mailto")
EMERGENCY_MARKERS = ("site_down", "ssl", "https", "availability", "mixed_content")
MONITOR_MARKERS = ("sitemap", "robots", "wordpress", "performance", "slow", "mobile")


def _campaign_issue_rows(campaign_id: str, limit: int = 250) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in fetch_all(
            """
            SELECT ai.issue_type, ai.severity, ai.title
            FROM campaign_leads cl
            JOIN audit_issues ai ON ai.audit_id = cl.audit_id
            WHERE cl.campaign_id = %s
              AND cl.status = 'preview'
            ORDER BY
              CASE ai.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
              ai.created_at DESC
            LIMIT %s
            """,
            (campaign_id, max(1, min(int(limit or 250), 500))),
        )
    ]


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    lowered = (value or "").lower()
    return any(marker in lowered for marker in markers)


def recommend_campaign_offer(campaign_id: str) -> dict[str, Any]:
    campaign = fetch_one("SELECT id, country, language, niche, offer_key FROM campaigns WHERE id = %s", (campaign_id,))
    if not campaign:
        raise ValueError("campaign_not_found")
    issues = _campaign_issue_rows(campaign_id)
    issue_counter = Counter(str(row["issue_type"] or "").lower() for row in issues)
    severity_counter = Counter(str(row["severity"] or "").lower() for row in issues)
    top_text = " ".join([str(row.get("issue_type") or "") + " " + str(row.get("title") or "") for row in issues[:20]])

    recommended = "contact_form_repair"
    reason = "contact_path_default_high_intent_offer"
    if severity_counter["critical"] >= 2 and _contains_any(top_text, EMERGENCY_MARKERS):
        recommended = "emergency_fix"
        reason = "multiple_public_critical_availability_or_ssl_signals"
    elif _contains_any(top_text, CONTACT_MARKERS):
        recommended = "contact_form_repair"
        reason = "visible_contact_or_booking_path_issue"
    elif issue_counter["wordpress"] or "wordpress" in top_text.lower():
        recommended = "fix_lite_monthly"
        reason = "wordpress_public_maintenance_opportunity"
    elif _contains_any(top_text, MONITOR_MARKERS):
        recommended = "monitor_monthly"
        reason = "monitoring_and_regression_prevention_fit"
    elif severity_counter["medium"] >= 3:
        recommended = "audit_onetime"
        reason = "several_medium_visibility_issues_without_clear_repair_type"

    economics = calculate_unit_economics(recommended)
    if economics["decision"] != "pass":
        recommended = "contact_form_repair"
        reason = "fallback_to_margin_passing_repair_offer"
        economics = calculate_unit_economics(recommended)

    return json_safe(
        {
            "campaign_id": campaign_id,
            "current_offer_key": campaign.get("offer_key") or "",
            "recommended_offer_key": recommended,
            "reason": reason,
            "niche": campaign.get("niche"),
            "country": campaign.get("country"),
            "language": campaign.get("language"),
            "issue_count": len(issues),
            "issue_type_counts": dict(issue_counter),
            "severity_counts": dict(severity_counter),
            "economics": economics,
            "decision": "CHANGE_OFFER" if (campaign.get("offer_key") or "") != recommended else "KEEP_OFFER",
            **SAFE_FLAGS,
        }
    )


def optimize_campaign_offers(limit: int = 50, apply: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 50), 200))
    campaigns = [
        dict(row)
        for row in fetch_all(
            """
            SELECT c.id, c.offer_key, c.country, c.niche,
                   count(cl.id) AS lead_count
            FROM campaigns c
            JOIN campaign_leads cl ON cl.campaign_id = c.id
            WHERE c.status IN ('draft', 'preview_ready')
              AND cl.status = 'preview'
              AND upper(COALESCE(c.country, '')) !~ '^(P7|P8|P9|P10|P11|P12|P59|P60|P61|P62|P63|P68|P72|P73|P74)'
            GROUP BY c.id
            ORDER BY count(cl.id) DESC, c.updated_at DESC
            LIMIT %s
            """,
            (safe_limit,),
        )
    ]
    items: list[dict[str, Any]] = []
    changed = 0
    for campaign in campaigns:
        recommendation = recommend_campaign_offer(str(campaign["id"]))
        should_change = recommendation["decision"] == "CHANGE_OFFER"
        if apply and should_change:
            execute(
                """
                UPDATE campaigns
                SET offer_key = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (recommendation["recommended_offer_key"], campaign["id"]),
            )
            execute(
                """
                UPDATE campaign_leads
                SET preview_json = COALESCE(preview_json, '{}'::jsonb) || %s::jsonb,
                    updated_at = now()
                WHERE campaign_id = %s
                  AND status = 'preview'
                """,
                (
                    Jsonb(
                        {
                            "offer_optimizer": {
                                "recommended_offer_key": recommendation["recommended_offer_key"],
                                "reason": recommendation["reason"],
                                "campaign_hash": recipient_hash(str(campaign["id"])),
                                "send_mail": False,
                                "live_outreach_allowed": False,
                            }
                        }
                    ),
                    campaign["id"],
                ),
            )
            changed += 1
        items.append(
            {
                "campaign_id": str(campaign["id"]),
                "campaign_hash": recipient_hash(str(campaign["id"])),
                "lead_count": int(campaign["lead_count"] or 0),
                "current_offer_key": recommendation["current_offer_key"],
                "recommended_offer_key": recommendation["recommended_offer_key"],
                "reason": recommendation["reason"],
                "decision": recommendation["decision"],
                "applied": bool(apply and should_change),
            }
        )
    result = json_safe(
        {
            "status": "applied" if apply else "preview",
            "campaigns_checked": len(campaigns),
            "offers_changed": changed,
            "items": items[:50],
            **SAFE_FLAGS,
        }
    )
    if apply:
        execute(
            """
            INSERT INTO system_events(type, severity, message, payload_json)
            VALUES ('campaign.offer_optimizer', 'info', 'Campaign offer optimizer evaluated', %s)
            """,
            (Jsonb(result),),
        )
    return result
