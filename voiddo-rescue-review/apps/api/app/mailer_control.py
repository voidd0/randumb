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
    transport = transport_gate_status({"email": email, "body": body})
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
    return dict(row)
