from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_one
from .mailer_autonomy import run_clean_window_recovery
from .p0 import json_safe, latest_mail_qa_decision, mail_signal_summary, warmup_calendar_health


BLOCKING_SIGNAL_TYPES = ("bounce", "dsn", "smtp_rate_limit", "spam_signal")


def latest_blocking_signal_next_safe_at(window_hours: int = 24) -> str | None:
    row = fetch_one(
        """
        SELECT max(created_at) + (%s || ' hours')::interval AS next_safe_at
        FROM mail_signals
        WHERE signal_type = ANY(%s)
          AND created_at >= now() - (%s || ' hours')::interval
        """,
        (window_hours, list(BLOCKING_SIGNAL_TYPES), window_hours),
    )
    if not row or not row["next_safe_at"]:
        return None
    return row["next_safe_at"].isoformat()


def warmup_resume_precheck(signals: dict[str, Any], mail_qa_decision: str) -> dict[str, Any]:
    warmup = warmup_calendar_health()
    blockers: list[str] = []
    if signals["bounce_or_dsn_count"] > 0:
        blockers.append("recent_bounce_or_dsn")
    if signals["rate_limit_count"] > 0:
        blockers.append("recent_rate_limit")
    if signals["spam_signal_count"] > 0:
        blockers.append("recent_spam_signal")
    if mail_qa_decision != "PASS":
        blockers.append("mail_qa_not_pass")
    if warmup["scheduled_total"] <= 0:
        blockers.append("no_scheduled_warmup")
    allowed = not blockers
    return {
        "allowed": allowed,
        "blockers": blockers,
        "warmup": warmup,
        "policy": "precheck_only_no_send",
    }


def clean_window_recheck(window_hours: int = 24, run_recovery_if_clear: bool = True) -> dict[str, Any]:
    signals = mail_signal_summary(window_hours)
    next_safe_at = latest_blocking_signal_next_safe_at(window_hours)
    signal_window_clear = not next_safe_at
    mail_qa_decision = latest_mail_qa_decision()
    recovery = None
    if signal_window_clear and run_recovery_if_clear:
        recovery = run_clean_window_recovery(window_hours)
        mail_qa_decision = recovery.get("mail_qa_decision") or mail_qa_decision
    warmup_gate = warmup_resume_precheck(signals, mail_qa_decision)
    if not signal_window_clear:
        status = "blocked_recent_signals"
    elif mail_qa_decision != "PASS":
        status = "blocked_mail_qa"
    elif warmup_gate["allowed"]:
        status = "ready_natural_warmup_only"
    else:
        status = "blocked_warmup_gate"
    result = {
        "signals": signals,
        "next_safe_at": next_safe_at,
        "signal_window_clear": signal_window_clear,
        "mail_qa_decision": mail_qa_decision,
        "warmup_gate": warmup_gate,
        "recovery": recovery,
        "live_outreach_allowed": False,
        "sends_started": False,
    }
    row = execute(
        """
        INSERT INTO clean_window_recheck_runs(
          status, window_hours, signal_window_clear, latest_mail_qa_decision,
          next_safe_at, sends_started, warmup_gate_json, result_json
        )
        VALUES (%s, %s, %s, %s, %s, false, %s, %s)
        RETURNING *
        """,
        (status, window_hours, signal_window_clear, mail_qa_decision, next_safe_at, Jsonb(json_safe(warmup_gate)), Jsonb(json_safe(result))),
    )
    payload = dict(row)
    payload["result_json"] = json_safe(result)
    return payload


def clean_window_recheck_summary() -> dict[str, Any]:
    latest = fetch_one(
        """
        SELECT *
        FROM clean_window_recheck_runs
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    signals = mail_signal_summary(24)
    next_safe_at = latest_blocking_signal_next_safe_at(24)
    mail_qa_decision = latest_mail_qa_decision()
    warmup_gate = warmup_resume_precheck(signals, mail_qa_decision)
    return json_safe(
        {
            "latest": dict(latest) if latest else {},
            "signals": signals,
            "signal_window_clear": not next_safe_at,
            "next_safe_at": next_safe_at,
            "mail_qa_decision": mail_qa_decision,
            "warmup_gate": warmup_gate,
            "live_outreach_allowed": False,
            "sends_started": False,
        }
    )
