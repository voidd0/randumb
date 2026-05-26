from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute
from .inbox import classify_reply


AUTO_SAFE = {"ask_price", "ask_details", "wrong_person", "out_of_office", "unsubscribe"}
HARD_STOP = {"angry", "legal_threat", "security_accusation", "custom_technical_request", "wants_call", "paid"}


def plan_reply_action(subject: str, body: str, mailbox: str = "support@voiddorescue.com") -> dict[str, Any]:
    classified = classify_reply(subject, body)
    label = str(classified["classification"])
    human = bool(classified["human_review_required"]) or label in HARD_STOP
    if label == "unsubscribe":
        safe_action = "suppress_sender_and_confirm_when_mail_qa_passes"
        confidence = 0.95
        reason = "explicit_unsubscribe"
    elif label in AUTO_SAFE:
        safe_action = "prepare_safe_reply_draft"
        confidence = 0.85
        reason = "safe_template_category"
    elif human:
        safe_action = "stop_thread_create_review_item"
        confidence = 0.9 if label in HARD_STOP else 0.55
        reason = "unsafe_or_unclear_reply"
    else:
        safe_action = "store_and_wait"
        confidence = 0.75
        reason = "informational_reply"
    row = execute(
        """
        INSERT INTO reply_action_plans(
          mailbox, classification, confidence, safe_action, auto_reply_allowed,
          human_review_required, reason, evidence_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (mailbox, label, confidence, safe_action, bool(classified["auto_reply_allowed"]) and not human, human, reason, Jsonb(classified)),
    )
    return dict(row)
