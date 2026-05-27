from __future__ import annotations

import hashlib
from email.utils import getaddresses, parseaddr
from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all
from .p0 import json_safe, store_owner_command


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_private_addresses_included": False,
    "secrets_included": False,
}


def _hash_email(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()


def _owner_emails() -> set[str]:
    settings = get_settings()
    raw = ",".join([settings.owner_command_email or "", settings.studio_owner_command_emails or ""])
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _addresses(value: str) -> list[str]:
    return [addr.lower() for _, addr in getaddresses([value or ""]) if addr]


def _alias_from_headers(to_header: str, delivered_to: str = "", x_original_to: str = "") -> str:
    for source in [delivered_to, x_original_to, to_header]:
        for addr in _addresses(source):
            if addr.endswith("@voiddo.com"):
                return addr
    return ""


def _message_hash(message_id: str) -> str:
    return hashlib.sha256((message_id or "").encode("utf-8")).hexdigest()[:16]


def _record_mail_signal(classified: dict[str, Any], message: dict[str, Any], message_id: str) -> dict[str, Any] | None:
    signal_map = {
        "bounce": ("bounce", "warning", "studio_mail_monitor", "studio mailbox delivery failure"),
        "dmarc_report": ("dmarc_failure", "info", "studio_mail_monitor", "studio mailbox DMARC report received"),
    }
    if classified["classification"] not in signal_map:
        return None
    signal_type, severity, source, summary = signal_map[classified["classification"]]
    sender = parseaddr(str(message.get("sender") or ""))[1].lower()
    row = execute(
        """
        INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, message_id, raw_summary)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            signal_type,
            severity,
            source,
            str(message.get("mailbox") or "studio:voiddo"),
            _hash_email(sender),
            classified.get("sender_domain") or "",
            message_id,
            summary,
        ),
    )
    return {"mail_signal_id": str(row["id"]), "signal_type": signal_type, "severity": severity}


def _create_studio_mail_task(classified: dict[str, Any], message: dict[str, Any], message_id: str) -> dict[str, Any] | None:
    task_map = {
        "billing": ("billing_bug", "high", "Autonomously triage billing mailbox signal"),
        "personal_or_support": ("customer_fix_request", "medium", "Autonomously triage studio support mailbox signal"),
        "stale_outreach_reply": ("outreach_template_improvement", "medium", "Autonomously triage stale outreach reply"),
    }
    if classified["classification"] not in task_map:
        return None
    task_type, priority, title = task_map[classified["classification"]]
    row = execute(
        """
        INSERT INTO codex_tasks(type, priority, status, title, description, input_json)
        VALUES (%s, %s, 'open', %s, %s, %s)
        RETURNING id
        """,
        (
            task_type,
            priority,
            title,
            "Created from studio mailbox monitor. Payload is redacted; inspect mailbox through approved monitor tooling only.",
            Jsonb(
                {
                    "source": "studio_mail_monitor",
                    "classification": classified["classification"],
                    "priority": classified["priority"],
                    "alias": classified["alias"],
                    "sender_hash": classified["sender_hash"],
                    "sender_domain": classified["sender_domain"],
                    "message_hash": _message_hash(message_id),
                    "autonomous_next_step": "classify_context_prepare_safe_action",
                    **SAFE_FLAGS,
                }
            ),
        ),
    )
    return {"codex_task_id": str(row["id"]), "task_type": task_type, "task_priority": priority}


def classify_studio_mail(message: dict[str, Any]) -> dict[str, Any]:
    sender = parseaddr(str(message.get("sender") or ""))[1].lower()
    reply_to = parseaddr(str(message.get("reply_to") or ""))[1].lower()
    subject = str(message.get("subject") or "")
    body = str(message.get("body") or "")
    to_header = str(message.get("to") or "")
    alias = _alias_from_headers(to_header, str(message.get("delivered_to") or ""), str(message.get("x_original_to") or ""))
    text = f"{subject}\n{body}".lower()
    sender_domain = sender.split("@")[-1] if "@" in sender else ""
    owner_sender = sender in _owner_emails() or reply_to in _owner_emails()

    if owner_sender:
        classification = "owner_command_global"
        priority = "critical"
        human = False
    elif "paddle" in sender_domain or alias == "billing@voiddo.com":
        classification = "billing"
        priority = "critical"
        human = True
    elif any(marker in sender for marker in ["mailer-daemon", "postmaster"]) or "delivery status notification" in text:
        classification = "bounce"
        priority = "low"
        human = False
    elif alias == "dmarc@voiddo.com" or "report domain" in text or "dmarc" in subject.lower():
        classification = "dmarc_report"
        priority = "low"
        human = False
    elif alias == "unsubscribe@voiddo.com" or any(marker in text for marker in ["unsubscribe", "remove me", "stop emailing"]):
        classification = "unsubscribe"
        priority = "high"
        human = False
    elif alias in {"support@voiddo.com", "hi@voiddo.com", "em@voiddo.com"}:
        classification = "personal_or_support"
        priority = "high"
        human = True
    elif subject.lower().startswith("re:") and any(marker in text for marker in ["urweb", "lead_id", "outreach"]):
        classification = "stale_outreach_reply"
        priority = "normal"
        human = True
    else:
        classification = "personal_or_support"
        priority = "normal"
        human = True

    return {
        "classification": classification,
        "priority": priority,
        "human_review_required": human,
        "alias": alias,
        "sender_hash": _hash_email(sender),
        "sender_domain": sender_domain,
        "owner_sender": owner_sender,
        **SAFE_FLAGS,
    }


def store_studio_mail_message(message: dict[str, Any]) -> dict[str, Any]:
    mailbox = str(message.get("mailbox") or "studio:voiddo")
    uid = str(message.get("uid") or "")
    message_id = str(message.get("message_id") or uid or message.get("subject") or "")
    if not uid:
        uid = hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:24]
    classified = classify_studio_mail(message)
    owner_command_id = None
    owner_result: dict[str, Any] | None = None
    mail_signal: dict[str, Any] | None = None
    triage_task: dict[str, Any] | None = None

    existing = fetch_all(
        """
        SELECT id, classification, owner_command_id
        FROM studio_mail_messages
        WHERE mailbox = %s AND uid = %s AND message_id = %s
        """,
        (mailbox, uid, message_id),
    )
    if existing:
        row = existing[0]
        return {
            "stored": False,
            "duplicate": True,
            "id": str(row["id"]),
            "classification": row["classification"],
            "owner_command_id": str(row["owner_command_id"]) if row.get("owner_command_id") else None,
            **SAFE_FLAGS,
        }

    if classified["classification"] == "owner_command_global":
        owner_result = store_owner_command(
            {
                "mailbox": mailbox,
                "uid": uid,
                "message_id": message_id,
                "sender": message.get("sender", ""),
                "reply_to": message.get("reply_to", ""),
                "subject": message.get("subject", ""),
                "body": message.get("body", ""),
                "authentication_results": message.get("authentication_results", ""),
            }
        )
        owner_command_id = owner_result.get("id")
    mail_signal = _record_mail_signal(classified, message, message_id)
    triage_task = _create_studio_mail_task(classified, message, message_id)

    result_json = json_safe(
        {
            "classification": classified["classification"],
            "priority": classified["priority"],
            "alias": classified["alias"],
            "sender_domain": classified["sender_domain"],
            "owner_command_id": owner_command_id,
            "mail_signal": mail_signal,
            "triage_task": triage_task,
            "owner_command": {
                "command": owner_result.get("command") if owner_result else None,
                "risk_level": owner_result.get("risk_level") if owner_result else None,
                "status": owner_result.get("status") if owner_result else None,
            },
            **SAFE_FLAGS,
        }
    )
    row = execute(
        """
        INSERT INTO studio_mail_messages(
          mailbox, uid, message_id, sender_hash, alias, classification, priority,
          owner_command_id, human_review_required, result_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            mailbox,
            uid,
            message_id,
            classified["sender_hash"],
            classified["alias"],
            classified["classification"],
            classified["priority"],
            owner_command_id,
            classified["human_review_required"],
            Jsonb(result_json),
        ),
    )

    execute(
        """
        INSERT INTO email_events(event_type, payload_json, mailbox, uid, message_id, classification, human_review_required)
        VALUES ('studio_mail_inbound', %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            Jsonb(
                {
                    "studio_mail_message_id": str(row["id"]),
                    "sender_hash": classified["sender_hash"],
                    "alias": classified["alias"],
                    "priority": classified["priority"],
                    **SAFE_FLAGS,
                }
            ),
            mailbox,
            uid,
            message_id,
            classified["classification"],
            classified["human_review_required"],
        ),
    )
    if classified["classification"] == "unsubscribe":
        sender = parseaddr(str(message.get("sender") or ""))[1].lower()
        if sender:
            existing = fetch_all("SELECT id FROM suppression_list WHERE lower(email) = lower(%s)", (sender,))
            if not existing:
                execute(
                    """
                    INSERT INTO suppression_list(email, reason, source)
                    VALUES (%s, 'voiddo_unsubscribe_request', 'studio_mail_monitor')
                    """,
                    (sender,),
                )
    severity = "critical" if classified["priority"] == "critical" else ("warning" if classified["human_review_required"] else "info")
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES (%s, %s, %s, %s)
        """,
        (
            f"studio_mail.{classified['classification']}",
            severity,
            "Studio mailbox message classified",
            Jsonb({"studio_mail_message_id": str(row["id"]), "alias": classified["alias"], "sender_hash": classified["sender_hash"], **SAFE_FLAGS}),
        ),
    )
    return {
        "stored": True,
        "duplicate": False,
        "id": str(row["id"]),
        "classification": classified["classification"],
        "priority": classified["priority"],
        "human_review_required": classified["human_review_required"],
        "owner_command_id": owner_command_id,
        "mail_signal": mail_signal,
        "triage_task": triage_task,
        **SAFE_FLAGS,
    }


def ingest_studio_mail_messages(messages: list[dict[str, Any]], dry_run: bool = False) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for message in messages[:50]:
        if dry_run:
            classified = classify_studio_mail(message)
            results.append({"stored": False, "duplicate": False, **classified})
        else:
            results.append(store_studio_mail_message(message))
    stored_count = len([item for item in results if item.get("stored")])
    result = json_safe(
        {
            "status": "dry_run" if dry_run else "stored",
            "dry_run": dry_run,
            "scanned_count": len(results),
            "stored_count": stored_count,
            "owner_command_count": len([item for item in results if item.get("classification") == "owner_command_global"]),
            "high_priority_count": len([item for item in results if item.get("priority") in {"high", "critical"}]),
            "human_review_count": len([item for item in results if item.get("human_review_required")]),
            "results": results,
            **SAFE_FLAGS,
        }
    )
    row = execute(
        """
        INSERT INTO studio_mail_monitor_runs(
          status, dry_run, scanned_count, stored_count, owner_command_count,
          high_priority_count, human_review_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_private_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (
            result["status"],
            dry_run,
            result["scanned_count"],
            result["stored_count"],
            result["owner_command_count"],
            result["high_priority_count"],
            result["human_review_count"],
            Jsonb(result),
        ),
    )
    result["run_id"] = str(row["id"])
    result["created_at"] = row["created_at"].isoformat()
    return result


def latest_studio_mail_messages(limit: int = 20) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, mailbox, alias, classification, priority, owner_command_id,
               human_review_required, created_at
        FROM studio_mail_messages
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 20), 100)),),
    )
    return {
        "count": len(rows),
        "messages": [
            {
                "id": str(row["id"]),
                "mailbox": row["mailbox"],
                "alias": row["alias"],
                "classification": row["classification"],
                "priority": row["priority"],
                "owner_command_id": str(row["owner_command_id"]) if row.get("owner_command_id") else None,
                "human_review_required": bool(row["human_review_required"]),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ],
        **SAFE_FLAGS,
    }


def latest_studio_mail_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, dry_run, scanned_count, stored_count, owner_command_count,
               high_priority_count, human_review_count, send_mail, smtp_called,
               live_outreach_allowed, raw_private_addresses_included, secrets_included, created_at
        FROM studio_mail_monitor_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 100)),),
    )
    return {
        "count": len(rows),
        "runs": [
            {
                "id": str(row["id"]),
                "status": row["status"],
                "dry_run": bool(row["dry_run"]),
                "scanned_count": int(row["scanned_count"] or 0),
                "stored_count": int(row["stored_count"] or 0),
                "owner_command_count": int(row["owner_command_count"] or 0),
                "high_priority_count": int(row["high_priority_count"] or 0),
                "human_review_count": int(row["human_review_count"] or 0),
                "send_mail": bool(row["send_mail"]),
                "smtp_called": bool(row["smtp_called"]),
                "live_outreach_allowed": bool(row["live_outreach_allowed"]),
                "raw_private_addresses_included": bool(row["raw_private_addresses_included"]),
                "secrets_included": bool(row["secrets_included"]),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ],
        **SAFE_FLAGS,
    }
