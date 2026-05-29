from __future__ import annotations

import re
from collections import Counter
from email import message_from_bytes
from email.message import Message
import imaplib
import ssl
from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .p0 import email_provider, json_safe, recipient_hash, set_runtime_control


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
BOUNCE_REASON_PATTERNS = {
    "mailbox_unavailable": ("mailbox unavailable", "user unknown", "recipient address rejected", "no such user", "address not found", "does not exist"),
    "domain_not_found": ("domain not found", "host or domain name not found", "no mx", "dns error", "unrouteable address"),
    "blocked_policy": ("blocked", "spam", "policy", "reputation", "blacklist", "denied", "rejected due to"),
    "temporary_defer": ("rate", "temporarily", "try again later", "greylist", "deferred"),
}


def _safe_summary(value: str | None) -> str:
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", value or "")
    return text[:180]


def _bounce_reason(text: str) -> str:
    lowered = (text or "").lower()
    for reason, markers in BOUNCE_REASON_PATTERNS.items():
        if any(marker in lowered for marker in markers):
            return reason
    return "unknown"


def _safe_provider_label(provider: str | None) -> str:
    label = (provider or "unknown").lower()
    if label in {"internal", "gmail", "microsoft", "icloud", "proton", "yahoo", "unknown"}:
        return label
    return "other_external"


def _count(query: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(query, params)
    return int((row or {}).get("count", 0) or 0)


def _signal_key(row: dict[str, Any]) -> str:
    if row.get("message_id"):
        return str(row["message_id"])
    return "|".join(
        [
            str(row.get("source") or ""),
            str(row.get("mailbox") or ""),
            str(row.get("created_at") or ""),
            str(row.get("raw_summary") or ""),
        ]
    )


def _mailbox_credentials(mailbox: str) -> tuple[str, str]:
    settings = get_settings()
    if mailbox == "audit":
        return settings.imap_username_audit, settings.imap_password_audit
    if mailbox == "fix":
        return settings.imap_username_fix, settings.imap_password_fix
    if mailbox == "support":
        return settings.imap_username_support, settings.imap_password_support
    return "", ""


def _tls_context() -> ssl.SSLContext:
    settings = get_settings()
    if settings.mail_tls_verify:
        return ssl.create_default_context()
    return ssl._create_unverified_context()


def _fetch_raw_email(mailbox: str, uid: str) -> bytes:
    settings = get_settings()
    username, password = _mailbox_credentials(mailbox)
    if not username or not password:
        return b""
    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, ssl_context=_tls_context(), timeout=30) as imap:
        imap.login(username, password)
        imap.select("INBOX")
        status, fetched = imap.uid("fetch", str(uid), "(BODY.PEEK[])")
        imap.logout()
    if status != "OK" or not fetched:
        return b""
    for item in fetched:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            return item[1]
    return b""


def _message_text(msg: Message) -> str:
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in {"text/plain", "message/delivery-status"}:
                payload = part.get_payload(decode=True)
                if payload:
                    parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
                else:
                    parts.append(str(part))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            parts.append(payload.decode(msg.get_content_charset() or "utf-8", errors="replace"))
        else:
            parts.append(str(msg))
    return "\n".join(parts)


def _first_header(payload: str, names: tuple[str, ...]) -> str:
    for name in names:
        match = re.search(rf"^{re.escape(name)}:\s*(.+)$", payload or "", flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).strip()
            if ";" in value:
                value = value.split(";", 1)[1].strip()
            return value
    return ""


def _extract_dsn_details(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {"ok": False, "reason": "empty_raw_message"}
    msg = message_from_bytes(raw)
    raw_text = raw.decode("utf-8", errors="replace")
    text = f"{_message_text(msg)}\n{raw_text}"
    bounced_recipient = _first_header(text, ("Final-Recipient", "Original-Recipient", "X-Failed-Recipients"))
    if bounced_recipient:
        found = EMAIL_RE.search(bounced_recipient)
        bounced_recipient = found.group(0).lower() if found else ""
    original_message_id = ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_type() == "message/rfc822":
            payload = part.get_payload()
            original = payload[0] if isinstance(payload, list) and payload else None
            if original:
                original_message_id = str(original.get("Message-ID") or "").strip()
                if not bounced_recipient:
                    found = EMAIL_RE.search(str(original.get("To") or ""))
                    bounced_recipient = found.group(0).lower() if found else ""
                break
    if not original_message_id:
        original_message_id = _first_header(text, ("Original-Message-ID", "Message-ID"))
    diagnostic = _first_header(text, ("Diagnostic-Code", "Status", "Remote-MTA"))
    reason = _bounce_reason(f"{text}\n{diagnostic}")
    return {
        "ok": bool(bounced_recipient or original_message_id or diagnostic),
        "bounced_recipient": bounced_recipient,
        "recipient_hash": recipient_hash(bounced_recipient),
        "provider": email_provider(bounced_recipient),
        "original_message_id": original_message_id,
        "original_message_id_present": bool(original_message_id),
        "diagnostic_present": bool(diagnostic),
        "reason": reason,
    }


def backfill_bounce_dsn_details(window_hours: int = 24, limit: int = 20, apply: bool = True) -> dict[str, Any]:
    hours = max(1, min(int(window_hours or 24), 168))
    safe_limit = max(1, min(int(limit or 20), 100))
    rows = [dict(row) for row in fetch_all(
        """
        SELECT mailbox, uid, message_id, created_at
        FROM email_events
        WHERE event_type = 'inbound_reply'
          AND classification = 'bounce'
          AND created_at >= now() - (%s || ' hours')::interval
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (hours, safe_limit),
    )]
    processed = 0
    enriched = 0
    suppressed = 0
    domain_suppressed = 0
    linked = 0
    outreach_marked_bounced = 0
    samples = []
    for row in rows:
        processed += 1
        details = _extract_dsn_details(_fetch_raw_email(str(row["mailbox"]), str(row["uid"])))
        if not details.get("ok"):
            samples.append({"mailbox": row["mailbox"], "uid_present": bool(row.get("uid")), "status": "not_enriched", "reason": details.get("reason")})
            continue
        enriched += 1
        outreach_row = None
        if details.get("original_message_id"):
            outreach_row = fetch_one(
                "SELECT id, lead_id FROM outreach_messages WHERE provider_message_id = %s LIMIT 1",
                (details["original_message_id"],),
            )
        linked += 1 if outreach_row else 0
        if apply:
            if details.get("bounced_recipient"):
                recipient_domain = details["bounced_recipient"].rsplit("@", 1)[-1].lower() if "@" in details["bounced_recipient"] else ""
                execute(
                    """
                    INSERT INTO suppression_list(email, reason, source)
                    SELECT %s, %s, 'inbox_bounce'
                    WHERE NOT EXISTS (
                      SELECT 1 FROM suppression_list
                      WHERE lower(email) = lower(%s)
                        AND source = 'inbox_bounce'
                    )
                    """,
                    (details["bounced_recipient"], f"bounce_{details['reason']}", details["bounced_recipient"]),
                )
                suppressed += 1
                if recipient_domain and details.get("reason") == "domain_not_found":
                    execute(
                        """
                        INSERT INTO suppression_list(domain, reason, source)
                        SELECT %s, %s, 'inbox_bounce_domain'
                        WHERE NOT EXISTS (
                          SELECT 1 FROM suppression_list
                          WHERE lower(domain) = lower(%s)
                            AND source = 'inbox_bounce_domain'
                        )
                        """,
                        (recipient_domain, "bounce_domain_not_found", recipient_domain),
                    )
                    domain_suppressed += 1
            execute(
                """
                UPDATE mail_signals
                SET recipient_hash = COALESCE(NULLIF(%s, ''), recipient_hash),
                    provider = COALESCE(NULLIF(%s, ''), provider),
                    message_id = COALESCE(NULLIF(%s, ''), message_id),
                    raw_summary = %s
                WHERE signal_type = 'bounce'
                  AND source = 'inbox_worker'
                  AND mailbox = %s
                  AND message_id = %s
                """,
                (
                    details.get("recipient_hash") or "",
                    details.get("provider") or "",
                    details.get("original_message_id") or "",
                    f"classified:bounce:{details['reason']}:dsn_backfilled",
                    row["mailbox"],
                    row["message_id"],
                ),
            )
            execute(
                """
                UPDATE email_events
                SET payload_json = payload_json || %s
                WHERE event_type = 'inbound_reply'
                  AND mailbox = %s
                  AND uid = %s
                  AND message_id = %s
                """,
                (
                    Jsonb(
                        {
                            "dsn_backfilled": True,
                            "recipient_hash": details.get("recipient_hash") or "",
                            "recipient_provider": _safe_provider_label(details.get("provider")),
                            "original_message_id_present": bool(details.get("original_message_id")),
                            "reason": details["reason"],
                            "matched_outreach": bool(outreach_row),
                        }
                    ),
                    row["mailbox"],
                    row["uid"],
                    row["message_id"],
                ),
            )
            if outreach_row:
                updated = execute(
                    """
                    UPDATE outreach_messages
                    SET status = 'bounced',
                        bounced_at = COALESCE(bounced_at, now())
                    WHERE id = %s
                    RETURNING id
                    """,
                    (outreach_row["id"],),
                )
                outreach_marked_bounced += 1 if updated else 0
                if outreach_row.get("lead_id"):
                    execute(
                        "UPDATE leads SET status = 'bounced', updated_at = now() WHERE id = %s",
                        (outreach_row["lead_id"],),
                    )
        samples.append(
            {
                "mailbox": row["mailbox"],
                "uid_present": bool(row.get("uid")),
                "status": "enriched",
                "recipient_hash_present": bool(details.get("recipient_hash")),
                "provider": _safe_provider_label(details.get("provider")),
                "original_message_id_present": bool(details.get("original_message_id")),
                "matched_outreach": bool(outreach_row),
                "reason": details["reason"],
            }
        )
    result = json_safe(
        {
            "status": "completed",
            "window_hours": hours,
            "processed": processed,
            "enriched": enriched,
            "suppression_upsert_attempts": suppressed,
            "domain_suppression_upsert_attempts": domain_suppressed,
            "linked_outreach_count": linked,
            "outreach_marked_bounced": outreach_marked_bounced,
            "apply": apply,
            "samples": samples[:10],
            **SAFE_FLAGS,
        }
    )
    if apply:
        execute(
            """
            INSERT INTO agent_runs(agent, status, started_at, completed_at, result_json)
            VALUES ('bounce_dsn_backfill_agent', 'completed', now(), now(), %s)
            """,
            (Jsonb(result),),
        )
    return result


def canary_bounce_recovery(window_hours: int = 24, apply_pause: bool = True, store: bool = True) -> dict[str, Any]:
    """No-send recovery planner for bounce/DSN signals seen during a live canary.

    This deliberately does not retry, requeue or unpause. It gives the autonomous
    loop a redacted recovery state so workers do not continue sending while the
    canary has unresolved mail reputation signals.
    """
    hours = max(1, min(int(window_hours or 24), 168))
    if store:
        backfill_bounce_dsn_details(window_hours=hours, limit=50, apply=True)
    signals = [dict(row) for row in fetch_all(
        """
        SELECT signal_type, severity, source, mailbox, recipient_hash, provider,
               message_id, raw_summary, created_at
        FROM mail_signals
        WHERE signal_type IN ('bounce', 'dsn')
          AND created_at >= now() - (%s || ' hours')::interval
        ORDER BY created_at DESC
        LIMIT 200
        """,
        (hours,),
    )]
    signal_keys = {_signal_key(row) for row in signals}
    message_ids = sorted({str(row["message_id"]) for row in signals if row.get("message_id")})
    linked_rows = []
    if message_ids:
        linked_rows = [dict(row) for row in fetch_all(
            """
            SELECT om.id, om.provider_message_id, om.sent_at, a.domain,
                   lower(split_part(COALESCE(l.email, ''), '@', 2)) AS recipient_domain
            FROM outreach_messages om
            LEFT JOIN leads l ON l.id = om.lead_id
            LEFT JOIN audits a ON a.id = om.audit_id
            WHERE om.status IN ('sent', 'bounced')
              AND om.provider_message_id = ANY(%s)
            ORDER BY om.sent_at DESC NULLS LAST
            LIMIT 100
            """,
            (message_ids,),
        )]
    blocked_rows = [dict(row) for row in fetch_all(
        """
        SELECT om.id, om.status, om.created_at, om.send_after,
               lower(split_part(COALESCE(l.email, ''), '@', 2)) AS recipient_domain
        FROM outreach_messages om
        LEFT JOIN leads l ON l.id = om.lead_id
        WHERE om.status IN ('failed', 'blocked', 'transport_blocked')
        ORDER BY om.created_at DESC
        LIMIT 50
        """
    )]
    bounced_rows = [dict(row) for row in fetch_all(
        """
        SELECT om.id, om.status, om.created_at, om.bounced_at,
               lower(split_part(COALESCE(l.email, ''), '@', 2)) AS recipient_domain
        FROM outreach_messages om
        LEFT JOIN leads l ON l.id = om.lead_id
        WHERE om.status = 'bounced'
        ORDER BY COALESCE(om.bounced_at, om.created_at) DESC
        LIMIT 50
        """
    )]
    queued_count = _count("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    sent_count = _count("SELECT count(*) AS count FROM outreach_messages WHERE status = 'sent'")
    inbox_bounce_suppression_count = _count(
        """
        SELECT count(*) AS count
        FROM suppression_list
        WHERE source = 'inbox_bounce'
          AND created_at >= now() - (%s || ' hours')::interval
        """,
        (hours,),
    )
    reason_counts = Counter()
    provider_counts = Counter()
    for row in signals:
        summary = str(row.get("raw_summary") or "")
        parts = summary.split(":")
        reason = "unknown"
        if "bounce" in parts:
            index = parts.index("bounce")
            if index + 1 < len(parts):
                reason = parts[index + 1] or "unknown"
        reason_counts[reason or "unknown"] += 1
        provider_counts[_safe_provider_label(row.get("provider"))] += 1

    blockers: list[str] = []
    if signals:
        blockers.append("recent_bounce_or_dsn")
    if len(linked_rows) < len(signal_keys):
        blockers.append("unlinked_bounce_or_dsn_signals")
    if blocked_rows:
        blockers.append("blocked_outreach_rows_present")

    pause_applied = False
    if blockers and apply_pause:
        set_runtime_control("pause_outreach", True, "canary_bounce_recovery", ",".join(blockers))
        pause_applied = True

    decision = "KEEP_PAUSED_RECOVER_BOUNCES" if blockers else "CLEAN_NO_BOUNCE_RECOVERY_NEEDED"
    next_action = (
        "classify_dsn_reasons_suppress_failed_recipients_wait_clean_window"
        if blockers
        else "canary_can_be_rechecked_by_scale_plan"
    )
    result = json_safe(
        {
            "status": "blocked" if blockers else "clean",
            "decision": decision,
            "next_action": next_action,
            "window_hours": hours,
            "sent_count": sent_count,
            "queued_count": queued_count,
            "bounce_or_dsn_signal_count": len(signals),
            "distinct_signal_count": len(signal_keys),
            "linked_sent_message_count": len(linked_rows),
            "unlinked_signal_count": max(0, len(signal_keys) - len(linked_rows)),
            "blocked_outreach_row_count": len(blocked_rows),
            "bounced_outreach_row_count": len(bounced_rows),
            "inbox_bounce_suppression_count": inbox_bounce_suppression_count,
            "reason_counts": dict(reason_counts),
            "provider_counts": dict(provider_counts),
            "pause_outreach_applied": pause_applied,
            "requeue_allowed": False,
            "unpause_allowed": False,
            "blockers": blockers,
            "signal_sample": [
                {
                    "signal_type": row["signal_type"],
                    "severity": row["severity"],
                    "source": row["source"],
                    "mailbox": row["mailbox"],
                    "provider": _safe_provider_label(row.get("provider")),
                    "recipient_hash_present": bool(row.get("recipient_hash")),
                    "message_id_present": bool(row.get("message_id")),
                    "raw_summary": _safe_summary(row.get("raw_summary")),
                    "created_at": row["created_at"],
                }
                for row in signals[:10]
            ],
            "linked_sent_sample": [
                {
                    "outreach_message_id": str(row["id"]),
                    "provider_message_id_present": bool(row.get("provider_message_id")),
                    "sent_at": row.get("sent_at"),
                    "audit_domain_hash": recipient_hash(row.get("domain") or ""),
                    "recipient_domain_hash": recipient_hash(row.get("recipient_domain") or ""),
                }
                for row in linked_rows[:10]
            ],
            "blocked_outreach_sample": [
                {
                    "outreach_message_id": str(row["id"]),
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "send_after": row.get("send_after"),
                    "recipient_domain_hash": recipient_hash(row.get("recipient_domain") or ""),
                }
                for row in blocked_rows[:10]
            ],
            "bounced_outreach_sample": [
                {
                    "outreach_message_id": str(row["id"]),
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "bounced_at": row.get("bounced_at"),
                    "recipient_domain_hash": recipient_hash(row.get("recipient_domain") or ""),
                }
                for row in bounced_rows[:10]
            ],
            **SAFE_FLAGS,
        }
    )
    if store:
        execute(
            """
            INSERT INTO agent_runs(agent, status, started_at, completed_at, result_json)
            VALUES ('canary_bounce_recovery_agent', %s, now(), now(), %s)
            """,
            ("blocked" if blockers else "completed", Jsonb(result)),
        )
        execute(
            "INSERT INTO system_events(type, severity, message, payload_json) VALUES ('outreach.canary_bounce_recovery', %s, %s, %s)",
            (
                "warning" if blockers else "info",
                decision,
                Jsonb(
                    {
                        "decision": decision,
                        "blockers": blockers,
                        "bounce_or_dsn_signal_count": len(signals),
                        "blocked_outreach_row_count": len(blocked_rows),
                        "bounced_outreach_row_count": len(bounced_rows),
                        "send_mail": False,
                    }
                ),
            ),
        )
    return result


def latest_canary_bounce_recovery_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, agent, status, result_json, created_at, completed_at
        FROM agent_runs
        WHERE agent = 'canary_bounce_recovery_agent'
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 50)),),
    )
    return json_safe({"count": len(rows), "runs": [dict(row) for row in rows], **SAFE_FLAGS})
