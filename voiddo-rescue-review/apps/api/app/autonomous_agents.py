from __future__ import annotations

import json
import os
from typing import Any, Callable

from psycopg.types.json import Jsonb

from .clean_window_recheck import clean_window_recheck, post_window_recheck_scheduler
from .contact_enrichment import contact_enrichment_candidates, run_hunter_contact_enrichment, run_public_contact_page_enrichment
from .db import connect, execute, fetch_one
from .email_templates import render_all_samples
from .economics import run_economics_audit
from .audit_evidence_remediation import audit_evidence_candidates, audit_evidence_remediation
from .audit_refresh_completion import audit_refresh_completion_watch
from .audit_refresh_drain import audit_refresh_drain_snapshot, prioritize_audit_refresh_jobs
from .audit_refresh_failures import audit_refresh_failure_snapshot, retry_failed_audit_refresh_jobs
from .audit_refresh_repair import audit_refresh_attachment_repair_snapshot, repair_audit_refresh_attachments
from .autonomous_mailer import run_autonomous_mailer_cycle
from .mailer_control import evaluate_latest_preview_outbound_message, evaluate_outbound_message
from .mailer_action_queue import process_mailer_action_queue
from .mailer_control_room import cleanup_mailer_digest_history, cleanup_mailer_policy_score_history, mailer_business_kpi_snapshot, mailer_digest_trend_guard, mailer_policy_score, mailer_policy_score_regression_guard, mailer_self_audit_matrix_snapshot, record_mailer_business_kpi_history, record_mailer_policy_score_history, record_mailer_self_audit_matrix_history, write_mailer_digest_agent_report, write_owner_status_report
from .mailer_readiness import run_clean_window_transition, sender_rotation_ready
from .mailer_autonomy import mailer_status_snapshot, record_mail_signal_lessons, run_clean_window_recovery
from .mailer_closed_loop import run_mailer_closed_loop
from .mailer_ops_actions import cleanup_mailer_ops_synthetic_history, write_mailer_ops_retention_agent_report
from .mail_recovery import check_mail_clean_window
from .mailer_throttle import throttle_decision
from .reply_actions import plan_reply_action
from .reply_safety_rehearsal import run_reply_safety_rehearsal
from .inbox_integrity_gate import run_inbox_integrity_gate
from .customer_journey import customer_journey_snapshot
from .customer_mail_simulation import run_customer_mail_simulation
from .customer_revenue_watchdog import latest_paid_customer_watchdog_runs, run_paid_customer_watchdog
from .monitoring import process_due_monitoring_targets, run_monitoring_check
from .owner_command_control import owner_command_control_summary
from .p0 import (
    build_warmup_calendar,
    dedupe_outreach_preview_messages,
    mail_signal_summary,
    prepare_outreach_preview,
    queue_outreach_preview,
    run_mail_qa,
    run_warmup_calendar_due,
    runtime_state_snapshot,
    write_blockers_report,
    write_daily_business_report,
)
from .quality_plugins import latest_quality_summary
from .campaign_actions import run_campaign_operator_cycle
from .canary_batch_quality import canary_batch_quality
from .canary_checkout_simulation import run_canary_checkout_simulation
from .canary_operator_packet import build_canary_operator_packet
from .canary_send_window_plan import build_canary_send_window_plan
from .campaign_control_room import campaign_control_room_snapshot, prepare_campaign_control_room
from .campaign_pipeline_repair import campaign_pipeline_gap_snapshot, repair_campaign_pipeline
from .post_scan_campaign_cycle import post_scan_campaign_cycle
from .campaign_preflight import campaign_preflight_batch, campaign_preflight_orphan_hygiene
from .campaign_remediation import campaign_remediation_plan, execute_campaign_remediation
from .campaign_remediation_feedback import campaign_remediation_feedback
from .campaign_preview_refresh import campaign_preview_refresh_snapshot, refresh_campaign_previews_if_needed
from .campaign_preview_hygiene import archive_campaign_preview_artifacts, archive_campaign_shell_artifacts, campaign_preview_hygiene_snapshot, campaign_shell_hygiene_snapshot
from .campaign_preview_quality import campaign_preview_quality_pack
from .campaign_preview_reviews import auto_review_campaign_previews
from .campaign_review_remediation import held_preview_remediation_candidates, remediate_held_preview_reviews
from .studio_mail_monitor import latest_studio_mail_messages
from .buyer_journey_scenarios import buyer_journey_readiness_scoreboard, run_buyer_journey_scenario
from .lead_discovery import apollo_organization_discovery, lead_discovery_target_plan, overpass_lead_discovery, performance_guided_regional_discovery_cycle, performance_guided_target_plan, regional_lead_discovery_cycle, stockpile_expansion_discovery_cycle, stockpile_expansion_target_plan
from .revenue_simulation import run_synthetic_lead_simulation
from .revenue_loop import prepare_revenue_loop, revenue_loop_snapshot
from .source_campaign_operator import advance_source_to_campaign, source_campaign_operator_snapshot
from .language_gate import check_no_ai_public_language
from .scout_run_recovery import recover_stale_scout_runs, stale_scout_run_recovery_snapshot
from .scanner_ops import recover_stale_running_scanner_jobs, retry_transient_scanner_failures, scanner_queue_health_snapshot, scanner_stale_running_snapshot
from .scanner_queue_hygiene import archive_scanner_queue_artifacts, scanner_queue_hygiene_snapshot
from .scanner_priority import prioritize_guided_scanner_jobs, scanner_guided_backlog
from .scanner_completion_watch import scanner_completion_watch
from .source_scanner_queue import queue_source_scanner_jobs, source_scanner_backlog
from .scout_sensitive_hygiene import archive_sensitive_scout_targets, scout_sensitive_target_snapshot
from .launch_readiness_scoreboard import launch_readiness_scoreboard
from .launch_activation import launch_activation_readiness, launch_activation_runbook, prepare_launch_activation
from .launch_rehearsal import latest_launch_rehearsal_runs, run_launch_rehearsal
from .lead_stockpile_health import lead_stockpile_health_snapshot, run_lead_stockpile_health
from .lead_supply_autopilot import lead_supply_autopilot
from .outreach_live_queue import live_outreach_queue_candidates, stage_live_outreach_batch
from .outreach_post_send_observer import latest_outreach_post_send_observer_runs, outreach_post_send_observer
from .launch_operating_lane import advance_launch_operating_lane, launch_operating_lane_snapshot
from .launch_repair_cycle import run_launch_repair_cycle
from .launch_repair_planner import execute_launch_repair_plan, launch_repair_plan
from .lead_scoring import backfill_post_scan_lead_scores
from .lead_quality_diagnostics import apply_scout_source_feedback, record_lead_quality_diagnostics
from .scouts import cleanup_scout_source_readiness_checks, process_queued_scout_runs, process_scout_run_gated, ready_scout_source_queue_candidates, run_scout_source_readiness, scout_source_readiness_regression_guard, scout_source_readiness_summary
from .scout_quality import cleanup_scout_campaign_quality_history, latest_scout_quality_gate, record_scout_campaign_quality_history, run_scout_quality_gate, scout_campaign_quality_regression_guard, scout_campaign_quality_summary
from .self_operating import run_self_audit, self_operating_summary
from .self_closed_loop import run_self_operating_closed_loop
from .warmup_planner import apply_provider_spacing_when_safe, plan_provider_spaced_warmup
from .warmup_block_recovery import recover_blocked_warmup_slots, warmup_block_recovery_snapshot
from .warmup_post_send import observe_warmup_post_send


def _record_agent(agent: str, func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    row = execute(
        "INSERT INTO agent_runs(agent, status, started_at) VALUES (%s, 'running', now()) RETURNING id",
        (agent,),
    )
    try:
        result = json.loads(json.dumps(func(), default=str))
        if agent == "mailer_digest_agent":
            digest_report = write_mailer_digest_agent_report(str(row["id"]), result)
            result["digest_agent_report"] = digest_report
            result["post_digest_queue_processing"] = process_mailer_action_queue(10)
        if agent == "mailer_ops_retention_agent":
            retention_report = write_mailer_ops_retention_agent_report(str(row["id"]), result)
            result["ops_retention_agent_report"] = retention_report
        if agent == "mailer_policy_score_agent":
            result["policy_score_history"] = record_mailer_policy_score_history(str(row["id"]), result)
        if agent == "mailer_business_kpi_agent":
            result["business_kpi_history"] = record_mailer_business_kpi_history(str(row["id"]), result)
        if agent == "mailer_self_audit_matrix_agent":
            result["self_audit_matrix_history"] = record_mailer_self_audit_matrix_history(str(row["id"]), result)
        if agent == "scout_campaign_quality_summary_agent":
            result["scout_campaign_quality_history"] = json.loads(json.dumps(record_scout_campaign_quality_history(str(row["id"]), result), default=str))
        done = execute(
            "UPDATE agent_runs SET status = 'completed', completed_at = now(), result_json = %s WHERE id = %s RETURNING *",
            (Jsonb(result), row["id"]),
        )
        return dict(done)
    except Exception as exc:
        failed = execute(
            "UPDATE agent_runs SET status = 'failed', completed_at = now(), error = %s WHERE id = %s RETURNING *",
            (type(exc).__name__, row["id"]),
        )
        return dict(failed)


def run_agent(agent: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}

    def scout_agent():
        run_id = payload.get("scout_run_id")
        if not run_id:
            return process_queued_scout_runs(int(payload.get("limit", 5)))
        return process_scout_run_gated(run_id)

    def scout_quality_agent():
        run_id = payload.get("scout_run_id")
        if run_id:
            return run_scout_quality_gate(run_id)
        row = fetch_one("SELECT id FROM scout_runs WHERE status IN ('completed', 'review_required') ORDER BY completed_at DESC NULLS LAST, created_at DESC LIMIT 1")
        if not row:
            return {"status": "idle", "reason": "no_completed_scout_runs", "send_mail": False, "live_outreach_allowed": False}
        quality = latest_scout_quality_gate(str(row["id"]))
        quality["scout_run_id"] = str(row["id"])
        return quality

    def scout_source_readiness_agent():
        source_id = payload.get("source_id")
        if source_id:
            return run_scout_source_readiness(source_id)
        row = fetch_one("SELECT id FROM scout_sources WHERE status = 'active' ORDER BY updated_at DESC, created_at DESC LIMIT 1")
        if not row:
            return {"status": "idle", "reason": "no_active_scout_sources", "send_mail": False, "live_outreach_allowed": False}
        return run_scout_source_readiness(str(row["id"]))

    def campaign_preview_quality_agent():
        campaign_id = payload.get("campaign_id")
        if not campaign_id:
            row = fetch_one("SELECT id FROM campaigns WHERE status = 'preview_ready' ORDER BY updated_at DESC, created_at DESC LIMIT 1")
            if not row:
                return {"status": "idle", "reason": "no_preview_ready_campaign", "send_mail": False, "live_outreach_allowed": False}
            campaign_id = str(row["id"])
        return campaign_preview_quality_pack(str(campaign_id), int(payload.get("limit", 20)))

    agents: dict[str, Callable[[], dict[str, Any]]] = {
        "scout_agent": scout_agent,
        "scout_quality_agent": scout_quality_agent,
        "scout_source_readiness_agent": scout_source_readiness_agent,
        "scout_source_readiness_summary_agent": lambda: scout_source_readiness_summary(),
        "scout_source_readiness_retention_agent": lambda: cleanup_scout_source_readiness_checks(),
        "scout_source_readiness_regression_guard_agent": lambda: scout_source_readiness_regression_guard(),
        "scout_source_queue_preview_agent": lambda: ready_scout_source_queue_candidates(int(payload.get("limit", 25))),
        "lead_discovery_target_plan_agent": lambda: lead_discovery_target_plan(False),
        "regional_lead_discovery_agent": lambda: regional_lead_discovery_cycle(
            int(payload.get("limit_targets", 1)),
            int(payload.get("per_target_limit", 25)),
            dry_run=bool(payload.get("dry_run", False)),
        ),
        "performance_guided_lead_discovery_agent": lambda: performance_guided_regional_discovery_cycle(
            int(payload.get("limit_targets", 2)),
            int(payload.get("per_target_limit", 25)),
            dry_run=bool(payload.get("dry_run", False)),
        ),
        "performance_guided_target_plan_agent": lambda: performance_guided_target_plan(int(payload.get("limit_targets", 5))),
        "stockpile_expansion_target_plan_agent": lambda: stockpile_expansion_target_plan(int(payload.get("limit_targets", 5))),
        "stockpile_expansion_discovery_agent": lambda: stockpile_expansion_discovery_cycle(
            int(payload.get("limit_targets", 3)),
            int(payload.get("per_target_limit", 35)),
            dry_run=bool(payload.get("dry_run", False)),
        ),
        "overpass_lead_discovery_agent": lambda: overpass_lead_discovery(
            payload.get("country", "US"),
            payload.get("city", "Boise"),
            payload.get("niche", "dentists"),
            payload.get("language", "en"),
            int(payload.get("limit", 50)),
            dry_run=True,
        ),
        "apollo_organization_discovery_agent": lambda: apollo_organization_discovery(
            payload.get("country", "US"),
            payload.get("city", "Boise"),
            payload.get("niche", "dentists"),
            payload.get("language", "en"),
            int(payload.get("limit", 25)),
            dry_run=bool(payload.get("dry_run", True)),
        ),
        "scout_campaign_quality_summary_agent": lambda: scout_campaign_quality_summary(),
        "scout_campaign_quality_retention_agent": lambda: cleanup_scout_campaign_quality_history(),
        "scout_campaign_quality_regression_guard_agent": lambda: scout_campaign_quality_regression_guard(),
        "scanner_agent": lambda: scanner_queue_health_snapshot(int(payload.get("limit", 20))),
        "scanner_retry_agent": lambda: retry_transient_scanner_failures(
            int(payload.get("limit", 5)),
            dry_run=bool(payload.get("dry_run", False)),
            allow_timeout_resilience_retry=bool(payload.get("allow_timeout_resilience_retry", True)),
        ),
        "scanner_stale_running_snapshot_agent": lambda: scanner_stale_running_snapshot(
            int(payload.get("limit", 20)),
            int(payload.get("older_than_minutes", 15)),
        ),
        "scanner_stale_recovery_agent": lambda: recover_stale_running_scanner_jobs(
            int(payload.get("limit", 10)),
            int(payload.get("older_than_minutes", 15)),
            dry_run=bool(payload.get("dry_run", False)),
            max_requeue_count=int(payload.get("max_requeue_count", 1)),
        ),
        "scanner_queue_hygiene_agent": lambda: archive_scanner_queue_artifacts(
            int(payload.get("limit", 500)),
            apply=bool(payload.get("apply", True)),
        ),
        "scanner_queue_hygiene_snapshot_agent": lambda: scanner_queue_hygiene_snapshot(int(payload.get("limit", 500))),
        "scanner_guided_backlog_agent": lambda: scanner_guided_backlog(int(payload.get("limit", 50))),
        "scanner_guided_priority_agent": lambda: prioritize_guided_scanner_jobs(int(payload.get("limit", 25)), dry_run=bool(payload.get("dry_run", True))),
        "scanner_completion_watch_agent": lambda: scanner_completion_watch(
            int(payload.get("limit", 100)),
            int(payload.get("min_new_completed", 1)),
            dry_run=bool(payload.get("dry_run", False)),
        ),
        "source_scanner_backlog_agent": lambda: source_scanner_backlog(int(payload.get("limit", 100)), payload.get("source_id")),
        "source_scanner_queue_agent": lambda: queue_source_scanner_jobs(
            int(payload.get("limit", 100)),
            dry_run=bool(payload.get("dry_run", False)),
            source_id=payload.get("source_id"),
        ),
        "post_scan_lead_scoring_agent": lambda: backfill_post_scan_lead_scores(int(payload.get("limit", 50)), dry_run=bool(payload.get("dry_run", False))),
        "contact_enrichment_candidates_agent": lambda: contact_enrichment_candidates(int(payload.get("limit", 25))),
        "contact_enrichment_agent": lambda: run_hunter_contact_enrichment(int(payload.get("limit", 10)), dry_run=bool(payload.get("dry_run", True))),
        "contact_page_enrichment_agent": lambda: run_public_contact_page_enrichment(
            int(payload.get("limit", 10)),
            dry_run=bool(payload.get("dry_run", False)),
            max_pages_per_domain=int(payload.get("max_pages_per_domain", 4)),
            max_seconds=int(payload.get("max_seconds", 45)),
        ),
        "lead_quality_diagnostics_agent": lambda: record_lead_quality_diagnostics(int(payload.get("limit", 50))),
        "scout_source_feedback_agent": lambda: apply_scout_source_feedback(int(payload.get("limit", 50)), dry_run=bool(payload.get("dry_run", True))),
        "scout_run_recovery_agent": lambda: recover_stale_scout_runs(
            int(payload.get("limit", 25)),
            int(payload.get("older_than_minutes", 120)),
            apply=bool(payload.get("apply", True)),
        ),
        "scout_run_recovery_snapshot_agent": lambda: stale_scout_run_recovery_snapshot(
            int(payload.get("limit", 50)),
            int(payload.get("older_than_minutes", 120)),
        ),
        "scout_sensitive_hygiene_agent": lambda: archive_sensitive_scout_targets(
            int(payload.get("limit", 200)),
            apply=bool(payload.get("apply", True)),
        ),
        "scout_sensitive_hygiene_snapshot_agent": lambda: scout_sensitive_target_snapshot(int(payload.get("limit", 200))),
        "audit_page_agent": lambda: {"dry_run": True, "status": "audit_pages_api_backed"},
        "audit_evidence_candidates_agent": lambda: audit_evidence_candidates(int(payload.get("limit", 25))),
        "audit_evidence_remediation_agent": lambda: audit_evidence_remediation(
            int(payload.get("limit", 25)),
            dry_run=bool(payload.get("dry_run", True)),
        ),
        "audit_refresh_drain_agent": lambda: audit_refresh_drain_snapshot(int(payload.get("limit", 25))),
        "audit_refresh_prioritize_agent": lambda: prioritize_audit_refresh_jobs(
            int(payload.get("limit", 25)),
            dry_run=bool(payload.get("dry_run", True)),
            priority=int(payload.get("priority", 220)),
        ),
        "audit_refresh_completion_watch_agent": lambda: audit_refresh_completion_watch(
            int(payload.get("limit", 25)),
            int(payload.get("min_new_completed", 1)),
            dry_run=bool(payload.get("dry_run", True)),
            force=bool(payload.get("force", False)),
        ),
        "audit_refresh_failure_agent": lambda: audit_refresh_failure_snapshot(int(payload.get("limit", 25))),
        "audit_refresh_retry_failures_agent": lambda: retry_failed_audit_refresh_jobs(
            int(payload.get("limit", 10)),
            dry_run=bool(payload.get("dry_run", True)),
            priority=int(payload.get("priority", 260)),
            allow_scanner_fix_retry=bool(payload.get("allow_scanner_fix_retry", False)),
        ),
        "audit_refresh_attachment_repair_agent": lambda: repair_audit_refresh_attachments(
            int(payload.get("limit", 25)),
            dry_run=bool(payload.get("dry_run", True)),
        ),
        "audit_refresh_attachment_repair_snapshot_agent": lambda: audit_refresh_attachment_repair_snapshot(
            int(payload.get("limit", 25)),
        ),
        "studio_mail_monitor_agent": lambda: latest_studio_mail_messages(int(payload.get("limit", 20))),
        "visual_qa_agent": lambda: {"dry_run": True, "status": "huanshu_required", "routes": ["/", "/r/demo", "/admin", "/customer", "/status"]},
        "mail_qa_agent": lambda: {"mail_qa": run_mail_qa()},
        "deliverability_agent": lambda: {"dry_run": True, "signals": mail_signal_summary()},
        "warmup_agent": lambda: run_warmup_calendar_due(limit=2),
        "warmup_block_recovery_agent": lambda: recover_blocked_warmup_slots(
            int(payload.get("limit", 25)),
            apply=bool(payload.get("apply", True)),
        ),
        "warmup_block_recovery_snapshot_agent": lambda: warmup_block_recovery_snapshot(int(payload.get("limit", 50))),
        "campaign_agent": lambda: prepare_outreach_preview(int(payload.get("limit", 20))),
        "outreach_preview_queue_agent": lambda: queue_outreach_preview(int(payload.get("limit", 20))),
        "outreach_preview_dedupe_agent": lambda: dedupe_outreach_preview_messages(
            int(payload.get("limit", 500)),
            apply=bool(payload.get("apply", True)),
        ),
        "campaign_operator_agent": lambda: run_campaign_operator_cycle(int(payload.get("limit", 25))),
        "campaign_control_room_agent": lambda: campaign_control_room_snapshot(int(payload.get("limit", 100))),
        "campaign_control_room_prepare_agent": lambda: prepare_campaign_control_room(int(payload.get("limit", 100)), dry_run=True),
        "campaign_pipeline_gap_agent": lambda: campaign_pipeline_gap_snapshot(int(payload.get("limit", 100))),
        "campaign_pipeline_repair_agent": lambda: repair_campaign_pipeline(int(payload.get("limit", 100)), dry_run=True),
        "campaign_preview_refresh_snapshot_agent": lambda: campaign_preview_refresh_snapshot(
            int(payload.get("limit", 100)),
            int(payload.get("stale_hours", 24)),
        ),
        "campaign_preview_refresh_agent": lambda: refresh_campaign_previews_if_needed(
            int(payload.get("limit", 100)),
            int(payload.get("stale_hours", 24)),
            dry_run=bool(payload.get("dry_run", False)),
        ),
        "campaign_preview_hygiene_agent": lambda: archive_campaign_preview_artifacts(
            int(payload.get("limit", 500)),
            apply=bool(payload.get("apply", True)),
        ),
        "campaign_preview_hygiene_snapshot_agent": lambda: campaign_preview_hygiene_snapshot(int(payload.get("limit", 500))),
        "campaign_shell_hygiene_agent": lambda: archive_campaign_shell_artifacts(
            int(payload.get("limit", 500)),
            apply=bool(payload.get("apply", True)),
        ),
        "campaign_shell_hygiene_snapshot_agent": lambda: campaign_shell_hygiene_snapshot(int(payload.get("limit", 500))),
        "campaign_preflight_agent": lambda: campaign_preflight_batch(int(payload.get("limit", 20)), payload.get("campaign_id")),
        "campaign_preflight_orphan_hygiene_agent": lambda: campaign_preflight_orphan_hygiene(
            int(payload.get("limit", 100)),
            apply=bool(payload.get("apply", True)),
        ),
        "campaign_remediation_agent": lambda: campaign_remediation_plan(
            int(payload.get("limit", 25)),
            create_tasks=bool(payload.get("create_tasks", True)),
        ),
        "campaign_remediation_executor_agent": lambda: execute_campaign_remediation(
            int(payload.get("limit", 10)),
            rerun_preflight=bool(payload.get("rerun_preflight", True)),
        ),
        "campaign_remediation_feedback_agent": lambda: campaign_remediation_feedback(
            int(payload.get("limit", 25)),
            int(payload.get("repeated_threshold", 3)),
        ),
        "post_scan_campaign_cycle_agent": lambda: post_scan_campaign_cycle(
            int(payload.get("limit", 100)),
            dry_run=bool(payload.get("dry_run", True)),
        ),
        "campaign_preview_quality_agent": campaign_preview_quality_agent,
        "campaign_preview_self_review_agent": lambda: auto_review_campaign_previews(
            int(payload.get("limit", 25)),
            apply=bool(payload.get("apply", True)),
            campaign_id=payload.get("campaign_id"),
            reconsider_held=bool(payload.get("reconsider_held", True)),
        ),
        "campaign_review_remediation_snapshot_agent": lambda: held_preview_remediation_candidates(int(payload.get("limit", 25))),
        "campaign_review_remediation_agent": lambda: remediate_held_preview_reviews(
            int(payload.get("limit", 25)),
            dry_run=bool(payload.get("dry_run", True)),
        ),
        "buyer_journey_scoreboard_agent": lambda: buyer_journey_readiness_scoreboard(),
        "buyer_journey_scenario_agent": lambda: run_buyer_journey_scenario(cleanup=True),
        "source_campaign_operator_agent": lambda: source_campaign_operator_snapshot(int(payload.get("limit", 25)), payload.get("source_id")),
        "source_campaign_operator_advance_agent": lambda: advance_source_to_campaign(
            payload.get("source_id"),
            int(payload.get("limit", 25)),
            dry_run=bool(payload.get("dry_run", False)),
            process_scout=bool(payload.get("process_scout", True)),
            prepare_campaigns=bool(payload.get("prepare_campaigns", True)),
        ),
        "source_campaign_operator_followup_advance_agent": lambda: advance_source_to_campaign(
            payload.get("source_id"),
            int(payload.get("limit", 25)),
            dry_run=bool(payload.get("dry_run", False)),
            process_scout=bool(payload.get("process_scout", True)),
            prepare_campaigns=bool(payload.get("prepare_campaigns", True)),
        ),
        "lead_stockpile_health_agent": lambda: lead_stockpile_health_snapshot(
            int(payload.get("target_preview_count", 50)),
            int(payload.get("canary_count", 20)),
            int(payload.get("limit", 100)),
        ),
        "lead_stockpile_health_advance_agent": lambda: run_lead_stockpile_health(
            int(payload.get("target_preview_count", 50)),
            int(payload.get("canary_count", 20)),
            int(payload.get("limit", 100)),
            apply=bool(payload.get("apply", True)),
        ),
        "lead_supply_autopilot_agent": lambda: lead_supply_autopilot(
            int(payload.get("target_preview_count", 100)),
            int(payload.get("canary_count", 20)),
            int(payload.get("limit", 120)),
            apply=bool(payload.get("apply", False)),
            enrichment_limit=int(payload.get("enrichment_limit", 10)),
            enrichment_seconds=int(payload.get("enrichment_seconds", 90)),
        ),
        "launch_readiness_scoreboard_agent": lambda: launch_readiness_scoreboard(int(payload.get("limit", 25))),
        "launch_activation_readiness_agent": lambda: launch_activation_readiness(int(payload.get("limit", 25))),
        "launch_activation_prepare_agent": lambda: prepare_launch_activation(int(payload.get("limit", 25)), "agent"),
        "launch_activation_runbook_agent": lambda: launch_activation_runbook(int(payload.get("limit", 25))),
        "launch_rehearsal_agent": lambda: run_launch_rehearsal(int(payload.get("limit", 20)), apply_pause=False),
        "launch_rehearsal_history_agent": lambda: latest_launch_rehearsal_runs(int(payload.get("limit", 10))),
        "live_outreach_queue_candidates_agent": lambda: live_outreach_queue_candidates(int(payload.get("limit", 20))),
        "live_outreach_stage_dry_run_agent": lambda: stage_live_outreach_batch(int(payload.get("limit", 20)), dry_run=True, requested_by="agent"),
        "canary_batch_quality_agent": lambda: canary_batch_quality(int(payload.get("limit", 20))),
        "canary_checkout_simulation_agent": lambda: run_canary_checkout_simulation(cleanup_after=bool(payload.get("cleanup_after", True))),
        "canary_operator_packet_agent": lambda: build_canary_operator_packet(int(payload.get("limit", 20)), store=True, run_checkout_simulation=bool(payload.get("run_checkout_simulation", False))),
        "canary_send_window_plan_agent": lambda: build_canary_send_window_plan(int(payload.get("limit", 20)), store=True),
        "outreach_post_send_observer_agent": lambda: outreach_post_send_observer(int(payload.get("window_hours", 24)), apply_pause=bool(payload.get("apply_pause", True))),
        "outreach_post_send_observer_history_agent": lambda: latest_outreach_post_send_observer_runs(int(payload.get("limit", 10))),
        "launch_repair_plan_agent": lambda: launch_repair_plan(int(payload.get("limit", 25))),
        "launch_repair_executor_agent": lambda: execute_launch_repair_plan(int(payload.get("limit", 25)), dry_run=True),
        "launch_repair_cycle_agent": lambda: run_launch_repair_cycle(int(payload.get("limit", 25)), execute_safe_auto=False),
        "launch_operating_lane_agent": lambda: launch_operating_lane_snapshot(int(payload.get("limit", 25))),
        "launch_operating_lane_advance_agent": lambda: advance_launch_operating_lane(int(payload.get("limit", 25)), execute_safe_auto=False),
        "inbox_agent": lambda: {"dry_run": True, "status": "worker_polls_when_enabled"},
        "reply_safety_rehearsal_agent": lambda: run_reply_safety_rehearsal(),
        "inbox_integrity_gate_agent": lambda: run_inbox_integrity_gate(int(payload.get("window_hours", 24))),
        "owner_command_agent": lambda: owner_command_control_summary(int(payload.get("limit", 20))),
        "checkout_agent": lambda: {"dry_run": True, "status": "paddle_webhook_handlers_ready"},
        "reporting_agent": lambda: runtime_state_snapshot(),
        "runtime_state_report_agent": lambda: {**runtime_state_snapshot(), "send_mail": False, "live_outreach_allowed": False},
        "daily_business_report_agent": lambda: {"report_path": write_daily_business_report(), "send_mail": False, "live_outreach_allowed": False},
        "blockers_report_agent": lambda: {"report_path": write_blockers_report(), "send_mail": False, "live_outreach_allowed": False},
        "fix_task_agent": lambda: {"dry_run": True, "status": "codex_tasks_endpoint_ready"},
        "mail_throttle_agent": lambda: throttle_decision("global", "diagnostic", 600),
        "email_template_agent": lambda: {"rendered": len(render_all_samples()), "all_pass": all(item["qa"]["passed"] for item in render_all_samples())},
        "warmup_calendar_agent": lambda: build_warmup_calendar(),
        "economics_agent": lambda: run_economics_audit(),
        "self_audit_agent": lambda: run_self_audit("agent_cycle"),
        "self_closed_loop_agent": lambda: run_self_operating_closed_loop(payload.get("scope", "agent_cycle"), int(payload.get("limit", 25))),
        "self_fix_agent": lambda: run_self_operating_closed_loop("self_fix_agent", int(payload.get("limit", 25))),
        "self_learning_agent": lambda: run_self_operating_closed_loop("self_learning_agent", int(payload.get("limit", 25))),
        "self_building_agent": lambda: run_self_operating_closed_loop("self_building_agent", int(payload.get("limit", 25))),
        "autonomous_mailer_agent": lambda: run_autonomous_mailer_cycle(),
        "autonomous_mailer_executor_agent": lambda: run_mailer_closed_loop(int(payload.get("limit", 10))),
        "customer_mail_simulation_agent": lambda: run_customer_mail_simulation(True),
        "paid_customer_watchdog_agent": lambda: run_paid_customer_watchdog(int(payload.get("limit", 25)), repair=bool(payload.get("repair", True))),
        "paid_customer_watchdog_history_agent": lambda: latest_paid_customer_watchdog_runs(int(payload.get("limit", 10))),
        "mailer_digest_agent": lambda: write_owner_status_report(send_if_safe=False),
        "mailer_digest_retention_agent": lambda: cleanup_mailer_digest_history(90),
        "mailer_digest_trend_guard_agent": lambda: mailer_digest_trend_guard(),
        "mailer_policy_score_agent": lambda: mailer_policy_score(),
        "mailer_policy_score_retention_agent": lambda: cleanup_mailer_policy_score_history(120),
        "mailer_policy_score_regression_guard_agent": lambda: mailer_policy_score_regression_guard(),
        "policy_trend_reporting_agent": lambda: {"runtime": runtime_state_snapshot(), "daily_business_report": write_daily_business_report(), "blockers_report": write_blockers_report(), "send_mail": False, "live_outreach_allowed": False},
        "mailer_business_kpi_agent": lambda: mailer_business_kpi_snapshot(),
        "mailer_self_audit_matrix_agent": lambda: mailer_self_audit_matrix_snapshot(),
        "mailer_ops_retention_agent": lambda: cleanup_mailer_ops_synthetic_history(),
        "outbound_mailer_gate_agent": lambda: evaluate_latest_preview_outbound_message(),
        "reply_action_agent": lambda: plan_reply_action("Price", "How much does it cost?", "audit@voiddorescue.com"),
        "quality_plugin_agent": lambda: latest_quality_summary(),
        "revenue_simulation_agent": lambda: run_synthetic_lead_simulation(int(payload.get("count", 25))),
        "revenue_loop_snapshot_agent": lambda: revenue_loop_snapshot(int(payload.get("limit", 25))),
        "revenue_loop_prepare_agent": lambda: prepare_revenue_loop(int(payload.get("limit", 25)), dry_run=True),
        "mail_clean_window_agent": lambda: check_mail_clean_window(24),
        "mail_clean_window_transition_agent": lambda: run_clean_window_transition(24),
        "mailer_status_agent": lambda: mailer_status_snapshot(),
        "mail_signal_learning_agent": lambda: record_mail_signal_lessons(24),
        "clean_window_recovery_agent": lambda: run_clean_window_recovery(24),
        "clean_window_recheck_agent": lambda: clean_window_recheck(24, False),
        "post_window_recheck_agent": lambda: post_window_recheck_scheduler(24, run_recovery_if_due=False),
        "customer_journey_agent": lambda: {"dry_run": True, "status": "customer_journeys_snapshot_on_payment_or_admin_request"},
        "monitoring_agent": lambda: {"dry_run": True, "status": "monitoring_targets_checked_by_protected_endpoint_or_scheduler"},
        "monitoring_scheduler_agent": lambda: process_due_monitoring_targets(5, True),
        "sender_rotation_readiness_agent": lambda: sender_rotation_ready(),
        "warmup_spacing_planner_agent": lambda: plan_provider_spaced_warmup(50, False),
        "warmup_spacing_apply_gate_agent": lambda: apply_provider_spacing_when_safe(50),
        "warmup_post_send_observer_agent": lambda: observe_warmup_post_send(int(payload.get("limit", 10)), pause_on_blocker=True),
        "public_language_gate_agent": lambda: check_no_ai_public_language(),
    }
    if agent not in agents:
        raise ValueError("unknown_agent")
    return _record_agent(agent, agents[agent])


DAILY_LOOP_ADVISORY_LOCK_KEY = 86420057


def _run_daily_loop_unlocked() -> dict[str, Any]:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        selected = [
            "mail_throttle_agent",
            "email_template_agent",
            "visual_qa_agent",
            "deliverability_agent",
            "economics_agent",
            "autonomous_mailer_agent",
            "mailer_ops_retention_agent",
            "mailer_digest_agent",
            "mailer_digest_retention_agent",
            "mailer_digest_trend_guard_agent",
            "mailer_policy_score_agent",
            "mailer_policy_score_retention_agent",
            "mailer_policy_score_regression_guard_agent",
            "policy_trend_reporting_agent",
            "mailer_business_kpi_agent",
            "mailer_self_audit_matrix_agent",
            "quality_plugin_agent",
            "warmup_block_recovery_snapshot_agent",
            "campaign_preview_hygiene_snapshot_agent",
            "campaign_shell_hygiene_snapshot_agent",
            "scanner_queue_hygiene_snapshot_agent",
            "scanner_stale_running_snapshot_agent",
            "scanner_stale_recovery_agent",
            "scout_run_recovery_snapshot_agent",
            "self_audit_agent",
            "self_closed_loop_agent",
            "self_fix_agent",
            "self_learning_agent",
            "self_building_agent",
        ]
    else:
        selected = [
        "mail_throttle_agent",
        "email_template_agent",
        "visual_qa_agent",
        "deliverability_agent",
        "scanner_agent",
        "scanner_retry_agent",
        "scanner_stale_running_snapshot_agent",
        "scanner_stale_recovery_agent",
        "scanner_queue_hygiene_agent",
        "scanner_queue_hygiene_snapshot_agent",
        "scanner_guided_backlog_agent",
        "scanner_guided_priority_agent",
        "scanner_completion_watch_agent",
        "source_scanner_backlog_agent",
        "source_scanner_queue_agent",
        "post_scan_lead_scoring_agent",
        "contact_enrichment_candidates_agent",
        "contact_enrichment_agent",
        "contact_page_enrichment_agent",
        "lead_quality_diagnostics_agent",
        "scout_source_feedback_agent",
        "scout_run_recovery_agent",
        "scout_run_recovery_snapshot_agent",
        "scout_sensitive_hygiene_agent",
        "scout_sensitive_hygiene_snapshot_agent",
        "campaign_agent",
        "outreach_preview_queue_agent",
        "outreach_preview_dedupe_agent",
        "campaign_operator_agent",
        "campaign_control_room_agent",
        "campaign_control_room_prepare_agent",
        "campaign_pipeline_gap_agent",
        "campaign_preview_refresh_snapshot_agent",
        "campaign_preview_refresh_agent",
        "campaign_preview_hygiene_agent",
        "campaign_preview_hygiene_snapshot_agent",
        "campaign_shell_hygiene_agent",
        "campaign_shell_hygiene_snapshot_agent",
        "campaign_preview_self_review_agent",
        "campaign_review_remediation_snapshot_agent",
        "campaign_review_remediation_agent",
        "campaign_preflight_agent",
        "campaign_preflight_orphan_hygiene_agent",
        "campaign_remediation_agent",
        "campaign_remediation_executor_agent",
        "campaign_remediation_feedback_agent",
        "audit_evidence_candidates_agent",
        "audit_evidence_remediation_agent",
        "audit_refresh_drain_agent",
        "audit_refresh_prioritize_agent",
        "audit_refresh_completion_watch_agent",
        "audit_refresh_failure_agent",
        "audit_refresh_retry_failures_agent",
        "audit_refresh_attachment_repair_snapshot_agent",
        "studio_mail_monitor_agent",
        "post_scan_campaign_cycle_agent",
        "campaign_preview_quality_agent",
        "buyer_journey_scoreboard_agent",
        "source_campaign_operator_agent",
        "source_campaign_operator_advance_agent",
        "lead_stockpile_health_agent",
        "lead_stockpile_health_advance_agent",
            "launch_readiness_scoreboard_agent",
            "launch_activation_readiness_agent",
            "launch_activation_runbook_agent",
            "launch_rehearsal_agent",
            "canary_operator_packet_agent",
            "canary_send_window_plan_agent",
            "live_outreach_queue_candidates_agent",
            "outreach_post_send_observer_agent",
            "launch_repair_plan_agent",
        "launch_repair_cycle_agent",
        "launch_operating_lane_agent",
        "reporting_agent",
        "fix_task_agent",
        "monitoring_scheduler_agent",
        "economics_agent",
        "autonomous_mailer_agent",
        "autonomous_mailer_executor_agent",
        "customer_mail_simulation_agent",
        "mailer_ops_retention_agent",
        "mailer_digest_agent",
        "autonomous_mailer_executor_agent",
        "mailer_digest_retention_agent",
        "mailer_digest_trend_guard_agent",
        "mailer_policy_score_agent",
        "mailer_policy_score_retention_agent",
        "mailer_policy_score_regression_guard_agent",
        "policy_trend_reporting_agent",
        "mailer_business_kpi_agent",
        "mailer_self_audit_matrix_agent",
        "scout_source_readiness_summary_agent",
        "scout_source_readiness_retention_agent",
        "scout_source_readiness_regression_guard_agent",
        "scout_source_queue_preview_agent",
        "lead_discovery_target_plan_agent",
        "regional_lead_discovery_agent",
        "performance_guided_target_plan_agent",
        "performance_guided_lead_discovery_agent",
        "stockpile_expansion_target_plan_agent",
        "stockpile_expansion_discovery_agent",
        "source_campaign_operator_followup_advance_agent",
        "lead_stockpile_health_agent",
        "lead_stockpile_health_advance_agent",
        "lead_supply_autopilot_agent",
        "overpass_lead_discovery_agent",
        "apollo_organization_discovery_agent",
        "scout_campaign_quality_summary_agent",
        "scout_campaign_quality_retention_agent",
        "scout_campaign_quality_regression_guard_agent",
        "scout_sensitive_hygiene_snapshot_agent",
            "revenue_loop_snapshot_agent",
            "revenue_loop_prepare_agent",
        "paid_customer_watchdog_agent",
        "outbound_mailer_gate_agent",
        "reply_action_agent",
        "reply_safety_rehearsal_agent",
        "inbox_integrity_gate_agent",
        "mail_clean_window_transition_agent",
        "mailer_status_agent",
        "mail_signal_learning_agent",
        "clean_window_recovery_agent",
        "clean_window_recheck_agent",
        "post_window_recheck_agent",
        "sender_rotation_readiness_agent",
        "warmup_agent",
        "warmup_block_recovery_agent",
        "warmup_block_recovery_snapshot_agent",
        "warmup_spacing_planner_agent",
        "warmup_spacing_apply_gate_agent",
        "warmup_post_send_observer_agent",
        "self_audit_agent",
        "self_closed_loop_agent",
        ]
    payload = {"limit": 1, "dry_run": True} if os.environ.get("PYTEST_CURRENT_TEST") else None
    runs = [run_agent(agent, payload) for agent in selected]
    return {"status": "completed", "agents": len(runs), "runs": runs, "live_outreach": False, "lock_acquired": True}


def run_daily_loop() -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (DAILY_LOOP_ADVISORY_LOCK_KEY,))
            locked = bool(cur.fetchone()[0])
        if not locked:
            return {
                "status": "skipped_already_running",
                "agents": 0,
                "runs": [],
                "live_outreach": False,
                "lock_acquired": False,
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
            }
        try:
            return _run_daily_loop_unlocked()
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (DAILY_LOOP_ADVISORY_LOCK_KEY,))
