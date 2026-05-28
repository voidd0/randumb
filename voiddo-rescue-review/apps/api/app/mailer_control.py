from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .campaign_preflight_status import latest_campaign_preflight_status
from .db import execute, fetch_one
from .email_templates import qa_email_template, render_email_template
from .mailer_throttle import throttle_decision
from .p0 import recipient_hash, transport_gate_status, warmup_domain_maturity_status


def evaluate_outbound_message(payload: dict[str, Any]) -> dict[str, Any]:
    email = (payload.get("email") or "").strip().lower()
    mailbox = payload.get("mailbox") or "audit@voiddorescue.com"
    template_key = payload.get("template_key") or "first_audit_notice"
    language = payload.get("language") or "en"
    body = payload.get("body") or ""
    rendered = None
    qa: dict[str, Any] = {"passed": False, "issues": ["missing_body_or_template"], "score": 0}
    try:
        rendered = render_email_template(template_key, language, payload.get("template_data") or {})
        qa = qa_email_template(rendered)
        body = body or rendered["text"]
    except Exception as exc:
        qa = {"passed": False, "issues": [f"template_error:{type(exc).__name__}"], "score": 0}
    suppressed = bool(fetch_one("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (email,))) if email else False
    transport = transport_gate_status({"email": email, "body": body, "html_body": rendered.get("html") if rendered else payload.get("html_body", "")})
    campaign_preflight = (
        latest_campaign_preflight_status(str(payload.get("campaign_id") or ""))
        if payload.get("campaign_id") and not payload.get("skip_campaign_preflight")
        else None
    )
    throttle = throttle_decision("mailbox", mailbox, 1800)
    warmup_maturity = warmup_domain_maturity_status()
    has_unsubscribe = "unsubscribe" in body.lower() or "הסרה" in body or "loobu" in body.lower()
    checks = {
        "template_qa": qa,
        "transport": transport,
        "campaign_preflight": campaign_preflight,
        "throttle": throttle,
        "warmup_maturity": warmup_maturity,
        "suppressed": suppressed,
        "has_unsubscribe": has_unsubscribe,
        "rendered_subject": rendered["subject"] if rendered else "",
    }
    blockers: list[str] = []
    if not email:
        blockers.append("missing_recipient")
    if suppressed:
        blockers.append("recipient_suppressed")
    if not qa.get("passed"):
        blockers.append("template_qa_failed")
    if not has_unsubscribe and template_key.startswith(("first_", "followup_")):
        blockers.append("missing_unsubscribe")
    if not throttle["allowed"]:
        blockers.append(throttle["reason"])
    if not transport["allowed"]:
        blockers.append(transport["reason"])
    if template_key.startswith(("first_", "followup_")) and not warmup_maturity["allowed"]:
        blockers.extend(warmup_maturity["blockers"])
    if campaign_preflight and not campaign_preflight["allowed"]:
        blockers.append(campaign_preflight["reason"])
    status = "ready" if not blockers else "blocked"
    action = "send_allowed_by_gates" if status == "ready" else "do_not_send"
    reason = "all_gates_passed" if status == "ready" else ",".join(sorted(set(blockers)))
    row = execute(
        """
        INSERT INTO outbound_mailer_decisions(
          outreach_message_id, campaign_id, mailbox, recipient_hash, template_key,
          status, action, reason, checks_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            payload.get("outreach_message_id"),
            payload.get("campaign_id"),
            mailbox,
            recipient_hash(email) if email else "",
            template_key,
            status,
            action,
            reason,
            Jsonb(checks),
        ),
    )
    result = dict(row)
    result["send_mail"] = False
    result["smtp_called"] = False
    result["live_outreach_allowed"] = False
    return result


def evaluate_latest_preview_outbound_message() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT om.id AS outreach_message_id, om.body, om.html_body, om.mailbox,
               l.email, cl.campaign_id
        FROM outreach_messages om
        JOIN leads l ON l.id = om.lead_id
        LEFT JOIN campaign_leads cl ON cl.lead_id = om.lead_id AND cl.audit_id = om.audit_id
        WHERE om.status = 'preview'
        ORDER BY om.created_at DESC
        LIMIT 1
        """
    )
    if not row:
        return evaluate_outbound_message(
            {
                "email": "sample@example.test",
                "template_key": "first_audit_notice",
                "template_data": {
                    "business_name": "Example Studio",
                    "name_or_team": "team",
                    "domain": "example.test",
                    "main_issue_short": "A public enquiry path may be unclear.",
                    "audit_url": "https://audit.rescue.voiddo.com/r/demo",
                    "unsubscribe_url": "https://go.rescue.voiddo.com/unsubscribe/u_00000000-0000-0000-0000-000000000000.sample",
                    "one_time_price": "$99",
                    "monthly_price": "$19",
                },
                "skip_campaign_preflight": True,
            }
        )
    return evaluate_outbound_message(
        {
            "outreach_message_id": str(row["outreach_message_id"]),
            "campaign_id": str(row["campaign_id"]) if row.get("campaign_id") else None,
            "email": row["email"],
            "mailbox": row["mailbox"],
            "template_key": "first_audit_notice",
            "body": row["body"],
            "html_body": row["html_body"],
        }
    )
