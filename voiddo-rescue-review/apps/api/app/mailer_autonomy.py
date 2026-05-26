from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .email_templates import render_all_samples
from .mailer_throttle import throttle_decision
from .p0 import json_safe, latest_mail_qa_decision, mail_signal_summary, run_mail_qa, warmup_calendar_health
from .quality_plugins import latest_quality_summary
from .warmup_planner import apply_provider_spacing_when_safe


def email_template_autonomy_qa() -> dict[str, Any]:
    rendered = render_all_samples()
    forbidden = ["codex", "chatgpt", "built by ai", "ai-generated", "operator console", "shell command"]
    failures: list[dict[str, Any]] = []
    for item in rendered:
        text = f"{item['subject']}\n{item['text']}".lower()
        issues = list(item["qa"].get("issues", []))
        for phrase in forbidden:
            if phrase in text:
                issues.append(f"forbidden_public_language:{phrase}")
        if issues:
            failures.append({"template_key": item["template_key"], "language": item["language"], "issues": issues})
    return {"checked": len(rendered), "failures": failures, "passed": not failures}


def record_mail_signal_lessons(window_hours: int = 24) -> dict[str, Any]:
    signals = mail_signal_summary(window_hours)
    lessons: list[dict[str, Any]] = []
    for item in signals["items"]:
        lesson_key = f"{item['signal_type']}:{item['severity']}"
        lesson = {
            "window_hours": window_hours,
            "count": int(item["count"]),
            "policy": "block_sends_and_increase_spacing_without_storing_raw_recipients",
            "no_raw_recipient_addresses": True,
        }
        row = execute(
            """
            INSERT INTO mail_signal_lessons(lesson_key, signal_type, severity, active, lesson_json)
            VALUES (%s, %s, %s, true, %s)
            ON CONFLICT (lesson_key) DO UPDATE
              SET active = true, lesson_json = EXCLUDED.lesson_json, updated_at = now()
            RETURNING *
            """,
            (lesson_key, item["signal_type"], item["severity"], Jsonb(lesson)),
        )
        lessons.append(dict(row))
    return {"signals": signals, "lessons_recorded": len(lessons), "lessons": lessons}


def _latest_campaign_summary() -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT status, count(*) AS count
        FROM campaign_leads
        GROUP BY status
        ORDER BY status
        """
    )
    return {"campaign_lead_statuses": [dict(row) for row in rows]}


def _inbox_summary() -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT classification, human_review_required, count(*) AS count
        FROM inbox_threads
        GROUP BY classification, human_review_required
        ORDER BY classification NULLS LAST, human_review_required
        """
    )
    return {"threads": [dict(row) for row in rows]}


def _owner_command_summary() -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT risk_level, status, count(*) AS count
        FROM owner_commands
        GROUP BY risk_level, status
        ORDER BY risk_level, status
        """
    )
    return {"commands": [dict(row) for row in rows]}


def mailer_status_snapshot() -> dict[str, Any]:
    signals = mail_signal_summary(24)
    mail_qa = latest_mail_qa_decision()
    warmup = warmup_calendar_health()
    throttle = {
        "global_outreach": throttle_decision("global", "outreach", 1800),
        "global_warmup": throttle_decision("global", "warmup", 1800),
        "global_diagnostic": throttle_decision("global", "diagnostic", 600),
    }
    inbox = _inbox_summary()
    owner_commands = _owner_command_summary()
    campaign = _latest_campaign_summary()
    templates = email_template_autonomy_qa()
    quality = latest_quality_summary()

    status = "ready_scheduler_no_outreach"
    next_safe_action = "allow_natural_warmup_timer_only_if_pre_send_gate_passes"
    if signals["bounce_or_dsn_count"] or signals["rate_limit_count"] or signals["spam_signal_count"]:
        status = "blocked_recent_mail_signals"
        next_safe_action = "wait_until_recent_signal_window_clears"
    elif mail_qa != "PASS":
        status = "blocked_mail_qa"
        next_safe_action = "rerun_mail_qa_without_deliverability_send"
    elif not all(item["allowed"] for item in throttle.values()):
        status = "blocked_throttle"
        next_safe_action = "wait_for_mail_throttle"
    elif not templates["passed"] or quality.get("blockers"):
        status = "blocked_quality_gate"
        next_safe_action = "fix_template_or_visual_quality"

    result = json_safe({
        "signals": signals,
        "mail_qa_decision": mail_qa,
        "warmup": warmup,
        "throttle": throttle,
        "inbox": inbox,
        "owner_commands": owner_commands,
        "campaign": campaign,
        "template_qa": templates,
        "quality": {"all_pass": quality.get("all_pass"), "blockers": len(quality.get("blockers", []))},
        "live_outreach_allowed": False,
    })
    row = execute(
        """
        INSERT INTO mailer_status_snapshots(
          status, next_safe_action, mail_qa_decision, bounce_or_dsn_count, rate_limit_count, spam_signal_count,
          warmup_json, throttle_json, inbox_json, owner_commands_json, campaign_json,
          template_qa_json, quality_json, result_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            status,
            next_safe_action,
            mail_qa,
            signals["bounce_or_dsn_count"],
            signals["rate_limit_count"],
            signals["spam_signal_count"],
            Jsonb(json_safe(warmup)),
            Jsonb(json_safe(throttle)),
            Jsonb(json_safe(inbox)),
            Jsonb(json_safe(owner_commands)),
            Jsonb(json_safe(campaign)),
            Jsonb(json_safe(templates)),
            Jsonb(json_safe({"all_pass": quality.get("all_pass"), "blockers": len(quality.get("blockers", []))})),
            Jsonb(result),
        ),
    )
    return dict(row)


def run_clean_window_recovery(window_hours: int = 24) -> dict[str, Any]:
    learning = record_mail_signal_lessons(window_hours)
    signals = learning["signals"]
    if signals["bounce_or_dsn_count"] or signals["rate_limit_count"] or signals["spam_signal_count"]:
        row = execute(
            """
            INSERT INTO clean_window_recovery_runs(status, window_hours, mail_qa_decision, sends_started, signals_json, result_json)
            VALUES ('blocked_recent_signals', %s, %s, false, %s, %s)
            RETURNING *
            """,
            (window_hours, latest_mail_qa_decision(), Jsonb(json_safe(signals)), Jsonb({"learning": {"lessons_recorded": learning["lessons_recorded"]}, "policy": "no_send_recovery"})),
        )
        return dict(row)
    mail_qa = run_mail_qa(allow_deliverability_send=False)
    repair = None
    status = "blocked_mail_qa"
    if mail_qa["decision"] == "PASS":
        repair = apply_provider_spacing_when_safe(50)
        status = "spacing_applied" if repair.get("applied") else repair.get("status", "spacing_not_applied")
    row = execute(
        """
        INSERT INTO clean_window_recovery_runs(status, window_hours, mail_qa_decision, spacing_repair_id, sends_started, signals_json, result_json)
        VALUES (%s, %s, %s, %s, false, %s, %s)
        RETURNING *
        """,
        (
            status,
            window_hours,
            mail_qa["decision"],
            repair.get("id") if repair else None,
            Jsonb(json_safe(signals)),
            Jsonb(json_safe({"mail_qa": mail_qa, "spacing_repair": repair, "policy": "no_send_recovery"})),
        ),
    )
    return dict(row)
