from __future__ import annotations

from email.utils import parseaddr
from typing import Any

from psycopg.types.json import Jsonb

from .db import connect


def persist_message(item: Any) -> bool:
    sender = parseaddr(item.sender)[1] or item.sender
    message_id = item.uid
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
                    Jsonb({"sender": sender, "subject": item.subject, "thread_id": str(thread_id)}),
                    item.mailbox,
                    item.uid,
                    message_id,
                    item.classification,
                    item.human_review_required,
                ),
            )
            if item.classification == "unsubscribe":
                cur.execute(
                    "INSERT INTO suppression_list(email, reason, source) VALUES (%s, 'unsubscribe_reply', 'inbox')",
                    (sender,),
                )
            if item.classification in {"legal_threat", "security_accusation", "angry"}:
                cur.execute(
                    "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, 'critical', %s, %s)",
                    (f"inbox.{item.classification}", "Unsafe reply requires human review", Jsonb({"sender": sender, "subject": item.subject})),
                )
            if any(marker in item.body.lower() for marker in ["found it in spam", "in spam", "spam folder"]):
                cur.execute(
                    "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
                    ("deliverability.spam_observed", "warning", "Test inbox spam placement signal observed", Jsonb({"sender": sender, "subject": item.subject})),
                )
        conn.commit()
    return True
