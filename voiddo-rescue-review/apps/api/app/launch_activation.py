from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .canary_batch_quality import canary_batch_quality
from .db import execute, fetch_all, fetch_one
from .launch_readiness_scoreboard import launch_readiness_scoreboard
from .p0 import json_safe, latest_preview_transport_gate_status, live_outreach_quota_status, set_runtime_control


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _count(sql: str, params: tuple = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"] or 0) if row else 0


def _latest_preflight_counts(limit: int = 25) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT DISTINCT ON (c.id) c.id AS campaign_id, p.decision, p.blocker_count, p.ready_count, p.created_at
        FROM campaigns c
        JOIN campaign_leads cl ON cl.campaign_id = c.id AND cl.status = 'preview'
        JOIN LATERAL (
          SELECT action
          FROM campaign_preview_reviews
          WHERE campaign_lead_id = cl.id
          ORDER BY created_at DESC
          LIMIT 1
        ) latest_review ON true
        LEFT JOIN campaign_preflight_runs p ON p.campaign_id = c.id
        WHERE c.status IN ('preview_ready', 'draft')
          AND latest_review.action = 'approved'
        ORDER BY c.id, p.created_at DESC NULLS LAST
        LIMIT %s
        """,
        (max(1, min(int(limit or 25), 100)),),
    )
    passed = [row for row in rows if row.get("decision") == "PASS_NO_SEND_PREFLIGHT"]
    missing = [row for row in rows if not row.get("decision")]
    return {
        "checked_campaign_count": len(rows),
        "passed_campaign_count": len(passed),
        "failed_campaign_count": len(rows) - len(passed) - len(missing),
        "missing_campaign_count": len(missing),
        "latest_pass_created_at": max((row["created_at"] for row in passed), default=None),
    }


def launch_activation_readiness(limit: int = 25) -> dict[str, Any]:
    settings = get_settings()
    scoreboard = launch_readiness_scoreboard(limit)
    transport = latest_preview_transport_gate_status()
    quota = live_outreach_quota_status()
    preflight = _latest_preflight_counts(limit)
    canary_quality = canary_batch_quality(min(max(1, int(limit or 20)), 20), store=False)
    preview_count = _count("SELECT count(*) AS count FROM outreach_messages WHERE status = 'preview'")
    approved_preview_count = _count(
        """
        SELECT count(*) AS count
        FROM campaign_leads cl
        JOIN LATERAL (
          SELECT action
          FROM campaign_preview_reviews
          WHERE campaign_lead_id = cl.id
          ORDER BY created_at DESC
          LIMIT 1
        ) latest_review ON true
        WHERE cl.status = 'preview'
          AND latest_review.action = 'approved'
        """
    )
    live_sent = _count("SELECT count(*) AS count FROM outreach_messages WHERE status = 'sent'")
    warmup_sent = _count("SELECT count(*) AS count FROM warmup_schedule WHERE status = 'sent'")
    blockers: list[str] = []
    if scoreboard.get("state") != "PREVIEW_PIPELINE_READY_NO_OUTREACH" or int(scoreboard.get("score") or 0) < 100:
        blockers.append("launch_scoreboard_not_preview_ready")
    if int(scoreboard.get("blocker_count") or 0) > 0:
        blockers.append("launch_scoreboard_has_blockers")
    if preview_count <= 0:
        blockers.append("preview_outreach_messages_missing")
    if approved_preview_count <= 0:
        blockers.append("approved_campaign_previews_missing")
    canary_quality_pass = canary_quality.get("decision") == "PASS_CANARY_BATCH_QUALITY"
    if preflight["passed_campaign_count"] <= 0 or (not canary_quality_pass and (preflight["failed_campaign_count"] > 0 or preflight["missing_campaign_count"] > 0)):
        blockers.append("campaign_preflight_not_clean")
    if not canary_quality_pass:
        blockers.append("canary_batch_quality_not_pass")
    transport_checks = transport.get("checks") or {}
    if not transport_checks.get("unsubscribe_one_click_ready"):
        blockers.append("signed_unsubscribe_not_ready")
    if not transport_checks.get("html_body_ready"):
        blockers.append("branded_html_body_not_ready")
    if not quota["allowed"]:
        blockers.extend(quota["blockers"])
    if settings.outreach_dry_run is not True or settings.outreach_paused is not True or settings.first_live_send_flag is not False:
        blockers.append("runtime_live_flags_not_locked_before_activation")

    decision = "READY_FOR_OPERATOR_ENV_ACTIVATION" if not blockers else "BLOCKED"
    return json_safe(
        {
            "status": "completed",
            "decision": decision,
            "blockers": sorted(set(blockers)),
            "scoreboard": {
                "state": scoreboard.get("state"),
                "score": int(scoreboard.get("score") or 0),
                "blocker_count": int(scoreboard.get("blocker_count") or 0),
                "live_outreach_allowed": bool(scoreboard.get("live_outreach_allowed", False)),
            },
            "preflight": preflight,
            "canary_quality": {
                "decision": canary_quality.get("decision"),
                "candidate_count": int(canary_quality.get("candidate_count") or 0),
                "segment_count": int(canary_quality.get("segment_count") or 0),
                "campaign_count": int(canary_quality.get("campaign_count") or 0),
                "recipient_domain_count": int(canary_quality.get("recipient_domain_count") or 0),
                "blockers": canary_quality.get("blockers") or [],
                "warnings": canary_quality.get("warnings") or [],
            },
            "preview_message_count": preview_count,
            "approved_preview_count": approved_preview_count,
            "live_outreach_sent_count": live_sent,
            "warmup_sent_count": warmup_sent,
            "transport_reason": transport.get("reason"),
            "transport_checks": {
                "outreach_dry_run": transport_checks.get("outreach_dry_run"),
                "outreach_paused": transport_checks.get("outreach_paused"),
                "first_live_send_flag": transport_checks.get("first_live_send_flag"),
                "unsubscribe_one_click_ready": transport_checks.get("unsubscribe_one_click_ready"),
                "html_body_ready": transport_checks.get("html_body_ready"),
                "live_quota": transport_checks.get("live_quota"),
            },
            "quota": quota,
            "activation_env_required": {
                "OUTREACH_DRY_RUN": "false",
                "OUTREACH_PAUSED": "false",
                "FIRST_LIVE_SEND_FLAG": "true",
                "DAILY_SEND_LIMIT": str(settings.daily_send_limit),
                "HOURLY_DOMAIN_SEND_LIMIT": str(settings.hourly_domain_send_limit),
            },
            "rollback_env": {
                "OUTREACH_DRY_RUN": "true",
                "OUTREACH_PAUSED": "true",
                "FIRST_LIVE_SEND_FLAG": "false",
            },
            "apply_default": "blocked_until_ALLOW_LIVE_OUTREACH_ACTIVATION_true_and_confirmation_text_matches",
            **SAFE_FLAGS,
        }
    )


def _record_activation_run(
    readiness: dict[str, Any],
    *,
    status: str,
    decision: str,
    requested_by: str,
    confirm_text: str = "",
    dry_run: bool = True,
    applied: bool = False,
) -> dict[str, Any]:
    scoreboard = readiness.get("scoreboard") or {}
    row = execute(
        """
        INSERT INTO launch_activation_runs(
          status, decision, requested_by, confirm_text_hash, dry_run, applied,
          scoreboard_state, scoreboard_score, blocker_count,
          preview_message_count, approved_preview_count,
          live_outreach_sent_count, warmup_sent_count,
          result_json, send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, status, decision, requested_by, dry_run, applied, created_at
        """,
        (
            status,
            decision,
            requested_by,
            hashlib.sha256(confirm_text.encode("utf-8")).hexdigest()[:24] if confirm_text else "",
            dry_run,
            applied,
            str(scoreboard.get("state") or ""),
            int(scoreboard.get("score") or 0),
            len(readiness.get("blockers") or []),
            int(readiness.get("preview_message_count") or 0),
            int(readiness.get("approved_preview_count") or 0),
            int(readiness.get("live_outreach_sent_count") or 0),
            int(readiness.get("warmup_sent_count") or 0),
            Jsonb(readiness),
        ),
    )
    result = dict(row)
    result.update(SAFE_FLAGS)
    return json_safe(result)


def prepare_launch_activation(limit: int = 25, requested_by: str = "operator") -> dict[str, Any]:
    readiness = launch_activation_readiness(limit)
    run = _record_activation_run(
        readiness,
        status="prepared" if readiness["decision"] == "READY_FOR_OPERATOR_ENV_ACTIVATION" else "blocked",
        decision=readiness["decision"],
        requested_by=requested_by,
        dry_run=True,
    )
    return json_safe({"readiness": readiness, "run": run, "applied": False, **SAFE_FLAGS})


def launch_activation_runbook(limit: int = 25) -> dict[str, Any]:
    readiness = launch_activation_readiness(limit)
    blockers = list(readiness.get("blockers") or [])
    canary_steps = [
        "verify_launch_activation_readiness",
        "verify_live_queue_candidates_redacted",
        "set_operator_env_allow_live_activation_true",
        "set_OUTREACH_DRY_RUN_false",
        "set_OUTREACH_PAUSED_false",
        "set_FIRST_LIVE_SEND_FLAG_true",
        "restart_rescue_api_worker_only",
        "stage_first_canary_batch_limit_20",
        "enable_OUTREACH_WORKER_ENABLED_for_bounded_worker_drain",
        "run_post_send_observer_after_each_send_window",
        "rollback_to_dry_run_and_paused_on_any_blocking_signal",
    ]
    rollback_steps = [
        "set_OUTREACH_DRY_RUN_true",
        "set_OUTREACH_PAUSED_true",
        "set_FIRST_LIVE_SEND_FLAG_false",
        "set_OUTREACH_WORKER_ENABLED_false",
        "restart_rescue_api_worker_only",
        "run_post_send_observer_apply_pause_true",
        "verify_queued_count_zero_or_transport_blocked",
    ]
    return json_safe(
        {
            "status": "ready" if not blockers else "blocked",
            "decision": readiness.get("decision"),
            "blockers": blockers,
            "canary_limit": min(20, get_settings().daily_send_limit),
            "canary_steps": canary_steps,
            "rollback_steps": rollback_steps,
            "activation_env_required": readiness.get("activation_env_required"),
            "rollback_env": {**readiness.get("rollback_env", {}), "OUTREACH_WORKER_ENABLED": "false"},
            "operator_guard": "No live activation is performed by this runbook API.",
            **SAFE_FLAGS,
        }
    )


def rollback_live_outreach(reason: str = "operator_rollback") -> dict[str, Any]:
    controls = [
        set_runtime_control("pause_outreach", True, "launch_rollback", reason),
        set_runtime_control("pause_auto_replies", True, "launch_rollback", reason),
    ]
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('launch.rollback', 'warning', 'Live outreach rollback control applied', %s)
        """,
        (Jsonb(json_safe({"reason": reason, "controls": controls, **SAFE_FLAGS})),),
    )
    return json_safe(
        {
            "ok": True,
            "action": "rollback_live_outreach",
            "controls": controls,
            "required_env": {
                "OUTREACH_DRY_RUN": "true",
                "OUTREACH_PAUSED": "true",
                "FIRST_LIVE_SEND_FLAG": "false",
                "OUTREACH_WORKER_ENABLED": "false",
            },
            "runtime_change_performed": True,
            "env_change_performed": False,
            **SAFE_FLAGS,
        }
    )


def apply_launch_activation(confirm_text: str, requested_by: str = "operator", limit: int = 25, dry_run: bool = True) -> dict[str, Any]:
    readiness = launch_activation_readiness(limit)
    settings = get_settings()
    blockers = list(readiness.get("blockers") or [])
    if confirm_text != "START LIVE OUTREACH":
        blockers.append("confirmation_text_mismatch")
    if not settings.allow_live_outreach_activation:
        blockers.append("allow_live_outreach_activation_env_false")
    if dry_run:
        blockers.append("dry_run_activation_no_runtime_change")
    decision = "READY_RECORDED_NO_ENV_CHANGE" if not blockers else "BLOCKED"
    runtime_controls: list[dict[str, Any]] = []
    if decision == "READY_RECORDED_NO_ENV_CHANGE":
        runtime_controls.append(
            json_safe(set_runtime_control("pause_outreach", False, "launch_activation", "confirmed_live_canary_activation"))
        )
    activation = {
        **readiness,
        "decision": decision,
        "blockers": sorted(set(blockers)),
        "applied": False,
        "runtime_change_performed": bool(runtime_controls),
        "runtime_controls": runtime_controls,
        "note": "This API records the verified activation decision and clears the outreach runtime pause only after all no-send gates pass. Host env changes remain guarded by the runtime deployment operator.",
        **SAFE_FLAGS,
    }
    run = _record_activation_run(
        activation,
        status="ready_recorded" if decision == "READY_RECORDED_NO_ENV_CHANGE" else "blocked",
        decision=decision,
        requested_by=requested_by,
        confirm_text=confirm_text,
        dry_run=dry_run,
        applied=False,
    )
    return json_safe({"activation": activation, "run": run, **SAFE_FLAGS})


def latest_launch_activation_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, decision, requested_by, dry_run, applied,
               scoreboard_state, scoreboard_score, blocker_count,
               preview_message_count, approved_preview_count,
               live_outreach_sent_count, warmup_sent_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM launch_activation_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 50)),),
    )
    return json_safe({"count": len(rows), "runs": [dict(row) for row in rows], **SAFE_FLAGS})
