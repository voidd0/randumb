from __future__ import annotations

from typing import Any

from .audit_strength import score_audit_strength
from .billing import checkout_config_status, PRODUCTS
from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .email_templates import qa_email_template, render_email_template
from .language_gate import check_no_ai_public_language
from .mailer_control import evaluate_outbound_message
from .p0 import json_safe


OUTREACH_GATE_EXPECTED_BLOCKERS = {"outreach_dry_run_enabled", "live_outreach_not_approved"}


def _price_text(product_key: str) -> str:
    product = PRODUCTS.get(product_key) or PRODUCTS["contact_form_repair"]
    amount = int(product["amount"])
    if product["mode"] == "subscription":
        return f"${amount}/month"
    return f"${amount}"


def _preview_rows(campaign_id: str, limit: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in fetch_all(
            """
            SELECT cl.id AS campaign_lead_id, cl.lead_id, cl.audit_id, cl.score AS campaign_score,
                   c.id AS campaign_id, c.language AS campaign_language, c.offer_key,
                   l.language AS lead_language, l.contact_name,
                   b.name AS business_name, b.domain,
                   a.public_slug, a.summary
            FROM campaign_leads cl
            JOIN campaigns c ON c.id = cl.campaign_id
            JOIN leads l ON l.id = cl.lead_id
            JOIN businesses b ON b.id = l.business_id
            LEFT JOIN audits a ON a.id = cl.audit_id
            WHERE cl.campaign_id = %s
            ORDER BY cl.score DESC, cl.created_at
            LIMIT %s
            """,
            (campaign_id, max(1, min(int(limit or 20), 100))),
        )
    ]


def campaign_preview_quality_pack(campaign_id: str, limit: int = 20) -> dict[str, Any]:
    campaign = fetch_one("SELECT * FROM campaigns WHERE id = %s", (campaign_id,))
    if not campaign:
        raise ValueError("campaign_not_found")
    settings = get_settings()
    checkout = checkout_config_status(settings)
    rows = _preview_rows(campaign_id, limit)
    items: list[dict[str, Any]] = []
    ready_count = 0
    blockers_by_code: dict[str, int] = {}
    for row in rows:
        blockers: list[str] = []
        audit_strength = {"final_score": 0, "issues_json": [{"code": "missing_audit"}]}
        if row.get("audit_id"):
            audit_strength = score_audit_strength(str(row["audit_id"]))
        if int(audit_strength.get("final_score") or 0) < 70:
            blockers.append("audit_strength_below_70")
        if not row.get("public_slug"):
            blockers.append("missing_public_audit_slug")
        if not checkout["ready"]:
            blockers.append("checkout_not_ready")
        product_key = row.get("offer_key") or "contact_form_repair"
        audit_url = f"{settings.audit_base_url}/r/{row['public_slug']}" if row.get("public_slug") else settings.audit_base_url
        unsubscribe_url = f"{settings.go_base_url}/unsubscribe/preview-{row['campaign_lead_id']}"
        language = row.get("lead_language") or row.get("campaign_language") or "en"
        template_data = {
            "business_name": row.get("business_name") or row.get("domain") or "your business",
            "name_or_team": row.get("contact_name") or "team",
            "domain": row.get("domain") or "",
            "main_issue_short": row.get("summary") or "A public website check found a possible enquiry-path issue.",
            "audit_url": audit_url,
            "unsubscribe_url": unsubscribe_url,
            "one_time_price": _price_text(product_key),
            "monthly_price": "$19",
        }
        rendered = render_email_template("first_audit_notice", language, template_data)
        template_qa = qa_email_template(rendered)
        if not template_qa["passed"]:
            blockers.append("template_qa_failed")
        language_gate = check_no_ai_public_language(
            [{"name": f"campaign_preview:{campaign_id}:{row['campaign_lead_id']}", "text": f"{rendered['subject']}\n{rendered['text']}"}],
            "campaign_preview_quality",
        )
        if language_gate["status"] != "pass":
            blockers.append("public_language_gate_failed")
        outbound = evaluate_outbound_message(
            {
                "email": "redacted@example.test",
                "campaign_id": campaign_id,
                "template_key": "first_audit_notice",
                "language": language,
                "template_data": template_data,
            }
        )
        outbound_reason = str(outbound.get("reason") or "")
        if outbound["status"] != "ready" and outbound_reason not in OUTREACH_GATE_EXPECTED_BLOCKERS:
            blockers.append("outbound_gate_unexpected_block")
        for blocker in blockers:
            blockers_by_code[blocker] = blockers_by_code.get(blocker, 0) + 1
        ready = not blockers
        if ready:
            ready_count += 1
        items.append(
            {
                "campaign_lead_id": str(row["campaign_lead_id"]),
                "lead_id": str(row["lead_id"]),
                "audit_id": str(row["audit_id"]) if row.get("audit_id") else None,
                "domain": row.get("domain"),
                "audit_strength_score": int(audit_strength.get("final_score") or 0),
                "template_score": int(template_qa.get("score") or 0),
                "language_gate_status": language_gate["status"],
                "checkout_ready": bool(checkout["ready"]),
                "audit_url_ready": bool(row.get("public_slug")),
                "unsubscribe_ready": True,
                "legal_note_ready": "public non-invasive" in rendered["text"].lower() or "בדיקת אתר ציבורית" in rendered["text"] or "mitteinvasiivne" in rendered["text"].lower(),
                "outbound_gate_status": outbound["status"],
                "outbound_gate_reason": outbound_reason,
                "ready_for_preview": ready,
                "blockers": blockers,
            }
        )
    status = "PASS_PREVIEW_QUALITY" if rows and ready_count == len(rows) else ("EMPTY_PREVIEW" if not rows else "REVIEW_REQUIRED")
    return json_safe(
        {
            "campaign_id": campaign_id,
            "status": status,
            "checked_count": len(rows),
            "ready_count": ready_count,
            "blockers_by_code": blockers_by_code,
            "checkout_ready": bool(checkout["ready"]),
            "items": items,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
