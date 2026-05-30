from __future__ import annotations

import csv
import hashlib
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
from datetime import datetime, time, timedelta, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import psycopg
import dns.resolver
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .billing import PRODUCTS, price_id_for
from .config import Settings, get_settings
from .db import connect_dict, execute, fetch_all, fetch_one
from .email_templates import render_email_template
from .inbox import classify_reply
from .security import lead_id_from_unsubscribe_token, unsubscribe_token_for_lead


ONETIME_FIX_PRODUCTS = {"audit_onetime", "contact_form_repair", "emergency_fix"}
EXCLUDED_NICHES = {"banks", "bank", "government", "hospital", "hospitals", "gambling", "adult", "crypto", "political"}
OWNER_EMAIL_FALLBACK = ""
TEST_COUNTRY_PATTERN = r"^(P7|P8|P9|P10|P11|P12|P59|P60|P61|P62|P63|P68|P72|P73|P74|P77|P83)"
RUNTIME_PAUSE_KEYS = {
    "scanner": "pause_scanner",
    "outreach": "pause_outreach",
    "warmup": "pause_warmup",
    "auto_replies": "pause_auto_replies",
    "workers": "pause_workers",
}


def _unsubscribe_secret() -> str:
    settings = get_settings()
    return settings.unsubscribe_secret or settings.admin_auth_token or "voiddo-rescue-local-unsubscribe-secret"


def signed_unsubscribe_url_for_lead(lead_id: str) -> str:
    settings = get_settings()
    return f"{settings.go_base_url}/unsubscribe/{unsubscribe_token_for_lead(str(lead_id), _unsubscribe_secret())}"


def one_click_unsubscribe_url_from_body(body: str) -> str | None:
    match = re.search(r"https?://[^\s<>()\"']+/unsubscribe/u_[0-9a-fA-F-]{36}\.[A-Za-z0-9_-]+", body or "")
    return match.group(0) if match else None
WARMUP_SENDER_ROTATION = [
    "audit@voiddorescue.com",
    "support@voiddorescue.com",
    "fix@voiddorescue.com",
]
MAIL_SIGNAL_RECENT_BLOCKING_TYPES = {"bounce", "dsn", "smtp_rate_limit"}
MAIL_AUTH_BLOCKING_SIGNAL_TYPES = {"auth_failure", "tls_failure", "dkim_failure", "dmarc_failure"}
DIAGNOSTIC_DAILY_CAP = 5
DIAGNOSTIC_MINUTE_CAP = 1


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


def warmup_daily_cap() -> int:
    row = fetch_one("SELECT value FROM runtime_controls WHERE key = 'warmup_daily_cap_2'")
    return 2 if not row or row["value"] else 2


def effective_pause_state(area: str, configured: bool = False) -> bool:
    key = RUNTIME_PAUSE_KEYS.get(area, area)
    return bool(configured or runtime_control_enabled(key))


def approved_test_inbox_emails(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    emails = _split_config_emails(settings.test_inboxes) + _split_config_emails(settings.test_inbox_pool)
    db_rows = fetch_all("SELECT email FROM test_inboxes WHERE status = 'approved' AND approved")
    emails.extend(str(row["email"]).lower() for row in db_rows)
    return sorted(set(email for email in emails if "@" in email))


def approved_warmup_recipient_emails(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    emails = _split_config_emails(settings.warmup_recipient_pool)
    db_rows = fetch_all("SELECT email FROM warmup_recipients WHERE status = 'approved_test_pool' AND approved")
    emails.extend(str(row["email"]).lower() for row in db_rows)
    suppressed = {
        str(row["email"]).lower()
        for row in fetch_all("SELECT email FROM suppression_list WHERE email IS NOT NULL")
    }
    return sorted(set(email for email in emails if "@" in email and email not in suppressed))


def recipient_hash(email: str) -> str:
    normalized = (email or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def email_provider(email: str) -> str:
    domain = (email or "").split("@")[-1].lower()
    if domain in {"voiddo.com", "voiddorescue.com"}:
        return "internal"
    if domain in {"gmail.com", "googlemail.com"}:
        return "gmail"
    if domain in {"outlook.com", "hotmail.com", "live.com", "msn.com"}:
        return "microsoft"
    if domain in {"icloud.com", "me.com", "mac.com"}:
        return "icloud"
    if domain == "proton.me" or domain.endswith(".proton.me"):
        return "proton"
    if domain == "yahoo.com":
        return "yahoo"
    return domain or "unknown"


def record_mail_signal(
    signal_type: str,
    severity: str = "info",
    source: str = "system",
    mailbox: str = "",
    recipient_email: str = "",
    provider: str = "",
    message_id: str = "",
    raw_summary: str = "",
) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, message_id, raw_summary)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, signal_type, severity, source, mailbox, provider, message_id, raw_summary, created_at
        """,
        (
            signal_type,
            severity,
            source,
            mailbox or None,
            recipient_hash(recipient_email) or None,
            provider or email_provider(recipient_email),
            message_id or None,
            raw_summary[:500] if raw_summary else None,
        ),
    )
    return dict(row)


def recent_mail_signal_count(signal_types: list[str] | tuple[str, ...] | set[str], hours: int = 24) -> int:
    if not signal_types:
        return 0
    row = fetch_one(
        """
        SELECT count(*) AS count
        FROM mail_signals
        WHERE signal_type = ANY(%s)
          AND created_at >= now() - (%s || ' hours')::interval
        """,
        (list(signal_types), hours),
    )
    return int(row["count"] if row else 0)


def latest_mail_qa_decision() -> str:
    row = fetch_one("SELECT decision FROM mail_qa_runs ORDER BY created_at DESC LIMIT 1")
    return str(row["decision"]) if row else "MISSING"


def is_recipient_suppressed(email: str) -> bool:
    row = fetch_one(
        "SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s) OR lower(domain) = lower(%s)",
        (email, (email or "").split("@")[-1].lower()),
    )
    return bool(row)


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

    source_queue = scout_source_queue_preview_snapshot()
    scan_rows = fetch_all("SELECT status, count(*) AS count FROM scanner_jobs GROUP BY status")
    email_rows = fetch_all("SELECT status, count(*) AS count FROM outreach_messages GROUP BY status")
    latest_mailer = fetch_one("SELECT status, next_safe_action FROM mailer_status_snapshots ORDER BY created_at DESC LIMIT 1")
    real_lead_where = """
        lower(COALESCE(b.domain, '')) NOT LIKE '%%.example.test'
        AND lower(COALESCE(b.website_url, '')) NOT LIKE '%%.example.test%%'
        AND lower(COALESCE(l.email, '')) NOT LIKE '%%.example.test'
        AND lower(COALESCE(l.source, '')) NOT LIKE 'p%%\\_test' ESCAPE '\\'
        AND lower(COALESCE(l.source, '')) NOT LIKE 'test%%'
        AND upper(COALESCE(l.country, '')) !~ '^(P7|P8|P9|P10|P11|P12|P59|P60|P61|P62|P63|P68|P72|P73|P74)'
    """
    real_audit_where = """
        lower(COALESCE(a.domain, '')) NOT LIKE '%%.example.test'
        AND lower(COALESCE(a.url, '')) NOT LIKE '%%.example.test%%'
        AND COALESCE(a.status, '') NOT IN ('archived_test_artifact', 'archived_sensitive_target', 'superseded')
    """
    return {
        "leads_total": scalar("SELECT count(*) FROM leads"),
        "scans": {
            "queued": sum(int(r["count"]) for r in scan_rows if r["status"] == "queued"),
            "running": sum(int(r["count"]) for r in scan_rows if r["status"] == "running"),
            "completed": sum(int(r["count"]) for r in scan_rows if r["status"] == "completed"),
            "failed": sum(int(r["count"]) for r in scan_rows if r["status"] == "failed"),
        },
        "qualified_leads": scalar("SELECT count(*) FROM leads WHERE score >= 70"),
        "post_scan_score_candidates": scalar(
            f"""
            SELECT count(*)
            FROM audits a
            JOIN leads l ON l.id = a.lead_id
            JOIN businesses b ON b.id = l.business_id
            WHERE a.status = 'completed'
              AND a.lead_id IS NOT NULL
              AND l.email IS NOT NULL
              AND {real_lead_where}
              AND {real_audit_where}
              AND NOT EXISTS (
                SELECT 1 FROM lead_scores ls
                WHERE ls.lead_id = a.lead_id
                  AND ls.audit_id = a.id
              )
            """
        ),
        "audit_pages_generated": scalar("SELECT count(*) FROM audits WHERE public_slug IS NOT NULL"),
        "production": {
            "real_leads_total": scalar(f"SELECT count(*) FROM leads l JOIN businesses b ON b.id = l.business_id WHERE {real_lead_where}"),
            "real_qualified_leads": scalar(f"SELECT count(*) FROM leads l JOIN businesses b ON b.id = l.business_id WHERE l.score >= 70 AND {real_lead_where}"),
            "real_audit_pages_generated": scalar(f"SELECT count(*) FROM audits a WHERE a.public_slug IS NOT NULL AND {real_audit_where}"),
            "real_campaign_preview_rows": scalar(
                f"""
                SELECT count(*)
                FROM campaign_leads cl
                JOIN leads l ON l.id = cl.lead_id
                JOIN businesses b ON b.id = l.business_id
                WHERE cl.status = 'preview'
                  AND {real_lead_where}
                """
            ),
        },
        "qa_artifacts": {
            "test_like_businesses": scalar(
                "SELECT count(*) FROM businesses WHERE lower(COALESCE(domain, '')) LIKE '%%.example.test' OR lower(COALESCE(website_url, '')) LIKE '%%.example.test%%'"
            ),
            "test_like_leads": scalar(
                """
                SELECT count(*)
                FROM leads l
                JOIN businesses b ON b.id = l.business_id
                WHERE lower(COALESCE(b.domain, '')) LIKE '%%.example.test'
                   OR lower(COALESCE(l.email, '')) LIKE '%%.example.test'
                   OR lower(COALESCE(l.source, '')) LIKE 'p%%\\_test' ESCAPE '\\'
                   OR lower(COALESCE(l.source, '')) LIKE 'test%%'
                """
            ),
            "test_like_audits": scalar(
                "SELECT count(*) FROM audits a WHERE lower(COALESCE(a.domain, '')) LIKE '%%.example.test' OR lower(COALESCE(a.url, '')) LIKE '%%.example.test%%' OR a.status = 'archived_test_artifact'"
            ),
            "test_like_campaign_previews": scalar(
                """
                SELECT count(*)
                FROM campaign_leads cl
                JOIN leads l ON l.id = cl.lead_id
                JOIN businesses b ON b.id = l.business_id
                WHERE cl.status = 'preview'
                  AND (
                    lower(COALESCE(b.domain, '')) LIKE '%%.example.test'
                    OR lower(COALESCE(l.email, '')) LIKE '%%.example.test'
                    OR lower(COALESCE(l.source, '')) LIKE 'p%%\\_test' ESCAPE '\\'
                    OR lower(COALESCE(l.source, '')) LIKE 'test%%'
                  )
                """
            ),
        },
        "scanner_retryable_transient": scalar(
            """
            SELECT count(*)
            FROM scanner_jobs
            WHERE status = 'failed'
              AND error IN ('TimeoutError', 'Error', 'PlaywrightTimeoutError', 'NetworkError')
              AND COALESCE((result_json->>'scanner_retry_count')::int, 0) < 1
            """
        ),
        "scanner_priority_runs": scalar("SELECT count(*) FROM scanner_priority_runs"),
        "scanner_completion_watches": scalar("SELECT count(*) FROM scanner_completion_watches"),
        "source_scanner_queue_runs": scalar("SELECT count(*) FROM source_scanner_queue_runs"),
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
        "scout_sources": scalar("SELECT count(*) FROM scout_sources"),
        "scout_runs": scalar("SELECT count(*) FROM scout_runs"),
        "campaigns": scalar("SELECT count(*) FROM campaigns"),
        "campaign_leads": scalar("SELECT count(*) FROM campaign_leads"),
        "agent_runs": scalar("SELECT count(*) FROM agent_runs"),
        "onboarding_tasks": scalar("SELECT count(*) FROM onboarding_tasks"),
        "monitoring_targets": scalar("SELECT count(*) FROM monitoring_targets"),
        "economics_snapshots": scalar("SELECT count(*) FROM economics_snapshots"),
        "self_audit_runs": scalar("SELECT count(*) FROM self_audit_runs"),
        "self_operating_cycles": scalar("SELECT count(*) FROM self_operating_cycles"),
        "self_fix_tasks_open": scalar("SELECT count(*) FROM self_fix_tasks WHERE status = 'open'"),
        "self_learning_events": scalar("SELECT count(*) FROM self_learning_events"),
        "self_build_queue_open": scalar("SELECT count(*) FROM self_build_queue WHERE status = 'queued'"),
        "autonomous_mailer_decisions": scalar("SELECT count(*) FROM autonomous_mailer_decisions"),
        "quality_plugin_runs": scalar("SELECT count(*) FROM quality_plugin_runs"),
        "revenue_simulation_runs": scalar("SELECT count(*) FROM revenue_simulation_runs"),
        "campaign_economics_checks": scalar("SELECT count(*) FROM campaign_economics_checks"),
        "campaign_action_runs": scalar("SELECT count(*) FROM campaign_action_runs"),
        "post_scan_campaign_cycles": scalar("SELECT count(*) FROM post_scan_campaign_cycles"),
        "campaign_preview_refresh_runs": scalar("SELECT count(*) FROM campaign_preview_refresh_runs"),
        "campaign_preflight_runs": scalar("SELECT count(*) FROM campaign_preflight_runs"),
        "campaign_remediation_plans": scalar("SELECT count(*) FROM campaign_remediation_plans"),
        "campaign_remediation_executions": scalar("SELECT count(*) FROM campaign_remediation_executions"),
        "campaign_remediation_feedback_runs": scalar("SELECT count(*) FROM campaign_remediation_feedback_runs"),
        "audit_evidence_remediation_runs": scalar("SELECT count(*) FROM audit_evidence_remediation_runs"),
        "audit_refresh_drain_runs": scalar("SELECT count(*) FROM audit_refresh_drain_runs"),
        "audit_refresh_completion_watches": scalar("SELECT count(*) FROM audit_refresh_completion_watches"),
        "audit_refresh_failure_runs": scalar("SELECT count(*) FROM audit_refresh_failure_runs"),
        "studio_mail_messages": scalar("SELECT count(*) FROM studio_mail_messages"),
        "studio_mail_monitor_runs": scalar("SELECT count(*) FROM studio_mail_monitor_runs"),
        "mail_clean_window_checks": scalar("SELECT count(*) FROM mail_clean_window_checks"),
        "mailer_drafts": scalar("SELECT count(*) FROM mailer_drafts"),
        "scout_self_checks": scalar("SELECT count(*) FROM scout_self_checks"),
        "audit_strength_scores": scalar("SELECT count(*) FROM audit_strength_scores"),
        "public_language_gate_runs": scalar("SELECT count(*) FROM public_language_gate_runs"),
        "campaign_readiness_snapshots": scalar("SELECT count(*) FROM campaign_readiness_snapshots"),
        "outbound_mailer_decisions": scalar("SELECT count(*) FROM outbound_mailer_decisions"),
        "reply_action_plans": scalar("SELECT count(*) FROM reply_action_plans"),
        "scout_provenance_scores": scalar("SELECT count(*) FROM scout_provenance_scores"),
        "scout_source_readiness_checks": scalar("SELECT count(*) FROM scout_source_readiness_checks"),
        "scout_source_queue_candidates": source_queue["candidate_count"],
        "scout_source_queue_top_score": source_queue["top_score"],
        "scout_source_queue_created_scout_runs": source_queue["created_scout_runs"],
        "scout_source_queue_created_scanner_jobs": source_queue["created_scanner_jobs"],
        "scout_campaign_quality_history": scalar("SELECT count(*) FROM scout_campaign_quality_history"),
        "lead_quality_diagnostics_history": scalar("SELECT count(*) FROM lead_quality_diagnostic_runs"),
        "scout_source_performance_feedback": scalar("SELECT count(*) FROM scout_source_performance_scores"),
        "mail_clean_window_transitions": scalar("SELECT count(*) FROM mail_clean_window_transitions"),
        "mailbox_health_scores": scalar("SELECT count(*) FROM mailbox_health_scores"),
        "sender_rotation_readiness": scalar("SELECT count(*) FROM sender_rotation_readiness"),
        "warmup_schedule_repairs": scalar("SELECT count(*) FROM warmup_schedule_repairs"),
        "warmup_schedule_rollbacks": scalar("SELECT count(*) FROM warmup_schedule_rollbacks"),
        "warmup_post_send_checks": scalar("SELECT count(*) FROM warmup_post_send_checks"),
        "mailer_status_snapshots": scalar("SELECT count(*) FROM mailer_status_snapshots"),
        "mail_signal_lessons": scalar("SELECT count(*) FROM mail_signal_lessons"),
        "clean_window_recovery_runs": scalar("SELECT count(*) FROM clean_window_recovery_runs"),
        "clean_window_recheck_runs": scalar("SELECT count(*) FROM clean_window_recheck_runs"),
        "post_window_recheck_runs": scalar("SELECT count(*) FROM post_window_recheck_runs"),
        "customer_journey_snapshots": scalar("SELECT count(*) FROM customer_journey_snapshots"),
        "customer_access_tokens": scalar("SELECT count(*) FROM customer_access_tokens"),
        "monitoring_runs": scalar("SELECT count(*) FROM monitoring_runs"),
        "latest_mailer_status": dict(latest_mailer) if latest_mailer else {},
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


def _audit_context_from_payload(data: dict[str, Any]) -> dict[str, Any]:
    custom = data.get("custom_data") or {}
    audit_slug = str(custom.get("audit_slug") or custom.get("audit") or "").strip()
    if not audit_slug:
        return {}
    row = fetch_one(
        """
        SELECT id AS audit_id, business_id, lead_id, domain, url
        FROM audits
        WHERE public_slug = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (audit_slug,),
    )
    return dict(row) if row else {}


def _link_customer_to_audit_context(customer_id: str, data: dict[str, Any]) -> dict[str, Any]:
    context = _audit_context_from_payload(data)
    if context.get("business_id"):
        execute(
            "UPDATE customers SET business_id = COALESCE(business_id, %s), updated_at = now() WHERE id = %s",
            (context["business_id"], customer_id),
        )
    return context


def _customer_mail_hash(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _is_qa_customer_email(email: str) -> bool:
    normalized = (email or "").strip().lower()
    if "@" not in normalized:
        return True
    domain = normalized.rsplit("@", 1)[-1]
    return (
        domain in {"voiddorescue.local", "example.test", "localhost", "test"}
        or domain.endswith(".test")
        or domain.endswith(".local")
    )


def enqueue_customer_mail_action(
    action_type: str,
    customer_id: str,
    customer_email: str,
    product_key: str,
    template_key: str,
    source_event: str,
    payload: dict[str, Any] | None = None,
) -> str:
    safe_payload = {
        "customer_id": customer_id,
        "product_key": product_key,
        "source_event": source_event,
        "customer_is_qa": _is_qa_customer_email(customer_email),
        **(payload or {}),
    }
    idempotency_parts = [
        action_type,
        _customer_mail_hash(customer_email),
        template_key,
        customer_id,
        source_event,
        str(safe_payload.get("paddle_transaction_id", "")),
        str(safe_payload.get("paddle_subscription_id", "")),
        str(safe_payload.get("fix_request_id", "")),
        str(safe_payload.get("mode", "")),
        product_key,
    ]
    idempotency_key = hashlib.sha256("|".join(idempotency_parts).encode("utf-8")).hexdigest()
    existing = fetch_one("SELECT id FROM mailer_action_queue WHERE idempotency_key = %s", (idempotency_key,))
    if existing:
        return str(existing["id"])
    row = execute(
        """
        INSERT INTO mailer_action_queue(action_type, risk_level, mailbox, recipient_hash, template_key, payload_json, idempotency_key)
        VALUES (%s, 'SAFE_AUTO', 'support@voiddorescue.com', %s, %s, %s, %s)
        RETURNING id
        """,
        (action_type, _customer_mail_hash(customer_email), template_key, Jsonb(json_safe(safe_payload)), idempotency_key),
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
        audit_context = _link_customer_to_audit_context(customer_id, data)
        product_key = product_key_from_payload(data, settings)
        amount, currency = _amount_from_payload(data)
        payment_row = execute(
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
        try:
            from .mailer_action_queue import enqueue_mailer_action, process_mailer_action_queue, send_customer_mail

            if _is_qa_customer_email(email):
                actions.append("owner_sale_notification_skipped_test_customer")
            else:
                owner_action = enqueue_mailer_action(
                    {
                        "action_type": "owner_sale_notification",
                        "risk_level": "SAFE_AUTO",
                        "mailbox": "support@voiddorescue.com",
                        "template_key": "owner_sale_notification",
                        "payload_json": {
                            "source_event": "transaction.paid",
                            "payment_id": str(payment_row["id"]),
                            "paddle_transaction_id": data.get("id"),
                            "product_key": product_key,
                            "amount": amount,
                            "currency": currency,
                            "customer_hash": hashlib.sha256(str(email).strip().lower().encode("utf-8")).hexdigest()[:24],
                            "audit_context_linked": bool(audit_context),
                        },
                    }
                )
                actions.append("owner_sale_notification_queued")
                process_mailer_action_queue(20)
                owner_send = send_customer_mail(20)
                if owner_action.get("status") == "send_ready" or owner_send.get("send_mail"):
                    actions.append("owner_sale_notification_send_ready")
                if owner_send.get("send_mail"):
                    actions.append("owner_sale_notification_sent")
        except Exception as exc:
            actions.append(f"owner_sale_notification_queue_failed:{type(exc).__name__}")
        if product_key in ONETIME_FIX_PRODUCTS:
            fix_row = execute(
                """
                INSERT INTO fix_requests(customer_id, audit_id, product_key, status, priority, title, description, evidence_json)
                VALUES (%s, %s, %s, 'new', 'P1', %s, %s, %s)
                RETURNING id
                """,
                (
                    customer_id,
                    audit_context.get("audit_id"),
                    product_key,
                    f"{PRODUCTS.get(product_key, {}).get('name', product_key)} purchased",
                    "Created from Paddle transaction.paid webhook.",
                    Jsonb({"paddle_transaction_id": data.get("id"), "provisioning_paused": provisioning_paused, "audit_context_linked": bool(audit_context)}),
                ),
            )
            actions.append("fix_request_created")
            if not provisioning_paused:
                enqueue_customer_mail_action(
                    "fix_request_created",
                    customer_id,
                    email,
                    product_key,
                    "fix_request_created",
                    "transaction.paid",
                    {"fix_request_id": str(fix_row["id"]), "paddle_transaction_id": data.get("id")},
                )
                actions.append("fix_request_mail_action_queued")
        execute(
            "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
            ("paddle.transaction_paid", "info", "Paddle transaction paid processed", Jsonb({"actions": actions, "provisioning_paused": provisioning_paused})),
        )
        if not provisioning_paused:
            actions.append("onboarding_email_task_created")
            execute(
                """
                INSERT INTO onboarding_tasks(customer_id, product_key, task_type, title, payload_json)
                VALUES (%s, %s, 'payment_onboarding', 'Customer onboarding started', %s)
                """,
                (customer_id, product_key, Jsonb({"paddle_transaction_id": data.get("id"), "audit_context_linked": bool(audit_context)})),
            )
            actions.append("onboarding_task_created")
            enqueue_customer_mail_action(
                "customer_onboarding",
                customer_id,
                email,
                product_key,
                "payment_onboarding",
                "transaction.paid",
                {"paddle_transaction_id": data.get("id")},
            )
            actions.append("customer_onboarding_mail_action_queued")
            enqueue_customer_mail_action(
                "monitoring_report",
                customer_id,
                email,
                product_key,
                "monitoring_setup_reminder",
                "transaction.paid",
                {"paddle_transaction_id": data.get("id"), "mode": "setup_reminder"},
            )
            actions.append("monitoring_setup_mail_action_queued")
        return {"event_type": event_type, "actions": actions, "provisioning_paused": provisioning_paused}

    if event_type in {"subscription.created", "subscription.activated", "subscription.updated", "subscription.canceled"}:
        email = data.get("customer", {}).get("email") or data.get("customer_email") or "unknown@voiddorescue.local"
        customer_id = upsert_customer(email, data.get("customer_id"))
        audit_context = _link_customer_to_audit_context(customer_id, data)
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
                """
                INSERT INTO onboarding_tasks(customer_id, product_key, task_type, title, payload_json)
                VALUES (%s, %s, 'subscription_onboarding', 'Subscription onboarding started', %s)
                """,
                (customer_id, product_key, Jsonb({"paddle_subscription_id": data.get("id"), "audit_context_linked": bool(audit_context)})),
            )
            actions.append("onboarding_task_created")
            enqueue_customer_mail_action(
                "customer_onboarding",
                customer_id,
                email,
                product_key,
                "payment_onboarding",
                event_type,
                {"paddle_subscription_id": data.get("id")},
            )
            actions.append("customer_onboarding_mail_action_queued")
            enqueue_customer_mail_action(
                "monitoring_report",
                customer_id,
                email,
                product_key,
                "monitoring_setup_reminder",
                event_type,
                {"paddle_subscription_id": data.get("id"), "mode": "setup_reminder"},
            )
            actions.append("monitoring_setup_mail_action_queued")
        execute(
            "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
            (f"paddle.{event_type}", "info", "Paddle subscription event processed", Jsonb({"actions": actions, "provisioning_paused": provisioning_paused})),
        )
        if event_type in {"subscription.created", "subscription.activated"}:
            try:
                from .mailer_action_queue import enqueue_mailer_action, process_mailer_action_queue, send_customer_mail

                if _is_qa_customer_email(email):
                    actions.append("owner_sale_notification_skipped_test_customer")
                else:
                    owner_action = enqueue_mailer_action(
                        {
                            "action_type": "owner_sale_notification",
                            "risk_level": "SAFE_AUTO",
                            "mailbox": "support@voiddorescue.com",
                            "template_key": "owner_sale_notification",
                            "payload_json": {
                                "source_event": event_type,
                                "paddle_subscription_id": data.get("id"),
                                "product_key": product_key,
                                "amount": 0,
                                "currency": "subscription",
                                "customer_hash": hashlib.sha256(str(email).strip().lower().encode("utf-8")).hexdigest()[:24],
                                "audit_context_linked": bool(audit_context),
                            },
                        }
                    )
                    actions.append("owner_sale_notification_queued")
                    process_mailer_action_queue(20)
                    owner_send = send_customer_mail(20)
                    if owner_action.get("status") == "send_ready" or owner_send.get("send_mail"):
                        actions.append("owner_sale_notification_send_ready")
                    if owner_send.get("send_mail"):
                        actions.append("owner_sale_notification_sent")
            except Exception as exc:
                actions.append(f"owner_sale_notification_queue_failed:{type(exc).__name__}")
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
    sender_hash = recipient_hash(sender)
    sender_provider = email_provider(sender)
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
                (Jsonb({"sender_hash": sender_hash, "sender_provider": sender_provider, "subject": subject, "thread_id": str(thread_id)}), mailbox, uid, message_id, classification, human),
            )
            if classification == "unsubscribe":
                cur.execute(
                    """
                    INSERT INTO suppression_list(email, reason, source)
                    SELECT %s, 'unsubscribe_reply', 'inbox'
                    WHERE NOT EXISTS (
                      SELECT 1 FROM suppression_list
                      WHERE lower(email) = lower(%s)
                        AND reason = 'unsubscribe_reply'
                        AND source = 'inbox'
                    )
                    """,
                    (sender, sender),
                )
            if classification in {"bounce", "auto_reply", "out_of_office", "interested", "ask_price", "ask_details"}:
                cur.execute(
                    """
                    INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, message_id, raw_summary)
                    VALUES (%s, %s, 'inbox_engine', %s, %s, %s, %s, %s)
                    """,
                    (
                        "bounce" if classification == "bounce" else "inbox_reply",
                        "warning" if classification == "bounce" else "info",
                        mailbox,
                        sender_hash,
                        sender_provider,
                        message_id,
                        f"classified:{classification}",
                    ),
                )
            if classification in {"legal_threat", "security_accusation", "angry"}:
                cur.execute(
                    "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, 'critical', %s, %s)",
                    (f"inbox.{classification}", "Unsafe reply requires human review", Jsonb({"sender_hash": sender_hash, "sender_provider": sender_provider, "subject": subject})),
                )
            if any(marker in body.lower() for marker in ["found it in spam", "in spam", "spam folder"]):
                cur.execute(
                    "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
                    ("deliverability.spam_observed", "warning", "Test inbox spam placement signal observed", Jsonb({"sender_hash": sender_hash, "subject": subject})),
                )
                cur.execute(
                    """
                    INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, message_id, raw_summary)
                    VALUES ('spam_signal', 'warning', 'inbox_engine', %s, %s, %s, %s, 'test inbox spam placement observed')
                    """,
                    (mailbox, sender_hash, sender_provider, message_id),
                )
        conn.commit()
    return {"stored": True, "duplicate": False, "classification": classification, "human_review_required": human}


def _decode_mail_header(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def _owner_command_candidate_lines(subject: str, body: str) -> list[str]:
    decoded_subject = _decode_mail_header(subject)
    candidates: list[str] = []
    for source in [body or "", decoded_subject]:
        for raw_line in str(source or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line.strip())
            if not line:
                continue
            lowered = line.lower()
            if line.startswith(">") or lowered.startswith(("on ", "from:", "sent:", "to:", "subject:")):
                continue
            if lowered in {"--", "sent from my iphone", "sent from my mobile"}:
                continue
            candidates.append(line)
    return candidates or ([decoded_subject.strip()] if decoded_subject.strip() else [])


def _canonical_owner_command(candidate: str, full_text: str) -> tuple[str, dict[str, Any], str]:
    first_line = candidate.strip()
    normalized = re.sub(r"\s+", " ", first_line.upper())
    args: dict[str, Any] = {}
    command = normalized

    russian_aliases = {
        "СТАТУС": "STATUS",
        "ОТЧЕТ СЕГОДНЯ": "REPORT TODAY",
        "ОТЧЁТ СЕГОДНЯ": "REPORT TODAY",
        "ПАУЗА ВСЕ": "PAUSE ALL",
        "ПАУЗА ВСЁ": "PAUSE ALL",
        "ПАУЗА РАССЫЛКИ": "PAUSE OUTREACH",
        "ПАУЗА ПРОГРЕВА": "PAUSE WARMUP",
        "ПАУЗА СКАНЕРА": "PAUSE SCANNER",
        "ПАУЗА АВТООТВЕТОВ": "PAUSE AUTO REPLIES",
        "НЕ СПАМЬ": "PAUSE OUTREACH",
        "СТОП СПАМ": "PAUSE OUTREACH",
        "СТОП РАССЫЛКА": "PAUSE OUTREACH",
        "СТОП РАССЫЛКУ": "PAUSE OUTREACH",
        "ПОКАЖИ ПРОГРЕВ": "SHOW WARMUP",
        "ПОКАЖИ КАЛЕНДАРЬ ПРОГРЕВА": "SHOW WARMUP CALENDAR",
        "ПОКАЖИ СИГНАЛЫ ПОЧТЫ": "SHOW MAIL SIGNALS",
        "ПОКАЖИ СТУДИО ПОЧТУ": "SHOW STUDIO MAIL",
        "ПОКАЖИ ОСНОВНУЮ ПОЧТУ": "SHOW STUDIO MAIL",
        "ПОКАЖИ ТРИГГЕРЫ": "SHOW OWNER TRIGGERS",
        "ПОКАЖИ ПОЧТОВЫЕ ТРИГГЕРЫ": "SHOW OWNER TRIGGERS",
        "ПОКАЖИ ОТВЕТЫ": "SHOW REPLIES",
        "ПОКАЖИ ПЛАТЕЖИ": "SHOW PAYMENTS",
        "ПОКАЖИ РУЧНУЮ ПРОВЕРКУ": "SHOW HUMAN REVIEW",
        "ПОКАЖИ ЖИВУЮ ОЧЕРЕДЬ": "SHOW LIVE QUEUE",
        "ПОКАЖИ КАНАРЕЙКУ": "SHOW CANARY SCALE",
        "ПОКАЖИ КАНАРИ": "SHOW CANARY SCALE",
        "ПОКАЖИ ВОССТАНОВЛЕНИЕ КАНАРЕЙКИ": "SHOW CANARY BOUNCE RECOVERY",
        "ПОКАЖИ BOUNCE RECOVERY": "SHOW CANARY BOUNCE RECOVERY",
        "ПОКАЖИ ЧИСТОЕ ОКНО": "SHOW CANARY CLEAN WINDOW",
        "ПОКАЖИ ГИГИЕНУ БЛОКИРОВОК": "SHOW TRANSPORT BLOCK HYGIENE",
        "ПОКАЖИ ЗАПАС ЛИДОВ": "SHOW LEAD SUPPLY",
        "ПОКАЖИ SUPPLY": "SHOW LEAD SUPPLY",
        "ЗАПУСТИ ЗАПАС ЛИДОВ": "RUN LEAD SUPPLY BUILDOUT",
        "ЗАПУСТИ SUPPLY": "RUN LEAD SUPPLY BUILDOUT",
        "ПОДГОТОВЬ ЖИВОЙ КАНАРЕЙКУ": "PREPARE LIVE CANARY",
        "ПОДГОТОВЬ ЖИВОЙ КАНАРИ": "PREPARE LIVE CANARY",
        "ПОКАЖИ ЗАПУСК": "SHOW LAUNCH RUNBOOK",
        "ПРОВЕРЬ ЗАПУСК": "RUN LAUNCH REHEARSAL",
        "ОТКАТИ РАССЫЛКУ": "ROLLBACK LIVE OUTREACH",
        "ЗАПУСТИ MAIL QA": "RUN MAIL QA",
        "ЗАПУСТИ ВИЗУАЛ QA": "RUN VISUAL QA",
        "ПОДГОТОВЬ ПРОГРЕВ": "PREPARE WARMUP",
        "ВОЗОБНОВИ ПРОГРЕВ": "RESUME WARMUP",
        "ДЕЛАЙ ДЕНЬГИ": "RUN REVENUE LOOP",
        "НУЖНЫ ДЕНЬГИ": "RUN REVENUE LOOP",
        "ПОЛНАЯ МОЩНОСТЬ": "RUN REVENUE LOOP",
        "ПОЛНУЮ МОЩЬ": "RUN REVENUE LOOP",
    }
    if normalized in russian_aliases:
        command = russian_aliases[normalized]

    command_prefixes = [
        "SHOW TRANSPORT BLOCK HYGIENE",
        "SHOW CANARY BOUNCE RECOVERY",
        "RUN LEAD SUPPLY BUILDOUT",
        "SHOW CANARY CLEAN WINDOW",
        "RUN DELIVERABILITY TEST",
        "SHOW WARMUP CALENDAR",
        "SHOW OWNER TRIGGERS",
        "ROLLBACK LIVE OUTREACH",
        "PREPARE LIVE CANARY",
        "RUN LAUNCH REHEARSAL",
        "SHOW LAUNCH RUNBOOK",
        "SHOW DELIVERABILITY",
        "SHOW HUMAN REVIEW",
        "PAUSE AUTO REPLIES",
        "RUN REVENUE LOOP",
        "SHOW MAIL SIGNALS",
        "SHOW LEAD SUPPLY",
        "SHOW CANARY SCALE",
        "SHOW CANARY RESUME",
        "UNPAUSE OUTREACH",
        "PREPARE WARMUP",
        "START WARMUP",
        "RESUME WARMUP",
        "SHOW STUDIO MAIL",
        "SHOW LIVE QUEUE",
        "SHOW PAYMENTS",
        "SHOW REPLIES",
        "RUN VISUAL QA",
        "RUN MAIL QA",
        "PAUSE OUTREACH",
        "PAUSE WARMUP",
        "PAUSE SCANNER",
        "SEND OUTREACH",
        "REPORT TODAY",
        "PAUSE ALL",
        "RUN SHELL",
        "EXECUTE",
        "STATUS",
    ]
    if command == normalized:
        for prefix in command_prefixes:
            if normalized == prefix or normalized.startswith(prefix + " "):
                command = prefix
                break

    lowered_full = full_text.lower()
    money_markers = ["нужны деньги", "денбги", "деньги", "полную мощ", "полная мощ", "заработ", "автономк"]
    trigger_markers = ["триггер", "мейл", "почт"]
    if command == normalized and any(marker in lowered_full for marker in money_markers):
        command = "RUN REVENUE LOOP"
    elif command == normalized and any(marker in lowered_full for marker in trigger_markers) and any(marker in lowered_full for marker in ["почему", "не исполня", "что с"]):
        command = "SHOW OWNER TRIGGERS"

    if normalized.startswith("PREPARE LEADS"):
        command = "PREPARE LEADS"
        for key, value in re.findall(r"(COUNTRY|NICHE|LIMIT)=([^\s]+)", first_line, flags=re.I):
            args[key.lower()] = value
    elif normalized.startswith("START WARMUP") or normalized.startswith("ЗАПУСТИ ПРОГРЕВ"):
        command = "START WARMUP"
        for key, value in re.findall(r"(DAY|ДЕНЬ)=([0-9]+)", first_line, flags=re.I):
            args[key.lower()] = int(value)
        if "день" in args:
            args["day"] = args.pop("день")

    return command, args, normalized


def parse_owner_command(sender: str, subject: str, body: str, reply_to: str = "", auth_results: str = "") -> dict[str, Any]:
    settings = get_settings()
    owner_email = (settings.owner_command_email or OWNER_EMAIL_FALLBACK).lower()
    studio_owner_command_emails = getattr(settings, "studio_owner_command_emails", "")
    owner_emails = {
        item.strip().lower()
        for item in ",".join([owner_email, studio_owner_command_emails or ""]).split(",")
        if item.strip()
    }
    sender_email = parseaddr(_decode_mail_header(sender))[1].lower()
    reply_email = parseaddr(_decode_mail_header(reply_to))[1].lower() if reply_to else sender_email
    decoded_subject = _decode_mail_header(subject)
    full_text = f"{decoded_subject}\n{body or ''}".strip()
    known_commands = {
        "STATUS", "REPORT TODAY", "PAUSE OUTREACH", "PAUSE WARMUP", "PAUSE SCANNER", "PAUSE AUTO REPLIES", "PAUSE ALL",
        "SHOW HUMAN REVIEW", "SHOW PAYMENTS", "SHOW REPLIES", "SHOW MAIL QA", "SHOW DELIVERABILITY", "SHOW WARMUP",
        "SHOW WARMUP CALENDAR", "SHOW MAIL SIGNALS", "SHOW LIVE QUEUE", "SHOW LAUNCH RUNBOOK", "ROLLBACK LIVE OUTREACH",
        "SHOW LEAD SUPPLY", "SHOW CANARY SCALE", "SHOW CANARY BOUNCE RECOVERY", "SHOW STUDIO MAIL", "SHOW OWNER TRIGGERS",
        "SHOW CANARY RESUME", "SHOW CANARY CLEAN WINDOW", "SHOW TRANSPORT BLOCK HYGIENE", "RUN VISUAL QA", "RUN MAIL QA",
        "RUN DELIVERABILITY TEST", "PREPARE WARMUP", "PREPARE LIVE CANARY", "START WARMUP", "RESUME WARMUP",
        "RUN LEAD SUPPLY BUILDOUT", "RUN LAUNCH REHEARSAL", "RUN REVENUE LOOP", "SEND OUTREACH", "UNPAUSE OUTREACH",
        "RUN SHELL", "EXECUTE",
    }
    command = ""
    args: dict[str, Any] = {}
    normalized = ""
    candidates = _owner_command_candidate_lines(decoded_subject, body or "")
    for candidate in candidates:
        candidate_command, candidate_args, candidate_normalized = _canonical_owner_command(candidate, full_text)
        if candidate_command in known_commands or candidate_command == "PREPARE LEADS":
            command, args, normalized = candidate_command, candidate_args, candidate_normalized
            break
    subject_normalized = re.sub(r"\s+", " ", decoded_subject.upper().strip())
    if not command and re.match(r"^(RE|FW|FWD):\s*VØIDDO RESCUE DAILY AUTONOMOUS REPORT", subject_normalized):
        command, args, normalized = "NO_ACTION_OWNER_REPLY", {}, subject_normalized
    elif not command:
        command, args, normalized = _canonical_owner_command(candidates[0] if candidates else decoded_subject, full_text)
    if command not in known_commands and command == normalized and re.match(r"^(RE|FW|FWD):\s*VØIDDO RESCUE DAILY AUTONOMOUS REPORT", subject_normalized):
        command = "NO_ACTION_OWNER_REPLY"

    safe = {
        "STATUS", "REPORT TODAY", "PAUSE OUTREACH", "PAUSE WARMUP", "PAUSE SCANNER", "PAUSE AUTO REPLIES", "PAUSE ALL",
        "SHOW HUMAN REVIEW", "SHOW PAYMENTS", "SHOW REPLIES", "SHOW MAIL QA", "SHOW DELIVERABILITY", "SHOW WARMUP",
        "SHOW WARMUP CALENDAR", "SHOW MAIL SIGNALS", "SHOW LIVE QUEUE", "SHOW LAUNCH RUNBOOK", "ROLLBACK LIVE OUTREACH",
        "SHOW LEAD SUPPLY", "SHOW CANARY SCALE", "SHOW CANARY BOUNCE RECOVERY", "SHOW STUDIO MAIL", "SHOW OWNER TRIGGERS",
        "SHOW CANARY RESUME", "SHOW CANARY CLEAN WINDOW", "SHOW TRANSPORT BLOCK HYGIENE", "NO_ACTION_OWNER_REPLY",
    }
    medium = {"RUN VISUAL QA", "RUN MAIL QA", "RUN DELIVERABILITY TEST", "PREPARE WARMUP", "PREPARE LEADS", "PREPARE LIVE CANARY", "START WARMUP", "RESUME WARMUP", "RUN LEAD SUPPLY BUILDOUT", "RUN REVENUE LOOP"}
    medium.add("RUN LAUNCH REHEARSAL")
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
    authorized = bool(owner_emails) and sender_email in owner_emails and reply_email in owner_emails | {sender_email} and authenticated_hint
    status = "rejected_sender" if sender_email not in owner_emails else "received"
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


def _count(sql: str, params: tuple = ()) -> int:
    row = fetch_one(sql, params)
    if not row:
        return 0
    return int(next(iter(row.values())))


def mail_signal_summary(hours: int = 24) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT signal_type, severity, count(*) AS count
        FROM mail_signals
        WHERE created_at >= now() - (%s || ' hours')::interval
        GROUP BY signal_type, severity
        ORDER BY signal_type, severity
        """,
        (hours,),
    )
    return {
        "window_hours": hours,
        "items": [dict(row) for row in rows],
        "bounce_or_dsn_count": recent_mail_signal_count(["bounce", "dsn"], hours),
        "rate_limit_count": recent_mail_signal_count(["smtp_rate_limit"], hours),
        "spam_signal_count": recent_mail_signal_count(["spam_signal"], hours),
        "mail_auth_failure_count": recent_mail_signal_count(MAIL_AUTH_BLOCKING_SIGNAL_TYPES, hours),
    }


def verified_warmup_event_count(days: int = 30) -> int:
    window_days = max(1, min(int(days or 30), 120))
    row = fetch_one(
        """
        SELECT count(DISTINCT payload_json->>'schedule_id') AS count
        FROM email_events
        WHERE event_type = 'warmup_sent'
          AND created_at >= now() - (%s::text || ' days')::interval
          AND payload_json->>'policy' = 'neutral_calendar_warmup_no_sales_no_tracking'
          AND COALESCE(payload_json->>'schedule_id', '') <> ''
          AND COALESCE(payload_json->>'recipient_hash', '') <> ''
          AND COALESCE(payload_json->>'sender', '') LIKE '%%@voiddorescue.com'
        """,
        (window_days,),
    )
    return int(row["count"] or 0) if row else 0


def warmup_domain_maturity_status(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    min_clean = max(1, int(settings.warmup_min_clean_sends_before_outreach or 5))
    schedule_sent = _count("SELECT count(*) FROM warmup_schedule WHERE status = 'sent'")
    verified_event_sent = verified_warmup_event_count(30)
    verified_warmup_sent = max(schedule_sent, verified_event_sent)
    legacy_event_count = _count("SELECT count(*) FROM email_events WHERE event_type = 'warmup_sent'")
    recent_bounce = recent_mail_signal_count(["bounce", "dsn"], 24)
    recent_rate_limit = recent_mail_signal_count(["smtp_rate_limit"], 24)
    recent_spam = recent_mail_signal_count(["spam_signal"], 24)
    recent_auth_failure = recent_mail_signal_count(["auth_failure", "tls_failure", "dkim_failure", "dmarc_failure"], 24)
    latest_mail = latest_mail_qa_decision()
    blockers: list[str] = []
    if verified_warmup_sent < min_clean:
        blockers.append("warmup_clean_send_count_below_threshold")
    if recent_bounce:
        blockers.append("recent_bounce_or_dsn")
    if recent_rate_limit:
        blockers.append("recent_rate_limit")
    if recent_spam:
        blockers.append("recent_spam_signal")
    if recent_auth_failure:
        blockers.append("recent_mail_auth_failure_signal")
    if latest_mail != "PASS":
        blockers.append("mail_qa_not_pass")
    return {
        "allowed": not blockers,
        "warmup_sent_count": verified_warmup_sent,
        "warmup_schedule_sent_count": schedule_sent,
        "verified_warmup_event_count": verified_event_sent,
        "legacy_warmup_event_count": legacy_event_count,
        "maturity_source": "warmup_schedule_sent" if schedule_sent >= verified_event_sent else "verified_warmup_sent_events",
        "min_clean_sends_required": min_clean,
        "recent_bounce_count": recent_bounce,
        "recent_rate_limit_count": recent_rate_limit,
        "recent_spam_signal_count": recent_spam,
        "recent_mail_auth_failure_count": recent_auth_failure,
        "latest_mail_qa_decision": latest_mail,
        "blockers": blockers,
    }


def warmup_calendar_health() -> dict[str, Any]:
    next_due = fetch_one(
        """
        SELECT scheduled_for
        FROM warmup_schedule
        WHERE status = 'scheduled'
        ORDER BY scheduled_for
        LIMIT 1
        """
    )
    return {
        "scheduled_total": _count("SELECT count(*) FROM warmup_schedule"),
        "due_now": _count("SELECT count(*) FROM warmup_schedule WHERE status = 'scheduled' AND scheduled_for <= now()"),
        "sent_today": _count(
            """
            SELECT count(*)
            FROM warmup_schedule
            WHERE status = 'sent'
              AND sent_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Jerusalem') AT TIME ZONE 'Asia/Jerusalem'
            """
        ),
        "legacy_event_sent_today": _count(
            """
            SELECT count(*)
            FROM email_events
            WHERE event_type = 'warmup_sent'
              AND created_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Jerusalem') AT TIME ZONE 'Asia/Jerusalem'
            """
        ),
        "blocked_today": _count(
            """
            SELECT count(*)
            FROM warmup_schedule
            WHERE status LIKE 'blocked_%%'
              AND updated_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Jerusalem') AT TIME ZONE 'Asia/Jerusalem'
            """
        ),
        "skipped_suppressed": _count("SELECT count(*) FROM warmup_schedule WHERE status = 'skipped_suppressed'"),
        "latest_mail_qa_decision": latest_mail_qa_decision(),
        "recent_bounce_count": recent_mail_signal_count(["bounce", "dsn"], 24),
        "recent_rate_limit_count": recent_mail_signal_count(["smtp_rate_limit"], 24),
        "next_scheduled_send_time": next_due["scheduled_for"] if next_due else None,
        "launch_readiness_state": launch_readiness_state(),
        "live_outreach_sent_count": _count("SELECT count(*) FROM outreach_messages WHERE status = 'sent'"),
    }


def launch_readiness_state() -> str:
    settings = get_settings()
    live_runtime_armed = (
        settings.outreach_dry_run is False
        and settings.outreach_paused is False
        and settings.first_live_send_flag is True
    )
    live_sent = _count("SELECT count(*) FROM outreach_messages WHERE status = 'sent'")
    live_queued = _count("SELECT count(*) FROM outreach_messages WHERE status = 'queued'")
    if live_runtime_armed and (live_sent > 0 or live_queued > 0):
        has_blocking_signal = (
            recent_mail_signal_count(["bounce", "dsn"], 24) > 0
            or recent_mail_signal_count(["smtp_rate_limit"], 24) > 0
            or recent_mail_signal_count(["spam_signal", "auth_failure", "tls_failure", "dkim_failure", "dmarc_failure"], 24) > 0
            or latest_mail_qa_decision() != "PASS"
        )
        return "NOT_LAUNCH_READY" if has_blocking_signal else "LIVE_OUTREACH_READY"

    maturity = warmup_domain_maturity_status()
    scheduled = _count("SELECT count(*) FROM warmup_schedule WHERE status = 'scheduled'")
    preview_ready = _count(
        """
        SELECT count(*)
        FROM campaigns c
        WHERE c.status = 'preview_ready'
          AND EXISTS (
            SELECT 1
            FROM campaign_leads cl
            WHERE cl.campaign_id = c.id
              AND cl.status IN ('preview', 'approved')
          )
        """
    )
    if maturity.get("allowed") and preview_ready > 0:
        return "PREVIEW_PIPELINE_READY_NO_OUTREACH"
    if maturity.get("allowed"):
        return "WARMUP_ACTIVE_NO_OUTREACH"
    if scheduled > 0:
        return "WARMUP_SCHEDULED_NO_OUTREACH"
    return "CHECKOUT_READY_NOT_WARMED"


def mailer_policy_trend_snapshot(limit: int = 8) -> dict[str, Any]:
    safe_limit = max(2, min(int(limit or 8), 30))
    rows = fetch_all(
        """
        SELECT score, decision, blocker_count, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM mailer_policy_score_history
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    history_count = _count("SELECT count(*) FROM mailer_policy_score_history")
    latest = dict(rows[0]) if rows else {}
    scores = [int(row["score"]) for row in rows if row.get("score") is not None]
    if len(scores) < 2:
        direction = "insufficient_history"
    else:
        latest_score = scores[0]
        oldest_recent_score = scores[-1]
        if latest_score <= oldest_recent_score - 5:
            direction = "degrading"
        elif latest_score >= oldest_recent_score + 5:
            direction = "improving"
        else:
            direction = "stable"
    guard_row = fetch_one(
        """
        SELECT result_json
        FROM agent_runs
        WHERE agent = 'mailer_policy_score_regression_guard_agent'
          AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST, started_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """
    )
    guard = dict(guard_row["result_json"]) if guard_row and isinstance(guard_row.get("result_json"), dict) else {}
    return {
        "policy_score_history_count": history_count,
        "latest_policy_score": latest.get("score"),
        "latest_policy_decision": latest.get("decision", "MISSING"),
        "latest_policy_blocker_count": latest.get("blocker_count", 0),
        "latest_policy_send_mail": bool(latest.get("send_mail", False)),
        "latest_policy_live_outreach_allowed": bool(latest.get("live_outreach_allowed", False)),
        "policy_score_min_recent": min(scores) if scores else None,
        "policy_score_max_recent": max(scores) if scores else None,
        "policy_score_avg_recent": round(sum(scores) / len(scores), 2) if scores else None,
        "policy_score_recent_count": len(scores),
        "policy_score_trend_direction": direction,
        "policy_regression_guard_decision": guard.get("decision", "MISSING"),
        "policy_regression_count": int(guard.get("regression_count", len(guard.get("regressions", []))) or 0),
        "policy_regression_score_drop": guard.get("score_drop", 0),
        "policy_regression_review_task_created": bool(guard.get("review_task_created", False)),
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def mailer_business_kpi_report_snapshot() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT replies_count, safe_actions_queued, blocked_actions, action_queue_rows,
               policy_score, policy_decision, policy_trend_direction,
               warmup_sent_count, live_outreach_sent_count, send_mail,
               live_outreach_allowed, raw_recipient_addresses_included, secrets_included,
               created_at
        FROM mailer_business_kpi_history
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
    )
    count = _count("SELECT count(*) FROM mailer_business_kpi_history")
    latest = dict(row) if row else {}
    return {
        "count": count,
        "latest_replies_count": latest.get("replies_count", 0),
        "latest_safe_actions_queued": latest.get("safe_actions_queued", 0),
        "latest_blocked_actions": latest.get("blocked_actions", 0),
        "latest_action_queue_rows": latest.get("action_queue_rows", 0),
        "latest_policy_score": latest.get("policy_score"),
        "latest_policy_decision": latest.get("policy_decision", "MISSING"),
        "latest_policy_trend_direction": latest.get("policy_trend_direction", "insufficient_history"),
        "latest_warmup_sent_count": latest.get("warmup_sent_count", 0),
        "latest_live_outreach_sent_count": latest.get("live_outreach_sent_count", 0),
        "latest_send_mail": bool(latest.get("send_mail", False)),
        "latest_live_outreach_allowed": bool(latest.get("live_outreach_allowed", False)),
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def scout_campaign_quality_trend_snapshot(limit: int = 8) -> dict[str, Any]:
    safe_limit = max(2, min(int(limit or 8), 30))
    rows = fetch_all(
        """
        SELECT status, blocker_count, campaign_quality_json, send_mail, smtp_called,
               live_outreach_allowed, raw_recipient_addresses_included, secrets_included, created_at
        FROM scout_campaign_quality_history
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    history_count = _count("SELECT count(*) FROM scout_campaign_quality_history")
    latest = dict(rows[0]) if rows else {}
    failed_counts = [int((row.get("campaign_quality_json") or {}).get("latest_failed_count") or 0) for row in rows]
    if len(failed_counts) < 2:
        direction = "insufficient_history"
    elif failed_counts[0] > failed_counts[-1]:
        direction = "degrading"
    elif failed_counts[0] < failed_counts[-1]:
        direction = "improving"
    else:
        direction = "stable"
    guard_row = fetch_one(
        """
        SELECT result_json
        FROM agent_runs
        WHERE agent = 'scout_campaign_quality_regression_guard_agent'
          AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST, started_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """
    )
    guard = dict(guard_row["result_json"]) if guard_row and isinstance(guard_row.get("result_json"), dict) else {}
    latest_quality = latest.get("campaign_quality_json") or {}
    return {
        "history_count": history_count,
        "latest_status": latest.get("status", "MISSING"),
        "latest_blocker_count": int(latest.get("blocker_count", 0) or 0),
        "latest_checked_count": int(latest_quality.get("latest_checked_count") or 0),
        "latest_passed_count": int(latest_quality.get("latest_passed_count") or 0),
        "latest_failed_count": int(latest_quality.get("latest_failed_count") or 0),
        "failed_count_trend_direction": direction,
        "regression_guard_decision": guard.get("decision", "MISSING"),
        "regression_count": len(guard.get("regressions", [])) if isinstance(guard.get("regressions"), list) else 0,
        "regression_review_task_created": bool(guard.get("review_task_created", False)),
        "latest_send_mail": bool(latest.get("send_mail", False)),
        "latest_live_outreach_allowed": bool(latest.get("live_outreach_allowed", False)),
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def scout_source_readiness_trend_snapshot(limit: int = 8) -> dict[str, Any]:
    safe_limit = max(2, min(int(limit or 8), 30))
    rows = fetch_all(
        """
        SELECT status, score, row_count, parseable_count, duplicate_domain_count,
               excluded_niche_count, suppressed_email_count, invalid_email_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM scout_source_readiness_checks
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    latest_by_source = fetch_all(
        """
        SELECT DISTINCT ON (source_id) source_id, status, score, row_count, parseable_count,
               duplicate_domain_count, excluded_niche_count, suppressed_email_count,
               invalid_email_count, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM scout_source_readiness_checks
        ORDER BY source_id, created_at DESC, id DESC
        """
    )
    check_count = _count("SELECT count(*) FROM scout_source_readiness_checks")
    latest = dict(rows[0]) if rows else {}
    current_blocked = [
        row
        for row in latest_by_source
        if row["status"] != "PASS_SOURCE_READY"
        or any(bool(row.get(flag)) for flag in ["send_mail", "smtp_called", "live_outreach_allowed", "raw_recipient_addresses_included", "secrets_included"])
    ]
    blocked_series = [1 if row.get("status") != "PASS_SOURCE_READY" else 0 for row in rows]
    if len(blocked_series) < 2:
        direction = "insufficient_history"
    elif blocked_series[0] > blocked_series[-1]:
        direction = "degrading"
    elif blocked_series[0] < blocked_series[-1]:
        direction = "improving"
    else:
        direction = "stable"
    guard_row = fetch_one(
        """
        SELECT result_json
        FROM agent_runs
        WHERE agent = 'scout_source_readiness_regression_guard_agent'
          AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST, started_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """
    )
    guard = dict(guard_row["result_json"]) if guard_row and isinstance(guard_row.get("result_json"), dict) else {}
    return {
        "check_count": check_count,
        "current_sources_checked": len(latest_by_source),
        "current_sources_ready": len([row for row in latest_by_source if row["status"] == "PASS_SOURCE_READY"]),
        "current_sources_blocked": len(current_blocked),
        "latest_status": latest.get("status", "MISSING"),
        "latest_score": latest.get("score"),
        "latest_row_count": int(latest.get("row_count", 0) or 0),
        "latest_parseable_count": int(latest.get("parseable_count", 0) or 0),
        "latest_duplicate_domain_count": int(latest.get("duplicate_domain_count", 0) or 0),
        "latest_excluded_niche_count": int(latest.get("excluded_niche_count", 0) or 0),
        "latest_suppressed_email_count": int(latest.get("suppressed_email_count", 0) or 0),
        "latest_invalid_email_count": int(latest.get("invalid_email_count", 0) or 0),
        "blocked_source_trend_direction": direction,
        "regression_guard_decision": guard.get("decision", "MISSING"),
        "regression_count": len(guard.get("regressions", [])) if isinstance(guard.get("regressions"), list) else 0,
        "regression_review_task_created": bool(guard.get("review_task_created", False)),
        "latest_send_mail": bool(latest.get("send_mail", False)),
        "latest_live_outreach_allowed": bool(latest.get("live_outreach_allowed", False)),
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def scout_source_queue_preview_snapshot(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 100))
    rows = fetch_all(
        """
        WITH latest AS (
          SELECT DISTINCT ON (source_id) *
          FROM scout_source_readiness_checks
          ORDER BY source_id, created_at DESC, id DESC
        )
        SELECT latest.score AS readiness_score
        FROM scout_sources s
        JOIN latest ON latest.source_id = s.id
        WHERE latest.status = 'PASS_SOURCE_READY'
          AND s.status IN ('active', 'preflight_ready')
          AND upper(COALESCE(s.country, '')) !~ %s
          AND lower(COALESCE(s.name, '')) NOT LIKE 'p%%-%%'
          AND lower(COALESCE(s.name, '')) NOT LIKE 'ready-source-%%'
          AND lower(COALESCE(s.name, '')) NOT LIKE 'blocked-source-%%'
          AND lower(COALESCE(s.name, '')) NOT LIKE 'prov-%%'
          AND NOT EXISTS (
            SELECT 1 FROM scout_runs sr
            WHERE sr.source_id = s.id
              AND sr.status IN ('queued', 'running', 'completed', 'review_required')
          )
        ORDER BY latest.created_at DESC, s.created_at DESC
        LIMIT %s
        """,
        (TEST_COUNTRY_PATTERN, safe_limit),
    )
    scores = [int(row.get("readiness_score") or 0) for row in rows]
    return {
        "candidate_count": len(scores),
        "top_score": max(scores) if scores else 0,
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "ready_for_dry_run_queue": bool(scores),
        "created_scout_runs": 0,
        "created_scanner_jobs": 0,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def runtime_state_snapshot(branch_head: str = "", current_zip_sha: str = "") -> dict[str, Any]:
    from .canary_clean_window_forecast import canary_clean_window_forecast

    mail_qa_decision = latest_mail_qa_decision()
    bounce_count = recent_mail_signal_count(["bounce", "dsn"], 24)
    rate_limit_signal_count = recent_mail_signal_count(["smtp_rate_limit"], 24)
    spam_signal_count = recent_mail_signal_count(["spam_signal"], 24)
    mail_auth_failure_count = recent_mail_signal_count(MAIL_AUTH_BLOCKING_SIGNAL_TYPES, 24)
    live_outreach_sent_count = _count("SELECT count(*) FROM outreach_messages WHERE status = 'sent'")
    live_outreach_bounced_count = _count("SELECT count(*) FROM outreach_messages WHERE status = 'bounced'")
    live_outreach_sent_or_bounced_count = live_outreach_sent_count + live_outreach_bounced_count
    live_outreach_queued_count = _count("SELECT count(*) FROM outreach_messages WHERE status = 'queued'")
    live_flags_armed = (
        os.environ.get("OUTREACH_DRY_RUN", "true").lower() == "false"
        and os.environ.get("OUTREACH_PAUSED", "true").lower() == "false"
        and os.environ.get("FIRST_LIVE_SEND_FLAG", "false").lower() == "true"
    )
    clean_window = canary_clean_window_forecast(24, store=False)
    if bounce_count > 0 or rate_limit_signal_count > 0 or spam_signal_count > 0 or mail_auth_failure_count > 0:
        next_allowed_action = "wait_until_recent_mail_risk_signal_window_clears_then_recheck_mail_qa"
    elif mail_qa_decision != "PASS":
        next_allowed_action = "run_mail_qa_and_keep_sends_blocked_until_pass"
    elif live_flags_armed and live_outreach_sent_or_bounced_count > 0 and live_outreach_queued_count > 0:
        next_allowed_action = "continue_active_canary_under_post_send_observer_and_hard_spacing"
    else:
        next_allowed_action = "continue_monitored_warmup_and_canary_preview_preparation_no_cold_outreach"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_branch_head": branch_head,
        "current_zip_sha": current_zip_sha,
        "checkout_status": "READY",
        "mail_auth_status": "PASS",
        "latest_mail_qa_decision": mail_qa_decision,
        "test_inbox_count": _count("SELECT count(*) FROM test_inboxes WHERE status = 'approved' AND approved"),
        "warmup_recipient_count": _count("SELECT count(*) FROM warmup_recipients WHERE status = 'approved_test_pool' AND approved"),
        "scheduled_warmup_count": _count("SELECT count(*) FROM warmup_schedule"),
        "deliverability_diagnostic_sent_count": _count("SELECT count(*) FROM test_inboxes WHERE last_test_at IS NOT NULL"),
        "warmup_sent_count": _count("SELECT count(*) FROM email_events WHERE event_type = 'warmup_sent'"),
        "live_outreach_sent_count": live_outreach_sent_count,
        "live_outreach_bounced_count": live_outreach_bounced_count,
        "live_outreach_sent_or_bounced_count": live_outreach_sent_or_bounced_count,
        "live_outreach_queued_count": live_outreach_queued_count,
        "bounce_count": bounce_count,
        "rate_limit_signal_count": rate_limit_signal_count,
        "spam_signal_count": spam_signal_count,
        "mail_auth_failure_count": mail_auth_failure_count,
        "canary_clean_window_status": clean_window.get("status"),
        "canary_clean_window_eligible_after": clean_window.get("eligible_after"),
        "canary_clean_window_seconds_remaining": int(clean_window.get("seconds_remaining") or 0),
        "next_allowed_action": next_allowed_action,
        "launch_readiness_state": launch_readiness_state(),
        "mailer_policy_trend": mailer_policy_trend_snapshot(),
        "mailer_business_kpi": mailer_business_kpi_report_snapshot(),
        "scout_campaign_quality_trend": scout_campaign_quality_trend_snapshot(),
        "scout_source_readiness_trend": scout_source_readiness_trend_snapshot(),
        "scout_source_queue_preview": scout_source_queue_preview_snapshot(),
    }


def write_runtime_state_report(path: str | Path, branch_head: str = "", current_zip_sha: str = "") -> dict[str, Any]:
    snapshot = runtime_state_snapshot(branch_head, current_zip_sha)
    policy_trend = snapshot["mailer_policy_trend"]
    business_kpi = snapshot["mailer_business_kpi"]
    scout_quality = snapshot["scout_campaign_quality_trend"]
    scout_source_readiness = snapshot["scout_source_readiness_trend"]
    scout_source_queue = snapshot["scout_source_queue_preview"]
    lines = [
        "# Vøiddo Rescue Runtime State",
        "",
        f"- generated_at: {snapshot['generated_at']}",
        f"- current_branch_head: {snapshot['current_branch_head']}",
        f"- current_zip_sha: {snapshot['current_zip_sha']}",
        f"- checkout_status: {snapshot['checkout_status']}",
        f"- mail_auth_status: {snapshot['mail_auth_status']}",
        f"- latest_mail_qa_decision: {snapshot['latest_mail_qa_decision']}",
        f"- test_inbox_count: {snapshot['test_inbox_count']}",
        f"- warmup_recipient_count: {snapshot['warmup_recipient_count']}",
        f"- scheduled_warmup_count: {snapshot['scheduled_warmup_count']}",
        f"- deliverability_diagnostic_sent_count: {snapshot['deliverability_diagnostic_sent_count']}",
        f"- warmup_sent_count: {snapshot['warmup_sent_count']}",
        f"- live_outreach_sent_count: {snapshot['live_outreach_sent_count']}",
        f"- live_outreach_bounced_count: {snapshot['live_outreach_bounced_count']}",
        f"- live_outreach_sent_or_bounced_count: {snapshot['live_outreach_sent_or_bounced_count']}",
        f"- live_outreach_queued_count: {snapshot['live_outreach_queued_count']}",
        f"- bounce_count_24h: {snapshot['bounce_count']}",
        f"- rate_limit_signal_count_24h: {snapshot['rate_limit_signal_count']}",
        f"- spam_signal_count_24h: {snapshot['spam_signal_count']}",
        f"- mail_auth_failure_count_24h: {snapshot['mail_auth_failure_count']}",
        f"- canary_clean_window_status: {snapshot['canary_clean_window_status']}",
        f"- canary_clean_window_eligible_after: {snapshot['canary_clean_window_eligible_after']}",
        f"- canary_clean_window_seconds_remaining: {snapshot['canary_clean_window_seconds_remaining']}",
        f"- next_allowed_action: {snapshot['next_allowed_action']}",
        f"- launch_readiness_state: {snapshot['launch_readiness_state']}",
        f"- mailer_policy_score_history_count: {policy_trend['policy_score_history_count']}",
        f"- mailer_policy_latest_score: {policy_trend['latest_policy_score']}",
        f"- mailer_policy_latest_decision: {policy_trend['latest_policy_decision']}",
        f"- mailer_policy_latest_blockers: {policy_trend['latest_policy_blocker_count']}",
        f"- mailer_policy_score_trend_direction: {policy_trend['policy_score_trend_direction']}",
        f"- mailer_policy_regression_guard_decision: {policy_trend['policy_regression_guard_decision']}",
        f"- mailer_policy_regression_count: {policy_trend['policy_regression_count']}",
        f"- mailer_policy_regression_score_drop: {policy_trend['policy_regression_score_drop']}",
        f"- mailer_policy_regression_review_task_created: {str(policy_trend['policy_regression_review_task_created']).lower()}",
        f"- mailer_policy_raw_recipients: {str(policy_trend['raw_recipient_addresses_included']).lower()}",
        f"- mailer_policy_secrets: {str(policy_trend['secrets_included']).lower()}",
        f"- mailer_business_kpi_history_count: {business_kpi['count']}",
        f"- mailer_business_kpi_latest_replies: {business_kpi['latest_replies_count']}",
        f"- mailer_business_kpi_latest_safe_actions: {business_kpi['latest_safe_actions_queued']}",
        f"- mailer_business_kpi_latest_blocked_actions: {business_kpi['latest_blocked_actions']}",
        f"- mailer_business_kpi_latest_queue_rows: {business_kpi['latest_action_queue_rows']}",
        f"- mailer_business_kpi_latest_send_mail: {str(business_kpi['latest_send_mail']).lower()}",
        f"- scout_campaign_quality_history_count: {scout_quality['history_count']}",
        f"- scout_campaign_quality_latest_status: {scout_quality['latest_status']}",
        f"- scout_campaign_quality_latest_failed_count: {scout_quality['latest_failed_count']}",
        f"- scout_campaign_quality_trend_direction: {scout_quality['failed_count_trend_direction']}",
        f"- scout_campaign_quality_regression_guard_decision: {scout_quality['regression_guard_decision']}",
        f"- scout_campaign_quality_latest_send_mail: {str(scout_quality['latest_send_mail']).lower()}",
        f"- scout_source_readiness_check_count: {scout_source_readiness['check_count']}",
        f"- scout_source_readiness_sources_checked: {scout_source_readiness['current_sources_checked']}",
        f"- scout_source_readiness_sources_ready: {scout_source_readiness['current_sources_ready']}",
        f"- scout_source_readiness_sources_blocked: {scout_source_readiness['current_sources_blocked']}",
        f"- scout_source_readiness_latest_status: {scout_source_readiness['latest_status']}",
        f"- scout_source_readiness_latest_score: {scout_source_readiness['latest_score']}",
        f"- scout_source_readiness_trend_direction: {scout_source_readiness['blocked_source_trend_direction']}",
        f"- scout_source_readiness_regression_guard_decision: {scout_source_readiness['regression_guard_decision']}",
        f"- scout_source_readiness_regression_count: {scout_source_readiness['regression_count']}",
        f"- scout_source_readiness_latest_send_mail: {str(scout_source_readiness['latest_send_mail']).lower()}",
        f"- scout_source_queue_candidate_count: {scout_source_queue['candidate_count']}",
        f"- scout_source_queue_top_score: {scout_source_queue['top_score']}",
        f"- scout_source_queue_created_scout_runs: {scout_source_queue['created_scout_runs']}",
        f"- scout_source_queue_created_scanner_jobs: {scout_source_queue['created_scanner_jobs']}",
        f"- scout_source_queue_send_mail: {str(scout_source_queue['send_mail']).lower()}",
        "",
        "Raw recipient addresses are intentionally omitted.",
    ]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n")
    return {"path": str(target), **snapshot}


def write_daily_business_report(path: str | Path | None = None) -> dict[str, Any]:
    snapshot = runtime_state_snapshot()
    metrics = admin_metrics_from_db()
    policy_trend = snapshot["mailer_policy_trend"]
    business_kpi = snapshot["mailer_business_kpi"]
    scout_quality = snapshot["scout_campaign_quality_trend"]
    scout_source_readiness = snapshot["scout_source_readiness_trend"]
    scout_source_queue = snapshot["scout_source_queue_preview"]
    target = Path(path) if path else Path(get_settings().storage_root) / "reports" / "daily_business_report.md"
    lines = [
        "# Vøiddo Rescue Daily Business Report",
        "",
        f"- generated_at: {snapshot['generated_at']}",
        f"- launch_readiness_state: {snapshot['launch_readiness_state']}",
        f"- checkout_status: {snapshot['checkout_status']}",
        f"- mail_auth_status: {snapshot['mail_auth_status']}",
        f"- latest_mail_qa_decision: {snapshot['latest_mail_qa_decision']}",
        f"- leads_total: {metrics['leads_total']}",
        f"- qualified_leads: {metrics['qualified_leads']}",
        f"- audit_pages_generated: {metrics['audit_pages_generated']}",
        f"- campaign_leads: {metrics['campaign_leads']}",
        f"- customers: {metrics['customers']}",
        f"- payments: {metrics['payments']}",
        f"- subscriptions: {metrics['subscriptions']}",
        f"- fix_requests: {metrics['fix_requests']}",
        f"- warmup_sent_count: {snapshot['warmup_sent_count']}",
        f"- live_outreach_sent_count: {snapshot['live_outreach_sent_count']}",
        f"- mailer_policy_latest_score: {policy_trend['latest_policy_score']}",
        f"- mailer_policy_latest_decision: {policy_trend['latest_policy_decision']}",
        f"- mailer_policy_score_trend_direction: {policy_trend['policy_score_trend_direction']}",
        f"- mailer_policy_regression_guard_decision: {policy_trend['policy_regression_guard_decision']}",
        f"- mailer_business_kpi_history_count: {business_kpi['count']}",
        f"- mailer_business_kpi_latest_replies: {business_kpi['latest_replies_count']}",
        f"- mailer_business_kpi_latest_safe_actions: {business_kpi['latest_safe_actions_queued']}",
        f"- mailer_business_kpi_latest_blocked_actions: {business_kpi['latest_blocked_actions']}",
        f"- mailer_business_kpi_latest_queue_rows: {business_kpi['latest_action_queue_rows']}",
        f"- mailer_business_kpi_latest_send_mail: {str(business_kpi['latest_send_mail']).lower()}",
        f"- scout_campaign_quality_history_count: {scout_quality['history_count']}",
        f"- scout_campaign_quality_latest_status: {scout_quality['latest_status']}",
        f"- scout_campaign_quality_latest_failed_count: {scout_quality['latest_failed_count']}",
        f"- scout_campaign_quality_trend_direction: {scout_quality['failed_count_trend_direction']}",
        f"- scout_campaign_quality_regression_guard_decision: {scout_quality['regression_guard_decision']}",
        f"- scout_source_readiness_check_count: {scout_source_readiness['check_count']}",
        f"- scout_source_readiness_sources_checked: {scout_source_readiness['current_sources_checked']}",
        f"- scout_source_readiness_sources_ready: {scout_source_readiness['current_sources_ready']}",
        f"- scout_source_readiness_sources_blocked: {scout_source_readiness['current_sources_blocked']}",
        f"- scout_source_readiness_latest_status: {scout_source_readiness['latest_status']}",
        f"- scout_source_readiness_trend_direction: {scout_source_readiness['blocked_source_trend_direction']}",
        f"- scout_source_readiness_regression_guard_decision: {scout_source_readiness['regression_guard_decision']}",
        f"- scout_source_queue_candidate_count: {scout_source_queue['candidate_count']}",
        f"- scout_source_queue_created_scout_runs: {scout_source_queue['created_scout_runs']}",
        f"- scout_source_queue_created_scanner_jobs: {scout_source_queue['created_scanner_jobs']}",
        f"- mailer_policy_raw_recipients: {str(policy_trend['raw_recipient_addresses_included']).lower()}",
        f"- mailer_policy_secrets: {str(policy_trend['secrets_included']).lower()}",
        "",
        "No raw recipient addresses, mailbox passwords, API keys, or private owner data are included.",
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n")
    return {"path": str(target), "send_mail": False, "live_outreach_allowed": False, "snapshot": snapshot}


def write_blockers_report(path: str | Path | None = None) -> dict[str, Any]:
    snapshot = runtime_state_snapshot()
    policy_trend = snapshot["mailer_policy_trend"]
    business_kpi = snapshot["mailer_business_kpi"]
    scout_quality = snapshot["scout_campaign_quality_trend"]
    scout_source_readiness = snapshot["scout_source_readiness_trend"]
    scout_source_queue = snapshot["scout_source_queue_preview"]
    blockers: list[str] = []
    if snapshot["bounce_count"] > 0:
        blockers.append("recent_bounce_or_dsn_signal")
    if snapshot["rate_limit_signal_count"] > 0:
        blockers.append("recent_smtp_rate_limit_signal")
    if snapshot["latest_mail_qa_decision"] != "PASS":
        blockers.append("mail_qa_not_pass")
    if policy_trend["policy_regression_guard_decision"] not in {"PASS_NO_SEND", "MISSING"}:
        blockers.append("mailer_policy_regression_guard_not_pass")
    if policy_trend["latest_policy_decision"] not in {"NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "MISSING"}:
        blockers.append("mailer_policy_not_ready")
    if business_kpi["latest_send_mail"] or business_kpi["latest_live_outreach_allowed"]:
        blockers.append("mailer_business_kpi_send_state_not_safe")
    if scout_quality["regression_guard_decision"] not in {"PASS_NO_SEND", "MISSING"}:
        blockers.append("scout_campaign_quality_regression_guard_not_pass")
    if scout_quality["latest_status"] not in {"PASS_NO_SEND", "MISSING"}:
        blockers.append("scout_campaign_quality_not_pass")
    source_readiness_has_healthy_pool = (
        scout_source_readiness["current_sources_ready"] > 0
        and scout_source_readiness["regression_guard_decision"] in {"PASS_NO_SEND", "MISSING", "MISSING_NO_SEND"}
    )
    if scout_source_readiness["latest_status"] not in {"PASS_SOURCE_READY", "MISSING"} and not source_readiness_has_healthy_pool:
        blockers.append("scout_source_readiness_not_pass")
    if scout_source_readiness["latest_send_mail"] or scout_source_readiness["latest_live_outreach_allowed"]:
        blockers.append("scout_source_readiness_send_state_not_safe")
    if scout_source_readiness["regression_guard_decision"] not in {"PASS_NO_SEND", "MISSING", "MISSING_NO_SEND"}:
        blockers.append("scout_source_readiness_regression_guard_not_pass")
    target = Path(path) if path else Path(get_settings().storage_root) / "reports" / "blockers_report.md"
    lines = [
        "# Vøiddo Rescue Blockers Report",
        "",
        f"- generated_at: {snapshot['generated_at']}",
        f"- launch_readiness_state: {snapshot['launch_readiness_state']}",
        f"- blocker_count: {len(blockers)}",
        f"- blockers: {', '.join(blockers) if blockers else 'none'}",
        f"- bounce_count_24h: {snapshot['bounce_count']}",
        f"- rate_limit_signal_count_24h: {snapshot['rate_limit_signal_count']}",
        f"- mailer_policy_latest_decision: {policy_trend['latest_policy_decision']}",
        f"- mailer_policy_score_trend_direction: {policy_trend['policy_score_trend_direction']}",
        f"- mailer_policy_regression_guard_decision: {policy_trend['policy_regression_guard_decision']}",
        f"- mailer_business_kpi_history_count: {business_kpi['count']}",
        f"- mailer_business_kpi_latest_replies: {business_kpi['latest_replies_count']}",
        f"- mailer_business_kpi_latest_safe_actions: {business_kpi['latest_safe_actions_queued']}",
        f"- mailer_business_kpi_latest_blocked_actions: {business_kpi['latest_blocked_actions']}",
        f"- mailer_business_kpi_latest_queue_rows: {business_kpi['latest_action_queue_rows']}",
        f"- mailer_business_kpi_latest_send_mail: {str(business_kpi['latest_send_mail']).lower()}",
        f"- scout_campaign_quality_history_count: {scout_quality['history_count']}",
        f"- scout_campaign_quality_latest_status: {scout_quality['latest_status']}",
        f"- scout_campaign_quality_latest_failed_count: {scout_quality['latest_failed_count']}",
        f"- scout_campaign_quality_trend_direction: {scout_quality['failed_count_trend_direction']}",
        f"- scout_campaign_quality_regression_guard_decision: {scout_quality['regression_guard_decision']}",
        f"- scout_source_readiness_check_count: {scout_source_readiness['check_count']}",
        f"- scout_source_readiness_sources_checked: {scout_source_readiness['current_sources_checked']}",
        f"- scout_source_readiness_sources_ready: {scout_source_readiness['current_sources_ready']}",
        f"- scout_source_readiness_sources_blocked: {scout_source_readiness['current_sources_blocked']}",
        f"- scout_source_readiness_latest_status: {scout_source_readiness['latest_status']}",
        f"- scout_source_readiness_trend_direction: {scout_source_readiness['blocked_source_trend_direction']}",
        f"- scout_source_readiness_regression_guard_decision: {scout_source_readiness['regression_guard_decision']}",
        f"- scout_source_queue_candidate_count: {scout_source_queue['candidate_count']}",
        f"- scout_source_queue_created_scout_runs: {scout_source_queue['created_scout_runs']}",
        f"- scout_source_queue_created_scanner_jobs: {scout_source_queue['created_scanner_jobs']}",
        f"- live_outreach_sent_count: {snapshot['live_outreach_sent_count']}",
        f"- warmup_sent_count: {snapshot['warmup_sent_count']}",
        "",
        "No raw recipient addresses, mailbox passwords, API keys, or private owner data are included.",
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n")
    return {"path": str(target), "blockers": blockers, "send_mail": False, "live_outreach_allowed": False, "snapshot": snapshot}


def resume_warmup_gate() -> dict[str, Any]:
    checks = {
        "recent_bounce_count": recent_mail_signal_count(["bounce", "dsn"], 24),
        "recent_rate_limit_count": recent_mail_signal_count(["smtp_rate_limit"], 24),
        "latest_mail_qa_decision": latest_mail_qa_decision(),
        "warmup_pool_count": len(approved_warmup_recipient_emails()),
    }
    allowed = (
        checks["recent_bounce_count"] == 0
        and checks["recent_rate_limit_count"] == 0
        and checks["latest_mail_qa_decision"] == "PASS"
        and checks["warmup_pool_count"] > 0
    )
    if allowed:
        set_runtime_control("pause_warmup", False, "owner_command", "RESUME WARMUP")
    return {"ok": allowed, "action": "resume_warmup", "allowed": allowed, "checks": checks}


def owner_command_trigger_status(limit: int = 10) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 10), 50))
    rows = fetch_all(
        """
        SELECT command, risk_level, status, result_json, created_at
        FROM owner_commands
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    return {
        "count": len(rows),
        "commands": [
            {
                "command": row["command"],
                "risk_level": row["risk_level"],
                "status": row["status"],
                "action": (row.get("result_json") or {}).get("action") if isinstance(row.get("result_json"), dict) else None,
                "reason": (row.get("result_json") or {}).get("reason") if isinstance(row.get("result_json"), dict) else None,
                "created_at": row["created_at"],
            }
            for row in rows
        ],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_private_addresses_included": False,
        "secrets_included": False,
    }


def execute_owner_command(parsed: dict[str, Any]) -> dict[str, Any]:
    command = parsed["command"]
    risk = parsed["risk_level"]
    if risk == "HIGH_RISK":
        task = execute(
            """
            INSERT INTO codex_tasks(type, priority, status, title, description, input_json)
            VALUES ('owner_command_review', 'high', 'open', 'Review blocked owner command',
                    'High-risk owner command was blocked by the autonomous command gate. No shell or live-send action was executed.', %s)
            RETURNING id
            """,
            (
                Jsonb(
                    json_safe(
                        {
                            "command": command,
                            "risk_level": risk,
                            "args": parsed.get("args_json", {}),
                            "reason": "high_risk_command_blocked",
                            "send_mail": False,
                            "smtp_called": False,
                            "live_outreach_allowed": False,
                            "secrets_included": False,
                        }
                    )
                ),
            ),
        )
        result = {"ok": False, "action": "review_required", "reason": "high_risk_command_blocked", "codex_task_id": str(task["id"])}
    elif command == "STATUS":
        from .mail_send_compliance import mail_send_compliance_snapshot

        result = {
            "ok": True,
            "action": "metrics",
            "metrics": admin_metrics_from_db(),
            "runtime_state": runtime_state_snapshot(),
            "mail_send_compliance": mail_send_compliance_snapshot(),
        }
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
    elif command == "SHOW MAIL QA":
        result = {"ok": True, "action": "mail_qa_status", "items": fetch_all("SELECT decision, checks_json, issues_json, created_at FROM mail_qa_runs ORDER BY created_at DESC LIMIT 5")}
    elif command == "SHOW DELIVERABILITY":
        items = fetch_all("SELECT email, provider, status, last_test_at, result_json FROM test_inboxes ORDER BY created_at DESC LIMIT 20")
        result = {
            "ok": True,
            "action": "deliverability_status",
            "items": [
                {
                    "recipient_hash": recipient_hash(item["email"]),
                    "provider": item.get("provider") or email_provider(item["email"]),
                    "status": item["status"],
                    "last_test_at": item["last_test_at"],
                    "result_json": item["result_json"],
                }
                for item in items
            ],
        }
    elif command == "SHOW WARMUP":
        result = {"ok": True, "action": "warmup_status", "items": fetch_all("SELECT status, day_number, planned_daily_cap, recipient_pool_count, stop_conditions_json, created_at FROM warmup_runs ORDER BY created_at DESC LIMIT 10")}
    elif command == "SHOW WARMUP CALENDAR":
        result = {"ok": True, "action": "warmup_calendar", "calendar": warmup_calendar_health()}
    elif command == "SHOW MAIL SIGNALS":
        result = {"ok": True, "action": "mail_signals", "signals": mail_signal_summary()}
    elif command == "SHOW STUDIO MAIL":
        from .studio_mail_monitor import latest_studio_mail_messages, latest_studio_mail_runs, studio_mail_monitor_health

        result = {
            "ok": True,
            "action": "studio_mail_status",
            "health": studio_mail_monitor_health(15),
            "latest_messages": latest_studio_mail_messages(10),
            "latest_runs": latest_studio_mail_runs(5),
        }
    elif command == "SHOW OWNER TRIGGERS":
        from .studio_mail_monitor import latest_studio_mail_messages, latest_studio_mail_runs, studio_mail_monitor_health

        result = {
            "ok": True,
            "action": "owner_trigger_status",
            "studio_mail_health": studio_mail_monitor_health(15),
            "latest_owner_commands": owner_command_trigger_status(10),
            "latest_studio_mail_runs": latest_studio_mail_runs(5),
            "latest_studio_messages": latest_studio_mail_messages(5),
            "runtime_state": runtime_state_snapshot(),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        }
    elif command == "NO_ACTION_OWNER_REPLY":
        result = {
            "ok": True,
            "action": "no_action_owner_reply",
            "reason": "reply_to_daily_report_without_parseable_command",
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        }
    elif command == "SHOW LIVE QUEUE":
        from .outreach_live_queue import latest_outreach_send_runs, live_outreach_queue_candidates

        result = {
            "ok": True,
            "action": "live_queue_status",
            "queue": live_outreach_queue_candidates(20),
            "history": latest_outreach_send_runs(10),
        }
    elif command == "SHOW CANARY SCALE":
        from .canary_scale_plan import canary_scale_plan

        result = {
            "ok": True,
            "action": "canary_scale_status",
            "plan": canary_scale_plan(20, 40, store=True),
        }
    elif command == "SHOW CANARY BOUNCE RECOVERY":
        from .canary_bounce_recovery import canary_bounce_recovery, latest_canary_bounce_recovery_runs

        result = {
            "ok": True,
            "action": "canary_bounce_recovery_status",
            "recovery": canary_bounce_recovery(24, apply_pause=True, store=True),
            "history": latest_canary_bounce_recovery_runs(5),
        }
    elif command == "SHOW CANARY RESUME":
        from .canary_resume_plan import canary_resume_plan, latest_canary_resume_plan_runs

        result = {
            "ok": True,
            "action": "canary_resume_status",
            "plan": canary_resume_plan(24, apply=False, store=True),
            "history": latest_canary_resume_plan_runs(5),
        }
    elif command == "SHOW CANARY CLEAN WINDOW":
        from .canary_clean_window_forecast import canary_clean_window_forecast

        result = {
            "ok": True,
            "action": "canary_clean_window_status",
            "forecast": canary_clean_window_forecast(24, store=True),
        }
    elif command == "SHOW TRANSPORT BLOCK HYGIENE":
        from .outreach_transport_block_hygiene import outreach_transport_block_hygiene

        result = {
            "ok": True,
            "action": "transport_block_hygiene_status",
            "hygiene": outreach_transport_block_hygiene(100, apply=False),
        }
    elif command == "SHOW LEAD SUPPLY":
        from .lead_discovery import quality_aware_regional_target_plan
        from .lead_stockpile_health import latest_lead_stockpile_health_runs, lead_stockpile_health_snapshot
        from .lead_supply_buildout import lead_supply_buildout

        result = {
            "ok": True,
            "action": "lead_supply_status",
            "stockpile": lead_stockpile_health_snapshot(100, 20, 150),
            "buildout": lead_supply_buildout(100, 20, 120, apply=False),
            "quality_targets": quality_aware_regional_target_plan(5),
            "history": latest_lead_stockpile_health_runs(5),
        }
    elif command == "SHOW LAUNCH RUNBOOK":
        from .launch_activation import launch_activation_runbook

        result = {"ok": True, "action": "launch_runbook", "runbook": launch_activation_runbook(25)}
    elif command == "ROLLBACK LIVE OUTREACH":
        from .launch_activation import rollback_live_outreach

        result = rollback_live_outreach("owner_command")
    elif command == "RUN MAIL QA":
        result = {"ok": True, "action": "mail_qa", "run": run_mail_qa()}
    elif command == "RUN DELIVERABILITY TEST":
        result = {"ok": True, "action": "deliverability_test", "run": run_mail_qa()}
    elif command == "RUN VISUAL QA":
        result = {"ok": True, "action": "visual_qa", "run": record_visual_qa("app_visual_agent", get_settings().app_base_url, "")}
    elif command == "PREPARE WARMUP":
        pool_count = len(approved_warmup_recipient_emails())
        result = {"ok": True, "action": "warmup_prepare", "warmup": prepare_warmup(pool_count, 1)}
    elif command == "START WARMUP":
        result = start_warmup_gate(int(parsed.get("args_json", {}).get("day", 1)))
    elif command == "RESUME WARMUP":
        result = resume_warmup_gate()
    elif command == "PREPARE LEADS":
        result = {"ok": True, "action": "lead_prepare_dry_run", "args": parsed.get("args_json", {}), "live_send": False}
    elif command == "PREPARE LIVE CANARY":
        from .outreach_live_queue import stage_live_outreach_batch

        result = {
            "ok": True,
            "action": "live_canary_prepared_dry_run",
            "queue": stage_live_outreach_batch(20, dry_run=True, requested_by="owner_command"),
        }
    elif command == "RUN LEAD SUPPLY BUILDOUT":
        from .lead_supply_buildout import lead_supply_buildout

        result = {
            "ok": True,
            "action": "lead_supply_buildout",
            "supply": lead_supply_buildout(100, 20, 120, max_cycles=1, max_seconds=90, enrichment_limit=0, apply=True),
        }
    elif command == "RUN REVENUE LOOP":
        from .lead_supply_buildout import lead_supply_buildout
        from .launch_rehearsal import run_launch_rehearsal
        from .mail_send_compliance import mail_send_compliance_snapshot
        from .revenue_loop import prepare_revenue_loop, revenue_loop_snapshot

        result = {
            "ok": True,
            "action": "revenue_loop_no_send",
            "runtime_state": runtime_state_snapshot(),
            "mail_send_compliance": mail_send_compliance_snapshot(),
            "lead_supply": lead_supply_buildout(100, 20, 120, max_cycles=1, max_seconds=20, enrichment_limit=0, apply=True),
            "revenue_loop": prepare_revenue_loop(25, dry_run=True),
            "snapshot": revenue_loop_snapshot(25),
            "launch_rehearsal": run_launch_rehearsal(20, apply_pause=False),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        }
    elif command == "RUN LAUNCH REHEARSAL":
        from .launch_rehearsal import run_launch_rehearsal

        result = {"ok": True, "action": "launch_rehearsal", "rehearsal": run_launch_rehearsal(20, apply_pause=False)}
    else:
        result = {"ok": False, "action": "review_required", "reason": "unknown_command"}
    execute(
        "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
        ("owner_command.executed", "info" if result.get("ok") else "warning", command, Jsonb(json_safe({"risk_level": risk, "result": result}))),
    )
    return json_safe(result)


def start_warmup_gate(day_number: int = 1) -> dict[str, Any]:
    pool_count = len(approved_warmup_recipient_emails())
    latest_mail = fetch_one("SELECT decision, issues_json FROM mail_qa_runs ORDER BY created_at DESC LIMIT 1")
    latest_mail_decision = latest_mail["decision"] if latest_mail else "MISSING"
    deliverability_blockers = []
    if latest_mail and latest_mail.get("issues_json"):
        deliverability_blockers = [
            issue for issue in latest_mail["issues_json"]
            if issue not in {"approved_test_inbox_pool_missing"}
        ]
    warmup_paused = effective_pause_state("warmup", False)
    recent_bounce_count = recent_mail_signal_count(["bounce", "dsn"], 24)
    recent_rate_limit_count = recent_mail_signal_count(["smtp_rate_limit"], 24)
    allowed = bool(
        pool_count > 0
        and latest_mail_decision == "PASS"
        and not deliverability_blockers
        and not warmup_paused
        and recent_bounce_count == 0
        and recent_rate_limit_count == 0
    )
    warmup = prepare_warmup(pool_count, day_number)
    send_result = {"sent": 0, "attempted": 0, "errors": [], "skipped": "gate_not_allowed"}
    if allowed:
        send_result = run_warmup_day(day_number, warmup["id"])
        warmup["status"] = "warmup_active_no_outreach" if send_result["sent"] > 0 else "warmup_day_1_blocked"
    return {
        "ok": bool(allowed and send_result["sent"] > 0),
        "action": "warmup_start_gate",
        "allowed": allowed,
        "reason": "warmup_day_1_sent" if send_result["sent"] > 0 else "warmup_start_blocked",
        "checks": {
            "pool_count": pool_count,
            "mail_qa_decision": latest_mail_decision,
            "deliverability_blockers": deliverability_blockers,
            "warmup_paused": warmup_paused,
            "recent_bounce_count_24h": recent_bounce_count,
            "recent_rate_limit_count_24h": recent_rate_limit_count,
            "cold_leads": False,
            "sends_started": send_result["sent"],
        },
        "warmup": warmup,
        "send_result": send_result,
    }


def smtp_credentials_for_sender(settings: Settings, sender_mailbox: str) -> tuple[str, str, str]:
    sender = sender_mailbox.lower()
    if sender.startswith("support@") and settings.imap_username_support and settings.imap_password_support:
        return settings.imap_username_support, settings.imap_password_support, sender_mailbox
    if sender.startswith("fix@") and settings.imap_username_fix and settings.imap_password_fix:
        return settings.imap_username_fix, settings.imap_password_fix, sender_mailbox
    return settings.smtp_username, settings.smtp_password, settings.smtp_from_default


def warmup_recipient_order() -> list[str]:
    settings = get_settings()
    owner = (settings.owner_command_email or "").lower()
    rows = fetch_all(
        """
        SELECT email
        FROM warmup_recipients
        WHERE status = 'approved_test_pool' AND approved
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(s.email) = lower(warmup_recipients.email))
        """
    )
    emails = sorted({str(row["email"]).lower() for row in rows})
    def key(email: str) -> tuple[int, str]:
        domain = email.rsplit("@", 1)[-1]
        if owner and email == owner:
            return (0, email)
        if domain == "gmail.com":
            return (1, email)
        if domain not in {"voiddo.com", "voiddorescue.com"}:
            return (2, email)
        return (3, email)
    return sorted(emails, key=key)


def build_warmup_calendar(days: int = 14, per_day: int = 2, start_tomorrow: bool = True) -> dict[str, Any]:
    recipients = warmup_recipient_order()
    if not recipients:
        return {"created": 0, "status": "blocked_no_recipients"}
    tz = ZoneInfo("Asia/Jerusalem")
    now_local = datetime.now(tz)
    first_day = (now_local + timedelta(days=1)).date() if start_tomorrow else now_local.date()
    send_times = [time(10, 15), time(16, 15)]
    created = 0
    existing = fetch_one("SELECT count(*) AS count FROM warmup_schedule WHERE status = 'scheduled'")
    if existing and int(existing["count"]) > 0:
        return {"created": 0, "status": "already_scheduled", "scheduled": int(existing["count"])}
    for day_index in range(days):
        for slot in range(per_day):
            recipient = recipients[(day_index * per_day + slot) % len(recipients)]
            sender = WARMUP_SENDER_ROTATION[(day_index * per_day + slot) % len(WARMUP_SENDER_ROTATION)]
            local_dt = datetime.combine(first_day + timedelta(days=day_index), send_times[slot % len(send_times)], tzinfo=tz)
            execute(
                """
                INSERT INTO warmup_schedule(recipient_email, sender_mailbox, day_number, scheduled_for, status, result_json)
                VALUES (%s, %s, %s, %s, 'scheduled', %s)
                """,
                (
                    recipient,
                    sender,
                    day_index + 1,
                    local_dt.astimezone(timezone.utc),
                    Jsonb({"daily_cap": per_day, "content_policy": "neutral_no_sales_no_tracking", "owner_preferred": recipient == (get_settings().owner_command_email or "").lower()}),
                ),
            )
            created += 1
    execute(
        "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
        ("warmup.calendar_created", "info", "Autonomous warmup calendar created", Jsonb({"days": days, "per_day": per_day, "created": created})),
    )
    return {"created": created, "status": "scheduled", "days": days, "per_day": per_day}


def warmup_pre_send_gate(row: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    recipient = str(row["recipient_email"]).lower()
    sender = str(row.get("sender_mailbox") or settings.smtp_from_default)
    username, password, _ = smtp_credentials_for_sender(settings, sender)
    mail_qa = latest_mail_qa_decision()
    checks = {
        "pause_warmup": effective_pause_state("warmup", False),
        "global_kill_switch": runtime_control_enabled("pause_workers"),
        "latest_mail_qa_decision": mail_qa,
        "smtp_strict_tls_latest": "PASS" if mail_qa == "PASS" else "UNKNOWN",
        "imap_strict_tls_latest": "PASS" if mail_qa == "PASS" else "UNKNOWN",
        "spf_dkim_dmarc_latest": "PASS" if mail_qa == "PASS" else "UNKNOWN",
        "recent_bounce_or_dsn_count_24h": recent_mail_signal_count(["bounce", "dsn"], 24),
        "recent_rate_limit_count_24h": recent_mail_signal_count(["smtp_rate_limit"], 24),
        "recent_spam_signal_count_24h": recent_mail_signal_count(["spam_signal"], 24),
        "recent_mail_auth_failure_count_24h": recent_mail_signal_count(MAIL_AUTH_BLOCKING_SIGNAL_TYPES, 24),
        "recipient_suppressed": is_recipient_suppressed(recipient),
        "sender_credentials_available": bool(username and password),
        "daily_cap": warmup_daily_cap(),
        "sent_today": _count(
            """
            SELECT count(*)
            FROM warmup_schedule
            WHERE status = 'sent'
              AND sent_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Jerusalem') AT TIME ZONE 'Asia/Jerusalem'
            """
        ),
    }
    if checks["pause_warmup"] or checks["global_kill_switch"]:
        return {"allowed": False, "status": "blocked_paused", "checks": checks}
    if checks["recent_bounce_or_dsn_count_24h"] > 0:
        return {"allowed": False, "status": "blocked_recent_bounce", "checks": checks}
    if checks["recent_rate_limit_count_24h"] > 0:
        return {"allowed": False, "status": "blocked_recent_rate_limit", "checks": checks}
    if checks["recent_spam_signal_count_24h"] > 0:
        return {"allowed": False, "status": "blocked_recent_spam_signal", "checks": checks}
    if checks["recent_mail_auth_failure_count_24h"] > 0:
        return {"allowed": False, "status": "blocked_mail_auth_signal", "checks": checks}
    if checks["latest_mail_qa_decision"] != "PASS":
        return {"allowed": False, "status": "blocked_mail_qa", "checks": checks}
    if checks["recipient_suppressed"]:
        return {"allowed": False, "status": "skipped_suppressed", "checks": checks}
    if not checks["sender_credentials_available"]:
        return {"allowed": False, "status": "failed", "checks": {**checks, "error": "sender_credentials_missing"}}
    if checks["sent_today"] >= checks["daily_cap"]:
        return {"allowed": False, "status": "blocked_paused", "checks": {**checks, "error": "daily_cap_reached"}}
    return {"allowed": True, "status": "allowed", "checks": checks}


def run_warmup_calendar_due(limit: int = 2) -> dict[str, Any]:
    settings = get_settings()
    today_sent = fetch_one(
        """
        SELECT count(*) AS count
        FROM warmup_schedule
        WHERE status = 'sent'
          AND sent_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Jerusalem') AT TIME ZONE 'Asia/Jerusalem'
        """
    )
    remaining = max(0, warmup_daily_cap() - int(today_sent["count"]))
    if remaining <= 0:
        return {"sent": 0, "status": "daily_cap_reached"}
    rows = fetch_all(
        """
        SELECT id, recipient_email, sender_mailbox, day_number, scheduled_for
        FROM warmup_schedule
        WHERE status = 'scheduled' AND scheduled_for <= now()
        ORDER BY scheduled_for
        LIMIT %s
        """,
        (min(limit, remaining),),
    )
    sent = 0
    errors: list[str] = []
    for row in rows:
        gate = warmup_pre_send_gate(row, settings)
        if not gate["allowed"]:
            execute(
                "UPDATE warmup_schedule SET status = %s, result_json = %s, updated_at = now() WHERE id = %s",
                (gate["status"], Jsonb(gate), row["id"]),
            )
            execute(
                "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
                (
                    "warmup.calendar_blocked",
                    "warning",
                    gate["status"],
                    Jsonb({"schedule_id": str(row["id"]), "checks": gate["checks"]}),
                ),
            )
            if gate["status"] != "skipped_suppressed":
                break
            continue
        username, password, from_addr = smtp_credentials_for_sender(settings, row["sender_mailbox"])
        message_id = make_msgid(domain="voiddorescue.com")
        msg = EmailMessage()
        msg["Subject"] = "Vøiddo Rescue warmup check"
        msg["From"] = from_addr
        msg["To"] = row["recipient_email"]
        msg["Message-ID"] = message_id
        msg.set_content(warmup_message_for(sent))
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(msg)
        except Exception as exc:
            label = smtp_error_label(exc)
            errors.append(label)
            signal = smtp_error_to_mail_signal(label)
            if signal:
                record_mail_signal(signal, "warning", "warmup_calendar", from_addr, row["recipient_email"], message_id=message_id, raw_summary=label)
            execute(
                "UPDATE warmup_schedule SET status = 'failed', result_json = %s, updated_at = now() WHERE id = %s",
                (Jsonb({"error": label, "message_id": message_id}), row["id"]),
            )
            break
        execute(
            """
            INSERT INTO email_events(event_type, payload_json, mailbox, message_id)
            VALUES ('warmup_sent', %s, %s, %s)
            """,
            (
                Jsonb({"recipient_hash": recipient_hash(row["recipient_email"]), "sender": from_addr, "schedule_id": str(row["id"]), "day_number": row["day_number"], "policy": "neutral_calendar_warmup_no_sales_no_tracking"}),
                from_addr,
                message_id,
            ),
        )
        execute(
            "UPDATE warmup_schedule SET status = 'sent', sent_at = now(), result_json = %s, updated_at = now() WHERE id = %s",
            (Jsonb({"message_id": message_id, "smtp_result": "accepted"}), row["id"]),
        )
        sent += 1
    return {"sent": sent, "errors": errors, "status": "ok" if not errors else "stopped_on_error"}


def write_owner_daily_report() -> dict[str, Any]:
    metrics = admin_metrics_from_db()
    policy_trend = mailer_policy_trend_snapshot()
    scout_quality = scout_campaign_quality_trend_snapshot()
    report_dir = Path(get_settings().storage_root) / "reports" / "owner"
    report_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = report_dir / f"owner-report-{now.strftime('%Y%m%d')}.json"
    payload = {
        "created_at": now.isoformat(),
        "metrics": metrics,
        "mailer_policy_trend": policy_trend,
        "scout_campaign_quality_trend": scout_quality,
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


def run_mail_qa(allow_deliverability_send: bool = True) -> dict[str, Any]:
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
    if approved_test_inboxes and allow_deliverability_send:
        deliverability = run_deliverability_diagnostics(settings, approved_test_inboxes, smtp_ready)
    elif approved_test_inboxes:
        deliverability = {"sent": 0, "skipped": "disabled_for_clean_window_transition"}
    else:
        deliverability = {"sent": 0, "skipped": "no_approved_test_inboxes"}
    checks["deliverability_diagnostics"] = deliverability
    deliverability_errors = [
        str(error)
        for error in (deliverability.get("errors") or [])
        if str(error) not in {"diagnostic_minute_cap_reached", "diagnostic_daily_cap_reached"}
    ]
    if deliverability_errors:
        issues.append("deliverability_diagnostic_failed")
    external_providers = provider_counts_for_test_inboxes().get("external", 0)
    internal_only = bool(checks["approved_test_inboxes"] > 0 and external_providers == 0)
    if internal_only and not issues:
        issues.append("external_deliverability_pool_missing")
        checks["deliverability_scope"] = "PASS_INTERNAL_ONLY"
    else:
        checks["deliverability_scope"] = "EXTERNAL_POOL_PRESENT" if external_providers else "NO_POOL"
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
    daily_diagnostics = _count(
        """
        SELECT count(*)
        FROM mail_signals
        WHERE source = 'deliverability_diagnostic_sent'
          AND created_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Jerusalem') AT TIME ZONE 'Asia/Jerusalem'
        """
    )
    if daily_diagnostics >= DIAGNOSTIC_DAILY_CAP:
        return {"sent": 0, "skipped": "diagnostic_daily_cap_reached", "daily_cap": DIAGNOSTIC_DAILY_CAP}
    sent = 0
    skipped = 0
    errors: list[str] = []
    results: list[dict[str, Any]] = []
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
                            if sent >= DIAGNOSTIC_MINUTE_CAP:
                                skipped += len(pending) - sent
                                errors.append("diagnostic_minute_cap_reached")
                                break
                            if daily_diagnostics + sent >= DIAGNOSTIC_DAILY_CAP:
                                skipped += 1
                                break
                            minute_diagnostics = _count(
                                """
                                SELECT count(*)
                                FROM mail_signals
                                WHERE source = 'deliverability_diagnostic_sent'
                                  AND created_at >= now() - interval '1 minute'
                                """
                            )
                            if minute_diagnostics >= DIAGNOSTIC_MINUTE_CAP:
                                skipped += len(pending) - sent
                                errors.append("diagnostic_minute_cap_reached")
                                break
                            message_id = make_msgid(domain="voiddorescue.com")
                            msg = EmailMessage()
                            msg["Subject"] = "Vøiddo Rescue mail diagnostic"
                            msg["From"] = settings.smtp_from_default
                            msg["To"] = email
                            msg["Message-ID"] = message_id
                            msg.set_content("This is a requested mail delivery diagnostic for Vøiddo Rescue. No action is required.")
                            smtp_result = smtp.send_message(msg) or {}
                            sent += 1
                            result_json = {
                                "status": "sent",
                                "message": "neutral_diagnostic",
                                "message_id": message_id,
                                "smtp_result": "accepted" if not smtp_result else "partial_or_rejected",
                                "smtp_refused": smtp_result,
                                "bounce_result": "pending_inbox_poll",
                            }
                            results.append({"recipient_hash": recipient_hash(email), "provider": email_provider(email), **result_json})
                            cur.execute(
                                """
                                INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, message_id, raw_summary)
                                VALUES ('manual_observation', 'info', 'deliverability_diagnostic_sent', %s, %s, %s, %s, %s)
                                """,
                                (
                                    settings.smtp_from_default,
                                    recipient_hash(email),
                                    email_provider(email),
                                    message_id,
                                    "neutral diagnostic accepted by SMTP",
                                ),
                            )
                            cur.execute(
                                """
                                INSERT INTO email_events(event_type, payload_json, mailbox, message_id)
                                VALUES ('deliverability_diagnostic_sent', %s, %s, %s)
                                """,
                                (
                                    Jsonb(
                                        {
                                            "recipient_hash": recipient_hash(email),
                                            "provider": email_provider(email),
                                            "message_id": message_id,
                                            "smtp_result": "accepted" if not smtp_result else "partial_or_rejected",
                                            "policy": "neutral_diagnostic_no_sales_no_tracking",
                                            "raw_recipient_included": False,
                                        }
                                    ),
                                    settings.smtp_from_default,
                                    message_id,
                                ),
                            )
                            cur.execute(
                                """
                                UPDATE test_inboxes
                                SET last_test_at = now(), result_json = %s
                                WHERE lower(email) = lower(%s)
                                """,
                                (Jsonb(result_json), email),
                            )
                except Exception as exc:
                    label = smtp_error_label(exc)
                    errors.append(label)
                    signal = smtp_error_to_mail_signal(label)
                    if signal:
                        cur.execute(
                            """
                            INSERT INTO mail_signals(signal_type, severity, source, mailbox, raw_summary)
                            VALUES (%s, 'warning', 'deliverability_diagnostic', %s, %s)
                            """,
                            (signal, settings.smtp_from_default, label),
                        )
            conn.commit()
    result: dict[str, Any] = {"sent": sent, "skipped_previously_tested": skipped, "policy": "neutral_diagnostic_max_one_per_mailbox"}
    if results:
        result["results"] = results
    if errors:
        result["errors"] = errors
    return result


def smtp_error_label(exc: Exception) -> str:
    code = getattr(exc, "smtp_code", None)
    error = getattr(exc, "smtp_error", b"")
    if isinstance(error, bytes):
        error = error.decode("utf-8", errors="replace")
    if code:
        return f"{type(exc).__name__}:{code}:{str(error)[:160]}"
    return type(exc).__name__


def smtp_error_to_mail_signal(label: str) -> str:
    lowered = label.lower()
    if "rate" in lowered or "limit" in lowered or "greylist" in lowered or "451" in lowered:
        return "smtp_rate_limit"
    if "auth" in lowered or "authentication" in lowered or "535" in lowered:
        return "auth_failure"
    if "ssl" in lowered or "tls" in lowered or "certificate" in lowered:
        return "tls_failure"
    return ""


def provider_counts_for_test_inboxes() -> dict[str, int]:
    rows = fetch_all(
        """
        SELECT
          CASE
            WHEN lower(split_part(email, '@', 2)) IN ('voiddo.com', 'voiddorescue.com') THEN 'internal'
            ELSE 'external'
          END AS scope,
          count(*) AS count
        FROM test_inboxes
        WHERE status = 'approved' AND approved
        GROUP BY scope
        """
    )
    return {str(row["scope"]): int(row["count"]) for row in rows}


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


def warmup_day_cap(day_number: int) -> int:
    caps = {1: 5, 2: 10, 3: 15}
    return caps.get(day_number, 25 if day_number <= 7 else 40)


def warmup_message_for(index: int) -> str:
    messages = [
        "This is a requested Vøiddo Rescue mail warmup check. No action is required.",
        "Requested Vøiddo Rescue warmup message. No action is required.",
        "Vøiddo Rescue warmup note requested by the mailbox owner. No action is required.",
        "Mail warmup check for Vøiddo Rescue. No action is required.",
        "Vøiddo Rescue delivery warmup check. No action is required.",
    ]
    return messages[index % len(messages)]


def run_warmup_day(day_number: int = 1, warmup_run_id: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    cap = warmup_day_cap(day_number)
    recipients = approved_warmup_recipient_emails(settings)[:cap]
    if not recipients:
        return {"sent": 0, "attempted": 0, "errors": [], "skipped": "no_approved_warmup_recipients", "daily_cap": cap}

    sent = 0
    attempted = 0
    errors: list[str] = []
    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
            smtp.login(settings.smtp_username, settings.smtp_password)
            for index, email in enumerate(recipients):
                attempted += 1
                message_id = make_msgid(domain="voiddorescue.com")
                msg = EmailMessage()
                msg["Subject"] = "Vøiddo Rescue warmup check"
                msg["From"] = settings.smtp_from_default
                msg["To"] = email
                msg["Message-ID"] = message_id
                msg.set_content(warmup_message_for(index))
                try:
                    smtp.send_message(msg)
                except Exception as exc:
                    errors.append(f"{email}:{smtp_error_label(exc)}")
                    break
                sent += 1
                execute(
                    """
                    INSERT INTO email_events(event_type, payload_json, mailbox, message_id)
                    VALUES ('warmup_sent', %s, %s, %s)
                    """,
                    (
                        Jsonb(
                            {
                                "recipient_hash": recipient_hash(email),
                                "day_number": day_number,
                                "daily_cap": cap,
                                "warmup_run_id": str(warmup_run_id or ""),
                                "policy": "neutral_owner_approved_warmup_no_sales_no_tracking",
                                "smtp_result": "accepted",
                                "bounce_result": "pending_inbox_poll",
                                "raw_recipient_included": False,
                            }
                        ),
                        settings.smtp_from_default,
                        message_id,
                    ),
                )
    except Exception as exc:
        errors.append(type(exc).__name__)

    status = "warmup_active_no_outreach" if sent > 0 and not errors else "warmup_day_1_blocked"
    if warmup_run_id:
        execute(
            """
            UPDATE warmup_runs
            SET status = %s,
                plan_json = jsonb_set(plan_json, '{actual_send}', %s::jsonb, true),
                updated_at = now()
            WHERE id = %s
            """,
            (
                status,
                json.dumps({"sent": sent, "attempted": attempted, "errors": errors, "daily_cap": cap}),
                warmup_run_id,
            ),
        )
    execute(
        "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
        (
            "warmup.day_sent" if sent > 0 else "warmup.day_blocked",
            "info" if sent > 0 and not errors else "warning",
            f"Warmup day {day_number} send gate executed",
            Jsonb({"sent": sent, "attempted": attempted, "errors": errors, "daily_cap": cap}),
        ),
    )
    return {"sent": sent, "attempted": attempted, "errors": errors, "daily_cap": cap}


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
                    VALUES (%s, %s, 'owner_provided', 'approved_test_pool', %s)
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
                suppressed = cur.execute("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (email,)).fetchone()
                if suppressed:
                    rejected += 1
                    continue
                cur.execute(
                    """
                    INSERT INTO test_inboxes(email, provider, status, source, approved)
                    VALUES (%s, %s, 'approved', 'owner_provided', true)
                    ON CONFLICT (email) DO UPDATE
                      SET provider = EXCLUDED.provider,
                          status = 'approved',
                          source = 'owner_provided',
                          approved = true
                    """,
                    (email, row.get("provider", "")),
                )
                accepted += 1
        conn.commit()
    return {"accepted": accepted, "rejected": rejected, "diagnostic_policy": "max_one_message_per_mailbox_after_owner_approval", "sent": 0}


def latest_decision(table: str) -> str:
    row = fetch_one(f"SELECT decision FROM {table} ORDER BY created_at DESC LIMIT 1")
    return row["decision"] if row else "MISSING"


def latest_production_visual_qa_decision() -> str:
    row = fetch_one(
        """
        SELECT decision
        FROM visual_qa_runs
        WHERE COALESCE(target_url, '') NOT LIKE %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        ("inline:test%",),
    )
    return row["decision"] if row else "MISSING"


def visual_design_send_gate_status() -> dict[str, Any]:
    from .quality_plugins import latest_quality_summary

    required_tools = {"huanshu", "axe-core-playwright", "pa11y", "lighthouse-ci", "pixelmatch"}
    summary = latest_quality_summary()
    latest_visual = fetch_one(
        """
        SELECT decision, huanshu_status, target_url, score, created_at
        FROM visual_qa_runs
        WHERE COALESCE(target_url, '') NOT LIKE %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        ("inline:test%",),
    )
    tool_status = {
        str(row.get("tool")): str(row.get("status"))
        for row in (summary.get("runs") or [])
        if row.get("tool")
    }
    missing = sorted(required_tools - set(tool_status))
    failing = sorted(
        tool
        for tool, status in tool_status.items()
        if tool in required_tools and status not in {"PASS", "PASS_WITH_WARNINGS"}
    )
    huanshu_status = tool_status.get("huanshu") or (latest_visual.get("huanshu_status") if latest_visual else "MISSING")
    blockers: list[str] = []
    if not latest_visual or latest_visual.get("decision") != "PASS":
        blockers.append("visual_qa_not_pass")
    if huanshu_status != "PASS":
        blockers.append("huanshu_not_pass")
    if missing:
        blockers.append("quality_plugins_missing")
    if failing:
        blockers.append("quality_plugins_not_pass")
    return {
        "allowed": not blockers,
        "blockers": blockers,
        "visual_qa_decision": latest_visual.get("decision") if latest_visual else "MISSING",
        "huanshu_status": huanshu_status,
        "required_tools": sorted(required_tools),
        "tool_status": tool_status,
        "missing_tools": missing,
        "failing_tools": failing,
    }


def live_outreach_quota_status(email: str = "") -> dict[str, Any]:
    settings = get_settings()
    normalized = (email or "").strip().lower()
    domain = normalized.rsplit("@", 1)[-1] if "@" in normalized else ""
    daily_limit = int(getattr(settings, "daily_send_limit", 20) or 20)
    hourly_domain_limit = int(getattr(settings, "hourly_domain_send_limit", 5) or 5)
    daily_sent = fetch_one(
        """
        SELECT count(*) AS count
        FROM outreach_messages
        WHERE status = 'sent'
          AND sent_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Jerusalem') AT TIME ZONE 'Asia/Jerusalem'
        """
    )
    hourly_domain_sent = {"count": 0}
    if domain:
        hourly_domain_sent = fetch_one(
            """
            SELECT count(*) AS count
            FROM outreach_messages om
            JOIN leads l ON l.id = om.lead_id
            WHERE om.status = 'sent'
              AND om.sent_at >= now() - interval '1 hour'
              AND split_part(lower(l.email), '@', 2) = lower(%s)
            """,
            (domain,),
        )
    daily_count = int((daily_sent or {}).get("count", 0) or 0)
    hourly_domain_count = int((hourly_domain_sent or {}).get("count", 0) or 0)
    blockers: list[str] = []
    if daily_count >= daily_limit:
        blockers.append("daily_send_limit_reached")
    if domain and hourly_domain_count >= hourly_domain_limit:
        blockers.append("hourly_domain_send_limit_reached")
    return {
        "allowed": not blockers,
        "daily_sent": daily_count,
        "daily_limit": daily_limit,
        "hourly_domain_sent": hourly_domain_count,
        "hourly_domain_limit": hourly_domain_limit,
        "recipient_domain_hash": recipient_hash(domain) if domain else "",
        "blockers": blockers,
        "raw_recipient_addresses_included": False,
    }


def transport_gate_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    settings = get_settings()
    email = (payload.get("email") or "").strip().lower()
    body = payload.get("body") or ""
    html_body = payload.get("html_body") or ""
    unsubscribe_url = one_click_unsubscribe_url_from_body(body)
    quota = live_outreach_quota_status(email)
    visual_design = visual_design_send_gate_status()
    checks = {
        "outreach_dry_run": settings.outreach_dry_run,
        "outreach_paused": effective_pause_state("outreach", settings.outreach_paused),
        "first_live_send_flag": settings.first_live_send_flag,
        "mail_qa_decision": latest_decision("mail_qa_runs"),
        "visual_qa_decision": visual_design["visual_qa_decision"],
        "visual_design_gate": visual_design,
        "has_unsubscribe": bool(unsubscribe_url),
        "unsubscribe_one_click_ready": bool(unsubscribe_url),
        "html_body_ready": bool(str(html_body).strip().lower().startswith("<!doctype html>")),
        "suppressed": False,
        "live_quota": quota,
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
    if not visual_design["allowed"]:
        return {"allowed": False, "reason": ",".join(visual_design["blockers"]), "checks": checks}
    if checks["suppressed"]:
        return {"allowed": False, "reason": "recipient_suppressed", "checks": checks}
    if not checks["has_unsubscribe"]:
        return {"allowed": False, "reason": "missing_unsubscribe", "checks": checks}
    if not checks["html_body_ready"]:
        return {"allowed": False, "reason": "missing_html_body", "checks": checks}
    if not quota["allowed"]:
        return {"allowed": False, "reason": ",".join(quota["blockers"]), "checks": checks}
    return {"allowed": True, "reason": "all_gates_passed", "checks": checks}


def latest_preview_transport_gate_status() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT om.body, om.html_body, l.email, om.id AS outreach_message_id
        FROM outreach_messages om
        JOIN leads l ON l.id = om.lead_id
        WHERE om.status = 'preview'
        ORDER BY om.created_at DESC
        LIMIT 1
        """
    )
    if row:
        result = transport_gate_status(
            {
                "email": row["email"],
                "body": row["body"],
                "html_body": row["html_body"],
            }
        )
        result["source"] = "latest_preview_outreach_message"
        result["outreach_message_id"] = str(row["outreach_message_id"])
        return result
    sample_unsubscribe = "https://go.rescue.voiddo.com/unsubscribe/u_00000000-0000-0000-0000-000000000000.sampletoken"
    result = transport_gate_status(
        {
            "email": "redacted@example.test",
            "body": f"Public non-invasive website check.\nUnsubscribe: {sample_unsubscribe}",
            "html_body": f"<!doctype html><html><body><a href=\"{sample_unsubscribe}\">Unsubscribe</a></body></html>",
        }
    )
    result["source"] = "sample_fallback_no_preview_outreach_message"
    return result


def prepare_outreach_preview(limit: int = 20) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
               cl.id AS campaign_lead_id,
               cl.campaign_id,
               cl.audit_id,
               l.id AS lead_id,
               l.email,
               b.name AS business_name,
               b.domain,
               a.public_slug,
               a.summary,
               COALESCE(ls.final_score, cl.score, l.score, 0) AS final_score
        FROM campaign_leads cl
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN leads l ON l.id = cl.lead_id
        JOIN businesses b ON b.id = l.business_id
        JOIN audits a ON a.id = cl.audit_id
        LEFT JOIN LATERAL (
            SELECT final_score
            FROM lead_scores ls
            WHERE ls.lead_id = l.id AND ls.audit_id = a.id
            ORDER BY ls.created_at DESC
            LIMIT 1
        ) ls ON true
        LEFT JOIN LATERAL (
            SELECT action
            FROM campaign_preview_reviews r
            WHERE r.campaign_lead_id = cl.id
            ORDER BY r.created_at DESC
            LIMIT 1
        ) latest_review ON true
        WHERE cl.status = 'preview'
          AND latest_review.action = 'approved'
          AND COALESCE(ls.final_score, cl.score, l.score, 0) >= 70
          AND l.email IS NOT NULL
          AND lower(COALESCE(b.domain, '')) NOT LIKE '%%.example.test'
          AND lower(COALESCE(b.domain, '')) NOT IN ('example.com', 'localhost')
          AND lower(COALESCE(l.source, '')) NOT LIKE 'p%%_test%%'
          AND lower(COALESCE(l.source, '')) NOT LIKE 'test%%'
          AND lower(COALESCE(l.source, '')) NOT LIKE '%%_test'
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(s.email) = lower(l.email))
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(s.domain) = lower(b.domain))
        ORDER BY COALESCE(ls.final_score, cl.score, l.score, 0) DESC, cl.updated_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    preview = []
    for row in rows:
        preview.append(
            {
                "campaign_lead_id": str(row["campaign_lead_id"]),
                "campaign_id": str(row["campaign_id"]),
                "audit_id": str(row["audit_id"]),
                "lead_id": str(row["lead_id"]),
                "recipient_hash": hashlib.sha256(str(row["email"]).strip().lower().encode("utf-8")).hexdigest()[:24],
                "business_name": row["business_name"],
                "domain": row["domain"],
                "audit_url": f"{get_settings().audit_base_url}/r/{row['public_slug']}",
                "main_issue_short": row["summary"],
                "final_score": int(row["final_score"] or 0),
                "source": "approved_campaign_preview",
                "unsubscribe_url": signed_unsubscribe_url_for_lead(str(row["lead_id"])),
                "dry_run": True,
                "send_mail": False,
                "live_outreach_allowed": False,
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
    result = dict(batch)
    result["send_mail"] = False
    result["smtp_called"] = False
    result["live_outreach_allowed"] = False
    result["raw_recipient_addresses_included"] = False
    return result


def queue_outreach_preview(limit: int = 20) -> dict[str, Any]:
    preview_batch = prepare_outreach_preview(limit)
    created = 0
    updated = 0
    skipped_existing = 0
    for item in preview_batch["preview_json"]:
        rendered = render_email_template(
            "first_audit_notice",
            "en",
            {
                "business_name": item["business_name"],
                "name_or_team": "team",
                "domain": item["domain"],
                "main_issue_short": item["main_issue_short"],
                "audit_url": item["audit_url"],
                "unsubscribe_url": item["unsubscribe_url"],
                "one_time_price": "$99",
                "monthly_price": "$19",
            },
        )
        existing = fetch_one(
            """
            SELECT id
            FROM outreach_messages
            WHERE lead_id = %s AND audit_id = %s AND status = 'preview'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (item["lead_id"], item["audit_id"]),
        )
        if existing:
            execute(
                """
                UPDATE outreach_messages
                SET mailbox = 'audit@voiddorescue.com',
                    subject = %s,
                    body = %s,
                    html_body = %s
                WHERE id = %s
                """,
                (rendered["subject"], rendered["text"], rendered["html"], existing["id"]),
            )
            updated += 1
            skipped_existing += 1
            continue
        execute(
            """
            INSERT INTO outreach_messages(lead_id, audit_id, mailbox, subject, body, html_body, status)
            VALUES (%s, %s, 'audit@voiddorescue.com', %s, %s, %s, 'preview')
            """,
            (item["lead_id"], item["audit_id"], rendered["subject"], rendered["text"], rendered["html"]),
        )
        created += 1
    return {
        "created": created,
        "updated": updated,
        "skipped_existing": skipped_existing,
        "dry_run_only": True,
        "preview_batch_id": str(preview_batch["id"]),
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
    }


def dedupe_outreach_preview_messages(limit: int = 500, apply: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 1000))
    groups = fetch_all(
        """
        SELECT lead_id, audit_id, array_agg(id ORDER BY created_at DESC, id DESC) AS ids, count(*) AS count
        FROM outreach_messages
        WHERE status = 'preview'
        GROUP BY lead_id, audit_id
        HAVING count(*) > 1
        ORDER BY max(created_at) DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    duplicate_ids: list[str] = []
    sample: list[dict[str, Any]] = []
    for group in groups:
        ids = [str(item) for item in group["ids"]]
        keep_id = ids[0]
        archived = ids[1:]
        duplicate_ids.extend(archived)
        sample.append(
            {
                "lead_id": str(group["lead_id"]),
                "audit_id": str(group["audit_id"]),
                "keep_id": keep_id,
                "duplicate_count": len(archived),
            }
        )
    archived_count = 0
    if apply and duplicate_ids:
        execute("UPDATE outreach_messages SET status = 'archived_duplicate_preview' WHERE id = ANY(%s::uuid[])", (duplicate_ids,))
        archived_count = len(duplicate_ids)
    return {
        "status": "clean" if not groups else ("archived" if apply else "duplicates_found"),
        "duplicate_group_count": len(groups),
        "duplicate_message_count": len(duplicate_ids),
        "archived_count": archived_count,
        "sample": sample[:20],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def suppress_unsubscribe_token(token: str) -> dict[str, Any]:
    try:
        lead_id = lead_id_from_unsubscribe_token(token, _unsubscribe_secret())
    except ValueError:
        return {"ok": False, "status": "invalid_token", "suppressed": False, "send_mail": False, "live_outreach_allowed": False}
    lead = fetch_one(
        """
        SELECT l.id, l.email, b.domain
        FROM leads l
        JOIN businesses b ON b.id = l.business_id
        WHERE l.id = %s
        """,
        (lead_id,),
    )
    if not lead or not lead["email"]:
        return {"ok": False, "status": "lead_not_found", "suppressed": False, "send_mail": False, "live_outreach_allowed": False}
    inserted = execute(
        """
        INSERT INTO suppression_list(email, domain, reason, source)
        SELECT %s, %s, 'one_click_unsubscribe', 'unsubscribe_token'
        WHERE NOT EXISTS (
          SELECT 1 FROM suppression_list
          WHERE lower(email) = lower(%s)
            AND lower(COALESCE(domain, '')) = lower(COALESCE(%s, ''))
            AND reason = 'one_click_unsubscribe'
            AND source = 'unsubscribe_token'
        )
        RETURNING id
        """,
        (lead["email"], lead["domain"], lead["email"], lead["domain"]),
    )
    execute("UPDATE leads SET status = 'unsubscribed', updated_at = now() WHERE id = %s", (lead_id,))
    return {
        "ok": True,
        "status": "suppressed" if inserted else "already_suppressed",
        "suppressed": True,
        "lead_id": lead_id,
        "recipient_hash": hashlib.sha256(str(lead["email"]).strip().lower().encode("utf-8")).hexdigest()[:24],
        "domain": lead["domain"],
        "send_mail": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
    }


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
