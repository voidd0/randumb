from __future__ import annotations

from typing import Any

from .config import get_settings
from .db import fetch_all, fetch_one
from .p0 import json_safe, latest_mail_qa_decision, mail_signal_summary, runtime_state_snapshot, warmup_calendar_health


def _count(sql: str, params: tuple = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def _group_counts(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in fetch_all(sql, params)]


def _latest_rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in fetch_all(sql, params)]


def mailer_autonomy_ledger() -> dict[str, Any]:
    settings = get_settings()
    runtime = runtime_state_snapshot()
    signals = mail_signal_summary(24)
    warmup = warmup_calendar_health()
    controls = _group_counts(
        """
        SELECT key, value, source, reason, updated_at
        FROM runtime_controls
        WHERE key IN ('pause_scanner', 'pause_outreach', 'pause_warmup', 'pause_auto_replies', 'pause_all_workers')
        ORDER BY key
        """
    )
    owner_commands = {
        "total": _count("SELECT count(*) FROM owner_commands"),
        "latest": _latest_rows(
            """
            SELECT command, risk_level, status, executed_at, created_at
            FROM owner_commands
            ORDER BY created_at DESC
            LIMIT 5
            """
        ),
    }
    inbound = {
        "threads_by_classification": _group_counts(
            """
            SELECT coalesce(classification, 'unclassified') AS classification, count(*) AS count
            FROM inbox_threads
            GROUP BY coalesce(classification, 'unclassified')
            ORDER BY classification
            """
        ),
        "human_review_required": _count("SELECT count(*) FROM inbox_threads WHERE human_review_required"),
        "email_events_by_type": _group_counts(
            """
            SELECT event_type, count(*) AS count
            FROM email_events
            GROUP BY event_type
            ORDER BY event_type
            """
        ),
    }
    outbound = {
        "messages_by_status": _group_counts(
            """
            SELECT status, count(*) AS count
            FROM outreach_messages
            GROUP BY status
            ORDER BY status
            """
        ),
        "live_sent_count": _count("SELECT count(*) FROM outreach_messages WHERE status = 'sent'"),
        "outbound_decisions_by_status": _group_counts(
            """
            SELECT status, action, reason, count(*) AS count
            FROM outbound_mailer_decisions
            GROUP BY status, action, reason
            ORDER BY status, action, reason
            """
        ),
        "drafts_by_status": _group_counts(
            """
            SELECT status, category, count(*) AS count
            FROM mailer_drafts
            GROUP BY status, category
            ORDER BY status, category
            """
        ),
    }
    throttle = {
        "states": _count("SELECT count(*) FROM mail_throttle_state"),
        "backoff_active": _count("SELECT count(*) FROM mail_throttle_state WHERE backoff_until IS NOT NULL AND backoff_until > now()"),
        "by_scope": _group_counts(
            """
            SELECT scope, count(*) AS count, max(updated_at) AS updated_at
            FROM mail_throttle_state
            GROUP BY scope
            ORDER BY scope
            """
        ),
    }
    suppression = {
        "total": _count("SELECT count(*) FROM suppression_list"),
        "by_reason": _group_counts(
            """
            SELECT reason, count(*) AS count
            FROM suppression_list
            GROUP BY reason
            ORDER BY reason
            """
        ),
    }
    gate_blockers: list[str] = []
    if settings.outreach_paused:
        gate_blockers.append("outreach_paused_env")
    if not settings.first_live_send_flag:
        gate_blockers.append("first_live_send_flag_false")
    if settings.auto_replies_paused:
        gate_blockers.append("auto_replies_paused_env")
    if signals["bounce_or_dsn_count"] > 0:
        gate_blockers.append("recent_bounce_or_dsn")
    if signals["rate_limit_count"] > 0:
        gate_blockers.append("recent_rate_limit")
    if latest_mail_qa_decision() != "PASS":
        gate_blockers.append("mail_qa_not_pass")
    if warmup["scheduled_total"] <= 0:
        gate_blockers.append("no_warmup_schedule")

    result = {
        "policy": "autonomous_mailer_all_io_gated_no_raw_addresses",
        "runtime": runtime,
        "controls": controls,
        "owner_commands": owner_commands,
        "inbound": inbound,
        "outbound": outbound,
        "signals": signals,
        "throttle": throttle,
        "suppression": suppression,
        "warmup": warmup,
        "gates": {
            "live_outreach_allowed": False,
            "auto_replies_allowed": not settings.auto_replies_paused and not gate_blockers,
            "warmup_natural_timer_only": True,
            "blockers": gate_blockers,
            "send_mail_from_ledger": False,
        },
        "privacy": {
            "raw_recipient_addresses_included": False,
            "raw_owner_address_included": False,
            "raw_subjects_or_bodies_included": False,
        },
    }
    return json_safe(result)
