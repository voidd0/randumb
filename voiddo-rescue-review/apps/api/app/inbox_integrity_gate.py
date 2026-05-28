from __future__ import annotations

import os
import re
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}

RAW_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
HARD_STOP = {"angry", "legal_threat", "security_accusation", "custom_technical_request", "wants_call", "paid"}
SIGNAL_CLASSES = {"bounce", "auto_reply", "out_of_office", "interested", "ask_price", "ask_details"}


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"] or 0) if row else 0


def _raw_email_hits(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for row in rows:
        payload = str(row.get("payload_json") or "")
        external_matches = [
            match.group(0).lower()
            for match in RAW_EMAIL_RE.finditer(payload)
            if not match.group(0).lower().endswith(("@voiddo.com", "@voiddorescue.com"))
        ]
        if external_matches:
            hits.append({"id": str(row.get("id")), "type": row.get("type") or row.get("event_type") or "", "created_at": str(row.get("created_at") or "")})
    return hits


def redact_legacy_inbox_sender_payloads() -> dict[str, int]:
    email_events = execute(
        """
        UPDATE email_events
        SET payload_json = (payload_json - 'sender') || jsonb_build_object(
            'sender_hash', COALESCE(NULLIF(payload_json->>'sender_hash', ''), 'legacy_redacted'),
            'legacy_sender_redacted', true
        )
        WHERE event_type IN ('inbound_reply', 'studio_mail_inbound')
          AND payload_json ? 'sender'
        RETURNING id
        """
    )
    system_events = execute(
        """
        UPDATE system_events
        SET payload_json = (payload_json - 'sender') || jsonb_build_object(
            'sender_hash', COALESCE(NULLIF(payload_json->>'sender_hash', ''), 'legacy_redacted'),
            'legacy_sender_redacted', true
        )
        WHERE (type LIKE 'inbox.%%' OR type LIKE 'studio_mail.%%' OR type = 'deliverability.spam_observed')
          AND payload_json ? 'sender'
        RETURNING id
        """
    )
    return {
        "email_events_redacted": 1 if email_events else 0,
        "system_events_redacted": 1 if system_events else 0,
    }


def run_inbox_integrity_gate(window_hours: int = 24, store: bool = True) -> dict[str, Any]:
    hours = max(1, min(int(window_hours or 24), 168))
    redaction = redact_legacy_inbox_sender_payloads()
    events = [dict(row) for row in fetch_all(
        """
        SELECT id, event_type, classification, human_review_required, payload_json, mailbox, message_id, created_at
        FROM email_events
        WHERE event_type IN ('inbound_reply', 'studio_mail_inbound')
          AND created_at >= now() - (%s::text || ' hours')::interval
        ORDER BY created_at DESC
        LIMIT 200
        """,
        (hours,),
    )]
    system_events = [dict(row) for row in fetch_all(
        """
        SELECT id, type, payload_json, created_at
        FROM system_events
        WHERE (type LIKE 'inbox.%%' OR type LIKE 'studio_mail.%%' OR type = 'deliverability.spam_observed')
          AND created_at >= now() - (%s::text || ' hours')::interval
        ORDER BY created_at DESC
        LIMIT 200
        """,
        (hours,),
    )]
    blockers: list[str] = []
    warnings: list[str] = []

    event_raw_hits = _raw_email_hits(events)
    system_raw_hits = _raw_email_hits(system_events)
    if event_raw_hits:
        blockers.append("raw_email_in_recent_email_event_payload")
    if system_raw_hits:
        blockers.append("raw_email_in_recent_system_event_payload")

    unsafe_events = [row for row in events if row.get("classification") in HARD_STOP]
    unsafe_without_review = [row for row in unsafe_events if not row.get("human_review_required")]
    if unsafe_without_review:
        blockers.append("hard_stop_reply_without_human_review")

    bounce_events = [row for row in events if row.get("classification") == "bounce"]
    bounce_without_signal = [
        row for row in bounce_events
        if not fetch_one("SELECT 1 FROM mail_signals WHERE message_id = %s AND signal_type IN ('bounce', 'dsn') LIMIT 1", (row.get("message_id"),))
    ]
    if bounce_without_signal:
        blockers.append("bounce_reply_without_mail_signal")

    spam_observations = _count(
        """
        SELECT count(*) AS count
        FROM mail_signals
        WHERE signal_type = 'spam_signal'
          AND created_at >= now() - (%s::text || ' hours')::interval
        """,
        (hours,),
    )
    signal_events = [row for row in events if row.get("classification") in SIGNAL_CLASSES]
    if signal_events and _count(
        """
        SELECT count(*) AS count
        FROM mail_signals
        WHERE source IN ('inbox_engine', 'inbox_worker', 'studio_mail_monitor')
          AND created_at >= now() - (%s::text || ' hours')::interval
        """,
        (hours,),
    ) <= 0:
        warnings.append("inbound_signal_events_without_recent_mail_signals")

    unsubscribe_events = [row for row in events if row.get("classification") == "unsubscribe"]
    suppression_count = _count(
        """
        SELECT count(*) AS count
        FROM suppression_list
        WHERE source IN ('inbox', 'studio_mail_monitor')
          AND created_at >= now() - (%s::text || ' hours')::interval
        """,
        (hours,),
    )
    if unsubscribe_events and suppression_count <= 0:
        blockers.append("unsubscribe_without_recent_suppression")

    auto_replies_paused = os.environ.get("AUTO_REPLIES_PAUSED", "true").strip().lower() != "false"
    if not auto_replies_paused:
        blockers.append("auto_replies_not_paused")

    result = json_safe(
        {
            "status": "completed" if not blockers else "blocked",
            "decision": "PASS_INBOX_INTEGRITY_GATE" if not blockers else "FAIL_INBOX_INTEGRITY_GATE",
            "window_hours": hours,
            "event_count": len(events),
            "system_event_count": len(system_events),
            "unsafe_event_count": len(unsafe_events),
            "bounce_event_count": len(bounce_events),
            "spam_signal_count": spam_observations,
            "unsubscribe_event_count": len(unsubscribe_events),
            "suppression_count": suppression_count,
            "legacy_email_events_redacted": redaction["email_events_redacted"],
            "legacy_system_events_redacted": redaction["system_events_redacted"],
            "auto_replies_paused": auto_replies_paused,
            "raw_email_event_payload_count": len(event_raw_hits),
            "raw_email_system_event_payload_count": len(system_raw_hits),
            "blockers": blockers,
            "warnings": warnings,
            **SAFE_FLAGS,
        }
    )
    if store:
        execute(
            "INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at) VALUES ('inbox_integrity_gate_agent', %s, %s, now(), now())",
            ("completed" if not blockers else "blocked", Jsonb(result)),
        )
    return result
