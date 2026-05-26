from __future__ import annotations

from email.message import EmailMessage
import os
import smtplib
import ssl

from psycopg.types.json import Jsonb

from .db import connect


def _latest_decision(table: str) -> str:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT decision FROM {table} ORDER BY created_at DESC LIMIT 1")
            row = cur.fetchone()
            return row["decision"] if row else "MISSING"


def transport_gate(email: str, body: str) -> tuple[bool, str, dict]:
    checks = {
        "outreach_dry_run": os.environ.get("OUTREACH_DRY_RUN", "true").lower() == "true",
        "outreach_paused": os.environ.get("OUTREACH_PAUSED", "true").lower() == "true",
        "first_live_send_flag": os.environ.get("FIRST_LIVE_SEND_FLAG", "false").lower() == "true",
        "mail_qa_decision": _latest_decision("mail_qa_runs"),
        "visual_qa_decision": _latest_decision("visual_qa_runs"),
        "has_unsubscribe": "unsubscribe" in body.lower(),
        "suppressed": False,
    }
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (email,))
            checks["suppressed"] = bool(cur.fetchone())
    if checks["outreach_dry_run"]:
        return False, "outreach_dry_run_enabled", checks
    if checks["outreach_paused"] or not checks["first_live_send_flag"]:
        return False, "live_outreach_not_approved", checks
    if checks["mail_qa_decision"] != "PASS":
        return False, "mail_qa_not_passed", checks
    if checks["visual_qa_decision"] != "PASS":
        return False, "visual_qa_not_passed", checks
    if checks["suppressed"]:
        return False, "recipient_suppressed", checks
    if not checks["has_unsubscribe"]:
        return False, "missing_unsubscribe", checks
    return True, "all_gates_passed", checks


def send_message_if_allowed(message_id: str) -> dict:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, mailbox, subject, body, status FROM outreach_messages WHERE id = %s", (message_id,))
            message = cur.fetchone()
            if not message:
                return {"sent": False, "reason": "message_not_found"}
            cur.execute("SELECT email FROM leads WHERE id = (SELECT lead_id FROM outreach_messages WHERE id = %s)", (message_id,))
            lead = cur.fetchone()
            email = lead["email"] if lead else ""
    allowed, reason, checks = transport_gate(email, message["body"])
    if not allowed:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO system_events(type, severity, message, payload_json) VALUES ('outreach.transport_blocked', 'warning', %s, %s)",
                    (reason, Jsonb({"message_id": message_id, "checks": checks})),
                )
            conn.commit()
        return {"sent": False, "reason": reason, "checks": checks}

    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM_DEFAULT", "audit@voiddorescue.com")
    msg["To"] = email
    msg["Subject"] = message["subject"]
    msg.set_content(message["body"])
    with smtplib.SMTP(os.environ.get("SMTP_HOST", "mail.voiddo.com"), int(os.environ.get("SMTP_PORT", "587")), timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(os.environ.get("SMTP_USERNAME", ""), os.environ.get("SMTP_PASSWORD", ""))
        smtp.send_message(msg)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE outreach_messages SET status = 'sent', sent_at = now() WHERE id = %s", (message_id,))
        conn.commit()
    return {"sent": True, "reason": "sent"}
