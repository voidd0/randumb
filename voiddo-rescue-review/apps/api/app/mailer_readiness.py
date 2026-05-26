from __future__ import annotations

from collections import Counter
from typing import Any

from psycopg.types.json import Jsonb

from .campaign_control import campaign_readiness_snapshot
from .config import get_settings
from .db import execute, fetch_all
from .mailer_throttle import throttle_decision
from .p0 import (
    WARMUP_SENDER_ROTATION,
    email_provider,
    latest_mail_qa_decision,
    mail_signal_summary,
    recent_mail_signal_count,
    run_mail_qa,
    smtp_credentials_for_sender,
)


def mailbox_health_score(mailbox: str) -> dict[str, Any]:
    settings = get_settings()
    username, password, from_addr = smtp_credentials_for_sender(settings, mailbox)
    mail_qa = latest_mail_qa_decision()
    recent_signals = recent_mail_signal_count(["bounce", "dsn", "smtp_rate_limit", "spam_signal"], 24)
    mailbox_signals = fetch_all(
        """
        SELECT signal_type, count(*) AS count
        FROM mail_signals
        WHERE mailbox = %s
          AND signal_type = ANY(%s)
          AND created_at >= now() - interval '24 hours'
        GROUP BY signal_type
        """,
        (from_addr, ["bounce", "dsn", "smtp_rate_limit", "spam_signal"]),
    )
    throttle = throttle_decision("mailbox", from_addr, 1800)
    credentials = bool(username and password)
    score = 100
    if not credentials:
        score -= 40
    if mail_qa != "PASS":
        score -= 35
    if recent_signals:
        score -= 35
    if not throttle["allowed"]:
        score -= 15
    score = max(0, score)
    status = "ready" if score >= 80 and credentials and mail_qa == "PASS" and recent_signals == 0 and throttle["allowed"] else "blocked"
    checks = {
        "from_addr": from_addr,
        "throttle": throttle,
        "global_recent_signals": recent_signals,
        "mailbox_signals": [dict(row) for row in mailbox_signals],
        "credential_source": "sender_specific_or_default",
    }
    row = execute(
        """
        INSERT INTO mailbox_health_scores(
          mailbox, status, score, credentials_available, mail_qa_decision,
          recent_signal_count, throttle_allowed, checks_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (mailbox, status, score, credentials, mail_qa, recent_signals, throttle["allowed"], Jsonb(checks)),
    )
    return dict(row)


def sender_rotation_ready() -> dict[str, Any]:
    health = [mailbox_health_score(mailbox) for mailbox in WARMUP_SENDER_ROTATION]
    ready = [item for item in health if item["status"] == "ready"]
    scheduled = fetch_all(
        """
        SELECT recipient_email
        FROM warmup_schedule
        WHERE status = 'scheduled'
        ORDER BY scheduled_for
        LIMIT 20
        """
    )
    providers = [email_provider(row["recipient_email"]) for row in scheduled]
    adjacent_same = sum(1 for index in range(1, len(providers)) if providers[index] == providers[index - 1])
    provider_counts = dict(Counter(providers))
    issues: list[dict[str, Any]] = []
    if not ready:
        issues.append({"code": "no_ready_sender_mailboxes", "severity": "high"})
    if adjacent_same:
        issues.append({"code": "same_provider_adjacent_slots", "severity": "medium", "count": adjacent_same})
    spacing_status = "pass" if not adjacent_same else "needs_spacing"
    status = "ready" if ready and spacing_status == "pass" else "blocked"
    row = execute(
        """
        INSERT INTO sender_rotation_readiness(
          status, ready_sender_count, total_sender_count, provider_spacing_status, issues_json, result_json
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            status,
            len(ready),
            len(health),
            spacing_status,
            Jsonb(issues),
            Jsonb({"mailboxes": [{"mailbox": item["mailbox"], "status": item["status"], "score": item["score"]} for item in health], "provider_counts": provider_counts}),
        ),
    )
    return dict(row)


def run_clean_window_transition(window_hours: int = 24) -> dict[str, Any]:
    signals = mail_signal_summary(window_hours)
    signal_blocked = signals["bounce_or_dsn_count"] > 0 or signals["rate_limit_count"] > 0 or signals["spam_signal_count"] > 0
    mail_qa_result: dict[str, Any] | None = None
    campaign_snapshots: list[dict[str, Any]] = []
    if not signal_blocked:
        mail_qa_result = run_mail_qa(allow_deliverability_send=False)
        for campaign in fetch_all("SELECT id FROM campaigns ORDER BY updated_at DESC NULLS LAST, created_at DESC LIMIT 5"):
            campaign_snapshots.append(campaign_readiness_snapshot(str(campaign["id"])))
    mail_qa_decision = mail_qa_result["decision"] if mail_qa_result else latest_mail_qa_decision()
    warmup_transition = "scheduler_ready_no_send" if not signal_blocked and mail_qa_decision == "PASS" else "not_ready"
    status = "ready_for_scheduler" if warmup_transition == "scheduler_ready_no_send" else ("blocked_recent_signals" if signal_blocked else "blocked_mail_qa")
    row = execute(
        """
        INSERT INTO mail_clean_window_transitions(
          status, window_hours, bounce_or_dsn_count, rate_limit_count, spam_signal_count,
          mail_qa_decision, warmup_transition, sends_started, result_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, false, %s)
        RETURNING *
        """,
        (
            status,
            window_hours,
            signals["bounce_or_dsn_count"],
            signals["rate_limit_count"],
            signals["spam_signal_count"],
            mail_qa_decision,
            warmup_transition,
            Jsonb({"signals": signals, "mail_qa_rerun": bool(mail_qa_result), "campaign_snapshots": len(campaign_snapshots), "policy": "no_send_transition"}),
        ),
    )
    return dict(row)
