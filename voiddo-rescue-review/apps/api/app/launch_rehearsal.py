from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .canary_batch_quality import canary_batch_quality
from .launch_activation import launch_activation_readiness, launch_activation_runbook
from .launch_readiness_scoreboard import launch_readiness_scoreboard
from .mailer_control_room import mailer_policy_score
from .outreach_live_queue import live_outreach_queue_candidates, stage_live_outreach_batch
from .outreach_post_send_observer import outreach_post_send_observer
from .p0 import json_safe
from .quality_plugins import latest_quality_summary
from .reply_safety_rehearsal import run_reply_safety_rehearsal


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _step(name: str, passed: bool, evidence: dict[str, Any] | None = None, blocker: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "blocker": blocker if not passed else "",
        "evidence": evidence or {},
    }


def run_launch_rehearsal(limit: int = 20, apply_pause: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 20))
    scoreboard = launch_readiness_scoreboard(safe_limit)
    activation = launch_activation_readiness(safe_limit)
    runbook = launch_activation_runbook(safe_limit)
    queue = live_outreach_queue_candidates(safe_limit)
    canary_quality = canary_batch_quality(safe_limit, store=True)
    stage = stage_live_outreach_batch(safe_limit, dry_run=True, requested_by="launch_rehearsal")
    observer = outreach_post_send_observer(24, apply_pause=apply_pause)
    mailer = mailer_policy_score()
    visual = latest_quality_summary()
    reply_safety = run_reply_safety_rehearsal(store=True)
    huanshu_rows = [
        row for row in (visual or {}).get("runs", [])
        if row.get("tool") == "huanshu"
    ]
    latest_huanshu_status = huanshu_rows[0].get("status") if huanshu_rows else "MISSING"

    stage_result = stage.get("result") or {}
    observer_result = observer.get("result") or {}
    quality_blockers = len((visual or {}).get("blockers") or [])
    steps = [
        _step(
            "launch_scoreboard_preview_ready",
            scoreboard.get("state") == "PREVIEW_PIPELINE_READY_NO_OUTREACH" and int(scoreboard.get("score") or 0) >= 100,
            {"state": scoreboard.get("state"), "score": scoreboard.get("score"), "blocker_count": scoreboard.get("blocker_count")},
            "launch_scoreboard_not_ready",
        ),
        _step(
            "activation_readiness_ready",
            activation.get("decision") == "READY_FOR_OPERATOR_ENV_ACTIVATION" and not activation.get("blockers"),
            {"decision": activation.get("decision"), "blockers": activation.get("blockers")},
            "activation_not_ready",
        ),
        _step(
            "runbook_ready",
            runbook.get("status") == "ready" and bool(runbook.get("rollback_env")),
            {"status": runbook.get("status"), "canary_limit": runbook.get("canary_limit")},
            "runbook_not_ready",
        ),
        _step(
            "live_queue_has_candidates",
            int(queue.get("candidate_count") or 0) > 0 and queue.get("raw_recipient_addresses_included") is False,
            {"candidate_count": queue.get("candidate_count")},
            "live_queue_empty_or_not_redacted",
        ),
        _step(
            "canary_batch_quality_pass",
            canary_quality.get("decision") == "PASS_CANARY_BATCH_QUALITY",
            {
                "decision": canary_quality.get("decision"),
                "candidate_count": canary_quality.get("candidate_count"),
                "segment_count": canary_quality.get("segment_count"),
                "campaign_count": canary_quality.get("campaign_count"),
                "recipient_domain_count": canary_quality.get("recipient_domain_count"),
                "blockers": canary_quality.get("blockers"),
                "warnings": canary_quality.get("warnings"),
            },
            "canary_batch_quality_not_pass",
        ),
        _step(
            "dry_run_stage_blocks_safely",
            stage_result.get("decision") == "BLOCKED"
            and int(stage_result.get("staged_count") or 0) == 0
            and int(stage_result.get("sent_count") or 0) == 0
            and "dry_run_no_messages_staged" in (stage_result.get("blockers") or []),
            {"decision": stage_result.get("decision"), "blockers": stage_result.get("blockers")},
            "dry_run_stage_not_safely_blocked",
        ),
        _step(
            "post_send_observer_clean",
            observer_result.get("decision") == "CLEAN_NO_POST_SEND_BLOCKERS",
            {
                "decision": observer_result.get("decision"),
                "bounce_or_dsn_count": observer_result.get("bounce_or_dsn_count"),
                "rate_limit_count": observer_result.get("rate_limit_count"),
                "spam_signal_count": observer_result.get("spam_signal_count"),
            },
            "post_send_observer_blocked",
        ),
        _step(
            "mailer_policy_clean",
            int(mailer.get("score") or 0) >= 100 and not mailer.get("blockers"),
            {"score": mailer.get("score"), "decision": mailer.get("decision"), "blockers": mailer.get("blockers")},
            "mailer_policy_not_clean",
        ),
        _step(
            "reply_safety_rehearsal_pass",
            reply_safety.get("decision") == "PASS_REPLY_SAFETY_REHEARSAL"
            and reply_safety.get("auto_replies_paused") is True
            and reply_safety.get("send_mail") is False
            and reply_safety.get("live_outreach_allowed") is False,
            {
                "decision": reply_safety.get("decision"),
                "sample_count": reply_safety.get("sample_count"),
                "blockers": reply_safety.get("blockers"),
                "auto_replies_paused": reply_safety.get("auto_replies_paused"),
            },
            "reply_safety_rehearsal_not_pass",
        ),
        _step(
            "visual_quality_clean",
            quality_blockers == 0 and latest_huanshu_status in {"PASS", "PASS_WITH_WARNINGS"},
            {"blocker_count": quality_blockers, "huanshu_latest_status": latest_huanshu_status},
            "visual_quality_blockers",
        ),
    ]
    blockers = [step["blocker"] for step in steps if not step["passed"]]
    decision = "READY_FOR_CANARY_OPERATOR_APPROVAL" if not blockers else "BLOCKED"
    result = json_safe(
        {
            "status": "ready" if not blockers else "blocked",
            "decision": decision,
            "blockers": blockers,
            "steps": steps,
            "preview_candidate_count": int(queue.get("candidate_count") or 0),
            "staged_count": int(stage_result.get("staged_count") or 0),
            "sent_count": int(stage_result.get("sent_count") or 0),
            "operator_note": "Rehearsal is dry-run only. It does not enable live outreach or send mail.",
            **SAFE_FLAGS,
        }
    )
    run = execute(
        """
        INSERT INTO launch_rehearsal_runs(
          status, decision, step_count, passed_step_count, blocker_count,
          preview_candidate_count, staged_count, sent_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, status, decision, step_count, passed_step_count, blocker_count,
                  preview_candidate_count, staged_count, sent_count, created_at
        """,
        (
            result["status"],
            decision,
            len(steps),
            len([step for step in steps if step["passed"]]),
            len(blockers),
            result["preview_candidate_count"],
            result["staged_count"],
            result["sent_count"],
            Jsonb(result),
        ),
    )
    return json_safe({"run": dict(run), "result": result, **SAFE_FLAGS})


def latest_launch_rehearsal_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, decision, step_count, passed_step_count, blocker_count,
               preview_candidate_count, staged_count, sent_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM launch_rehearsal_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 50)),),
    )
    return json_safe({"count": len(rows), "runs": [dict(row) for row in rows], **SAFE_FLAGS})
