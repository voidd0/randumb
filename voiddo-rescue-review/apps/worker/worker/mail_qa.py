from __future__ import annotations

import imaplib
import os
import smtplib
import ssl
from typing import Any

import dns.resolver
from psycopg.types.json import Jsonb

from .db import connect
from .inbox_engine import classify


AGENTS = {
    "dns_mail_auth_agent",
    "smtp_agent",
    "imap_agent",
    "deliverability_agent",
    "reply_classifier_agent",
    "outreach_safety_agent",
}


def _dig(record_type: str, name: str) -> str:
    try:
        answers = dns.resolver.resolve(name, record_type, lifetime=15)
        return "\n".join(str(answer).strip() for answer in answers)
    except Exception as exc:
        return f"ERROR:{type(exc).__name__}"


def _record(agent: str, decision: str, checks: dict[str, Any], issues: list[str]) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mail_qa_runs(agent, status, decision, checks_json, issues_json)
                VALUES (%s, 'completed', %s, %s, %s)
                RETURNING id, agent, decision, checks_json, issues_json
                """,
                (agent, decision, Jsonb(checks), Jsonb(issues)),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row)


def run_agent(agent: str) -> dict[str, Any]:
    if agent == "dns_mail_auth_agent":
        checks = {
            "a_mail": _dig("A", "mail.voiddorescue.com"),
            "mx": _dig("MX", "voiddorescue.com"),
            "spf": _dig("TXT", "voiddorescue.com"),
            "dkim": _dig("TXT", "dkim._domainkey.voiddorescue.com"),
            "dmarc": _dig("TXT", "_dmarc.voiddorescue.com"),
            "autoconfig": _dig("CNAME", "autoconfig.voiddorescue.com"),
            "autodiscover": _dig("CNAME", "autodiscover.voiddorescue.com"),
        }
        issues = []
        if "v=DKIM1" not in checks["dkim"]:
            issues.append("missing_dkim")
        if "TTL: Automatic" in checks["dmarc"]:
            issues.append("dmarc_contains_literal_ttl")
        if "v=DMARC1" not in checks["dmarc"]:
            issues.append("missing_dmarc")
        return _record(agent, "PASS" if not issues else "FAIL_BLOCK_LAUNCH", checks, issues)

    if agent == "smtp_agent":
        checks = {"host": os.environ.get("SMTP_HOST", ""), "port": os.environ.get("SMTP_PORT", "587")}
        issues = []
        try:
            with smtplib.SMTP(checks["host"], int(checks["port"]), timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(os.environ.get("SMTP_USERNAME", ""), os.environ.get("SMTP_PASSWORD", ""))
            checks["strict_tls_login"] = "ok"
        except Exception as exc:
            checks["strict_tls_login"] = f"fail:{type(exc).__name__}"
            issues.append("smtp_strict_tls_login_failed")
        return _record(agent, "PASS" if not issues else "FAIL_BLOCK_LAUNCH", checks, issues)

    if agent == "imap_agent":
        checks = {"host": os.environ.get("IMAP_HOST", ""), "port": os.environ.get("IMAP_PORT", "993")}
        issues = []
        try:
            with imaplib.IMAP4_SSL(checks["host"], int(checks["port"]), ssl_context=ssl.create_default_context(), timeout=20) as imap:
                imap.login(os.environ.get("IMAP_USERNAME_AUDIT", ""), os.environ.get("IMAP_PASSWORD_AUDIT", ""))
                imap.select("INBOX", readonly=True)
                imap.logout()
            checks["strict_tls_login"] = "ok"
        except Exception as exc:
            checks["strict_tls_login"] = f"fail:{type(exc).__name__}"
            issues.append("imap_strict_tls_login_failed")
        return _record(agent, "PASS" if not issues else "FAIL_BLOCK_LAUNCH", checks, issues)

    if agent == "deliverability_agent":
        return _record(agent, "FAIL_BLOCK_LAUNCH", {"mode": "approved_test_inboxes_only", "sent": 0}, ["approved_test_recipient_pool_missing"])

    if agent == "reply_classifier_agent":
        samples = {
            "unsubscribe": classify("remove me", "unsubscribe")[0],
            "price": classify("pricing", "how much does it cost?")[0],
            "security": classify("scan", "unauthorized security scan")[0],
        }
        return _record(agent, "PASS", samples, [])

    if agent == "outreach_safety_agent":
        checks = {
            "outreach_dry_run": os.environ.get("OUTREACH_DRY_RUN", "true"),
            "outreach_paused": os.environ.get("OUTREACH_PAUSED", "true"),
            "first_live_send_flag": os.environ.get("FIRST_LIVE_SEND_FLAG", "false"),
        }
        issues = [] if checks["outreach_dry_run"].lower() == "true" and checks["first_live_send_flag"].lower() != "true" else ["live_send_gate_not_safe"]
        return _record(agent, "PASS" if not issues else "FAIL_BLOCK_LAUNCH", checks, issues)

    raise ValueError(f"unknown mail QA agent: {agent}")
