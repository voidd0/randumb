from __future__ import annotations

from email.message import EmailMessage
from email.utils import make_msgid
import hashlib
import os
import re
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


def _recipient_hash(value: str) -> str:
    normalized = (value or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24] if normalized else ""


def _visual_design_gate() -> dict:
    required = {"huanshu", "axe-core-playwright", "pa11y", "lighthouse-ci", "pixelmatch"}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT decision, huanshu_status, target_url, score, created_at
                FROM visual_qa_runs
                WHERE COALESCE(target_url, '') NOT LIKE 'inline:test%%'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            visual = cur.fetchone()
            cur.execute(
                """
                SELECT DISTINCT ON (tool) tool, status, score, target, created_at
                FROM quality_plugin_runs
                ORDER BY tool, created_at DESC
                """
            )
            tools = [dict(row) for row in cur.fetchall()]
    tool_status = {str(row["tool"]): str(row["status"]) for row in tools}
    missing = sorted(required - set(tool_status))
    failing = sorted(tool for tool, status in tool_status.items() if tool in required and status not in {"PASS", "PASS_WITH_WARNINGS"})
    huanshu_status = tool_status.get("huanshu") or (visual["huanshu_status"] if visual else "MISSING")
    blockers = []
    if not visual or visual.get("decision") != "PASS":
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
        "visual_qa_decision": visual["decision"] if visual else "MISSING",
        "huanshu_status": huanshu_status,
        "required_tools": sorted(required),
        "tool_status": tool_status,
        "missing_tools": missing,
        "failing_tools": failing,
    }


def _count(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row["count"] or 0) if row else 0


def _runtime_control_enabled(cur, *keys: str) -> bool:
    if not keys:
        return False
    cur.execute("SELECT 1 FROM runtime_controls WHERE key = ANY(%s) AND value = true LIMIT 1", (list(keys),))
    return bool(cur.fetchone())


def unsubscribe_url_from_body(body: str) -> str | None:
    match = re.search(r"https?://[^\s<>()\"']+/unsubscribe/u_[0-9a-fA-F-]{36}\.[A-Za-z0-9_-]+", body or "")
    return match.group(0) if match else None


def _warmup_maturity(cur) -> dict:
    min_clean = max(1, int(os.environ.get("WARMUP_MIN_CLEAN_SENDS_BEFORE_OUTREACH", "5") or "5"))
    warmup_sent = _count(cur, "SELECT count(*) AS count FROM warmup_schedule WHERE status = 'sent'")
    verified_event_count = _count(
        cur,
        """
        SELECT count(*) AS count
        FROM email_events
        WHERE event_type = 'warmup_sent'
          AND created_at >= now() - interval '30 days'
          AND payload_json->>'policy' = 'neutral_calendar_warmup_no_sales_no_tracking'
          AND COALESCE(payload_json->>'schedule_id', '') <> ''
          AND COALESCE(payload_json->>'recipient_hash', '') <> ''
          AND COALESCE(payload_json->>'sender', '') LIKE '%%@voiddorescue.com'
        """,
    )
    verified_warmup_sent = max(warmup_sent, verified_event_count)
    legacy_event_count = _count(cur, "SELECT count(*) AS count FROM email_events WHERE event_type = 'warmup_sent'")
    recent_bounce = _count(cur, "SELECT count(*) AS count FROM mail_signals WHERE signal_type IN ('bounce','dsn') AND created_at >= now() - interval '24 hours'")
    recent_rate = _count(cur, "SELECT count(*) AS count FROM mail_signals WHERE signal_type = 'smtp_rate_limit' AND created_at >= now() - interval '24 hours'")
    recent_spam = _count(cur, "SELECT count(*) AS count FROM mail_signals WHERE signal_type = 'spam_signal' AND created_at >= now() - interval '24 hours'")
    recent_auth_failure = _count(cur, "SELECT count(*) AS count FROM mail_signals WHERE signal_type IN ('auth_failure','tls_failure','dkim_failure','dmarc_failure') AND created_at >= now() - interval '24 hours'")
    blockers = []
    if verified_warmup_sent < min_clean:
        blockers.append("warmup_clean_send_count_below_threshold")
    if recent_bounce:
        blockers.append("recent_bounce_or_dsn")
    if recent_rate:
        blockers.append("recent_rate_limit")
    if recent_spam:
        blockers.append("recent_spam_signal")
    if recent_auth_failure:
        blockers.append("recent_mail_auth_failure_signal")
    return {
        "allowed": not blockers,
        "warmup_sent_count": verified_warmup_sent,
        "warmup_schedule_sent_count": warmup_sent,
        "verified_warmup_event_count": verified_event_count,
        "legacy_warmup_event_count": legacy_event_count,
        "maturity_source": "warmup_schedule_sent" if warmup_sent >= verified_event_count else "verified_warmup_sent_events",
        "min_clean_sends_required": min_clean,
        "recent_bounce_count": recent_bounce,
        "recent_rate_limit_count": recent_rate,
        "recent_spam_signal_count": recent_spam,
        "recent_mail_auth_failure_count": recent_auth_failure,
        "blockers": blockers,
    }


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


def _live_quota(cur, email: str) -> dict:
    domain = (email or "").strip().lower().rsplit("@", 1)[-1] if "@" in (email or "") else ""
    daily_limit = max(1, int(os.environ.get("DAILY_SEND_LIMIT", "20") or "20"))
    hourly_domain_limit = max(1, int(os.environ.get("HOURLY_DOMAIN_SEND_LIMIT", "5") or "5"))
    daily_sent = _count(
        cur,
        """
        SELECT count(*) AS count
        FROM outreach_messages
        WHERE status = 'sent'
          AND sent_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Jerusalem') AT TIME ZONE 'Asia/Jerusalem'
        """,
    )
    hourly_domain_sent = 0
    if domain:
        hourly_domain_sent = _count(
            cur,
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
    blockers = []
    if daily_sent >= daily_limit:
        blockers.append("daily_send_limit_reached")
    if domain and hourly_domain_sent >= hourly_domain_limit:
        blockers.append("hourly_domain_send_limit_reached")
    return {
        "allowed": not blockers,
        "daily_sent": daily_sent,
        "daily_limit": daily_limit,
        "hourly_domain_sent": hourly_domain_sent,
        "hourly_domain_limit": hourly_domain_limit,
        "blockers": blockers,
    }


def transport_gate(email: str, body: str, campaign_id: str | None = None, html_body: str = "") -> tuple[bool, str, dict]:
    unsubscribe_url = unsubscribe_url_from_body(body)
    visual_design = _visual_design_gate()
    checks = {
        "outreach_dry_run": os.environ.get("OUTREACH_DRY_RUN", "true").lower() == "true",
        "outreach_paused": os.environ.get("OUTREACH_PAUSED", "true").lower() == "true",
        "runtime_outreach_paused": False,
        "first_live_send_flag": os.environ.get("FIRST_LIVE_SEND_FLAG", "false").lower() == "true",
        "mail_qa_decision": _latest_decision("mail_qa_runs"),
        "visual_qa_decision": visual_design["visual_qa_decision"],
        "visual_design_gate": visual_design,
        "has_unsubscribe": bool(unsubscribe_url),
        "unsubscribe_one_click_ready": bool(unsubscribe_url),
        "html_body_ready": bool(str(html_body or "").strip().lower().startswith("<!doctype html>")),
        "suppressed": False,
        "campaign_preflight": {"allowed": False, "reason": "not_checked"},
        "warmup_maturity": {"allowed": False, "reason": "not_checked"},
        "live_quota": {"allowed": False, "reason": "not_checked"},
    }
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (email,))
            checks["suppressed"] = bool(cur.fetchone())
            checks["campaign_preflight"] = _latest_campaign_preflight(cur, campaign_id)
            checks["warmup_maturity"] = _warmup_maturity(cur)
            checks["live_quota"] = _live_quota(cur, email)
            checks["runtime_outreach_paused"] = _runtime_control_enabled(cur, "pause_outreach", "pause_all_workers", "pause_workers")
    if checks["outreach_dry_run"]:
        return False, "outreach_dry_run_enabled", checks
    if checks["outreach_paused"] or checks["runtime_outreach_paused"] or not checks["first_live_send_flag"]:
        return False, "live_outreach_not_approved", checks
    if checks["mail_qa_decision"] != "PASS":
        return False, "mail_qa_not_passed", checks
    if checks["visual_qa_decision"] != "PASS":
        return False, "visual_qa_not_passed", checks
    if not visual_design["allowed"]:
        return False, ",".join(visual_design["blockers"]), checks
    if not checks["campaign_preflight"]["allowed"]:
        return False, checks["campaign_preflight"]["reason"], checks
    if not checks["warmup_maturity"]["allowed"]:
        return False, ",".join(checks["warmup_maturity"]["blockers"]), checks
    if checks["suppressed"]:
        return False, "recipient_suppressed", checks
    if not checks["has_unsubscribe"]:
        return False, "missing_unsubscribe", checks
    if not checks["html_body_ready"]:
        return False, "missing_html_body", checks
    if not checks["live_quota"]["allowed"]:
        return False, ",".join(checks["live_quota"]["blockers"]), checks
    return True, "all_gates_passed", checks


def send_message_if_allowed(message_id: str) -> dict:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, lead_id, audit_id, mailbox, subject, body, html_body, status FROM outreach_messages WHERE id = %s", (message_id,))
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
    allowed, reason, checks = transport_gate(email, message["body"], campaign_id, str(message.get("html_body") or ""))
    if not allowed:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO system_events(type, severity, message, payload_json) VALUES ('outreach.transport_blocked', 'warning', %s, %s)",
                    (reason, Jsonb({"message_id": message_id, "checks": checks})),
                )
                cur.execute("UPDATE outreach_messages SET status = 'transport_blocked' WHERE id = %s", (message_id,))
            conn.commit()
        return {"sent": False, "reason": reason, "checks": checks}

    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM_DEFAULT", "audit@voiddorescue.com")
    msg["To"] = email
    msg["Subject"] = message["subject"]
    unsubscribe_url = unsubscribe_url_from_body(message["body"])
    if unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    provider_message_id = make_msgid(domain="voiddorescue.com")
    msg["Message-ID"] = provider_message_id
    msg.set_content(message["body"])
    if message.get("html_body"):
        msg.add_alternative(message["html_body"], subtype="html")
    with smtplib.SMTP(os.environ.get("SMTP_HOST", "mail.voiddo.com"), int(os.environ.get("SMTP_PORT", "587")), timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(os.environ.get("SMTP_USERNAME", ""), os.environ.get("SMTP_PASSWORD", ""))
        smtp.send_message(msg)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE outreach_messages SET status = 'sent', sent_at = now(), provider_message_id = %s WHERE id = %s",
                (provider_message_id, message_id),
            )
            cur.execute(
                """
                INSERT INTO email_events(outreach_message_id, event_type, payload_json, mailbox, message_id)
                VALUES (%s, 'outreach_sent', %s, %s, %s)
                """,
                (
                    message_id,
                    Jsonb(
                        {
                            "recipient_hash": _recipient_hash(email),
                            "recipient_domain_hash": _recipient_hash(email.rsplit("@", 1)[-1] if "@" in email else ""),
                            "campaign_id": campaign_id or "",
                            "unsubscribe_one_click_ready": bool(unsubscribe_url),
                            "list_unsubscribe_header": bool(unsubscribe_url),
                            "smtp_result": "accepted",
                            "policy": "proof_based_outreach_with_one_click_unsubscribe",
                            "raw_recipient_included": False,
                        }
                    ),
                    message["mailbox"],
                    provider_message_id,
                ),
            )
        conn.commit()
    return {"sent": True, "reason": "sent", "message_id": provider_message_id}


def process_outreach_queue(limit: int = 1) -> dict:
    safe_limit = max(1, min(int(limit or 1), 5))
    min_spacing_minutes = max(1, int(os.environ.get("OUTREACH_MIN_SEND_SPACING_MINUTES", "24") or "24"))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM outreach_messages
                WHERE status = 'queued'
                  AND COALESCE(send_after, created_at) <= now()
                  AND NOT EXISTS (
                    SELECT 1
                    FROM outreach_messages recent
                    WHERE recent.status = 'sent'
                      AND recent.sent_at >= now() - (%s::text || ' minutes')::interval
                  )
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (min_spacing_minutes, safe_limit),
            )
            rows = cur.fetchall()
            ids = [str(row["id"]) for row in rows]
            if ids:
                cur.execute("UPDATE outreach_messages SET status = 'sending' WHERE id = ANY(%s::uuid[])", (ids,))
        conn.commit()
    sent = 0
    blocked = 0
    results = []
    for message_id in ids:
        try:
            result = send_message_if_allowed(message_id)
        except Exception as exc:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE outreach_messages
                        SET status = 'transport_failed'
                        WHERE id = %s
                        """,
                        (message_id,),
                    )
                    cur.execute(
                        "INSERT INTO system_events(type, severity, message, payload_json) VALUES ('outreach.transport_failed', 'error', %s, %s)",
                        (type(exc).__name__, Jsonb({"message_id": message_id})),
                    )
                conn.commit()
            result = {"sent": False, "reason": type(exc).__name__}
        results.append({"message_id": message_id, "sent": bool(result.get("sent")), "reason": result.get("reason")})
        if result.get("sent"):
            sent += 1
        else:
            blocked += 1
            break
    return {"processed": len(ids), "sent": sent, "blocked": blocked, "results": results}
