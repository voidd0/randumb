from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .mailer_action_queue import enqueue_mailer_action
from .mailer_autonomy import mailer_status_snapshot
from .mailer_ops_actions import mailer_ops_action_summary
from .p0 import json_safe, latest_mail_qa_decision, mail_signal_summary, runtime_state_snapshot, warmup_calendar_health


def _rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in fetch_all(sql, params)]


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
                "raw_recipient_addresses_included": False,
                "secrets_included": False,
            },
            "email_sent": bool((latest_report or {}).get("payload_json", {}).get("email_sent", False)) if latest_report else False,
            "send_mail": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    )


def write_owner_status_report(send_if_safe: bool = False) -> dict[str, Any]:
    settings = get_settings()
    state = runtime_state_snapshot()
    mailer = mailer_control_room_summary(write_snapshot=True)
    ops = mailer_ops_action_summary()
    monitoring = monitoring_control_room_summary()
    blocked = bool(mailer["warmup_blocked_reason"]) or state["latest_mail_qa_decision"] != "PASS"
    email_sent = False
    send_decision = "blocked_recent_mail_signals" if blocked else "not_sent_draft_only"
    if send_if_safe and not blocked:
        send_decision = "ready_but_no_transport_send_in_report_path"

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
                "mailer_ops": {
                    "real_count": ops["real_count"],
                    "synthetic_count": ops["synthetic_count"],
                    "blocked_unsafe_count": ops["blocked_unsafe_count"],
                },
                "email_sent": False,
            },
        }
    )
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('owner_report.generated', 'info', 'Autonomous owner status report generated', %s)
        """,
        (Jsonb({"path": str(path), "email_sent": email_sent, "send_decision": send_decision, "safe": True}),),
    )
    return {
        "path": str(path),
        "email_sent": email_sent,
        "send_decision": send_decision,
        "state": state,
        "mailer": mailer,
        "monitoring": monitoring,
        "mailer_ops": ops,
        "owner_report_action": draft,
    }


def write_mailer_digest_agent_report(agent_run_id: str, owner_report: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    state = owner_report.get("state") or runtime_state_snapshot()
    mailer = owner_report.get("mailer") or mailer_control_room_summary(write_snapshot=False)
    action = owner_report.get("owner_report_action") or {}
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
