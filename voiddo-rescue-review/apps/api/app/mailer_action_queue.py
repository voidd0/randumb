from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .mailer_autonomy_ledger import mailer_autonomy_ledger
from .p0 import json_safe, latest_mail_qa_decision, mail_signal_summary


HIGH_RISK_ACTIONS = {"cold_outreach", "send_outreach", "start_warmup", "unpause_outreach", "execute_shell"}
MEDIUM_RISK_ACTIONS = {"deliverability_diagnostic", "warmup_slot"}
CUSTOMER_MAIL_ACTIONS = {"customer_onboarding", "fix_request_created", "monitoring_report"}
SAFE_ACTIONS = {"owner_report", "safe_reply_draft", "outreach_preview", *CUSTOMER_MAIL_ACTIONS}


def _hash_recipient(value: str) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _count(sql: str, params: tuple = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def enqueue_mailer_action(payload: dict[str, Any]) -> dict[str, Any]:
    action_type = str(payload.get("action_type", "owner_report")).strip().lower()
    risk_level = str(payload.get("risk_level") or ("HIGH_RISK" if action_type in HIGH_RISK_ACTIONS else "MEDIUM_RISK" if action_type in MEDIUM_RISK_ACTIONS else "SAFE_AUTO"))
    recipient_hash = _hash_recipient(str(payload.get("recipient_email", "")))
    row = execute(
        """
        INSERT INTO mailer_action_queue(action_type, risk_level, mailbox, recipient_hash, template_key, payload_json, send_after)
        VALUES (%s, %s, %s, %s, %s, %s, NULLIF(%s, '')::timestamptz)
        RETURNING id, action_type, risk_level, status, mailbox, recipient_hash, template_key, send_after, attempt_count, created_at, updated_at
        """,
        (
            action_type,
            risk_level,
            payload.get("mailbox", "audit@voiddorescue.com"),
            recipient_hash,
            payload.get("template_key", ""),
            Jsonb(json_safe({k: v for k, v in payload.items() if k != "recipient_email"})),
            payload.get("send_after", ""),
        ),
    )
    return json_safe(dict(row))


def _gate_action(action: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    signals = mail_signal_summary(24)
    blockers: list[str] = []
    action_type = action["action_type"]
    if action_type in HIGH_RISK_ACTIONS:
        blockers.append("high_risk_action_requires_review")
    if action_type in {"cold_outreach", "send_outreach", "outreach_preview"}:
        if settings.outreach_paused:
            blockers.append("outreach_paused_env")
        if not settings.first_live_send_flag and action_type != "outreach_preview":
            blockers.append("first_live_send_flag_false")
    if action_type in {"safe_reply_draft"} and settings.auto_replies_paused:
        blockers.append("auto_replies_paused_env")
    if action_type in {"deliverability_diagnostic", "warmup_slot", "owner_report", "safe_reply_draft", *CUSTOMER_MAIL_ACTIONS}:
        if signals["bounce_or_dsn_count"] > 0:
            blockers.append("recent_bounce_or_dsn")
        if signals["rate_limit_count"] > 0:
            blockers.append("recent_rate_limit")
        if latest_mail_qa_decision() != "PASS":
            blockers.append("mail_qa_not_pass")
    if action_type in CUSTOMER_MAIL_ACTIONS and not settings.customer_mail_sending_enabled:
        blockers.append("customer_mail_sending_flag_false")
    if action_type == "warmup_slot":
        blockers.append("natural_warmup_timer_only")

    if blockers:
        status = "prepared" if action_type in {"owner_report", *CUSTOMER_MAIL_ACTIONS} and "high_risk_action_requires_review" not in blockers else "blocked"
    else:
        status = "prepared"
    return {
        "status": status,
        "blockers": blockers,
        "send_mail": False,
        "live_outreach_allowed": False,
        "reason": "prepared_no_send" if status == "prepared" else "blocked_by_gate",
    }


def process_mailer_action_queue(limit: int = 10) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in fetch_all(
            """
            SELECT *
            FROM mailer_action_queue
            WHERE status = 'queued'
              AND (send_after IS NULL OR send_after <= now())
            ORDER BY created_at
            LIMIT %s
            """,
            (limit,),
        )
    ]
    processed = []
    for row in rows:
        gate = _gate_action(row)
        updated = execute(
            """
            UPDATE mailer_action_queue
            SET status = %s,
                gate_result_json = %s,
                result_json = %s,
                attempt_count = attempt_count + 1,
                updated_at = now()
            WHERE id = %s
            RETURNING id, action_type, risk_level, status, mailbox, recipient_hash, template_key, gate_result_json, attempt_count, updated_at
            """,
            (gate["status"], Jsonb(json_safe(gate)), Jsonb({"send_mail": False, "live_outreach_allowed": False}), row["id"]),
        )
        processed.append(dict(updated))
    return json_safe({"processed": len(processed), "actions": processed, "send_mail": False, "live_outreach_allowed": False})


def mailer_action_queue_summary() -> dict[str, Any]:
    rows = [
        dict(row)
        for row in fetch_all(
            """
            SELECT status, action_type, risk_level, count(*) AS count
            FROM mailer_action_queue
            GROUP BY status, action_type, risk_level
            ORDER BY status, action_type, risk_level
            """
        )
    ]
    latest = [
        dict(row)
        for row in fetch_all(
            """
            SELECT id, action_type, risk_level, status, mailbox, recipient_hash, template_key,
                   gate_result_json, attempt_count, updated_at, created_at
            FROM mailer_action_queue
            ORDER BY created_at DESC
            LIMIT 10
            """
        )
    ]
    ledger = mailer_autonomy_ledger()
    return json_safe(
        {
            "counts": rows,
            "latest": latest,
            "queued": _count("SELECT count(*) FROM mailer_action_queue WHERE status = 'queued'"),
            "prepared": _count("SELECT count(*) FROM mailer_action_queue WHERE status = 'prepared'"),
            "blocked": _count("SELECT count(*) FROM mailer_action_queue WHERE status = 'blocked'"),
            "sent": _count("SELECT count(*) FROM mailer_action_queue WHERE status = 'sent'"),
            "ledger_blockers": ledger["gates"]["blockers"],
            "raw_recipient_addresses_included": False,
            "send_mail": False,
            "live_outreach_allowed": False,
        }
    )
