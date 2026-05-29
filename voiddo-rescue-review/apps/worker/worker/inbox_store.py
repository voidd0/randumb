from __future__ import annotations

import hashlib
from email.utils import parseaddr
from typing import Any

from psycopg.types.json import Jsonb

from .db import connect

BOUNCE_REASON_PATTERNS = {
    "mailbox_unavailable": ["mailbox unavailable", "user unknown", "recipient address rejected", "no such user", "address not found", "does not exist"],
    "domain_not_found": ["domain not found", "host or domain name not found", "no mx", "dns error", "unrouteable address"],
    "blocked_policy": ["blocked", "spam", "policy", "reputation", "blacklist", "denied", "rejected due to"],
    "temporary_defer": ["rate", "temporarily", "try again later", "greylist", "deferred"],
}


def _recipient_hash(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()


def _email_provider(email: str) -> str:
    domain = (email or "").split("@")[-1].lower()
    if domain in {"voiddo.com", "voiddorescue.com"}:
        return "internal"
    if domain in {"gmail.com", "googlemail.com"}:
        return "gmail"
    if domain in {"outlook.com", "hotmail.com", "live.com", "msn.com"}:
        return "microsoft"
    if domain in {"icloud.com", "me.com", "mac.com"}:
        return "icloud"
    if domain == "proton.me" or domain.endswith(".proton.me"):
        return "proton"
    if domain == "yahoo.com":
        return "yahoo"
    return domain or "unknown"


def _bounce_reason(subject: str, body: str) -> str:
    text = f"{subject}\n{body}".lower()
    for reason, markers in BOUNCE_REASON_PATTERNS.items():
        if any(marker in text for marker in markers):
            return reason
    return "unknown"


def _extract_bounced_recipient(body: str) -> str:
    import re

    patterns = [
        r"Final-Recipient:\s*rfc822;\s*([^\s<>;,]+@[^\s<>;,]+)",
        r"Original-Recipient:\s*rfc822;\s*([^\s<>;,]+@[^\s<>;,]+)",
        r"X-Failed-Recipients:\s*([^\s<>;,]+@[^\s<>;,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, body or "", flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().lower()
    return ""


def persist_message(item: Any) -> bool:
    sender = parseaddr(item.sender)[1] or item.sender
    message_id = item.uid
    sender_hash = _recipient_hash(sender)
    sender_provider = _email_provider(sender)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM email_events WHERE mailbox = %s AND uid = %s AND message_id = %s",
                (item.mailbox, item.uid, message_id),
            )
            if cur.fetchone():
                return False
            cur.execute(
                """
                INSERT INTO inbox_threads(mailbox, external_thread_id, classification, human_review_required, last_message_preview)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (item.mailbox, message_id, item.classification, item.human_review_required, item.body[:240]),
            )
            thread_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO email_events(event_type, payload_json, mailbox, uid, message_id, classification, human_review_required)
                VALUES ('inbound_reply', %s, %s, %s, %s, %s, %s)
                """,
                (
                    Jsonb({"sender_hash": sender_hash, "sender_provider": sender_provider, "subject": item.subject, "thread_id": str(thread_id)}),
                    item.mailbox,
                    item.uid,
                    message_id,
                    item.classification,
                    item.human_review_required,
                ),
            )
            if item.classification == "unsubscribe":
                cur.execute(
                    """
                    INSERT INTO suppression_list(email, reason, source)
                    SELECT %s, 'unsubscribe_reply', 'inbox'
                    WHERE NOT EXISTS (
                      SELECT 1 FROM suppression_list
                      WHERE lower(email) = lower(%s)
                        AND reason = 'unsubscribe_reply'
                        AND source = 'inbox'
                    )
                    """,
                    (sender, sender),
                )
            bounce_reason = _bounce_reason(item.subject, item.body) if item.classification == "bounce" else ""
            bounced_recipient = _extract_bounced_recipient(item.body) if item.classification == "bounce" else ""
            if item.classification == "bounce" and bounced_recipient:
                cur.execute(
                    """
                    INSERT INTO suppression_list(email, reason, source)
                    SELECT %s, %s, 'inbox_bounce'
                    WHERE NOT EXISTS (
                      SELECT 1 FROM suppression_list
                      WHERE lower(email) = lower(%s)
                        AND source = 'inbox_bounce'
                    )
                    """,
                    (bounced_recipient, f"bounce_{bounce_reason}", bounced_recipient),
                )
            if item.classification in {"bounce", "auto_reply", "out_of_office", "interested", "ask_price", "ask_details"}:
                cur.execute(
                    """
                    INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, message_id, raw_summary)
                    VALUES (%s, %s, 'inbox_worker', %s, %s, %s, %s, %s)
                    """,
                    (
                        "bounce" if item.classification == "bounce" else "inbox_reply",
                        "warning" if item.classification == "bounce" else "info",
                        item.mailbox,
                        sender_hash,
                        sender_provider,
                        message_id,
                        f"classified:{item.classification}" + (f":{bounce_reason}" if bounce_reason else ""),
                    ),
                )
            if item.classification in {"legal_threat", "security_accusation", "angry"}:
                cur.execute(
                    "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, 'critical', %s, %s)",
                    (f"inbox.{item.classification}", "Unsafe reply requires human review", Jsonb({"sender_hash": sender_hash, "sender_provider": sender_provider, "subject": item.subject})),
                )
            if any(marker in item.body.lower() for marker in ["found it in spam", "in spam", "spam folder"]):
                cur.execute(
                    "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
                    ("deliverability.spam_observed", "warning", "Test inbox spam placement signal observed", Jsonb({"sender_hash": sender_hash, "subject": item.subject})),
                )
                cur.execute(
                    """
                    INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, message_id, raw_summary)
                    VALUES ('spam_signal', 'warning', 'inbox_worker', %s, %s, %s, %s, 'test inbox spam placement observed')
                    """,
                    (item.mailbox, sender_hash, sender_provider, message_id),
                )
        conn.commit()
    return True
