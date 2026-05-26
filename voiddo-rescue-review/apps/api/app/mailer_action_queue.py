from __future__ import annotations

import hashlib
import ssl
import smtplib
import uuid
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .email_templates import qa_email_template, render_email_template
from .mailer_autonomy_ledger import mailer_autonomy_ledger
from .mailer_throttle import record_throttle_send, throttle_decision
from .p0 import json_safe, latest_mail_qa_decision, mail_signal_summary, smtp_credentials_for_sender, smtp_error_label


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


def _idempotency_key(action_type: str, recipient_hash: str, template_key: str, payload: dict[str, Any]) -> str:
    if action_type not in CUSTOMER_MAIL_ACTIONS:
        return ""
    parts = [
        action_type,
        recipient_hash,
        template_key or "",
        str(payload.get("customer_id", "")),
        str(payload.get("source_event", "")),
        str(payload.get("paddle_transaction_id", "")),
        str(payload.get("paddle_subscription_id", "")),
        str(payload.get("fix_request_id", "")),
        str(payload.get("mode", "")),
        str(payload.get("product_key", "")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def record_send_ledger(action: dict[str, Any], status: str, gate: dict[str, Any] | None = None, result: dict[str, Any] | None = None) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO mailer_send_ledger(action_id, action_type, mailbox, recipient_hash, template_key, status, gate_result_json, result_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (action_id) DO UPDATE
          SET status = EXCLUDED.status,
              gate_result_json = EXCLUDED.gate_result_json,
              result_json = EXCLUDED.result_json,
              updated_at = now()
        RETURNING id, action_id, action_type, mailbox, recipient_hash, template_key, status, gate_result_json, result_json, created_at, updated_at
        """,
        (
            action["id"],
            action["action_type"],
            action.get("mailbox", ""),
            action.get("recipient_hash", ""),
            action.get("template_key", ""),
            status,
            Jsonb(json_safe(gate or {})),
            Jsonb(json_safe(result or {})),
        ),
    )
    return json_safe(dict(row))


def _audit_recipient_resolution(action: dict[str, Any], customer_id: str | None, recipient_hash: str, status: str, reason: str) -> None:
    execute(
        """
        INSERT INTO recipient_resolver_audit(action_id, customer_id, recipient_hash, status, reason)
        VALUES (%s, NULLIF(%s, '')::uuid, %s, %s, %s)
        """,
        (action["id"], customer_id or "", recipient_hash, status, reason),
    )


def resolve_customer_recipient(action: dict[str, Any]) -> dict[str, Any]:
    payload = action.get("payload_json") or {}
    customer_id = str(payload.get("customer_id") or "")
    if not customer_id:
        _audit_recipient_resolution(action, None, action.get("recipient_hash", ""), "blocked", "customer_id_missing")
        return {"resolved": False, "blocker": "customer_id_missing", "recipient_hash": action.get("recipient_hash", "")}
    try:
        uuid.UUID(customer_id)
    except ValueError:
        _audit_recipient_resolution(action, None, action.get("recipient_hash", ""), "blocked", "customer_id_invalid")
        return {"resolved": False, "blocker": "customer_id_invalid", "recipient_hash": action.get("recipient_hash", "")}
    customer = fetch_one("SELECT id, email FROM customers WHERE id = %s", (customer_id,))
    if not customer:
        _audit_recipient_resolution(action, None, action.get("recipient_hash", ""), "blocked", "customer_not_found")
        return {"resolved": False, "blocker": "customer_not_found", "recipient_hash": action.get("recipient_hash", "")}
    email = str(customer["email"]).strip().lower()
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    recipient_hash = _hash_recipient(email)
    suppressed = fetch_one("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s) OR lower(domain) = lower(%s)", (email, domain))
    if suppressed:
        _audit_recipient_resolution(action, customer_id, recipient_hash, "blocked", "recipient_suppressed")
        return {"resolved": False, "blocker": "recipient_suppressed", "recipient_hash": recipient_hash}
    _audit_recipient_resolution(action, customer_id, recipient_hash, "resolved", "customer_email_resolved")
    return {"resolved": True, "recipient_email": email, "recipient_hash": recipient_hash}


def enqueue_mailer_action(payload: dict[str, Any]) -> dict[str, Any]:
    action_type = str(payload.get("action_type", "owner_report")).strip().lower()
    risk_level = str(payload.get("risk_level") or ("HIGH_RISK" if action_type in HIGH_RISK_ACTIONS else "MEDIUM_RISK" if action_type in MEDIUM_RISK_ACTIONS else "SAFE_AUTO"))
    recipient_hash = _hash_recipient(str(payload.get("recipient_email", "")))
    template_key = str(payload.get("template_key", ""))
    safe_payload = json_safe({k: v for k, v in payload.items() if k != "recipient_email"})
    idempotency_key = _idempotency_key(action_type, recipient_hash, template_key, safe_payload)
    if idempotency_key:
        existing = fetch_one(
            """
            SELECT id, action_type, risk_level, status, mailbox, recipient_hash, template_key, idempotency_key,
                   send_after, attempt_count, created_at, updated_at
            FROM mailer_action_queue
            WHERE idempotency_key = %s
            """,
            (idempotency_key,),
        )
        if existing:
            return json_safe(dict(existing))
    row = execute(
        """
        INSERT INTO mailer_action_queue(action_type, risk_level, mailbox, recipient_hash, template_key, payload_json, send_after, idempotency_key)
        VALUES (%s, %s, %s, %s, %s, %s, NULLIF(%s, '')::timestamptz, %s)
        RETURNING id, action_type, risk_level, status, mailbox, recipient_hash, template_key, idempotency_key, send_after, attempt_count, created_at, updated_at
        """,
        (
            action_type,
            risk_level,
            payload.get("mailbox", "audit@voiddorescue.com"),
            recipient_hash,
            template_key,
            Jsonb(safe_payload),
            payload.get("send_after", ""),
            idempotency_key,
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
    throttle = None
    rendered = None
    if action_type in CUSTOMER_MAIL_ACTIONS:
        rendered = render_customer_mail_preview(action)
        if not rendered["qa"]["passed"]:
            blockers.append("customer_template_qa_failed")
        throttle = throttle_decision("customer_mail", action.get("mailbox", "support@voiddorescue.com"), 600)
        if not throttle["allowed"]:
            blockers.append(f"throttle:{throttle['reason']}")
        if not settings.customer_mail_sending_enabled:
            blockers.append("customer_mail_sending_flag_false")
    if action_type == "warmup_slot":
        blockers.append("natural_warmup_timer_only")

    if action_type in CUSTOMER_MAIL_ACTIONS and not blockers:
        status = "send_ready"
    elif blockers:
        status = "prepared" if action_type in {"owner_report", *CUSTOMER_MAIL_ACTIONS} and "high_risk_action_requires_review" not in blockers else "blocked"
    else:
        status = "prepared"
    return {
        "status": status,
        "blockers": blockers,
        "send_mail": False,
        "send_ready": status == "send_ready",
        "live_outreach_allowed": False,
        "customer_mail": action_type in CUSTOMER_MAIL_ACTIONS,
        "throttle": throttle,
        "template_qa": rendered["qa"] if rendered else None,
        "reason": "prepared_no_send" if status == "prepared" else "blocked_by_gate",
    }


def render_customer_mail_preview(action: dict[str, Any]) -> dict[str, Any]:
    action_type = action["action_type"]
    template_key = action.get("template_key") or {
        "customer_onboarding": "payment_onboarding",
        "fix_request_created": "fix_request_created",
        "monitoring_report": "monitoring_setup_reminder",
    }.get(action_type, "payment_onboarding")
    payload = action.get("payload_json") or {}
    data = {
        "customer_url": "https://app.rescue.voiddo.com/customer",
        "fix_request_title": payload.get("product_key", "Website fix request"),
        "status": "prepared",
    }
    rendered = render_email_template(template_key, "en", data)
    return {"rendered": rendered, "qa": qa_email_template(rendered)}


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


def transport_dry_run(limit: int = 10) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in fetch_all(
            """
            SELECT *
            FROM mailer_action_queue
            WHERE status = 'send_ready'
            ORDER BY updated_at, created_at
            LIMIT %s
            """,
            (limit,),
        )
    ]
    recorded = []
    for row in rows:
        preview = render_customer_mail_preview(row)
        result = {
            "status": "dry_run_recorded",
            "message_id": make_msgid(domain="voiddorescue.local"),
            "subject_length": len(preview["rendered"]["subject"]),
            "body_length": len(preview["rendered"]["text"]),
            "template_key": preview["rendered"]["template_key"],
            "send_mail": False,
            "smtp_called": False,
            "raw_recipient_included": False,
        }
        updated = execute(
            """
            UPDATE mailer_action_queue
            SET status = 'dry_run_recorded',
                result_json = %s,
                attempt_count = attempt_count + 1,
                updated_at = now()
            WHERE id = %s
            RETURNING id, action_type, risk_level, status, mailbox, recipient_hash, template_key, result_json, attempt_count, updated_at
            """,
            (Jsonb(json_safe(result)), row["id"]),
        )
        recorded.append(dict(updated))
    return json_safe({"processed": len(recorded), "actions": recorded, "send_mail": False, "smtp_called": False, "live_outreach_allowed": False})


def _real_send_gate(action: dict[str, Any], preview: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    signals = mail_signal_summary(24)
    preview = preview or render_customer_mail_preview(action)
    throttle = throttle_decision("customer_mail", action.get("mailbox", "support@voiddorescue.com"), 600)
    blockers: list[str] = []
    if action.get("status") != "send_ready":
        blockers.append("action_not_send_ready")
    if action.get("action_type") not in CUSTOMER_MAIL_ACTIONS:
        blockers.append("not_customer_mail_action")
    if not settings.customer_mail_sending_enabled:
        blockers.append("customer_mail_sending_flag_false")
    if not settings.customer_mail_real_send_enabled:
        blockers.append("customer_mail_real_send_flag_false")
    if latest_mail_qa_decision() != "PASS":
        blockers.append("mail_qa_not_pass")
    if signals["bounce_or_dsn_count"] > 0:
        blockers.append("recent_bounce_or_dsn")
    if signals["rate_limit_count"] > 0:
        blockers.append("recent_rate_limit")
    if not preview["qa"]["passed"]:
        blockers.append("customer_template_qa_failed")
    if not throttle["allowed"]:
        blockers.append(f"throttle:{throttle['reason']}")
    return {
        "allowed": not blockers,
        "blockers": blockers,
        "send_mail": not blockers,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "signals": signals,
        "throttle": throttle,
        "template_qa": preview["qa"],
    }


def send_customer_mail_via_smtp(action: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    resolved = resolve_customer_recipient(action)
    if not resolved.get("resolved"):
        return {"sent": False, "smtp_called": False, "blocker": resolved.get("blocker", "recipient_resolver_missing")}
    recipient = str(resolved["recipient_email"])
    username, password, from_addr = smtp_credentials_for_sender(settings, str(action.get("mailbox") or settings.smtp_from_default))
    if not username or not password:
        return {"sent": False, "smtp_called": False, "blocker": "smtp_credentials_missing"}
    message_id = make_msgid(domain="voiddorescue.com")
    msg = EmailMessage()
    msg["Subject"] = preview["rendered"]["subject"]
    msg["From"] = from_addr
    msg["To"] = recipient
    msg["Message-ID"] = message_id
    msg.set_content(preview["rendered"]["text"])
    ctx = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ctx)
        smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(msg)
    return {"sent": True, "smtp_called": True, "provider_message_id": message_id}


def send_customer_mail(limit: int = 10) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in fetch_all(
            """
            SELECT *
            FROM mailer_action_queue
            WHERE status = 'send_ready'
            ORDER BY updated_at, created_at
            LIMIT %s
            """,
            (limit,),
        )
    ]
    actions = []
    for row in rows:
        preview = render_customer_mail_preview(row)
        gate = _real_send_gate(row, preview)
        if not gate["allowed"]:
            result = {
                "status": "transport_blocked",
                "blockers": gate["blockers"],
                "send_mail": False,
                "smtp_called": False,
                "raw_recipient_included": False,
            }
            updated = execute(
                """
                UPDATE mailer_action_queue
                SET status = 'transport_blocked',
                    gate_result_json = %s,
                    result_json = %s,
                    attempt_count = attempt_count + 1,
                    updated_at = now()
                WHERE id = %s
                RETURNING id, action_type, risk_level, status, mailbox, recipient_hash, template_key, gate_result_json, result_json, attempt_count, updated_at
                """,
                (Jsonb(json_safe(gate)), Jsonb(json_safe(result)), row["id"]),
            )
            record_send_ledger(dict(updated), "transport_blocked", gate, result)
            actions.append(dict(updated))
            continue
        try:
            smtp_result = send_customer_mail_via_smtp(row, preview)
            if not smtp_result.get("sent"):
                result = {
                    "status": "transport_blocked",
                    "blockers": [smtp_result.get("blocker", "smtp_transport_not_ready")],
                    "send_mail": False,
                    "smtp_called": bool(smtp_result.get("smtp_called")),
                    "raw_recipient_included": False,
                }
                updated = execute(
                    """
                    UPDATE mailer_action_queue
                    SET status = 'transport_blocked',
                        gate_result_json = %s,
                        result_json = %s,
                        attempt_count = attempt_count + 1,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id, action_type, risk_level, status, mailbox, recipient_hash, template_key, gate_result_json, result_json, attempt_count, updated_at
                    """,
                    (Jsonb(json_safe({**gate, "transport_blocker": result["blockers"][0]})), Jsonb(json_safe(result)), row["id"]),
                )
                record_send_ledger(dict(updated), "transport_blocked", {**gate, "transport_blocker": result["blockers"][0]}, result)
                actions.append(dict(updated))
                continue
            result = {
                "status": "sent",
                "provider_message_id": smtp_result.get("provider_message_id", ""),
                "send_mail": True,
                "smtp_called": True,
                "raw_recipient_included": False,
            }
            updated = execute(
                """
                UPDATE mailer_action_queue
                SET status = 'sent',
                    result_json = %s,
                    attempt_count = attempt_count + 1,
                    updated_at = now()
                WHERE id = %s
                RETURNING id, action_type, risk_level, status, mailbox, recipient_hash, template_key, result_json, attempt_count, updated_at
                """,
                (Jsonb(json_safe(result)), row["id"]),
            )
            record_throttle_send("customer_mail", row.get("mailbox", "support@voiddorescue.com"), "customer_mail_sent")
            record_send_ledger(dict(updated), "sent", gate, result)
            actions.append(dict(updated))
        except Exception as exc:
            result = {
                "status": "failed",
                "error": smtp_error_label(exc),
                "error_type": type(exc).__name__,
                "send_mail": False,
                "smtp_called": True,
                "raw_recipient_included": False,
            }
            updated = execute(
                """
                UPDATE mailer_action_queue
                SET status = 'failed',
                    result_json = %s,
                    attempt_count = attempt_count + 1,
                    updated_at = now()
                WHERE id = %s
                RETURNING id, action_type, risk_level, status, mailbox, recipient_hash, template_key, result_json, attempt_count, updated_at
                """,
                (Jsonb(json_safe(result)), row["id"]),
            )
            record_send_ledger(dict(updated), "failed", gate, result)
            actions.append(dict(updated))
    return json_safe(
        {
            "processed": len(actions),
            "actions": actions,
            "send_mail": any((item.get("result_json") or {}).get("send_mail") for item in actions),
            "smtp_called": any((item.get("result_json") or {}).get("smtp_called") for item in actions),
            "live_outreach_allowed": False,
        }
    )


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
            "send_ready": _count("SELECT count(*) FROM mailer_action_queue WHERE status = 'send_ready'"),
            "sent": _count("SELECT count(*) FROM mailer_action_queue WHERE status = 'sent'"),
            "transport_blocked": _count("SELECT count(*) FROM mailer_action_queue WHERE status = 'transport_blocked'"),
            "failed": _count("SELECT count(*) FROM mailer_action_queue WHERE status = 'failed'"),
            "dry_run_recorded": _count("SELECT count(*) FROM mailer_action_queue WHERE status = 'dry_run_recorded'"),
            "send_ledger": {
                "total": _count("SELECT count(*) FROM mailer_send_ledger"),
                "sent": _count("SELECT count(*) FROM mailer_send_ledger WHERE status = 'sent'"),
                "blocked": _count("SELECT count(*) FROM mailer_send_ledger WHERE status = 'transport_blocked'"),
                "failed": _count("SELECT count(*) FROM mailer_send_ledger WHERE status = 'failed'"),
            },
            "ledger_blockers": ledger["gates"]["blockers"],
            "raw_recipient_addresses_included": False,
            "send_mail": False,
            "live_outreach_allowed": False,
        }
    )
