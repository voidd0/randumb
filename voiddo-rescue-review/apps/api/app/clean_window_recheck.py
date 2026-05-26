from __future__ import annotations

from datetime import datetime, timezone
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


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _transition_decision(recheck_status: str) -> str:
    if recheck_status == "ready_natural_warmup_only":
        return "WARMUP_READY_PENDING_NATURAL_TIMER"
    if recheck_status == "blocked_recent_signals":
        return "WAIT_RECENT_SIGNALS"
    if recheck_status == "blocked_mail_qa":
        return "WAIT_MAIL_QA"
    return "WAIT_WARMUP_GATE"


def post_window_recheck_scheduler(window_hours: int = 24, now: datetime | None = None, run_recovery_if_due: bool = True) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    summary = clean_window_recheck_summary()
    next_safe = _parse_dt(summary.get("next_safe_at"))
    recheck_due = next_safe is None or now >= next_safe
    recheck = None
    executed_at = None
    if recheck_due:
        recheck = clean_window_recheck(window_hours, run_recovery_if_due)
        executed_at = now
        status = "recheck_executed"
        transition = _transition_decision(recheck["status"])
    else:
        status = "not_due"
        transition = "WAIT_UNTIL_NEXT_SAFE_AT"
    result = {
        "summary": summary,
        "recheck": recheck,
        "now": now.isoformat(),
        "next_safe_at": next_safe.isoformat() if next_safe else None,
        "recheck_due": recheck_due,
        "transition_decision": transition,
        "live_outreach_allowed": False,
        "sends_started": False,
    }
    row = execute(
        """
        INSERT INTO post_window_recheck_runs(
          status, window_hours, next_safe_at, recheck_due, recheck_executed_at,
          transition_decision, sends_started, result_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, false, %s)
        RETURNING *
        """,
        (status, window_hours, next_safe, recheck_due, executed_at, transition, Jsonb(json_safe(result))),
    )
    payload = dict(row)
    payload["result_json"] = json_safe(result)
    return payload


def post_window_recheck_summary() -> dict[str, Any]:
    latest = fetch_one(
        """
        SELECT *
        FROM post_window_recheck_runs
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    clean_summary = clean_window_recheck_summary()
    next_safe = _parse_dt(clean_summary.get("next_safe_at"))
    now = datetime.now(timezone.utc)
    return json_safe(
        {
            "latest": dict(latest) if latest else {},
            "clean_window": clean_summary,
            "next_safe_at": next_safe.isoformat() if next_safe else None,
            "recheck_due": next_safe is None or now >= next_safe,
            "transition_decision": dict(latest)["transition_decision"] if latest else "NOT_RUN",
            "live_outreach_allowed": False,
            "sends_started": False,
        }
    )
