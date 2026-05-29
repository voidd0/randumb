from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .campaign_preflight_status import latest_campaign_preflight_status
from .canary_scale_plan import canary_scale_plan
from .db import execute, fetch_all, fetch_one
from .mail_send_compliance import mail_send_compliance_snapshot
from .p0 import json_safe, latest_mail_qa_decision, mail_signal_summary, runtime_control_enabled, set_runtime_control


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _latest_blocking_signal_at(window_hours: int) -> str | None:
    row = fetch_one(
        """
        SELECT max(created_at) AS last_signal_at
        FROM mail_signals
        WHERE signal_type IN (
          'bounce', 'dsn', 'smtp_rate_limit', 'spam_signal',
          'auth_failure', 'tls_failure', 'dkim_failure', 'dmarc_failure'
        )
          AND created_at >= now() - (%s || ' hours')::interval
        """,
        (max(1, min(int(window_hours or 24), 168)),),
    )
    value = (row or {}).get("last_signal_at")
    return value.isoformat() if value else None


def _queued_campaign_preflights(limit: int = 20) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT DISTINCT cl.campaign_id
        FROM outreach_messages om
        JOIN campaign_leads cl
          ON cl.lead_id = om.lead_id
         AND (cl.audit_id = om.audit_id OR cl.audit_id IS NULL OR om.audit_id IS NULL)
        WHERE om.status = 'queued'
          AND cl.campaign_id IS NOT NULL
        ORDER BY cl.campaign_id
        LIMIT %s
        """,
        (max(1, min(int(limit or 20), 100)),),
    )
    statuses = [latest_campaign_preflight_status(str(row["campaign_id"])) for row in rows]
    blocked = [item for item in statuses if not item.get("allowed")]
    return {
        "campaign_count": len(statuses),
        "allowed_count": len(statuses) - len(blocked),
        "blocked_count": len(blocked),
        "blocked_reasons": sorted({str(item.get("reason") or "unknown") for item in blocked}),
        "policy_stale_count": len([item for item in blocked if item.get("reason") == "campaign_preflight_policy_stale"]),
        "current_policy_count": len([item for item in statuses if item.get("policy_current")]),
        **SAFE_FLAGS,
    }


def canary_resume_plan(window_hours: int = 24, apply: bool = False, store: bool = True) -> dict[str, Any]:
    """Evaluate whether a paused canary may resume.

    This is intentionally conservative. It can clear `pause_outreach` only when
    explicitly called with `apply=True` and every safety gate is clean. It never
    stages new messages and never sends mail.
    """
    safe_window = max(1, min(int(window_hours or 24), 168))
    signals = mail_signal_summary(safe_window)
    mail_qa = latest_mail_qa_decision()
    compliance = mail_send_compliance_snapshot(safe_window)
    scale = canary_scale_plan(20, 40, store=False)
    queued_preflights = _queued_campaign_preflights(20)
    pause_outreach = runtime_control_enabled("pause_outreach")
    last_signal_at = _latest_blocking_signal_at(safe_window)

    blockers: list[str] = []
    if int(signals.get("bounce_or_dsn_count", 0) or 0) > 0:
        blockers.append("recent_bounce_or_dsn")
    if int(signals.get("rate_limit_count", 0) or 0) > 0:
        blockers.append("recent_rate_limit")
    if int(signals.get("spam_signal_count", 0) or 0) > 0:
        blockers.append("recent_spam_signal")
    if int(signals.get("mail_auth_failure_count", 0) or 0) > 0:
        blockers.append("recent_mail_auth_failure")
    if mail_qa != "PASS":
        blockers.append("mail_qa_not_pass")
    if compliance.get("decision") != "PASS":
        blockers.append("mail_send_compliance_not_pass")
    if scale.get("decision") not in {"CONTINUE_CURRENT_CANARY", "READY_FOR_NEXT_BATCH_DRY_RUN"}:
        blockers.append("canary_scale_not_ready")
    if int(scale.get("queued_count", 0) or 0) <= 0 and scale.get("decision") == "CONTINUE_CURRENT_CANARY":
        blockers.append("queued_canary_rows_missing")
    if int(queued_preflights.get("blocked_count", 0) or 0) > 0:
        blockers.append("queued_campaign_preflight_not_current_pass")
    if int(queued_preflights.get("campaign_count", 0) or 0) <= 0 and int(scale.get("queued_count", 0) or 0) > 0:
        blockers.append("queued_campaign_context_missing")

    if blockers:
        decision = "KEEP_PAUSED"
        next_action = "wait_clean_signal_window_and_repair_canary_blockers"
    elif not pause_outreach:
        decision = "ALREADY_ACTIVE"
        next_action = "let_worker_continue_existing_queued_canary_under_post_send_observer"
    elif apply:
        set_runtime_control("pause_outreach", False, "canary_resume_plan", "clean_window_all_gates_passed")
        decision = "RESUMED_CANARY"
        next_action = "worker_may_continue_existing_queue_under_spacing_and_post_send_observer"
    else:
        decision = "READY_TO_RESUME_DRY_RUN"
        next_action = "call_with_apply_true_only_after_operator_or_owner_policy_allows_resume"

    result = json_safe(
        {
            "status": "completed",
            "decision": decision,
            "next_action": next_action,
            "window_hours": safe_window,
            "apply_requested": bool(apply),
            "pause_outreach_before": pause_outreach,
            "pause_outreach_after": runtime_control_enabled("pause_outreach"),
            "last_blocking_signal_at": last_signal_at,
            "signal_counts": {
                "bounce_or_dsn": int(signals.get("bounce_or_dsn_count", 0) or 0),
                "rate_limit": int(signals.get("rate_limit_count", 0) or 0),
                "spam": int(signals.get("spam_signal_count", 0) or 0),
                "mail_auth_failure": int(signals.get("mail_auth_failure_count", 0) or 0),
            },
            "mail_qa_decision": mail_qa,
            "mail_send_compliance_decision": compliance.get("decision"),
            "canary_scale_decision": scale.get("decision"),
            "canary_scale_blockers": scale.get("blockers", []),
            "queued_count": int(scale.get("queued_count", 0) or 0),
            "sent_or_bounced_count": int(scale.get("sent_or_bounced_count", scale.get("sent_count", 0)) or 0),
            "smtp_sent_count": int(scale.get("smtp_sent_count", 0) or 0),
            "bounced_count": int(scale.get("bounced_count", 0) or 0),
            "blocked_count": int(scale.get("blocked_count", 0) or 0),
            "queued_campaign_preflights": queued_preflights,
            "blockers": blockers,
            **SAFE_FLAGS,
        }
    )
    if store:
        execute(
            """
            INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at)
            VALUES ('canary_resume_plan_agent', %s, %s, now(), now())
            """,
            ("blocked" if blockers else "completed", Jsonb(result)),
        )
    return result


def latest_canary_resume_plan_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, result_json, created_at
        FROM agent_runs
        WHERE agent = 'canary_resume_plan_agent'
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 100)),),
    )
    return {
        "count": len(rows),
        "runs": [
            {
                "id": str(row["id"]),
                "status": row["status"],
                "decision": (row["result_json"] or {}).get("decision"),
                "blockers": (row["result_json"] or {}).get("blockers", []),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ],
        **SAFE_FLAGS,
    }
