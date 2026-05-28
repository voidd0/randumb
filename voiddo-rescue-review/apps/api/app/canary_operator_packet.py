from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .canary_batch_quality import canary_batch_quality
from .canary_checkout_simulation import run_canary_checkout_simulation
from .db import execute, fetch_one
from .inbox_integrity_gate import run_inbox_integrity_gate
from .launch_activation import launch_activation_readiness, launch_activation_runbook
from .launch_readiness_scoreboard import launch_readiness_scoreboard
from .launch_rehearsal import run_launch_rehearsal
from .outreach_live_queue import live_outreach_queue_candidates
from .p0 import json_safe, run_mail_qa
from .reply_safety_rehearsal import run_reply_safety_rehearsal


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"] or 0) if row else 0


def build_canary_operator_packet(limit: int = 20, store: bool = True, run_checkout_simulation: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 20))
    mail = run_mail_qa(allow_deliverability_send=False)
    scoreboard = launch_readiness_scoreboard(safe_limit)
    activation = launch_activation_readiness(safe_limit)
    runbook = launch_activation_runbook(safe_limit)
    quality = canary_batch_quality(safe_limit, store=True)
    reply_safety = run_reply_safety_rehearsal(store=True)
    inbox_integrity = run_inbox_integrity_gate(24, store=True)
    rehearsal = run_launch_rehearsal(safe_limit, apply_pause=False)
    queue = live_outreach_queue_candidates(safe_limit)
    checkout_simulation = run_canary_checkout_simulation(cleanup_after=True) if run_checkout_simulation else {"decision": "SKIPPED_NOT_REQUESTED", **SAFE_FLAGS}

    live_sent = _count("SELECT count(*) AS count FROM outreach_messages WHERE status = 'sent'")
    staged_sent = int((rehearsal.get("result") or {}).get("sent_count") or 0)
    blockers: list[str] = []
    if mail.get("decision") != "PASS":
        blockers.append("mail_qa_not_pass")
    if scoreboard.get("score") != 100 or scoreboard.get("state") != "PREVIEW_PIPELINE_READY_NO_OUTREACH":
        blockers.append("launch_scoreboard_not_preview_ready")
    if activation.get("decision") != "READY_FOR_OPERATOR_ENV_ACTIVATION":
        blockers.append("activation_not_ready")
    if runbook.get("status") != "ready":
        blockers.append("runbook_not_ready")
    if quality.get("decision") != "PASS_CANARY_BATCH_QUALITY":
        blockers.append("canary_quality_not_pass")
    if reply_safety.get("decision") != "PASS_REPLY_SAFETY_REHEARSAL":
        blockers.append("reply_safety_not_pass")
    if inbox_integrity.get("decision") != "PASS_INBOX_INTEGRITY_GATE":
        blockers.append("inbox_integrity_not_pass")
    if (rehearsal.get("result") or {}).get("decision") != "READY_FOR_CANARY_OPERATOR_APPROVAL":
        blockers.append("launch_rehearsal_not_ready")
    if int(queue.get("candidate_count") or 0) < safe_limit:
        blockers.append("canary_queue_below_limit")
    if live_sent or staged_sent:
        blockers.append("unexpected_send_count")
    if run_checkout_simulation and checkout_simulation.get("decision") != "PASS_CANARY_CHECKOUT_SIMULATION":
        blockers.append("checkout_simulation_not_pass")

    result = json_safe(
        {
            "status": "ready" if not blockers else "blocked",
            "decision": "READY_FOR_REDACTED_CANARY_OPERATOR_REVIEW" if not blockers else "BLOCKED_CANARY_OPERATOR_PACKET",
            "limit": safe_limit,
            "blockers": blockers,
            "mail_qa_decision": mail.get("decision"),
            "launch_state": scoreboard.get("state"),
            "launch_score": scoreboard.get("score"),
            "activation_decision": activation.get("decision"),
            "runbook_status": runbook.get("status"),
            "canary_quality_decision": quality.get("decision"),
            "canary_candidate_count": quality.get("candidate_count"),
            "segment_count": quality.get("segment_count"),
            "campaign_count": quality.get("campaign_count"),
            "recipient_domain_count": quality.get("recipient_domain_count"),
            "reply_safety_decision": reply_safety.get("decision"),
            "inbox_integrity_decision": inbox_integrity.get("decision"),
            "rehearsal_decision": (rehearsal.get("result") or {}).get("decision"),
            "rehearsal_steps": {
                "passed": (rehearsal.get("run") or {}).get("passed_step_count"),
                "total": (rehearsal.get("run") or {}).get("step_count"),
            },
            "checkout_simulation_decision": checkout_simulation.get("decision"),
            "live_queue_candidate_count": queue.get("candidate_count"),
            "live_outreach_sent_count": live_sent,
            "rehearsal_sent_count": staged_sent,
            "required_live_unlock_conditions": [
                "owner_explicit_canary_activation",
                "OUTREACH_DRY_RUN=false",
                "OUTREACH_PAUSED=false",
                "FIRST_LIVE_SEND_FLAG=true",
                "fresh_mail_qa_pass",
                "fresh_visual_qa_pass",
                "fresh_inbox_integrity_pass",
                "post_send_observer_after_each_window",
            ],
            **SAFE_FLAGS,
        }
    )
    if store:
        execute(
            "INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at) VALUES ('canary_operator_packet_agent', %s, %s, now(), now())",
            ("completed" if not blockers else "blocked", Jsonb(result)),
        )
    return result
