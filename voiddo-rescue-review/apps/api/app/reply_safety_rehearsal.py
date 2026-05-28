from __future__ import annotations

import os
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute
from .p0 import json_safe
from .reply_actions import plan_reply_action


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}

SAMPLES: list[dict[str, str]] = [
    {"name": "ask_price", "subject": "Re: possible website issue", "body": "How much does the one-time fix cost?", "expected": "ask_price", "expected_action": "prepare_safe_reply_draft"},
    {"name": "ask_details", "subject": "Re: audit", "body": "Can you send more details and screenshots?", "expected": "ask_details", "expected_action": "prepare_safe_reply_draft"},
    {"name": "unsubscribe", "subject": "Stop", "body": "Please unsubscribe and remove me.", "expected": "unsubscribe", "expected_action": "suppress_sender_and_confirm_when_mail_qa_passes"},
    {"name": "legal", "subject": "Legal", "body": "My lawyer will contact you about this.", "expected": "legal_threat", "expected_action": "stop_thread_create_review_item"},
    {"name": "security", "subject": "Security", "body": "This was an unauthorized security scan.", "expected": "security_accusation", "expected_action": "stop_thread_create_review_item"},
    {"name": "angry", "subject": "Spam", "body": "This is spam and I will report you.", "expected": "angry", "expected_action": "stop_thread_create_review_item"},
    {"name": "wants_call", "subject": "Call", "body": "Can you call me tomorrow?", "expected": "wants_call", "expected_action": "stop_thread_create_review_item"},
]


def run_reply_safety_rehearsal(store: bool = True) -> dict[str, Any]:
    rows = []
    blockers: list[str] = []
    auto_replies_paused = os.environ.get("AUTO_REPLIES_PAUSED", "true").strip().lower() != "false"
    if not auto_replies_paused:
        blockers.append("auto_replies_not_paused")
    for sample in SAMPLES:
        plan = plan_reply_action(sample["subject"], sample["body"], "support@voiddorescue.com")
        classification = plan["classification"]
        safe_action = plan["safe_action"]
        human_review = bool(plan["human_review_required"])
        auto_reply_allowed = bool(plan["auto_reply_allowed"])
        sample_blockers = []
        if classification != sample["expected"]:
            sample_blockers.append("classification_mismatch")
        if safe_action != sample["expected_action"]:
            sample_blockers.append("safe_action_mismatch")
        if sample["expected_action"] == "stop_thread_create_review_item" and not human_review:
            sample_blockers.append("hard_stop_without_human_review")
        if auto_reply_allowed and not auto_replies_paused:
            sample_blockers.append("auto_reply_could_send")
        blockers.extend(f"{sample['name']}:{item}" for item in sample_blockers)
        rows.append(
            {
                "sample": sample["name"],
                "classification": classification,
                "safe_action": safe_action,
                "human_review_required": human_review,
                "auto_reply_allowed_by_category": auto_reply_allowed,
                "auto_reply_effectively_blocked": auto_replies_paused or not auto_reply_allowed,
                "blockers": sample_blockers,
            }
        )
    result = json_safe(
        {
            "status": "completed",
            "decision": "PASS_REPLY_SAFETY_REHEARSAL" if not blockers else "FAIL_REPLY_SAFETY_REHEARSAL",
            "auto_replies_paused": auto_replies_paused,
            "sample_count": len(rows),
            "blockers": blockers,
            "samples": rows,
            **SAFE_FLAGS,
        }
    )
    if store:
        execute(
            "INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at) VALUES ('reply_safety_rehearsal_agent', %s, %s, now(), now())",
            ("completed" if result["decision"].startswith("PASS") else "blocked", Jsonb(result)),
        )
    return result
