from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute
from .inbox import classify_reply
from .mailer_throttle import throttle_decision
from .p0 import mail_signal_summary, transport_gate_status


SAFE_AUTO_REPLY_CATEGORIES = {"ask_price", "ask_details", "wrong_person", "out_of_office", "unsubscribe"}
UNSAFE_CATEGORIES = {"angry", "legal_threat", "security_accusation", "custom_technical_request", "wants_call"}


def record_mailer_decision(direction: str, mailbox: str, category: str, status: str, action: str, reason: str, checks: dict[str, Any]) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO autonomous_mailer_decisions(direction, mailbox, category, status, action, reason, checks_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (direction, mailbox, category, status, action, reason, Jsonb(checks)),
    )
    return dict(row)


def decide_outbound_mail(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    settings = get_settings()
    throttle = throttle_decision("global", "outreach", 1800)
    transport = transport_gate_status(payload)
    signals = mail_signal_summary(24)
    checks = {
        "outreach_paused": settings.outreach_paused,
        "first_live_send_flag": settings.first_live_send_flag,
        "auto_replies_paused": settings.auto_replies_paused,
        "throttle": throttle,
        "transport": transport,
        "signals": signals,
    }
    if settings.outreach_paused:
        return record_mailer_decision("outbound", settings.smtp_from_default, "campaign", "blocked", "do_not_send", "outreach_paused", checks)
    if not settings.first_live_send_flag:
        return record_mailer_decision("outbound", settings.smtp_from_default, "campaign", "blocked", "do_not_send", "first_live_send_flag_false", checks)
    if not throttle["allowed"]:
        return record_mailer_decision("outbound", settings.smtp_from_default, "campaign", "blocked", "do_not_send", throttle["reason"], checks)
    if not transport["allowed"]:
        return record_mailer_decision("outbound", settings.smtp_from_default, "campaign", "blocked", "do_not_send", transport["reason"], checks)
    return record_mailer_decision("outbound", settings.smtp_from_default, "campaign", "ready", "send_allowed_by_gates", "all_gates_passed", checks)


def decide_inbound_mail(subject: str, body: str, mailbox: str = "support@voiddorescue.com") -> dict[str, Any]:
    settings = get_settings()
    classified = classify_reply(subject, body)
    category = classified.get("classification", "human_review_required")
    checks = {"classification": classified, "auto_replies_paused": settings.auto_replies_paused}
    if category == "unsubscribe":
        return record_mailer_decision("inbound", mailbox, category, "suppression_required", "suppress_thread", "unsubscribe_request", checks)
    if category in UNSAFE_CATEGORIES or classified.get("human_review_required"):
        return record_mailer_decision("inbound", mailbox, category, "review_required", "stop_automation_and_alert", "unsafe_or_custom_reply", checks)
    if category in SAFE_AUTO_REPLY_CATEGORIES and not settings.auto_replies_paused:
        return record_mailer_decision("inbound", mailbox, category, "ready", "safe_auto_reply_allowed", "safe_category_and_autoreplies_enabled", checks)
    if category in SAFE_AUTO_REPLY_CATEGORIES:
        return record_mailer_decision("inbound", mailbox, category, "blocked", "draft_only", "auto_replies_paused", checks)
    return record_mailer_decision("inbound", mailbox, category, "stored", "no_reply", "informational_or_auto_reply", checks)


def run_autonomous_mailer_cycle() -> dict[str, Any]:
    outbound = decide_outbound_mail({})
    inbound_samples = [
        decide_inbound_mail("Price?", "Can you send pricing details?", "audit@voiddorescue.com"),
        decide_inbound_mail("Legal", "This is a legal threat", "support@voiddorescue.com"),
    ]
    return {"outbound": outbound, "inbound_samples": inbound_samples, "sent": 0}
