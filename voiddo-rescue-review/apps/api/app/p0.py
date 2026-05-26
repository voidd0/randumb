from __future__ import annotations

import csv
import io
import json
import os
import re
import socket
import ssl
import smtplib
import imaplib
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
import dns.resolver
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .billing import PRODUCTS, price_id_for
from .config import Settings, get_settings
from .db import connect_dict, execute, fetch_all, fetch_one
from .inbox import classify_reply


ONETIME_FIX_PRODUCTS = {"audit_onetime", "contact_form_repair", "emergency_fix"}
EXCLUDED_NICHES = {"banks", "bank", "government", "hospital", "hospitals", "gambling", "adult", "crypto", "political"}
OWNER_EMAIL_FALLBACK = ""
RUNTIME_PAUSE_KEYS = {
    "scanner": "pause_scanner",
    "outreach": "pause_outreach",
    "warmup": "pause_warmup",
    "auto_replies": "pause_auto_replies",
    "workers": "pause_workers",
}


def _split_config_emails(raw: str) -> list[str]:
    seen: set[str] = set()
    emails: list[str] = []
    for item in re.split(r"[\s,;]+", raw or ""):
        email = item.strip().lower()
        if not email or "@" not in email or email in seen:
            continue
        seen.add(email)
        emails.append(email)
    return emails


def runtime_control_enabled(key: str) -> bool:
    row = fetch_one("SELECT value FROM runtime_controls WHERE key = %s", (key,))
    return bool(row and row["value"])


def set_runtime_control(key: str, value: bool, source: str, reason: str = "") -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO runtime_controls(key, value, source, reason)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (key) DO UPDATE
          SET value = EXCLUDED.value,
              source = EXCLUDED.source,
              reason = EXCLUDED.reason,
              updated_at = now()
        RETURNING key, value, source, reason, updated_at
        """,
        (key, value, source, reason),
    )
    return dict(row)


def effective_pause_state(area: str, configured: bool = False) -> bool:
    key = RUNTIME_PAUSE_KEYS.get(area, area)
    return bool(configured or runtime_control_enabled(key))


def approved_test_inbox_emails(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    emails = _split_config_emails(settings.test_inboxes) + _split_config_emails(settings.test_inbox_pool)
    db_rows = fetch_all("SELECT email FROM test_inboxes WHERE status = 'approved'")
    emails.extend(str(row["email"]).lower() for row in db_rows)
    return sorted(set(email for email in emails if "@" in email))


def approved_warmup_recipient_emails(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    emails = _split_config_emails(settings.warmup_recipient_pool)
    db_rows = fetch_all("SELECT email FROM warmup_recipients WHERE status = 'approved_test_pool'")
    emails.extend(str(row["email"]).lower() for row in db_rows)
    suppressed = {
        str(row["email"]).lower()
        for row in fetch_all("SELECT email FROM suppression_list WHERE email IS NOT NULL")
    }
    return sorted(set(email for email in emails if "@" in email and email not in suppressed))


def create_scanner_job(url: str, business_name: str | None, dry_run: bool = False) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status)
        VALUES (%s, %s, %s, 'queued')
        RETURNING id, url, business_name, dry_run, status, queued_at
        """,
        (url, business_name, dry_run),
    )
    return dict(row)


def get_scanner_job(job_id: str) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT id, url, business_name, dry_run, status, audit_id, result_json,
               error, queued_at, started_at, completed_at, updated_at
        FROM scanner_jobs
        WHERE id = %s
        """,
        (job_id,),
    )
    return dict(row) if row else None


def get_audit_by_slug(slug: str) -> dict[str, Any] | None:
    audit = fetch_one(
        """
        SELECT id, business_id, lead_id, domain, url, status, score, summary,
               public_slug, checked_at, created_at
        FROM audits
        WHERE public_slug = %s
        """,
        (slug,),
    )
    if not audit:
        return None
    issues = fetch_all(
        """
        SELECT issue_type, severity, title, public_text, internal_notes,
               evidence_json, recommendation, created_at
        FROM audit_issues
        WHERE audit_id = %s
        ORDER BY CASE severity
          WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, created_at
        """,
        (audit["id"],),
    )
    screenshots = fetch_all(
        """
        SELECT type, file_path, public_url, viewport, created_at
        FROM screenshots
        WHERE audit_id = %s
        ORDER BY created_at
        """,
        (audit["id"],),
    )
    business = None
    if audit.get("business_id"):
        business = fetch_one("SELECT name, email, country, city, niche FROM businesses WHERE id = %s", (audit["business_id"],))
    return {
        **dict(audit),
        "business": dict(business) if business else None,
        "issues": [dict(item) for item in issues],
        "screenshots": [dict(item) for item in screenshots],
        "checkout_links": checkout_links_for_audit(slug),
    }


def checkout_links_for_audit(slug: str) -> dict[str, str]:
    settings = get_settings()
    links: dict[str, str] = {}
    for key in PRODUCTS:
        price_id = price_id_for(settings, key)
        if price_id:
            links[key] = f"{settings.go_base_url}/checkout/{key}?audit={slug}&price_id={price_id}"
    return links


def admin_metrics_from_db() -> dict[str, Any]:
    def scalar(sql: str, params: tuple = ()) -> int:
        row = fetch_one(sql, params)
        return int(next(iter(row.values()))) if row else 0

    scan_rows = fetch_all("SELECT status, count(*) AS count FROM scanner_jobs GROUP BY status")
    email_rows = fetch_all("SELECT status, count(*) AS count FROM outreach_messages GROUP BY status")
    return {
        "leads_total": scalar("SELECT count(*) FROM leads"),
        "scans": {
            "queued": sum(int(r["count"]) for r in scan_rows if r["status"] == "queued"),
            "running": sum(int(r["count"]) for r in scan_rows if r["status"] == "running"),
            "completed": sum(int(r["count"]) for r in scan_rows if r["status"] == "completed"),
            "failed": sum(int(r["count"]) for r in scan_rows if r["status"] == "failed"),
        },
        "qualified_leads": scalar("SELECT count(*) FROM leads WHERE score >= 70"),
        "audit_pages_generated": scalar("SELECT count(*) FROM audits WHERE public_slug IS NOT NULL"),
        "emails": {
            "queued": sum(int(r["count"]) for r in email_rows if r["status"] == "queued"),
            "sent": sum(int(r["count"]) for r in email_rows if r["status"] == "sent"),
            "bounced": sum(int(r["count"]) for r in email_rows if r["status"] == "bounced"),
            "replied": scalar("SELECT count(*) FROM inbox_threads"),
        },
        "interested_replies": scalar("SELECT count(*) FROM inbox_threads WHERE classification = 'interested'"),
        "human_review_required": scalar("SELECT count(*) FROM inbox_threads WHERE human_review_required"),
        "payments": scalar("SELECT count(*) FROM payments"),
        "subscriptions": scalar("SELECT count(*) FROM subscriptions"),
        "customers": scalar("SELECT count(*) FROM customers"),
        "fix_requests": scalar("SELECT count(*) FROM fix_requests"),
        "owner_commands": scalar("SELECT count(*) FROM owner_commands"),
        "visual_qa_runs": scalar("SELECT count(*) FROM visual_qa_runs"),
        "mail_qa_runs": scalar("SELECT count(*) FROM mail_qa_runs"),
        "warmup_runs": scalar("SELECT count(*) FROM warmup_runs"),
        "warmup_recipients": scalar("SELECT count(*) FROM warmup_recipients WHERE status = 'approved_test_pool'"),
        "test_inboxes": scalar("SELECT count(*) FROM test_inboxes WHERE status = 'approved'"),
        "lead_batches": scalar("SELECT count(*) FROM lead_batches"),
        "outreach_preview_batches": scalar("SELECT count(*) FROM outreach_preview_batches"),
        "workers": {"api": "ok", "worker": "configured"},
        "kill_switches": {
            "global": get_settings().global_kill_switch,
            "scanning": effective_pause_state("scanner", get_settings().scanning_paused),
            "outreach": effective_pause_state("outreach", get_settings().outreach_paused),
            "warmup": effective_pause_state("warmup", False),
            "auto_replies": effective_pause_state("auto_replies", get_settings().auto_replies_paused),
            "workers": effective_pause_state("workers", False),
            "paddle_provisioning": get_settings().paddle_provisioning_paused,
        },
    }


def product_key_from_payload(data: dict[str, Any], settings: Settings) -> str:
    custom = data.get("custom_data") or {}
    if custom.get("product_key"):
        return str(custom["product_key"])
    price_ids = {price_id_for(settings, key): key for key in PRODUCTS if price_id_for(settings, key)}
    for item in data.get("items") or []:
        price = item.get("price") or {}
        if price.get("id") in price_ids:
            return price_ids[price["id"]]
    return "unknown"


def _amount_from_payload(data: dict[str, Any]) -> tuple[float | None, str | None]:
    totals = data.get("details", {}).get("totals", {})
    raw = totals.get("total") or totals.get("grand_total")
    currency = totals.get("currency_code") or data.get("currency_code")
    if raw is None:
        return None, currency
    try:
        return round(float(raw) / 100, 2), currency
    except (TypeError, ValueError):
        return None, currency


def upsert_customer(email: str, paddle_customer_id: str | None) -> str:
    row = execute(
        """
        INSERT INTO customers(email, paddle_customer_id, status)
        VALUES (%s, %s, 'active')
        ON CONFLICT (lower(email)) DO UPDATE
          SET paddle_customer_id = COALESCE(EXCLUDED.paddle_customer_id, customers.paddle_customer_id),
              status = 'active',
              updated_at = now()
        RETURNING id
        """,
        (email, paddle_customer_id),
    )
    return str(row["id"])


def handle_paddle_event(payload: dict[str, Any], provisioning_paused: bool) -> dict[str, Any]:
    settings = get_settings()
    event_type = payload.get("event_type", "unknown")
    data = payload.get("data") or {}
    actions: list[str] = []

    if event_type == "transaction.paid":
        email = data.get("customer", {}).get("email") or data.get("customer_email") or "unknown@voiddorescue.local"
        customer_id = upsert_customer(email, data.get("customer_id"))
        product_key = product_key_from_payload(data, settings)
        amount, currency = _amount_from_payload(data)
        execute(
            """
            INSERT INTO payments(customer_id, paddle_transaction_id, amount, currency, product_key, status)
            VALUES (%s, %s, %s, %s, %s, 'paid')
            ON CONFLICT (paddle_transaction_id) DO UPDATE
              SET status = 'paid', amount = EXCLUDED.amount, currency = EXCLUDED.currency, product_key = EXCLUDED.product_key
            RETURNING id
            """,
            (customer_id, data.get("id"), amount, currency, product_key),
        )
        actions.append("payment_recorded")
        if product_key in ONETIME_FIX_PRODUCTS:
            execute(
                """
                INSERT INTO fix_requests(customer_id, product_key, status, priority, title, description, evidence_json)
                VALUES (%s, %s, 'new', 'P1', %s, %s, %s)
                RETURNING id
                """,
                (
                    customer_id,
                    product_key,
                    f"{PRODUCTS.get(product_key, {}).get('name', product_key)} purchased",
                    "Created from Paddle transaction.paid webhook.",
                    Jsonb({"paddle_transaction_id": data.get("id"), "provisioning_paused": provisioning_paused}),
                ),
            )
            actions.append("fix_request_created")
        execute(
            "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
            ("paddle.transaction_paid", "info", "Paddle transaction paid processed", Jsonb({"actions": actions, "provisioning_paused": provisioning_paused})),
        )
        if not provisioning_paused:
            actions.append("onboarding_email_task_created")
        return {"event_type": event_type, "actions": actions, "provisioning_paused": provisioning_paused}

    if event_type in {"subscription.created", "subscription.activated", "subscription.updated", "subscription.canceled"}:
        email = data.get("customer", {}).get("email") or data.get("customer_email") or "unknown@voiddorescue.local"
        customer_id = upsert_customer(email, data.get("customer_id"))
        product_key = product_key_from_payload(data, settings)
        status = data.get("status") or event_type.rsplit(".", 1)[-1]
        execute(
            """
            INSERT INTO subscriptions(customer_id, paddle_subscription_id, product_key, status, current_period_start, current_period_end)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (paddle_subscription_id) DO UPDATE
              SET product_key = EXCLUDED.product_key,
                  status = EXCLUDED.status,
                  current_period_start = EXCLUDED.current_period_start,
                  current_period_end = EXCLUDED.current_period_end,
                  updated_at = now()
            RETURNING id
            """,
            (
                customer_id,
                data.get("id"),
                product_key,
                status,
                data.get("current_billing_period", {}).get("starts_at"),
                data.get("current_billing_period", {}).get("ends_at"),
            ),
        )
        actions.append("subscription_recorded")
        if not provisioning_paused and event_type in {"subscription.created", "subscription.activated"}:
            actions.append("onboarding_email_task_created")
        execute(
            "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
            (f"paddle.{event_type}", "info", "Paddle subscription event processed", Jsonb({"actions": actions, "provisioning_paused": provisioning_paused})),
        )
        return {"event_type": event_type, "actions": actions, "provisioning_paused": provisioning_paused}

    if event_type in {"payment.failed", "transaction.payment_failed"}:
        execute(
            "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
            ("paddle.payment_failed", "warning", "Paddle payment failed", Jsonb({"paddle_id": data.get("id")})),
        )
        return {"event_type": event_type, "actions": ["payment_failed_logged"], "provisioning_paused": provisioning_paused}

    execute(
        "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
        ("paddle.unhandled", "info", "Unhandled Paddle event verified", Jsonb({"event_type": event_type})),
    )
    return {"event_type": event_type, "actions": ["verified_unhandled"], "provisioning_paused": provisioning_paused}


def persist_inbound_message(message: dict[str, Any]) -> dict[str, Any]:
    mailbox = message.get("mailbox", "audit")
    uid = str(message.get("uid") or "")
    message_id = str(message.get("message_id") or uid or message.get("subject") or "")
    subject = message.get("subject", "")
    body = message.get("body", "")
    sender = parseaddr(message.get("sender", ""))[1] or message.get("sender", "")
    classified = classify_reply(subject, body)
    classification = classified["classification"]
    human = bool(classified["human_review_required"])

    with connect_dict() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM email_events
                WHERE mailbox = %s AND uid = %s AND message_id = %s
                """,
                (mailbox, uid, message_id),
            )
            existing = cur.fetchone()
            if existing:
                return {"stored": False, "duplicate": True, "classification": classification, "human_review_required": human}
            cur.execute(
                """
                INSERT INTO inbox_threads(mailbox, external_thread_id, classification, human_review_required, last_message_preview)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (mailbox, message.get("thread_id") or message_id, classification, human, body[:240]),
            )
            thread_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO email_events(event_type, payload_json, mailbox, uid, message_id, classification, human_review_required)
                VALUES ('inbound_reply', %s, %s, %s, %s, %s, %s)
                """,
                (Jsonb({"sender": sender, "subject": subject, "thread_id": str(thread_id)}), mailbox, uid, message_id, classification, human),
            )
            if classification == "unsubscribe":
                cur.execute(
                    """
                    INSERT INTO suppression_list(email, reason, source)
                    VALUES (%s, 'unsubscribe_reply', 'inbox')
                    """,
                    (sender,),
                )
            if classification in {"legal_threat", "security_accusation", "angry"}:
                cur.execute(
                    "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, 'critical', %s, %s)",
                    (f"inbox.{classification}", "Unsafe reply requires human review", Jsonb({"sender": sender, "subject": subject})),
                )
        conn.commit()
    return {"stored": True, "duplicate": False, "classification": classification, "human_review_required": human}


def parse_owner_command(sender: str, subject: str, body: str, reply_to: str = "", auth_results: str = "") -> dict[str, Any]:
    owner_email = (get_settings().owner_command_email or OWNER_EMAIL_FALLBACK).lower()
    sender_email = parseaddr(sender)[1].lower()
    reply_email = parseaddr(reply_to)[1].lower() if reply_to else sender_email
    text = f"{subject}\n{body}".strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    normalized = re.sub(r"\s+", " ", first_line.upper())
    args: dict[str, Any] = {}
    command = normalized

    if normalized.startswith("PREPARE LEADS"):
        command = "PREPARE LEADS"
        for key, value in re.findall(r"(COUNTRY|NICHE|LIMIT)=([^\s]+)", first_line, flags=re.I):
            args[key.lower()] = value

    safe = {"STATUS", "REPORT TODAY", "PAUSE OUTREACH", "PAUSE WARMUP", "PAUSE SCANNER", "PAUSE AUTO REPLIES", "PAUSE ALL", "SHOW HUMAN REVIEW", "SHOW PAYMENTS", "SHOW REPLIES"}
    medium = {"RUN VISUAL QA", "RUN MAIL QA", "PREPARE WARMUP", "PREPARE LEADS"}
    high = {"SEND OUTREACH", "START WARMUP", "UNPAUSE OUTREACH", "RUN SHELL", "EXECUTE"}
    if command in safe:
        risk = "SAFE_AUTO"
    elif command in medium:
        risk = "MEDIUM_RISK"
    elif command in high or any(word in normalized for word in [";", "&&", "|", "`", "$("]):
        risk = "HIGH_RISK"
    else:
        risk = "HIGH_RISK"

    authenticated_hint = "pass" in auth_results.lower() or "dkim=pass" in auth_results.lower() or not auth_results
    authorized = bool(owner_email) and sender_email == owner_email and reply_email in {owner_email, sender_email} and authenticated_hint
    status = "rejected_sender" if sender_email != owner_email else "received"
    if authorized and risk == "SAFE_AUTO":
        status = "executed"
    elif authorized and risk == "MEDIUM_RISK":
        status = "prepared"
    elif authorized:
        status = "review_required"

    return {
        "command": command,
        "args_json": args,
        "risk_level": risk,
        "authorized": authorized,
        "status": status,
        "sender_email": sender_email,
        "reply_email": reply_email,
    }


def store_owner_command(message: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_owner_command(
        message.get("sender", ""),
        message.get("subject", ""),
        message.get("body", ""),
        message.get("reply_to", ""),
        message.get("authentication_results", ""),
    )
    result = json_safe(execute_owner_command(parsed) if parsed["authorized"] else {"ok": False, "action": parsed["status"]})
    uid = str(message.get("uid") or uuid.uuid4().hex)
    message_id = str(message.get("message_id") or uid)
    row = execute(
        """
        INSERT INTO owner_commands(mailbox, uid, message_id, sender, reply_to, subject, body, command,
                                   args_json, risk_level, status, authentication_summary, result_json, executed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s = 'executed' THEN now() ELSE NULL END)
        ON CONFLICT (mailbox, uid, message_id) DO UPDATE
          SET result_json = owner_commands.result_json
        RETURNING id, command, risk_level, status, result_json
        """,
        (
            message.get("mailbox", "owner"),
            uid,
            message_id,
            parsed["sender_email"],
            parsed["reply_email"],
            message.get("subject", ""),
            message.get("body", ""),
            parsed["command"],
            Jsonb(parsed["args_json"]),
            parsed["risk_level"],
            parsed["status"],
            message.get("authentication_results", "")[:500],
            Jsonb(result),
            parsed["status"],
        ),
    )
    return dict(row)


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def execute_owner_command(parsed: dict[str, Any]) -> dict[str, Any]:
    command = parsed["command"]
    risk = parsed["risk_level"]
    if risk == "HIGH_RISK":
        result = {"ok": False, "action": "review_required", "reason": "high_risk_command_blocked"}
    elif command == "STATUS":
        result = {"ok": True, "action": "metrics", "metrics": admin_metrics_from_db()}
    elif command == "REPORT TODAY":
        result = {"ok": True, "action": "report_today", "report": write_owner_daily_report()}
    elif command == "PAUSE ALL":
        paused = [set_runtime_control(key, True, "owner_command", "PAUSE ALL") for key in RUNTIME_PAUSE_KEYS.values()]
        result = {"ok": True, "action": "pause_recorded", "paused": paused}
    elif command.startswith("PAUSE "):
        area = command.replace("PAUSE ", "").lower().replace(" ", "_")
        key = RUNTIME_PAUSE_KEYS.get(area, f"pause_{area}")
        result = {"ok": True, "action": "pause_recorded", "paused": set_runtime_control(key, True, "owner_command", command)}
    elif command == "SHOW HUMAN REVIEW":
        result = {"ok": True, "action": "human_review", "items": fetch_all("SELECT mailbox, classification, last_message_preview FROM inbox_threads WHERE human_review_required ORDER BY updated_at DESC LIMIT 20")}
    elif command == "SHOW PAYMENTS":
        result = {"ok": True, "action": "payments", "items": fetch_all("SELECT amount, currency, product_key, status, created_at FROM payments ORDER BY created_at DESC LIMIT 20")}
    elif command == "SHOW REPLIES":
        result = {"ok": True, "action": "replies", "items": fetch_all("SELECT mailbox, classification, last_message_preview, updated_at FROM inbox_threads ORDER BY updated_at DESC LIMIT 20")}
    elif command == "RUN MAIL QA":
        result = {"ok": True, "action": "mail_qa", "run": run_mail_qa()}
    elif command == "RUN VISUAL QA":
        result = {"ok": True, "action": "visual_qa", "run": record_visual_qa("app_visual_agent", get_settings().app_base_url, "")}
    elif command == "PREPARE WARMUP":
        pool_count = len(approved_warmup_recipient_emails())
        result = {"ok": True, "action": "warmup_prepare", "warmup": prepare_warmup(pool_count, 1)}
    elif command == "PREPARE LEADS":
        result = {"ok": True, "action": "lead_prepare_dry_run", "args": parsed.get("args_json", {}), "live_send": False}
    else:
        result = {"ok": False, "action": "review_required", "reason": "unknown_command"}
    execute(
        "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
        ("owner_command.executed", "info" if result.get("ok") else "warning", command, Jsonb(json_safe({"risk_level": risk, "result": result}))),
    )
    return json_safe(result)


def write_owner_daily_report() -> dict[str, Any]:
    metrics = admin_metrics_from_db()
    report_dir = Path(get_settings().storage_root) / "reports" / "owner"
    report_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = report_dir / f"owner-report-{now.strftime('%Y%m%d')}.json"
    payload = {
        "created_at": now.isoformat(),
        "metrics": metrics,
        "launch_decision": "NOT_LAUNCH_READY",
        "live_outreach_sent": 0,
        "warmup_sent": 0,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    execute(
        "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
        ("owner_command.report_today", "info", "Owner daily report created", Jsonb({"path": str(path)})),
    )
    return {"path": str(path), "created_at": payload["created_at"]}


def huanshu_adapter_status() -> dict[str, Any]:
    candidates = [
        os.environ.get("HUANSHU_CLI", ""),
        "/app/app/huanshu_cli.py",
        "/usr/local/bin/huanshu",
        "/usr/bin/huanshu",
    ]
    executable = next((path for path in candidates if path and os.path.exists(path) and os.access(path, os.X_OK)), "")
    if not executable:
        return {"status": "BLOCKED_HUANSHU_NOT_AVAILABLE", "tool": None, "passed": False}
    try:
        completed = subprocess.run([executable, "--version"], text=True, capture_output=True, timeout=10, check=False)
    except Exception as exc:
        return {"status": "BLOCKED_HUANSHU_ERROR", "tool": executable, "passed": False, "error": type(exc).__name__}
    return {"status": "PASS" if completed.returncode == 0 else "BLOCKED_HUANSHU_ERROR", "tool": executable, "passed": completed.returncode == 0}


def record_visual_qa(agent: str, target_url: str, html: str = "") -> dict[str, Any]:
    issues: list[str] = []
    if "{{" in html or "}}" in html:
        issues.append("unresolved_template_vars")
    if "placeholder" in html.lower():
        issues.append("placeholder_text")
    huanshu = huanshu_adapter_status()
    if not huanshu["passed"]:
        issues.append(huanshu["status"])
    score = max(0, 100 - 25 * len(issues))
    hard_blockers = {"unresolved_template_vars", "raw_json_visible", "broken_images", "console_errors", "page_errors"}
    has_hard_blocker = any(issue in hard_blockers or issue.startswith("BLOCKED_HUANSHU") for issue in issues)
    decision = "FAIL_BLOCK_LAUNCH" if has_hard_blocker or not huanshu["passed"] else ("PASS" if score >= 90 else "PASS_WITH_WARNINGS")
    row = execute(
        """
        INSERT INTO visual_qa_runs(agent, target_url, status, huanshu_status, score, decision, issues_json, screenshots_json, completed_at)
        VALUES (%s, %s, 'completed', %s, %s, %s, %s, %s, now())
        RETURNING id, agent, target_url, huanshu_status, score, decision, issues_json
        """,
        (agent, target_url, huanshu["status"], score, decision, Jsonb(issues), Jsonb([])),
    )
    return dict(row)


def _dig(record_type: str, name: str) -> str:
    try:
        answers = dns.resolver.resolve(name, record_type, lifetime=15)
        return "\n".join(str(answer).strip() for answer in answers)
    except Exception as exc:
        return f"ERROR:{type(exc).__name__}"


def run_mail_qa() -> dict[str, Any]:
    settings = get_settings()
    checks = {
        "a_mail": _dig("A", "mail.voiddorescue.com"),
        "mx": _dig("MX", "voiddorescue.com"),
        "spf": _dig("TXT", "voiddorescue.com"),
        "dkim": _dig("TXT", "dkim._domainkey.voiddorescue.com"),
        "dmarc": _dig("TXT", "_dmarc.voiddorescue.com"),
        "autoconfig": _dig("CNAME", "autoconfig.voiddorescue.com"),
        "autodiscover": _dig("CNAME", "autodiscover.voiddorescue.com"),
    }
    issues: list[str] = []
    if "v=DKIM1" not in checks["dkim"]:
        issues.append("missing_dkim")
    if "TTL: Automatic" in checks["dmarc"]:
        issues.append("dmarc_contains_literal_ttl")
    if "v=DMARC1" not in checks["dmarc"]:
        issues.append("missing_dmarc")

    ctx = ssl.create_default_context()
    smtp_status = "not_configured"
    imap_status = "not_configured"
    smtp_ready = False
    try:
        if settings.smtp_username and settings.smtp_password:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp_status = "ok"
            smtp_ready = True
    except Exception as exc:
        smtp_status = f"fail:{type(exc).__name__}"
        issues.append("smtp_strict_tls_login_failed")
    try:
        if settings.imap_username_audit and settings.imap_password_audit:
            with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, ssl_context=ctx, timeout=20) as imap:
                imap.login(settings.imap_username_audit, settings.imap_password_audit)
                imap.select("INBOX", readonly=True)
                imap.logout()
            imap_status = "ok"
    except Exception as exc:
        imap_status = f"fail:{type(exc).__name__}"
        issues.append("imap_strict_tls_login_failed")

    checks["smtp_strict_tls_login"] = smtp_status
    checks["imap_strict_tls_login"] = imap_status
    approved_test_inboxes = approved_test_inbox_emails(settings)
    checks["approved_test_inboxes"] = len(approved_test_inboxes)
    if checks["approved_test_inboxes"] <= 0:
        issues.append("approved_test_inbox_pool_missing")
    deliverability = run_deliverability_diagnostics(settings, approved_test_inboxes, smtp_ready) if approved_test_inboxes else {"sent": 0, "skipped": "no_approved_test_inboxes"}
    checks["deliverability_diagnostics"] = deliverability
    decision = "PASS" if not issues else "FAIL_BLOCK_LAUNCH"
    row = execute(
        """
        INSERT INTO mail_qa_runs(agent, status, decision, checks_json, issues_json)
        VALUES ('dns_mail_auth_agent', 'completed', %s, %s, %s)
        RETURNING id, decision, checks_json, issues_json
        """,
        (decision, Jsonb(checks), Jsonb(issues)),
    )
    return dict(row)


def run_deliverability_diagnostics(settings: Settings, recipients: list[str], smtp_ready: bool) -> dict[str, Any]:
    if not smtp_ready:
        return {"sent": 0, "skipped": "smtp_not_ready"}
    sent = 0
    skipped = 0
    errors: list[str] = []
    with connect_dict() as conn:
        with conn.cursor() as cur:
            pending: list[str] = []
            for email in recipients:
                row = cur.execute(
                    """
                    INSERT INTO test_inboxes(email, status)
                    VALUES (%s, 'approved')
                    ON CONFLICT (email) DO UPDATE SET status = 'approved'
                    RETURNING email, last_test_at
                    """,
                    (email,),
                ).fetchone()
                if row and row["last_test_at"]:
                    skipped += 1
                else:
                    pending.append(email)
            if pending:
                ctx = ssl.create_default_context()
                try:
                    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                        smtp.ehlo()
                        smtp.starttls(context=ctx)
                        smtp.ehlo()
                        smtp.login(settings.smtp_username, settings.smtp_password)
                        for email in pending:
                            msg = EmailMessage()
                            msg["Subject"] = "Vøiddo Rescue mail diagnostic"
                            msg["From"] = settings.smtp_from_default
                            msg["To"] = email
                            msg.set_content("Neutral mail setup diagnostic for voiddorescue.com. No action is required.")
                            smtp.send_message(msg)
                            sent += 1
                            cur.execute(
                                """
                                UPDATE test_inboxes
                                SET last_test_at = now(), result_json = %s
                                WHERE lower(email) = lower(%s)
                                """,
                                (Jsonb({"status": "sent", "message": "neutral_diagnostic"}), email),
                            )
                except Exception as exc:
                    errors.append(type(exc).__name__)
            conn.commit()
    result: dict[str, Any] = {"sent": sent, "skipped_previously_tested": skipped, "policy": "neutral_diagnostic_max_one_per_mailbox"}
    if errors:
        result["errors"] = errors
    return result


def prepare_warmup(recipient_pool_count: int = 0, day_number: int = 1) -> dict[str, Any]:
    if recipient_pool_count <= 0:
        recipient_pool_count = len(approved_warmup_recipient_emails())
    caps = {1: 5, 2: 10, 3: 15}
    cap = caps.get(day_number, 25 if day_number <= 7 else 40)
    status = "ready_dry_run" if recipient_pool_count > 0 else "blocked_no_recipient_pool"
    stop_conditions = ["bounce", "spam_signal", "auth_failure", "tls_failure", "dkim_failure", "dmarc_failure"]
    row = execute(
        """
        INSERT INTO warmup_runs(status, day_number, planned_daily_cap, recipient_pool_count, plan_json, stop_conditions_json)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, status, day_number, planned_daily_cap, recipient_pool_count, stop_conditions_json
        """,
        (
            status,
            day_number,
            cap,
            recipient_pool_count,
            Jsonb({"dry_run": True, "no_sending": True, "daily_cap": cap, "pool_preview_count": recipient_pool_count}),
            Jsonb(stop_conditions),
        ),
    )
    return dict(row)


def import_warmup_recipients(csv_text: str, mailbox: str = "audit@voiddorescue.com") -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    accepted = 0
    rejected = 0
    with connect_dict() as conn:
        with conn.cursor() as cur:
            for row in reader:
                email = (row.get("email") or "").strip().lower()
                if not email or "@" not in email:
                    rejected += 1
                    continue
                suppressed = cur.execute("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (email,)).fetchone()
                if suppressed:
                    rejected += 1
                    continue
                existing = cur.execute(
                    "SELECT 1 FROM warmup_recipients WHERE lower(email) = lower(%s) AND mailbox = %s",
                    (email, mailbox),
                ).fetchone()
                if existing:
                    continue
                cur.execute(
                    """
                    INSERT INTO warmup_recipients(email, mailbox, source, status, notes)
                    VALUES (%s, %s, 'owner_pool', 'approved_test_pool', %s)
                    """,
                    (email, mailbox, row.get("notes", "")),
                )
                accepted += 1
        conn.commit()
    return {"accepted": accepted, "rejected": rejected, "dry_run_only": True, "sending_started": False}


def import_test_inboxes(csv_text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    accepted = 0
    rejected = 0
    with connect_dict() as conn:
        with conn.cursor() as cur:
            for row in reader:
                email = (row.get("email") or "").strip().lower()
                if not email or "@" not in email:
                    rejected += 1
                    continue
                cur.execute(
                    """
                    INSERT INTO test_inboxes(email, provider, status)
                    VALUES (%s, %s, 'approved')
                    ON CONFLICT (email) DO UPDATE SET provider = EXCLUDED.provider, status = 'approved'
                    """,
                    (email, row.get("provider", "")),
                )
                accepted += 1
        conn.commit()
    return {"accepted": accepted, "rejected": rejected, "diagnostic_policy": "max_one_message_per_mailbox_after_owner_approval", "sent": 0}


def latest_decision(table: str) -> str:
    row = fetch_one(f"SELECT decision FROM {table} ORDER BY created_at DESC LIMIT 1")
    return row["decision"] if row else "MISSING"


def transport_gate_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    settings = get_settings()
    email = (payload.get("email") or "").strip().lower()
    body = payload.get("body") or ""
    checks = {
        "outreach_dry_run": settings.outreach_dry_run,
        "outreach_paused": effective_pause_state("outreach", settings.outreach_paused),
        "first_live_send_flag": settings.first_live_send_flag,
        "mail_qa_decision": latest_decision("mail_qa_runs"),
        "visual_qa_decision": latest_decision("visual_qa_runs"),
        "has_unsubscribe": "unsubscribe" in body.lower(),
        "suppressed": False,
    }
    if email:
        row = fetch_one("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (email,))
        checks["suppressed"] = bool(row)
    if settings.outreach_dry_run:
        return {"allowed": False, "reason": "outreach_dry_run_enabled", "checks": checks}
    if checks["outreach_paused"] or not settings.first_live_send_flag:
        return {"allowed": False, "reason": "live_outreach_not_approved", "checks": checks}
    if checks["mail_qa_decision"] != "PASS":
        return {"allowed": False, "reason": "mail_qa_not_passed", "checks": checks}
    if checks["visual_qa_decision"] != "PASS":
        return {"allowed": False, "reason": "visual_qa_not_passed", "checks": checks}
    if checks["suppressed"]:
        return {"allowed": False, "reason": "recipient_suppressed", "checks": checks}
    if not checks["has_unsubscribe"]:
        return {"allowed": False, "reason": "missing_unsubscribe", "checks": checks}
    return {"allowed": True, "reason": "all_gates_passed", "checks": checks}


def prepare_outreach_preview(limit: int = 20) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT l.id AS lead_id, l.email, b.name AS business_name, b.domain, a.public_slug, a.summary
        FROM leads l
        JOIN businesses b ON b.id = l.business_id
        JOIN audits a ON a.business_id = b.id
        WHERE l.score >= 70
          AND l.email IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(s.email) = lower(l.email))
        ORDER BY l.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    preview = []
    for row in rows:
        preview.append(
            {
                "lead_id": str(row["lead_id"]),
                "email": row["email"],
                "business_name": row["business_name"],
                "domain": row["domain"],
                "audit_url": f"{get_settings().audit_base_url}/r/{row['public_slug']}",
                "main_issue_short": row["summary"],
                "dry_run": True,
            }
        )
    batch = execute(
        """
        INSERT INTO outreach_preview_batches(total_candidates, preview_json)
        VALUES (%s, %s)
        RETURNING id, status, total_candidates, preview_json
        """,
        (len(preview), Jsonb(preview)),
    )
    return dict(batch)


def queue_outreach_preview(limit: int = 20) -> dict[str, Any]:
    preview_batch = prepare_outreach_preview(limit)
    created = 0
    for item in preview_batch["preview_json"]:
        body = (
            f"Hi team,\n\nI checked {item['domain']} today and found a possible issue that may affect customer enquiries:\n\n"
            f"{item['main_issue_short']}\n\nScreenshots and test details:\n{item['audit_url']}\n\n"
            "Public non-invasive website check.\nUnsubscribe: https://go.rescue.voiddo.com/unsubscribe/preview"
        )
        execute(
            """
            INSERT INTO outreach_messages(lead_id, mailbox, subject, body, status)
            VALUES (%s, 'audit@voiddorescue.com', %s, %s, 'preview')
            """,
            (item["lead_id"], f"Possible issue on {item['business_name']} website", body),
        )
        created += 1
    return {"created": created, "dry_run_only": True, "preview_batch_id": str(preview_batch["id"])}


def import_lead_batch(name: str, csv_text: str, country: str | None = None, niche: str | None = None, score_threshold: int = 70) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    seen: set[tuple[str, str]] = set()
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for row in reader:
        email = (row.get("email") or "").strip().lower()
        website = (row.get("website_url") or row.get("url") or "").strip()
        domain = (row.get("domain") or urlparse(website).netloc or website).lower().replace("www.", "")
        lead_niche = (row.get("niche") or niche or "").strip().lower()
        key = (domain, email)
        if not domain or key in seen or lead_niche in EXCLUDED_NICHES:
            rejected += 1
            continue
        seen.add(key)
        accepted.append({"email": email, "domain": domain, "website_url": website, "niche": lead_niche, "score": int(row.get("score") or score_threshold)})
    preview = accepted[:20]
    batch = execute(
        """
        INSERT INTO lead_batches(name, source, status, total_rows, accepted_rows, rejected_rows, country, niche, score_threshold, preview_json)
        VALUES (%s, 'csv', 'dry_run_imported', %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, status, total_rows, accepted_rows, rejected_rows, preview_json
        """,
        (name, len(accepted) + rejected, len(accepted), rejected, country, niche, score_threshold, Jsonb(preview)),
    )
    with connect_dict() as conn:
        with conn.cursor() as cur:
            for item in accepted:
                cur.execute(
                    """
                    INSERT INTO businesses(name, website_url, domain, email, country, niche, source, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'lead_batch_dry_run', 'imported')
                    RETURNING id
                    """,
                    (item["domain"], item["website_url"], item["domain"], item["email"] or None, country, item["niche"]),
                )
                business_id = cur.fetchone()["id"]
                cur.execute(
                    """
                    INSERT INTO leads(business_id, email, source, status, score, country, niche)
                    VALUES (%s, %s, 'lead_batch_dry_run', 'dry_run', %s, %s, %s)
                    """,
                    (business_id, item["email"] or None, item["score"], country, item["niche"]),
                )
        conn.commit()
    return dict(batch)
