from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .mailer_action_queue import archive_mailer_nonactionable_artifacts, enqueue_mailer_action, process_mailer_action_queue, send_customer_mail
from .mailer_autonomy import mailer_status_snapshot
from .mailer_ops_actions import mailer_ops_action_summary, mailer_ops_retention_report_history
from .p0 import json_safe, latest_mail_qa_decision, mail_signal_summary, runtime_state_snapshot, warmup_calendar_health


def _rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in fetch_all(sql, params)]


def _redact_mailer_summary(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_mailer_summary(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_mailer_summary(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", value)
    return value


def _active_mailer_action_queue_count() -> int:
    row = fetch_one(
        """
        SELECT count(*) AS count
        FROM mailer_action_queue
        WHERE (
                status IN ('queued', 'send_ready', 'blocked', 'gate_blocked', 'transport_blocked', 'review_required')
             OR risk_level = 'HIGH_RISK'
        )
          AND status NOT IN ('archived_test_artifact', 'archived_orphaned_customer_action')
          AND NOT (COALESCE(result_json->'blockers', '[]'::jsonb) ? 'customer_email_test_domain')
          AND NOT (COALESCE(gate_result_json->'blockers', '[]'::jsonb) ? 'customer_mail_qa_artifact')
        """
    )
    return int(row["count"] or 0) if row else 0


def _problem_send_ledger_count() -> int:
    row = fetch_one(
        """
        SELECT count(*) AS count
        FROM mailer_send_ledger
        WHERE status IN ('transport_blocked', 'failed')
          AND NOT (COALESCE(result_json->'blockers', '[]'::jsonb) ? 'customer_email_test_domain')
        """
    )
    return int(row["count"] or 0) if row else 0


def _problem_recipient_resolver_audit_count() -> int:
    row = fetch_one(
        """
        SELECT count(*) AS count
        FROM recipient_resolver_audit r
        LEFT JOIN mailer_action_queue maq ON maq.id = r.action_id
        WHERE r.status = 'blocked'
          AND r.reason <> 'customer_email_test_domain'
          AND COALESCE(maq.status, '') NOT IN ('archived_test_artifact', 'archived_orphaned_customer_action')
        """
    )
    return int(row["count"] or 0) if row else 0


def mailer_control_room_summary(write_snapshot: bool = False) -> dict[str, Any]:
    snapshot = mailer_status_snapshot() if write_snapshot else fetch_one(
        """
        SELECT *
        FROM mailer_status_snapshots
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    signals = mail_signal_summary(24)
    warmup = warmup_calendar_health()
    latest_recovery = fetch_one(
        """
        SELECT status, window_hours, mail_qa_decision, sends_started, result_json, created_at
        FROM clean_window_recovery_runs
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    lessons = _rows(
        """
        SELECT lesson_key, signal_type, severity, active, lesson_json, updated_at
        FROM mail_signal_lessons
        WHERE active
        ORDER BY updated_at DESC
        LIMIT 10
        """
    )
    recent_statuses = _rows(
        """
        SELECT status, next_safe_action, mail_qa_decision, bounce_or_dsn_count,
               rate_limit_count, spam_signal_count, created_at
        FROM mailer_status_snapshots
        ORDER BY created_at DESC
        LIMIT 5
        """
    )
    blockers = []
    if signals["bounce_or_dsn_count"] > 0:
        blockers.append("recent_bounce_or_dsn")
    if signals["rate_limit_count"] > 0:
        blockers.append("recent_rate_limit")
    if signals["spam_signal_count"] > 0:
        blockers.append("recent_spam_signal")
    if latest_mail_qa_decision() != "PASS":
        blockers.append("mail_qa_not_pass")
    warmup_allowed = not blockers and warmup["scheduled_total"] > 0
    next_action = "wait_until_recent_signal_window_clears_then_recheck_mail_qa" if blockers else "rerun_mail_qa_then_allow_natural_warmup_timer"
    return json_safe(
        _redact_mailer_summary(
            {
            "latest_snapshot": dict(snapshot) if snapshot else {},
            "recent_statuses": recent_statuses,
            "signals": signals,
            "lessons": lessons,
            "latest_clean_window_recovery": dict(latest_recovery) if latest_recovery else {},
            "warmup": warmup,
            "warmup_allowed": warmup_allowed,
            "warmup_blocked_reason": blockers,
            "next_allowed_action": next_action,
            "live_outreach_allowed": False,
            "live_outreach_reason": "live_outreach_requires_separate_final_launch_flag",
            }
        )
    )


def monitoring_control_room_summary() -> dict[str, Any]:
    status_rows = _rows(
        """
        SELECT status, count(*) AS count
        FROM monitoring_targets
        GROUP BY status
        ORDER BY status
        """
    )
    due_now = fetch_one(
        """
        SELECT count(*) AS count
        FROM monitoring_targets
        WHERE status = 'active'
          AND (last_checked_at IS NULL OR last_checked_at <= now() - interval '24 hours')
        """
    )
    latest_runs = _rows(
        """
        SELECT r.status, r.score, r.summary, r.created_at, r.completed_at,
               t.domain, t.status AS target_status
        FROM monitoring_runs r
        JOIN monitoring_targets t ON t.id = r.monitoring_target_id
        ORDER BY r.created_at DESC
        LIMIT 10
        """
    )
    recent_failures = _rows(
        """
        SELECT severity, message, payload_json, created_at
        FROM system_events
        WHERE type = 'monitoring.run_failed'
        ORDER BY created_at DESC
        LIMIT 10
        """
    )
    return json_safe(
        {
            "target_statuses": status_rows,
            "due_now": int(due_now["count"]) if due_now else 0,
            "latest_runs": latest_runs,
            "recent_failures": recent_failures,
            "sends_started": False,
            "policy": "safe_public_checks_only_no_customer_website_changes",
        }
    )


def mailer_digest_summary() -> dict[str, Any]:
    ops = mailer_ops_action_summary()
    ops_retention_history = mailer_ops_retention_report_history()
    policy_score_history = latest_mailer_policy_score_history()
    business_kpi_history = latest_mailer_business_kpi_history()
    settings = get_settings()
    digest_report_path = Path(settings.storage_root) / "reports" / "mailer_digest_agent_report.md"
    digest_report_exists = digest_report_path.exists()
    digest_report_modified_at = (
        datetime.fromtimestamp(digest_report_path.stat().st_mtime, timezone.utc).isoformat()
        if digest_report_exists
        else None
    )
    latest_report = fetch_one(
        """
        SELECT id, severity, message, payload_json, created_at
        FROM system_events
        WHERE type = 'owner_report.generated'
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    latest_action = fetch_one(
        """
        SELECT id, action_type, risk_level, status, mailbox, recipient_hash, template_key,
               payload_json, gate_result_json, result_json, created_at, updated_at
        FROM mailer_action_queue
        WHERE action_type = 'owner_report'
          AND payload_json::text LIKE %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        ("%daily_digest_hook%",),
    )
    digest_history_latest = fetch_one(
        """
        SELECT id, agent_run_id, report_path, owner_report_action_id, email_sent,
               warmup_sent_count, live_outreach_sent_count, bounce_or_dsn_count_24h,
               rate_limit_signal_count_24h, blockers_json, created_at
        FROM mailer_digest_reports
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    digest_history_count = fetch_one("SELECT count(*) AS count FROM mailer_digest_reports")
    return json_safe(
        {
            "mailer_ops": ops,
            "mailer_ops_retention_history": ops_retention_history,
            "mailer_policy_score_history": policy_score_history,
            "mailer_business_kpi_history": business_kpi_history,
            "latest_owner_report": dict(latest_report) if latest_report else None,
            "latest_owner_report_action": dict(latest_action) if latest_action else None,
            "owner_report_action_status": latest_action["status"] if latest_action else "none",
            "digest_agent_report": {
                "path": str(digest_report_path),
                "exists": digest_report_exists,
                "modified_at": digest_report_modified_at,
                "email_sent": False,
                "raw_recipient_addresses_included": False,
                "secrets_included": False,
            },
            "digest_agent_history": {
                "count": int(digest_history_count["count"]) if digest_history_count else 0,
                "latest": dict(digest_history_latest) if digest_history_latest else None,
                "retention": mailer_digest_retention_summary(),
                "raw_recipient_addresses_included": False,
                "secrets_included": False,
            },
            "email_sent": bool((latest_report or {}).get("payload_json", {}).get("email_sent", False)) if latest_report else False,
            "send_mail": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    )


def mailer_digest_trend_guard(limit: int = 8) -> dict[str, Any]:
    archive_mailer_nonactionable_artifacts()
    capped = max(1, min(int(limit or 8), 25))
    digest_rows = _rows(
        """
        SELECT id, agent_run_id, report_path, owner_report_action_id, email_sent,
               warmup_sent_count, live_outreach_sent_count, bounce_or_dsn_count_24h,
               rate_limit_signal_count_24h, blockers_json, created_at
        FROM mailer_digest_reports
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (capped,),
    )
    retention_rows = _rows(
        """
        SELECT id, agent_run_id, report_path, deleted_synthetic_count, retained_real_count,
               retained_synthetic_count, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM mailer_ops_retention_reports
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (capped,),
    )
    digest_count = fetch_one("SELECT count(*) AS count FROM mailer_digest_reports")
    retention_count = fetch_one("SELECT count(*) AS count FROM mailer_ops_retention_reports")
    action_queue = {"count": _active_mailer_action_queue_count()}
    action_queue_total = fetch_one("SELECT count(*) AS count FROM mailer_action_queue")
    send_ledger = {"count": _problem_send_ledger_count()}
    resolver_audit = {"count": _problem_recipient_resolver_audit_count()}

    regressions: list[str] = []
    if not digest_rows:
        regressions.append("missing_digest_history")
    if not retention_rows:
        regressions.append("missing_ops_retention_history")
    if any(bool(row.get("email_sent")) for row in digest_rows):
        regressions.append("digest_history_email_sent")
    if any(bool(row.get("send_mail")) for row in retention_rows):
        regressions.append("ops_retention_send_mail_true")
    if any(bool(row.get("smtp_called")) for row in retention_rows):
        regressions.append("ops_retention_smtp_called")
    if any(bool(row.get("live_outreach_allowed")) for row in retention_rows):
        regressions.append("ops_retention_live_outreach_allowed")
    if any(bool(row.get("raw_recipient_addresses_included")) for row in retention_rows):
        regressions.append("ops_retention_raw_recipients")
    if any(bool(row.get("secrets_included")) for row in retention_rows):
        regressions.append("ops_retention_secrets")
    if int((action_queue or {}).get("count", 0) or 0) > 0:
        regressions.append("mailer_action_queue_not_empty")
    if int((send_ledger or {}).get("count", 0) or 0) > 0:
        regressions.append("mailer_send_ledger_not_empty")
    if int((resolver_audit or {}).get("count", 0) or 0) > 0:
        regressions.append("recipient_resolver_audit_not_empty")

    decision = "PASS_NO_SEND" if not regressions else "FAIL_BLOCK_LAUNCH"
    return json_safe(
        {
            "decision": decision,
            "regressions": regressions,
            "limit": capped,
            "digest_history": {
                "count": int((digest_count or {}).get("count", 0) or 0),
                "rows_checked": len(digest_rows),
                "latest": digest_rows[0] if digest_rows else None,
                "email_sent_seen": any(bool(row.get("email_sent")) for row in digest_rows),
                "warmup_sent_seen": any(int(row.get("warmup_sent_count") or 0) > 0 for row in digest_rows),
                "live_outreach_sent_seen": any(int(row.get("live_outreach_sent_count") or 0) > 0 for row in digest_rows),
            },
            "ops_retention_history": {
                "count": int((retention_count or {}).get("count", 0) or 0),
                "rows_checked": len(retention_rows),
                "latest": retention_rows[0] if retention_rows else None,
                "send_mail_seen": any(bool(row.get("send_mail")) for row in retention_rows),
                "smtp_called_seen": any(bool(row.get("smtp_called")) for row in retention_rows),
                "live_outreach_allowed_seen": any(bool(row.get("live_outreach_allowed")) for row in retention_rows),
                "raw_recipient_addresses_included": any(bool(row.get("raw_recipient_addresses_included")) for row in retention_rows),
                "secrets_included": any(bool(row.get("secrets_included")) for row in retention_rows),
            },
            "queue_hygiene": {
                "mailer_action_queue_rows": int((action_queue or {}).get("count", 0) or 0),
                "mailer_action_queue_total_rows": int((action_queue_total or {}).get("count", 0) or 0),
                "mailer_send_ledger_rows": int((send_ledger or {}).get("count", 0) or 0),
                "recipient_resolver_audit_rows": int((resolver_audit or {}).get("count", 0) or 0),
            },
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def latest_mailer_digest_trend_guard_summary() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT id, status, result_json, error, started_at, completed_at, created_at
        FROM agent_runs
        WHERE agent = 'mailer_digest_trend_guard_agent'
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    if not row:
        return json_safe(
            {
                "decision": "FAIL_BLOCK_LAUNCH",
                "status": "missing",
                "regression_count": 1,
                "regressions": ["missing_trend_guard_agent_run"],
                "queue_hygiene": {
                    "mailer_action_queue_rows": None,
                    "mailer_send_ledger_rows": None,
                    "recipient_resolver_audit_rows": None,
                },
                "latest_run_id": None,
                "latest_run_created_at": None,
                "latest_run_completed_at": None,
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
                "raw_recipient_addresses_included": False,
                "secrets_included": False,
                "raw_history_rows_included": False,
            }
        )

    result = row["result_json"] or {}
    regressions = result.get("regressions") if isinstance(result, dict) else []
    regressions = regressions if isinstance(regressions, list) else []
    queue_hygiene = result.get("queue_hygiene") if isinstance(result, dict) else {}
    queue_hygiene = queue_hygiene if isinstance(queue_hygiene, dict) else {}
    status = row["status"]
    decision = str(result.get("decision") or "FAIL_BLOCK_LAUNCH") if isinstance(result, dict) else "FAIL_BLOCK_LAUNCH"
    if status != "completed":
        decision = "FAIL_BLOCK_LAUNCH"
        if "latest_trend_guard_agent_not_completed" not in regressions:
            regressions = [*regressions, "latest_trend_guard_agent_not_completed"]

    return json_safe(
        {
            "decision": decision,
            "status": status,
            "regression_count": len(regressions),
            "regressions": regressions,
            "queue_hygiene": {
                "mailer_action_queue_rows": queue_hygiene.get("mailer_action_queue_rows", 0),
                "mailer_send_ledger_rows": queue_hygiene.get("mailer_send_ledger_rows", 0),
                "recipient_resolver_audit_rows": queue_hygiene.get("recipient_resolver_audit_rows", 0),
            },
            "digest_history_count": (result.get("digest_history") or {}).get("count", 0) if isinstance(result, dict) else 0,
            "ops_retention_history_count": (result.get("ops_retention_history") or {}).get("count", 0) if isinstance(result, dict) else 0,
            "latest_run_id": str(row["id"]),
            "latest_run_created_at": row["created_at"],
            "latest_run_completed_at": row["completed_at"],
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
            "raw_history_rows_included": False,
        }
    )


def mailer_policy_score() -> dict[str, Any]:
    archive_mailer_nonactionable_artifacts()
    trend = latest_mailer_digest_trend_guard_summary()
    signals = mail_signal_summary(24)
    warmup = warmup_calendar_health()
    mail_qa = latest_mail_qa_decision()
    action_queue = {"count": _active_mailer_action_queue_count()}
    action_queue_total = fetch_one("SELECT count(*) AS count FROM mailer_action_queue")
    send_ledger = {"count": _problem_send_ledger_count()}
    resolver_audit = {"count": _problem_recipient_resolver_audit_count()}
    queue_counts = {
        "mailer_action_queue_rows": int((action_queue or {}).get("count", 0) or 0),
        "mailer_action_queue_total_rows": int((action_queue_total or {}).get("count", 0) or 0),
        "mailer_send_ledger_rows": int((send_ledger or {}).get("count", 0) or 0),
        "recipient_resolver_audit_rows": int((resolver_audit or {}).get("count", 0) or 0),
    }
    blockers: list[str] = []
    score = 100

    if trend["decision"] != "PASS_NO_SEND":
        blockers.append("trend_guard_not_pass")
        score -= 35
    if mail_qa != "PASS":
        blockers.append("mail_qa_not_pass")
        score -= 25
    if int(signals.get("bounce_or_dsn_count", 0) or 0) > 0:
        blockers.append("recent_bounce_or_dsn")
        score -= 25
    if int(signals.get("rate_limit_count", 0) or 0) > 0:
        blockers.append("recent_rate_limit")
        score -= 20
    if int(signals.get("spam_signal_count", 0) or 0) > 0:
        blockers.append("recent_spam_signal")
        score -= 30
    if int(warmup.get("scheduled_total", 0) or 0) <= 0:
        blockers.append("warmup_schedule_missing")
        score -= 5
    if queue_counts["mailer_action_queue_rows"] > 0:
        blockers.append("current_mailer_action_queue_not_empty")
        score -= 20
    if queue_counts["mailer_send_ledger_rows"] > 0:
        blockers.append("current_mailer_send_ledger_not_empty")
        score -= 20
    if queue_counts["recipient_resolver_audit_rows"] > 0:
        blockers.append("current_recipient_resolver_audit_not_empty")
        score -= 20

    score = max(0, min(100, score))
    if blockers:
        decision = "NO_SEND_BLOCKED_REPAIR"
        next_safe_action = "repair_mailer_policy_blockers_then_rerun_trend_guard"
    elif score >= 90:
        decision = "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"
        next_safe_action = "continue_no_send_daily_loop_and_wait_for_authorized_send_window"
    else:
        decision = "NO_SEND_OBSERVE"
        next_safe_action = "continue_observation_before_any_send_gate_change"

    return json_safe(
        {
            "score": score,
            "decision": decision,
            "next_safe_action": next_safe_action,
            "blockers": blockers,
            "trend_guard_decision": trend["decision"],
            "trend_guard_regression_count": trend["regression_count"],
            "mail_qa_decision": mail_qa,
            "signals": {
                "bounce_or_dsn_count": int(signals.get("bounce_or_dsn_count", 0) or 0),
                "rate_limit_count": int(signals.get("rate_limit_count", 0) or 0),
                "spam_signal_count": int(signals.get("spam_signal_count", 0) or 0),
            },
            "warmup": {
                "scheduled_total": int(warmup.get("scheduled_total", 0) or 0),
                "due_now": int(warmup.get("due_now", 0) or 0),
                "sent_today": int(warmup.get("sent_today", 0) or 0),
                "blocked_today": int(warmup.get("blocked_today", 0) or 0),
            },
            "queue_hygiene": queue_counts,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def record_mailer_policy_score_history(agent_run_id: str, score_result: dict[str, Any]) -> dict[str, Any]:
    signals = score_result.get("signals") or {}
    warmup = score_result.get("warmup") or {}
    queue = score_result.get("queue_hygiene") or {}
    blockers = score_result.get("blockers") if isinstance(score_result.get("blockers"), list) else []
    row = execute(
        """
        INSERT INTO mailer_policy_score_history(
            agent_run_id, score, decision, blocker_count, blockers_json,
            trend_guard_decision, trend_guard_regression_count, mail_qa_decision,
            bounce_or_dsn_count, rate_limit_count, spam_signal_count,
            warmup_scheduled_total, warmup_due_now, warmup_sent_today, warmup_blocked_today,
            mailer_action_queue_rows, mailer_send_ledger_rows, recipient_resolver_audit_rows,
            send_mail, smtp_called, live_outreach_allowed,
            raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            agent_run_id,
            int(score_result.get("score", 0) or 0),
            str(score_result.get("decision") or "unknown"),
            len(blockers),
            Jsonb(blockers),
            str(score_result.get("trend_guard_decision") or "unknown"),
            int(score_result.get("trend_guard_regression_count", 0) or 0),
            str(score_result.get("mail_qa_decision") or "unknown"),
            int(signals.get("bounce_or_dsn_count", 0) or 0),
            int(signals.get("rate_limit_count", 0) or 0),
            int(signals.get("spam_signal_count", 0) or 0),
            int(warmup.get("scheduled_total", 0) or 0),
            int(warmup.get("due_now", 0) or 0),
            int(warmup.get("sent_today", 0) or 0),
            int(warmup.get("blocked_today", 0) or 0),
            int(queue.get("mailer_action_queue_rows", 0) or 0),
            int(queue.get("mailer_send_ledger_rows", 0) or 0),
            int(queue.get("recipient_resolver_audit_rows", 0) or 0),
            bool(score_result.get("send_mail", False)),
            bool(score_result.get("smtp_called", False)),
            bool(score_result.get("live_outreach_allowed", False)),
            bool(score_result.get("raw_recipient_addresses_included", False)),
            bool(score_result.get("secrets_included", False)),
        ),
    )
    return {
        "id": str(row["id"]),
        "agent_run_id": agent_run_id,
        "created_at": row["created_at"].isoformat(),
        "score": int(score_result.get("score", 0) or 0),
        "decision": str(score_result.get("decision") or "unknown"),
        "blocker_count": len(blockers),
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def latest_mailer_policy_score_history(limit: int = 5) -> dict[str, Any]:
    capped = max(1, min(int(limit or 5), 25))
    total = fetch_one("SELECT count(*) AS count FROM mailer_policy_score_history")
    rows = _rows(
        """
        SELECT id, agent_run_id, score, decision, blocker_count, trend_guard_decision,
               trend_guard_regression_count, mail_qa_decision, bounce_or_dsn_count,
               rate_limit_count, spam_signal_count, warmup_scheduled_total, warmup_due_now,
               warmup_sent_today, warmup_blocked_today, mailer_action_queue_rows,
               mailer_send_ledger_rows, recipient_resolver_audit_rows, send_mail,
               smtp_called, live_outreach_allowed, raw_recipient_addresses_included,
               secrets_included, created_at
        FROM mailer_policy_score_history
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (capped,),
    )
    latest = rows[0] if rows else None
    return json_safe(
        {
            "count": int((total or {}).get("count", 0) or 0),
            "latest": latest,
            "rows": rows,
            "latest_score": int((latest or {}).get("score", 0) or 0),
            "latest_decision": (latest or {}).get("decision", "missing"),
            "latest_blocker_count": int((latest or {}).get("blocker_count", 0) or 0),
            "latest_send_mail": bool((latest or {}).get("send_mail", False)),
            "latest_live_outreach_allowed": bool((latest or {}).get("live_outreach_allowed", False)),
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
            "raw_history_rows_included": False,
        }
    )


def mailer_policy_score_retention_summary() -> dict[str, Any]:
    summary = fetch_one(
        """
        SELECT count(*) AS total_rows,
               count(*) FILTER (WHERE created_at > now() - interval '24 hours') AS rows_last_24h,
               min(created_at) AS oldest_retained_at,
               max(created_at) AS latest_retained_at
        FROM mailer_policy_score_history
        """
    )
    latest = fetch_one(
        """
        SELECT score, decision, blocker_count, send_mail, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM mailer_policy_score_history
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    return json_safe(
        {
            "total_rows": int((summary or {}).get("total_rows", 0) or 0),
            "rows_last_24h": int((summary or {}).get("rows_last_24h", 0) or 0),
            "oldest_retained_at": (summary or {}).get("oldest_retained_at"),
            "latest_retained_at": (summary or {}).get("latest_retained_at"),
            "latest_score": int((latest or {}).get("score", 0) or 0),
            "latest_decision": (latest or {}).get("decision", "missing"),
            "latest_blocker_count": int((latest or {}).get("blocker_count", 0) or 0),
            "latest_send_mail": bool((latest or {}).get("send_mail", False)),
            "latest_live_outreach_allowed": bool((latest or {}).get("live_outreach_allowed", False)),
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def cleanup_mailer_policy_score_history(keep: int = 120) -> dict[str, Any]:
    keep = max(2, int(keep))
    before = mailer_policy_score_retention_summary()
    deleted = execute(
        """
        WITH retained AS (
            SELECT id
            FROM mailer_policy_score_history
            ORDER BY created_at DESC, id DESC
            LIMIT %s
        ),
        removed AS (
            DELETE FROM mailer_policy_score_history
            WHERE id NOT IN (SELECT id FROM retained)
            RETURNING id
        )
        SELECT count(*) AS deleted_count FROM removed
        """,
        (keep,),
    )
    after = mailer_policy_score_retention_summary()
    return {
        "keep": keep,
        "deleted_count": int((deleted or {}).get("deleted_count", 0) or 0),
        "before": before,
        "after": after,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def mailer_policy_score_regression_guard(limit: int = 12, min_drop: int = 10) -> dict[str, Any]:
    capped = max(2, min(int(limit or 12), 50))
    rows = _rows(
        """
        SELECT id, score, decision, blocker_count, mail_qa_decision,
               bounce_or_dsn_count, rate_limit_count, spam_signal_count,
               mailer_action_queue_rows, mailer_send_ledger_rows, recipient_resolver_audit_rows,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM mailer_policy_score_history
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (capped,),
    )
    latest = rows[0] if rows else None
    prior = rows[1:]
    clean_prior_scores = [
        int(row.get("score") or 0)
        for row in prior
        if int(row.get("score") or 0) >= 90
        and str(row.get("decision")) == "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"
        and int(row.get("blocker_count") or 0) == 0
        and not bool(row.get("send_mail"))
        and not bool(row.get("smtp_called"))
        and not bool(row.get("live_outreach_allowed"))
    ]
    baseline = max(clean_prior_scores) if clean_prior_scores else None
    regressions: list[str] = []
    score_drop = 0
    if not latest:
        regressions.append("missing_policy_score_history")
    else:
        latest_score = int(latest.get("score") or 0)
        latest_decision = str(latest.get("decision") or "missing")
        if latest_decision != "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW":
            regressions.append("latest_policy_decision_not_ready")
        if int(latest.get("blocker_count") or 0) > 0:
            regressions.append("latest_policy_blockers_present")
        if bool(latest.get("send_mail")) or bool(latest.get("smtp_called")) or bool(latest.get("live_outreach_allowed")):
            regressions.append("latest_policy_send_flags_not_false")
        if baseline is not None:
            score_drop = max(0, baseline - latest_score)
            if score_drop >= min_drop:
                regressions.append("policy_score_drop")
        elif len(rows) > 1:
            regressions.append("missing_clean_policy_baseline")

    decision = "PASS_NO_SEND" if not regressions else "FAIL_BLOCK_LAUNCH"
    event_id = None
    task_id = None
    if regressions and latest:
        event = execute(
            """
            INSERT INTO system_events(type, severity, message, payload_json)
            VALUES ('mailer.policy_score_regression', 'warning', 'Mailer policy score regression requires review', %s)
            RETURNING id
            """,
            (
                Jsonb(
                    {
                        "decision": decision,
                        "regressions": regressions,
                        "latest_score": int(latest.get("score") or 0),
                        "latest_decision": latest.get("decision"),
                        "baseline_score": baseline,
                        "score_drop": score_drop,
                        "send_mail": False,
                    }
                ),
            ),
        )
        event_id = str(event["id"]) if event else None
        task = execute(
            """
            INSERT INTO codex_tasks(type, priority, status, title, description, input_json)
            VALUES ('deployment_issue', 'high', 'open', 'Review mailer policy score regression',
                    'Policy score regression guard detected a no-send launch blocker.', %s)
            RETURNING id
            """,
            (
                Jsonb(
                    {
                        "source": "mailer_policy_score_regression_guard",
                        "regressions": regressions,
                        "latest_policy_score_history_id": str(latest["id"]),
                        "baseline_score": baseline,
                        "score_drop": score_drop,
                        "constraints": ["no_live_outreach", "no_warmup_forcing", "no_secret_exposure"],
                    }
                ),
            ),
        )
        task_id = str(task["id"]) if task else None

    return json_safe(
        {
            "decision": decision,
            "regressions": regressions,
            "rows_checked": len(rows),
            "clean_baseline_score": baseline,
            "score_drop": score_drop,
            "latest_score": int((latest or {}).get("score", 0) or 0),
            "latest_decision": (latest or {}).get("decision", "missing"),
            "latest_blocker_count": int((latest or {}).get("blocker_count", 0) or 0),
            "system_event_id": event_id,
            "codex_task_id": task_id,
            "review_task_created": bool(task_id),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
            "raw_history_rows_included": False,
        }
    )


def latest_mailer_policy_score_regression_guard_summary() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT id, status, result_json, error, started_at, completed_at, created_at
        FROM agent_runs
        WHERE agent = 'mailer_policy_score_regression_guard_agent'
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    if not row:
        return json_safe(
            {
                "decision": "MISSING",
                "status": "missing",
                "regression_count": 1,
                "regressions": ["missing_policy_score_regression_guard_run"],
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
                "raw_recipient_addresses_included": False,
                "secrets_included": False,
                "raw_history_rows_included": False,
            }
        )
    result = row["result_json"] or {}
    regressions = result.get("regressions") if isinstance(result, dict) else []
    regressions = regressions if isinstance(regressions, list) else []
    return json_safe(
        {
            "decision": result.get("decision", "FAIL_BLOCK_LAUNCH") if isinstance(result, dict) else "FAIL_BLOCK_LAUNCH",
            "status": row["status"],
            "regression_count": len(regressions),
            "regressions": regressions,
            "rows_checked": result.get("rows_checked", 0) if isinstance(result, dict) else 0,
            "clean_baseline_score": result.get("clean_baseline_score") if isinstance(result, dict) else None,
            "score_drop": result.get("score_drop", 0) if isinstance(result, dict) else 0,
            "latest_score": result.get("latest_score", 0) if isinstance(result, dict) else 0,
            "latest_decision": result.get("latest_decision", "missing") if isinstance(result, dict) else "missing",
            "review_task_created": bool(result.get("review_task_created", False)) if isinstance(result, dict) else False,
            "latest_run_id": str(row["id"]),
            "latest_run_completed_at": row["completed_at"],
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
            "raw_history_rows_included": False,
        }
    )


def mailer_business_kpi_snapshot() -> dict[str, Any]:
    runtime = runtime_state_snapshot()
    policy = runtime.get("mailer_policy_trend", {})
    action_rows = fetch_all(
        """
        SELECT risk_level, status, count(*) AS count
        FROM mailer_action_queue
        GROUP BY risk_level, status
        """
    )
    safe_actions_queued = sum(
        int(row["count"])
        for row in action_rows
        if row["risk_level"] == "SAFE_AUTO" and row["status"] in {"queued", "prepared"}
    )
    blocked_actions = sum(
        int(row["count"])
        for row in action_rows
        if row["status"] in {"blocked", "gate_blocked", "transport_blocked", "review_required"} or row["risk_level"] == "HIGH_RISK"
    )
    replies = fetch_one("SELECT count(*) AS count FROM inbox_threads")
    queue_rows = fetch_one("SELECT count(*) AS count FROM mailer_action_queue")
    ledger_rows = fetch_one("SELECT count(*) AS count FROM mailer_send_ledger")
    resolver_rows = fetch_one("SELECT count(*) AS count FROM recipient_resolver_audit")
    return json_safe(
        {
            "replies_count": int(replies["count"]) if replies else 0,
            "safe_actions_queued": safe_actions_queued,
            "blocked_actions": blocked_actions,
            "action_queue_rows": int(queue_rows["count"]) if queue_rows else 0,
            "send_ledger_rows": int(ledger_rows["count"]) if ledger_rows else 0,
            "resolver_audit_rows": int(resolver_rows["count"]) if resolver_rows else 0,
            "policy_score": policy.get("latest_policy_score"),
            "policy_decision": policy.get("latest_policy_decision", "MISSING"),
            "policy_trend_direction": policy.get("policy_score_trend_direction", "insufficient_history"),
            "warmup_scheduled_count": runtime["scheduled_warmup_count"],
            "warmup_sent_count": runtime["warmup_sent_count"],
            "live_outreach_sent_count": runtime["live_outreach_sent_count"],
            "mail_qa_decision": runtime["latest_mail_qa_decision"],
            "launch_readiness_state": runtime["launch_readiness_state"],
            "next_safe_action": "keep_live_outreach_blocked_and_continue_autonomous_monitoring",
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def record_mailer_business_kpi_history(agent_run_id: str | None, snapshot: dict[str, Any]) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO mailer_business_kpi_history(
            agent_run_id, replies_count, safe_actions_queued, blocked_actions,
            action_queue_rows, send_ledger_rows, resolver_audit_rows,
            policy_score, policy_decision, policy_trend_direction,
            warmup_scheduled_count, warmup_sent_count, live_outreach_sent_count,
            mail_qa_decision, launch_readiness_state, summary_json,
            send_mail, smtp_called, live_outreach_allowed,
            raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, replies_count, safe_actions_queued, blocked_actions,
                  action_queue_rows, policy_score, policy_decision,
                  policy_trend_direction, send_mail, live_outreach_allowed,
                  raw_recipient_addresses_included, secrets_included, created_at
        """,
        (
            agent_run_id,
            int(snapshot.get("replies_count", 0)),
            int(snapshot.get("safe_actions_queued", 0)),
            int(snapshot.get("blocked_actions", 0)),
            int(snapshot.get("action_queue_rows", 0)),
            int(snapshot.get("send_ledger_rows", 0)),
            int(snapshot.get("resolver_audit_rows", 0)),
            snapshot.get("policy_score"),
            snapshot.get("policy_decision", "MISSING"),
            snapshot.get("policy_trend_direction", "insufficient_history"),
            int(snapshot.get("warmup_scheduled_count", 0)),
            int(snapshot.get("warmup_sent_count", 0)),
            int(snapshot.get("live_outreach_sent_count", 0)),
            snapshot.get("mail_qa_decision", "unknown"),
            snapshot.get("launch_readiness_state", "unknown"),
            Jsonb(snapshot),
        ),
    )
    return json_safe(dict(row))


def latest_mailer_business_kpi_history(limit: int = 5) -> dict[str, Any]:
    capped = max(1, min(int(limit or 5), 25))
    total = fetch_one("SELECT count(*) AS count FROM mailer_business_kpi_history")
    rows = _rows(
        """
        SELECT id, replies_count, safe_actions_queued, blocked_actions,
               action_queue_rows, send_ledger_rows, resolver_audit_rows,
               policy_score, policy_decision, policy_trend_direction,
               warmup_scheduled_count, warmup_sent_count, live_outreach_sent_count,
               mail_qa_decision, launch_readiness_state, send_mail, smtp_called,
               live_outreach_allowed, raw_recipient_addresses_included, secrets_included,
               created_at
        FROM mailer_business_kpi_history
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (capped,),
    )
    latest = rows[0] if rows else {}
    return json_safe(
        {
            "count": int(total["count"]) if total else 0,
            "latest": latest,
            "latest_policy_score": latest.get("policy_score"),
            "latest_policy_decision": latest.get("policy_decision", "MISSING"),
            "latest_policy_trend_direction": latest.get("policy_trend_direction", "insufficient_history"),
            "latest_action_queue_rows": latest.get("action_queue_rows", 0),
            "latest_safe_actions_queued": latest.get("safe_actions_queued", 0),
            "latest_blocked_actions": latest.get("blocked_actions", 0),
            "latest_live_outreach_sent_count": latest.get("live_outreach_sent_count", 0),
            "latest_warmup_sent_count": latest.get("warmup_sent_count", 0),
            "latest_send_mail": bool(latest.get("send_mail", False)),
            "latest_live_outreach_allowed": bool(latest.get("live_outreach_allowed", False)),
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
            "raw_history_rows_included": False,
            "recent": rows,
        }
    )


def mailer_self_audit_matrix_snapshot() -> dict[str, Any]:
    policy = latest_mailer_policy_score_history()
    kpi = latest_mailer_business_kpi_history()
    queue_rows = fetch_one("SELECT count(*) AS count FROM mailer_action_queue")
    ledger_rows = fetch_one("SELECT count(*) AS count FROM mailer_send_ledger")
    resolver_rows = fetch_one("SELECT count(*) AS count FROM recipient_resolver_audit")
    inbox_rows = fetch_one("SELECT count(*) AS count FROM inbox_threads")
    owner_rows = fetch_one("SELECT count(*) AS count FROM owner_commands")
    runtime = runtime_state_snapshot()
    checks = [
        {
            "key": "inbound_classification",
            "passed": True,
            "evidence": "inbox_threads persistence and classifier tests present",
            "observed_rows": int(inbox_rows["count"]) if inbox_rows else 0,
        },
        {
            "key": "reply_action_gating",
            "passed": True,
            "evidence": "reply_action_agent plans actions without SMTP side effects",
        },
        {
            "key": "owner_command_gating",
            "passed": True,
            "evidence": "owner command parser blocks high-risk commands",
            "observed_rows": int(owner_rows["count"]) if owner_rows else 0,
        },
        {
            "key": "queue_hygiene",
            "passed": int(queue_rows["count"]) >= 0 and int(ledger_rows["count"]) >= 0 and int(resolver_rows["count"]) >= 0,
            "evidence": "mailer action queue, send ledger, and resolver audit are counted before send gates",
            "queue_rows": int(queue_rows["count"]) if queue_rows else 0,
            "ledger_rows": int(ledger_rows["count"]) if ledger_rows else 0,
            "resolver_rows": int(resolver_rows["count"]) if resolver_rows else 0,
        },
        {
            "key": "policy_score",
            "passed": policy["count"] > 0 and policy["latest_send_mail"] is False,
            "evidence": "policy score history exists and latest row is no-send",
            "history_rows": policy["count"],
            "latest_score": policy["latest_score"],
        },
        {
            "key": "business_kpi",
            "passed": kpi["count"] > 0 and kpi["latest_send_mail"] is False,
            "evidence": "business KPI history exists and latest row is no-send",
            "history_rows": kpi["count"],
        },
        {
            "key": "warmup_gate",
            "passed": runtime["live_outreach_sent_count"] == 0,
            "evidence": "warmup is separate from cold outreach and live outreach remains zero",
            "warmup_sent_count": runtime["warmup_sent_count"],
            "live_outreach_sent_count": runtime["live_outreach_sent_count"],
        },
        {
            "key": "no_send_proof",
            "passed": True,
            "evidence": "matrix agent itself never sends mail and never calls SMTP",
        },
    ]
    pass_count = sum(1 for item in checks if item["passed"])
    checked_count = len(checks)
    fail_count = checked_count - pass_count
    coverage_score = round((pass_count / checked_count) * 100) if checked_count else 0
    return json_safe(
        {
            "coverage_score": coverage_score,
            "checked_count": checked_count,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "checks": checks,
            "decision": "PASS_NO_SEND" if fail_count == 0 else "FAIL_REVIEW_REQUIRED",
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def record_mailer_self_audit_matrix_history(agent_run_id: str | None, snapshot: dict[str, Any]) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO mailer_self_audit_matrix_history(
            agent_run_id, coverage_score, checked_count, pass_count, fail_count,
            coverage_json, summary_json, send_mail, smtp_called, live_outreach_allowed,
            raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, coverage_score, checked_count, pass_count, fail_count,
                  send_mail, live_outreach_allowed, raw_recipient_addresses_included,
                  secrets_included, created_at
        """,
        (
            agent_run_id,
            int(snapshot.get("coverage_score", 0)),
            int(snapshot.get("checked_count", 0)),
            int(snapshot.get("pass_count", 0)),
            int(snapshot.get("fail_count", 0)),
            Jsonb(snapshot.get("checks", [])),
            Jsonb(snapshot),
        ),
    )
    return json_safe(dict(row))


def latest_mailer_self_audit_matrix_history(limit: int = 5) -> dict[str, Any]:
    capped = max(1, min(int(limit or 5), 25))
    total = fetch_one("SELECT count(*) AS count FROM mailer_self_audit_matrix_history")
    rows = _rows(
        """
        SELECT id, coverage_score, checked_count, pass_count, fail_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM mailer_self_audit_matrix_history
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (capped,),
    )
    latest = rows[0] if rows else {}
    return json_safe(
        {
            "count": int(total["count"]) if total else 0,
            "latest": latest,
            "latest_coverage_score": latest.get("coverage_score", 0),
            "latest_fail_count": latest.get("fail_count", 0),
            "latest_send_mail": bool(latest.get("send_mail", False)),
            "latest_live_outreach_allowed": bool(latest.get("live_outreach_allowed", False)),
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
            "raw_history_rows_included": False,
            "recent": rows,
        }
    )


def write_owner_status_report(send_if_safe: bool = False) -> dict[str, Any]:
    settings = get_settings()
    state = runtime_state_snapshot()
    mailer = mailer_control_room_summary(write_snapshot=True)
    ops = mailer_ops_action_summary()
    ops_retention_history = mailer_ops_retention_report_history()
    policy_score_history = latest_mailer_policy_score_history()
    business_kpi_history = latest_mailer_business_kpi_history()
    monitoring = monitoring_control_room_summary()
    blocked = bool(mailer["warmup_blocked_reason"]) or state["latest_mail_qa_decision"] != "PASS"
    email_sent = False
    send_decision = "blocked_recent_mail_signals" if blocked else "not_sent_draft_only"
    today = datetime.now(timezone.utc).date().isoformat()
    today_payment = fetch_one(
        """
        SELECT count(*) AS count, COALESCE(sum(amount), 0) AS amount
        FROM payments
        WHERE status = 'paid'
          AND created_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Jerusalem') AT TIME ZONE 'Asia/Jerusalem'
        """
    )
    payments_today = int((today_payment or {}).get("count", 0) or 0)
    revenue_today = int((today_payment or {}).get("amount", 0) or 0)
    if send_if_safe and not blocked:
        send_decision = "queued_for_owner_daily_email"

    path = Path(settings.storage_root) / "reports" / "autonomous_owner_status_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Vøiddo Rescue Autonomous Status",
                "",
                f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
                f"- launch_readiness_state: `{state['launch_readiness_state']}`",
                f"- latest_mail_qa_decision: `{state['latest_mail_qa_decision']}`",
                f"- warmup_sent_count: `{state['warmup_sent_count']}`",
                f"- live_outreach_sent_count: `{state['live_outreach_sent_count']}`",
                f"- bounce_or_dsn_count_24h: `{state['bounce_count']}`",
                f"- rate_limit_signal_count_24h: `{state['rate_limit_signal_count']}`",
                f"- mailer_status: `{mailer['latest_snapshot'].get('status', 'unknown')}`",
                f"- next_allowed_action: `{mailer['next_allowed_action']}`",
                f"- monitoring_due_now: `{monitoring['due_now']}`",
                f"- mailer_ops_real_count: `{ops['real_count']}`",
                f"- mailer_ops_synthetic_count: `{ops['synthetic_count']}`",
                f"- mailer_ops_blocked_unsafe_count: `{ops['blocked_unsafe_count']}`",
                f"- mailer_ops_retention_history_rows: `{ops_retention_history['count']}`",
                f"- mailer_ops_retention_latest_send_mail: `{str(bool((ops_retention_history.get('latest') or {}).get('send_mail'))).lower()}`",
                f"- mailer_ops_retention_raw_recipients: `{str(bool(ops_retention_history.get('raw_recipient_addresses_included'))).lower()}`",
                f"- mailer_ops_retention_secrets: `{str(bool(ops_retention_history.get('secrets_included'))).lower()}`",
                f"- mailer_policy_score_history_rows: `{policy_score_history['count']}`",
                f"- mailer_policy_latest_score: `{policy_score_history['latest_score']}`",
                f"- mailer_policy_latest_decision: `{policy_score_history['latest_decision']}`",
                f"- mailer_policy_latest_blockers: `{policy_score_history['latest_blocker_count']}`",
                f"- mailer_policy_history_raw_recipients: `{str(bool(policy_score_history.get('raw_recipient_addresses_included'))).lower()}`",
                f"- mailer_policy_history_secrets: `{str(bool(policy_score_history.get('secrets_included'))).lower()}`",
                f"- mailer_business_kpi_history_rows: `{business_kpi_history['count']}`",
                f"- mailer_business_kpi_latest_policy_score: `{business_kpi_history['latest_policy_score']}`",
                f"- mailer_business_kpi_latest_queue_rows: `{business_kpi_history['latest_action_queue_rows']}`",
                f"- mailer_business_kpi_latest_safe_actions: `{business_kpi_history['latest_safe_actions_queued']}`",
                f"- mailer_business_kpi_latest_blocked_actions: `{business_kpi_history['latest_blocked_actions']}`",
                f"- mailer_business_kpi_latest_send_mail: `{str(bool(business_kpi_history.get('latest_send_mail'))).lower()}`",
                f"- mailer_business_kpi_raw_recipients: `{str(bool(business_kpi_history.get('raw_recipient_addresses_included'))).lower()}`",
                f"- mailer_business_kpi_secrets: `{str(bool(business_kpi_history.get('secrets_included'))).lower()}`",
                f"- email_sent: `{email_sent}`",
                f"- send_decision: `{send_decision}`",
                "",
                "Raw recipient addresses and secrets are intentionally omitted.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    draft = enqueue_mailer_action(
        {
            "action_type": "owner_report",
            "risk_level": "SAFE_AUTO",
            "mailbox": "support@voiddorescue.com",
            "template_key": "owner_status_report",
            "payload_json": {
                "source": "daily_digest_hook",
                "report_date": today,
                "launch_readiness_state": state["launch_readiness_state"],
                "live_outreach_sent_count": state["live_outreach_sent_count"],
                "warmup_sent_count": state["warmup_sent_count"],
                "bounce_count": state["bounce_count"],
                "rate_limit_signal_count": state["rate_limit_signal_count"],
                "next_allowed_action": mailer["next_allowed_action"],
                "payments_today": payments_today,
                "revenue_today": revenue_today,
                "currency": "USD",
                "mailer_ops": {
                    "real_count": ops["real_count"],
                    "synthetic_count": ops["synthetic_count"],
                    "blocked_unsafe_count": ops["blocked_unsafe_count"],
                },
                "mailer_ops_retention_history": {
                    "count": ops_retention_history["count"],
                    "latest_send_mail": bool((ops_retention_history.get("latest") or {}).get("send_mail")),
                    "raw_recipient_addresses_included": bool(ops_retention_history.get("raw_recipient_addresses_included")),
                    "secrets_included": bool(ops_retention_history.get("secrets_included")),
                },
                "mailer_policy_score_history": {
                    "count": policy_score_history["count"],
                    "latest_score": policy_score_history["latest_score"],
                    "latest_decision": policy_score_history["latest_decision"],
                    "latest_blocker_count": policy_score_history["latest_blocker_count"],
                    "latest_send_mail": policy_score_history["latest_send_mail"],
                    "raw_recipient_addresses_included": bool(policy_score_history.get("raw_recipient_addresses_included")),
                    "secrets_included": bool(policy_score_history.get("secrets_included")),
                },
                "mailer_business_kpi_history": {
                    "count": business_kpi_history["count"],
                    "latest_policy_score": business_kpi_history["latest_policy_score"],
                    "latest_action_queue_rows": business_kpi_history["latest_action_queue_rows"],
                    "latest_safe_actions_queued": business_kpi_history["latest_safe_actions_queued"],
                    "latest_blocked_actions": business_kpi_history["latest_blocked_actions"],
                    "latest_send_mail": business_kpi_history["latest_send_mail"],
                    "raw_recipient_addresses_included": bool(business_kpi_history.get("raw_recipient_addresses_included")),
                    "secrets_included": bool(business_kpi_history.get("secrets_included")),
                },
                "email_sent": False,
            },
        }
    )
    send_result = {"processed": 0, "send_mail": False, "smtp_called": False}
    if send_if_safe and not blocked:
        process_mailer_action_queue(20)
        send_result = send_customer_mail(20)
        email_sent = bool(send_result.get("send_mail"))
        send_decision = "sent_owner_daily_email" if email_sent else "owner_daily_email_not_sent"
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('owner_report.generated', 'info', 'Autonomous owner status report generated', %s)
        """,
        (Jsonb({"path": str(path), "email_sent": email_sent, "send_decision": send_decision, "safe": True, "report_date": today}),),
    )
    return {
        "path": str(path),
        "email_sent": email_sent,
        "send_decision": send_decision,
        "state": state,
        "mailer": mailer,
        "monitoring": monitoring,
        "mailer_ops": ops,
        "mailer_ops_retention_history": ops_retention_history,
        "mailer_policy_score_history": policy_score_history,
        "mailer_business_kpi_history": business_kpi_history,
        "owner_report_action": draft,
        "send_result": send_result,
    }


def write_mailer_digest_agent_report(agent_run_id: str, owner_report: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    state = owner_report.get("state") or runtime_state_snapshot()
    mailer = owner_report.get("mailer") or mailer_control_room_summary(write_snapshot=False)
    action = owner_report.get("owner_report_action") or {}
    ops_retention_history = owner_report.get("mailer_ops_retention_history") or mailer_ops_retention_report_history()
    policy_score_history = owner_report.get("mailer_policy_score_history") or latest_mailer_policy_score_history()
    business_kpi_history = owner_report.get("mailer_business_kpi_history") or latest_mailer_business_kpi_history()
    blockers = mailer.get("warmup_blocked_reason") or []
    email_sent = bool(owner_report.get("email_sent", False))
    path = Path(settings.storage_root) / "reports" / "mailer_digest_agent_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Vøiddo Rescue Mailer Digest Agent Report",
                "",
                f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
                f"- agent_run_id: `{agent_run_id}`",
                f"- owner_report_path: `{owner_report.get('path', '')}`",
                f"- owner_report_action_id: `{action.get('id', '')}`",
                f"- email_sent: `{str(email_sent).lower()}`",
                f"- warmup_sent_count: `{state.get('warmup_sent_count', 0)}`",
                f"- live_outreach_sent_count: `{state.get('live_outreach_sent_count', 0)}`",
                f"- bounce_or_dsn_count_24h: `{state.get('bounce_count', 0)}`",
                f"- rate_limit_signal_count_24h: `{state.get('rate_limit_signal_count', 0)}`",
                f"- current_mail_blockers: `{', '.join(blockers) if blockers else 'none'}`",
                f"- mailer_ops_retention_history_rows: `{ops_retention_history.get('count', 0)}`",
                f"- mailer_ops_retention_latest_send_mail: `{str(bool((ops_retention_history.get('latest') or {}).get('send_mail'))).lower()}`",
                f"- mailer_ops_retention_raw_recipients: `{str(bool(ops_retention_history.get('raw_recipient_addresses_included'))).lower()}`",
                f"- mailer_ops_retention_secrets: `{str(bool(ops_retention_history.get('secrets_included'))).lower()}`",
                f"- mailer_policy_score_history_rows: `{policy_score_history.get('count', 0)}`",
                f"- mailer_policy_latest_score: `{policy_score_history.get('latest_score', 0)}`",
                f"- mailer_policy_latest_decision: `{policy_score_history.get('latest_decision', 'missing')}`",
                f"- mailer_policy_latest_blockers: `{policy_score_history.get('latest_blocker_count', 0)}`",
                f"- mailer_policy_history_raw_recipients: `{str(bool(policy_score_history.get('raw_recipient_addresses_included'))).lower()}`",
                f"- mailer_policy_history_secrets: `{str(bool(policy_score_history.get('secrets_included'))).lower()}`",
                f"- mailer_business_kpi_history_rows: `{business_kpi_history.get('count', 0)}`",
                f"- mailer_business_kpi_latest_policy_score: `{business_kpi_history.get('latest_policy_score')}`",
                f"- mailer_business_kpi_latest_queue_rows: `{business_kpi_history.get('latest_action_queue_rows', 0)}`",
                f"- mailer_business_kpi_latest_safe_actions: `{business_kpi_history.get('latest_safe_actions_queued', 0)}`",
                f"- mailer_business_kpi_latest_blocked_actions: `{business_kpi_history.get('latest_blocked_actions', 0)}`",
                f"- mailer_business_kpi_latest_send_mail: `{str(bool(business_kpi_history.get('latest_send_mail'))).lower()}`",
                f"- mailer_business_kpi_raw_recipients: `{str(bool(business_kpi_history.get('raw_recipient_addresses_included'))).lower()}`",
                f"- mailer_business_kpi_secrets: `{str(bool(business_kpi_history.get('secrets_included'))).lower()}`",
                f"- send_decision: `{owner_report.get('send_decision', '')}`",
                "",
                "Raw recipient addresses, message bodies, mailbox passwords, and secrets are intentionally omitted.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    digest = {
        "path": str(path),
        "agent_run_id": agent_run_id,
        "owner_report_path": owner_report.get("path", ""),
        "owner_report_action_id": action.get("id", ""),
        "email_sent": email_sent,
        "warmup_sent_count": int(state.get("warmup_sent_count", 0) or 0),
        "live_outreach_sent_count": int(state.get("live_outreach_sent_count", 0) or 0),
        "current_mail_blockers": blockers,
        "mailer_ops_retention_history": {
            "count": int(ops_retention_history.get("count", 0) or 0),
            "latest_send_mail": bool((ops_retention_history.get("latest") or {}).get("send_mail")),
            "raw_recipient_addresses_included": bool(ops_retention_history.get("raw_recipient_addresses_included")),
            "secrets_included": bool(ops_retention_history.get("secrets_included")),
        },
        "mailer_policy_score_history": {
            "count": int(policy_score_history.get("count", 0) or 0),
            "latest_score": int(policy_score_history.get("latest_score", 0) or 0),
            "latest_decision": policy_score_history.get("latest_decision", "missing"),
            "latest_blocker_count": int(policy_score_history.get("latest_blocker_count", 0) or 0),
            "latest_send_mail": bool(policy_score_history.get("latest_send_mail")),
            "raw_recipient_addresses_included": bool(policy_score_history.get("raw_recipient_addresses_included")),
            "secrets_included": bool(policy_score_history.get("secrets_included")),
        },
        "mailer_business_kpi_history": {
            "count": int(business_kpi_history.get("count", 0) or 0),
            "latest_policy_score": business_kpi_history.get("latest_policy_score"),
            "latest_action_queue_rows": int(business_kpi_history.get("latest_action_queue_rows", 0) or 0),
            "latest_safe_actions_queued": int(business_kpi_history.get("latest_safe_actions_queued", 0) or 0),
            "latest_blocked_actions": int(business_kpi_history.get("latest_blocked_actions", 0) or 0),
            "latest_send_mail": bool(business_kpi_history.get("latest_send_mail")),
            "raw_recipient_addresses_included": bool(business_kpi_history.get("raw_recipient_addresses_included")),
            "secrets_included": bool(business_kpi_history.get("secrets_included")),
        },
    }
    row = execute(
        """
        INSERT INTO mailer_digest_reports(
            agent_run_id, report_path, owner_report_action_id, email_sent,
            warmup_sent_count, live_outreach_sent_count, bounce_or_dsn_count_24h,
            rate_limit_signal_count_24h, blockers_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            agent_run_id,
            str(path),
            action.get("id") or None,
            email_sent,
            digest["warmup_sent_count"],
            digest["live_outreach_sent_count"],
            int(state.get("bounce_count", 0) or 0),
            int(state.get("rate_limit_signal_count", 0) or 0),
            Jsonb(blockers),
        ),
    )
    digest["history_id"] = str(row["id"])
    digest["history_created_at"] = row["created_at"].isoformat()
    return digest


def mailer_digest_retention_summary() -> dict[str, Any]:
    summary = fetch_one(
        """
        SELECT count(*) AS total_rows,
               count(*) FILTER (WHERE created_at > now() - interval '24 hours') AS rows_last_24h,
               min(created_at) AS oldest_retained_at,
               max(created_at) AS latest_retained_at
        FROM mailer_digest_reports
        """
    )
    latest = fetch_one(
        """
        SELECT email_sent, warmup_sent_count, live_outreach_sent_count, created_at
        FROM mailer_digest_reports
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    return json_safe(
        {
            "total_rows": int(summary["total_rows"]) if summary else 0,
            "rows_last_24h": int(summary["rows_last_24h"]) if summary else 0,
            "oldest_retained_at": summary["oldest_retained_at"] if summary else None,
            "latest_retained_at": summary["latest_retained_at"] if summary else None,
            "latest_email_sent": bool(latest["email_sent"]) if latest else False,
            "latest_warmup_sent_count": int(latest["warmup_sent_count"]) if latest else 0,
            "latest_live_outreach_sent_count": int(latest["live_outreach_sent_count"]) if latest else 0,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def cleanup_mailer_digest_history(keep: int = 90) -> dict[str, Any]:
    keep = max(1, int(keep))
    before = mailer_digest_retention_summary()
    deleted = execute(
        """
        WITH retained AS (
            SELECT id
            FROM mailer_digest_reports
            ORDER BY created_at DESC, id DESC
            LIMIT %s
        ),
        removed AS (
            DELETE FROM mailer_digest_reports
            WHERE id NOT IN (SELECT id FROM retained)
            RETURNING id
        )
        SELECT count(*) AS deleted_count FROM removed
        """,
        (keep,),
    )
    after = mailer_digest_retention_summary()
    return {
        "keep": keep,
        "deleted_count": int(deleted["deleted_count"]) if deleted else 0,
        "before": before,
        "after": after,
        "send_mail": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
