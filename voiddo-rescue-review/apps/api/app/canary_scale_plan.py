from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_one
from .launch_readiness_scoreboard import launch_readiness_scoreboard
from .mail_send_compliance import mail_send_compliance_snapshot
from .p0 import json_safe, latest_mail_qa_decision, mail_signal_summary, recipient_hash


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _count(query: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(query, params)
    return int((row or {}).get("count", 0) or 0)


def canary_scale_plan(canary_limit: int = 20, next_batch_limit: int = 40, store: bool = True) -> dict[str, Any]:
    """Read-only canary evaluator.

    It does not stage or send mail. The output is intentionally suitable for
    automation: continue the current canary, pause on risk, or prepare the next
    batch in dry-run only after the current canary has fully completed cleanly.
    """
    safe_canary_limit = max(1, min(int(canary_limit or 20), 100))
    safe_next_limit = max(safe_canary_limit, min(int(next_batch_limit or 40), 100))
    mail_qa = latest_mail_qa_decision()
    signals = mail_signal_summary(24)
    compliance = mail_send_compliance_snapshot(24)
    scoreboard = launch_readiness_scoreboard(25)

    sent = _count("SELECT count(*) AS count FROM outreach_messages WHERE status IN ('sent', 'bounced')")
    queued = _count("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    blocked = _count(
        "SELECT count(*) AS count FROM outreach_messages WHERE status IN ('failed', 'blocked', 'transport_blocked', 'bounced')"
    )
    preview = _count("SELECT count(*) AS count FROM outreach_messages WHERE status = 'preview'")
    first_sent = fetch_one("SELECT min(sent_at) AS first_sent_at FROM outreach_messages WHERE status = 'sent'")
    reply_count = _count(
        """
        SELECT count(*) AS count
        FROM inbox_threads it
        WHERE it.lead_id IN (
            SELECT lead_id FROM outreach_messages
            WHERE status IN ('sent', 'bounced')
              AND lead_id IS NOT NULL
        )
          AND it.updated_at >= COALESCE((SELECT min(sent_at) FROM outreach_messages WHERE status = 'sent'), now())
        """
    )
    click_count = _count(
        """
        SELECT count(*) AS count
        FROM email_events ee
        JOIN outreach_messages om ON om.id = ee.outreach_message_id
        WHERE om.status IN ('sent', 'bounced')
          AND ee.event_type IN ('click', 'clicked', 'outreach_click')
          AND ee.created_at >= COALESCE((SELECT min(sent_at) FROM outreach_messages WHERE status = 'sent'), now())
        """
    )
    latest_sent = fetch_one(
        """
        SELECT om.id, om.sent_at, lower(split_part(COALESCE(l.email, ''), '@', 2)) AS recipient_domain
        FROM outreach_messages om
        LEFT JOIN leads l ON l.id = om.lead_id
        WHERE om.status = 'sent'
        ORDER BY om.sent_at DESC NULLS LAST
        LIMIT 1
        """
    )

    blockers: list[str] = []
    if mail_qa != "PASS":
        blockers.append("mail_qa_not_pass")
    if compliance.get("decision") != "PASS":
        blockers.append("mail_send_compliance_not_pass")
    if int(signals.get("bounce_or_dsn_count", 0) or 0) > 0:
        blockers.append("recent_bounce_or_dsn")
    if int(signals.get("rate_limit_count", 0) or 0) > 0:
        blockers.append("recent_rate_limit")
    if int(signals.get("spam_signal_count", 0) or 0) > 0:
        blockers.append("recent_spam_signal")
    if int(signals.get("mail_auth_failure_count", 0) or 0) > 0:
        blockers.append("recent_mail_auth_failure")
    if blocked:
        blockers.append("blocked_or_failed_outreach_rows_present")
    if int(scoreboard.get("blocker_count", 0) or 0) > 0:
        blockers.append("launch_scoreboard_has_blockers")

    if blockers:
        decision = "PAUSE_AND_REVIEW_CANARY"
        next_action = "pause_outreach_and_investigate_mail_or_queue_signal"
    elif queued > 0:
        decision = "CONTINUE_CURRENT_CANARY"
        next_action = "let_worker_continue_existing_queued_canary_under_post_send_observer"
    elif sent < safe_canary_limit:
        decision = "WAIT_INSUFFICIENT_CANARY_VOLUME"
        next_action = "prepare_more_candidates_in_dry_run_before_any_scale_up"
    else:
        decision = "READY_FOR_NEXT_BATCH_DRY_RUN"
        next_action = "prepare_next_batch_preview_and_preflight_only_no_send"

    result = json_safe(
        {
            "decision": decision,
            "next_action": next_action,
            "canary_limit": safe_canary_limit,
            "recommended_next_batch_limit": safe_next_limit if decision == "READY_FOR_NEXT_BATCH_DRY_RUN" else 0,
            "sent_count": sent,
            "queued_count": queued,
            "blocked_count": blocked,
            "preview_count": preview,
            "reply_count_since_first_send": reply_count,
            "click_count_since_first_send": click_count,
            "first_sent_at": (first_sent or {}).get("first_sent_at"),
            "latest_sent": {
                "outreach_message_id": str(latest_sent["id"]) if latest_sent else "",
                "sent_at": latest_sent.get("sent_at") if latest_sent else None,
                "recipient_domain_hash": recipient_hash(latest_sent.get("recipient_domain") or "") if latest_sent else "",
            },
            "mail_qa_decision": mail_qa,
            "mail_send_compliance_decision": compliance.get("decision"),
            "launch_readiness_state": scoreboard.get("state"),
            "launch_score": scoreboard.get("score"),
            "launch_blocker_count": int(scoreboard.get("blocker_count", 0) or 0),
            "signal_counts": {
                "bounce_or_dsn": int(signals.get("bounce_or_dsn_count", 0) or 0),
                "rate_limit": int(signals.get("rate_limit_count", 0) or 0),
                "spam": int(signals.get("spam_signal_count", 0) or 0),
                "mail_auth_failure": int(signals.get("mail_auth_failure_count", 0) or 0),
            },
            "blockers": blockers,
            **SAFE_FLAGS,
        }
    )
    if store:
        execute(
            """
            INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at)
            VALUES ('canary_scale_plan_agent', %s, %s, now(), now())
            """,
            ("blocked" if blockers else "completed", Jsonb(result)),
        )
    return result
