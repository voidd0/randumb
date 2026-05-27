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


def _latest_campaign_preflight(cur, campaign_id: str | None) -> dict:
    if not campaign_id:
        return {"allowed": False, "reason": "campaign_preflight_campaign_id_missing", "decision": "MISSING", "fresh": False}
    cur.execute(
        """
        SELECT id, decision, checked_count, ready_count, blocker_count, created_at,
               created_at >= now() - interval '120 minutes' AS fresh
        FROM campaign_preflight_runs
        WHERE campaign_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (campaign_id,),
    )
    row = cur.fetchone()
    if not row:
        return {"allowed": False, "reason": "campaign_preflight_missing", "decision": "MISSING", "fresh": False}
    allowed = row["decision"] == "PASS_NO_SEND_PREFLIGHT" and bool(row["fresh"])
    return {
        "allowed": allowed,
        "reason": "campaign_preflight_pass" if allowed else ("campaign_preflight_stale" if row["decision"] == "PASS_NO_SEND_PREFLIGHT" else "campaign_preflight_not_pass"),
        "id": str(row["id"]),
        "decision": row["decision"],
        "checked_count": int(row["checked_count"] or 0),
        "ready_count": int(row["ready_count"] or 0),
        "blocker_count": int(row["blocker_count"] or 0),
        "fresh": bool(row["fresh"]),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def transport_gate(email: str, body: str, campaign_id: str | None = None) -> tuple[bool, str, dict]:
    checks = {
        "outreach_dry_run": os.environ.get("OUTREACH_DRY_RUN", "true").lower() == "true",
        "outreach_paused": os.environ.get("OUTREACH_PAUSED", "true").lower() == "true",
        "first_live_send_flag": os.environ.get("FIRST_LIVE_SEND_FLAG", "false").lower() == "true",
        "mail_qa_decision": _latest_decision("mail_qa_runs"),
        "visual_qa_decision": _latest_decision("visual_qa_runs"),
        "has_unsubscribe": "unsubscribe" in body.lower(),
        "suppressed": False,
        "campaign_preflight": {"allowed": False, "reason": "not_checked"},
    }
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (email,))
            checks["suppressed"] = bool(cur.fetchone())
            checks["campaign_preflight"] = _latest_campaign_preflight(cur, campaign_id)
    if checks["outreach_dry_run"]:
        return False, "outreach_dry_run_enabled", checks
    if checks["outreach_paused"] or not checks["first_live_send_flag"]:
        return False, "live_outreach_not_approved", checks
    if checks["mail_qa_decision"] != "PASS":
        return False, "mail_qa_not_passed", checks
    if checks["visual_qa_decision"] != "PASS":
        return False, "visual_qa_not_passed", checks
    if not checks["campaign_preflight"]["allowed"]:
        return False, checks["campaign_preflight"]["reason"], checks
    if checks["suppressed"]:
        return False, "recipient_suppressed", checks
    if not checks["has_unsubscribe"]:
        return False, "missing_unsubscribe", checks
    return True, "all_gates_passed", checks


def send_message_if_allowed(message_id: str) -> dict:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, lead_id, audit_id, mailbox, subject, body, status FROM outreach_messages WHERE id = %s", (message_id,))
            message = cur.fetchone()
            if not message:
                return {"sent": False, "reason": "message_not_found"}
            cur.execute("SELECT email FROM leads WHERE id = (SELECT lead_id FROM outreach_messages WHERE id = %s)", (message_id,))
            lead = cur.fetchone()
            email = lead["email"] if lead else ""
            cur.execute(
                """
                SELECT campaign_id
                FROM campaign_leads
                WHERE lead_id = %s
                  AND (audit_id = %s OR %s IS NULL)
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (message["lead_id"], message["audit_id"], message["audit_id"]),
            )
            campaign = cur.fetchone()
            campaign_id = str(campaign["campaign_id"]) if campaign else None
    allowed, reason, checks = transport_gate(email, message["body"], campaign_id)
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
