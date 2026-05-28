from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from uuid import UUID

from .billing import checkout_config_status, hosted_checkout_url, product_checkout_config, PRODUCTS
from .codex_tasks import create_task
from .auth import require_admin
from .config import get_settings
from .email_quality import check_email_quality
from .inbox import classify_reply
from .models import OutreachPreviewRequest, ScanRequest, SuppressionRequest
from .p0 import (
    admin_metrics_from_db,
    create_scanner_job,
    get_audit_by_slug,
    get_scanner_job,
    handle_paddle_event,
    import_lead_batch,
    persist_inbound_message,
    prepare_warmup,
    record_visual_qa,
    run_mail_qa,
    import_warmup_recipients,
    import_test_inboxes,
    dedupe_outreach_preview_messages,
    prepare_outreach_preview,
    queue_outreach_preview,
    run_warmup_calendar_due,
    store_owner_command,
    suppress_unsubscribe_token,
    transport_gate_status,
    effective_pause_state,
)
from .outreach import outreach_allowed, render_template
from .scanner import deterministic_safe_scan
from .scanner_completion_watch import latest_scanner_completion_watches, scanner_completion_watch
from .scanner_ops import latest_scanner_stale_recovery_runs, recover_stale_running_scanner_jobs, retry_transient_scanner_failures, scanner_queue_health_snapshot, scanner_stale_running_snapshot
from .scanner_queue_hygiene import archive_scanner_queue_artifacts, scanner_queue_hygiene_snapshot
from .scanner_priority import latest_scanner_priority_runs, prioritize_guided_scanner_jobs, scanner_guided_backlog
from .source_scanner_queue import latest_source_scanner_queue_runs, queue_source_scanner_jobs, source_scanner_backlog
from .security import verify_paddle_signature
from .visual_quality import check_visual_publish_gate
from .autonomous_agents import run_agent, run_daily_loop
from .email_templates import render_email_template, qa_email_template, render_all_samples
from .lead_scoring import backfill_post_scan_lead_scores, score_lead
from .lead_quality_diagnostics import apply_scout_source_feedback, latest_lead_quality_diagnostics_history, latest_scout_source_performance, lead_quality_diagnostics_snapshot, record_lead_quality_diagnostics, scout_source_performance
from .audit_strength import score_audit_strength
from .audit_evidence_remediation import audit_evidence_candidates, audit_evidence_remediation, latest_audit_evidence_remediation_runs
from .audit_refresh_completion import audit_refresh_completion_watch, latest_audit_refresh_completion_watches
from .audit_refresh_drain import audit_refresh_drain_snapshot, latest_audit_refresh_drain_runs, prioritize_audit_refresh_jobs
from .audit_refresh_failures import audit_refresh_failure_snapshot, latest_audit_refresh_failure_runs, retry_failed_audit_refresh_jobs
from .audit_refresh_repair import audit_refresh_attachment_repair_snapshot, repair_audit_refresh_attachments
from .mailer_throttle import throttle_decision
from .campaign_economics import run_campaign_economics_check
from .campaign_control import campaign_readiness_snapshot
from .campaign_actions import campaign_actions_summary, run_campaign_action
from .campaign_control_room import campaign_control_room_snapshot, campaign_preview_rows, prepare_campaign_control_room
from .campaign_preview_reviews import auto_review_campaign_previews, latest_campaign_preview_reviews, review_campaign_preview
from .campaign_review_remediation import held_preview_remediation_candidates, remediate_held_preview_reviews
from .campaign_pipeline_repair import campaign_pipeline_gap_snapshot, repair_campaign_pipeline
from .campaign_preflight import campaign_preflight_batch, campaign_preflight_orphan_hygiene, latest_campaign_preflight_runs
from .campaign_remediation import campaign_remediation_plan, execute_campaign_remediation, latest_campaign_remediation_executions, latest_campaign_remediation_plans
from .campaign_remediation_feedback import campaign_remediation_feedback, latest_campaign_remediation_feedback
from .campaign_preview_refresh import campaign_preview_refresh_snapshot, latest_campaign_preview_refresh_runs, refresh_campaign_previews_if_needed
from .campaign_preview_hygiene import archive_campaign_preview_artifacts, archive_campaign_shell_artifacts, campaign_preview_hygiene_snapshot, campaign_shell_hygiene_snapshot
from .scout_sensitive_hygiene import archive_sensitive_scout_targets, scout_sensitive_target_snapshot
from .post_scan_campaign_cycle import latest_post_scan_campaign_cycles, post_scan_campaign_cycle
from .campaign_preview_quality import campaign_preview_quality_pack
from .studio_mail_monitor import ingest_studio_mail_messages, latest_studio_mail_messages, latest_studio_mail_runs
from .buyer_journey_scenarios import buyer_journey_readiness_scoreboard, run_buyer_journey_scenario
from .clean_window_recheck import clean_window_recheck, clean_window_recheck_summary, post_window_recheck_scheduler, post_window_recheck_summary
from .contact_enrichment import contact_enrichment_candidates, run_hunter_contact_enrichment, run_public_contact_page_enrichment
from .economics import calculate_unit_economics, latest_economics_summary, run_economics_audit
from .autonomous_mailer import decide_inbound_mail, decide_outbound_mail, run_autonomous_mailer_cycle
from .mailer_control import evaluate_outbound_message
from .mailer_readiness import mailbox_health_score, run_clean_window_transition, sender_rotation_ready
from .mailer_autonomy import email_template_autonomy_qa, mailer_status_snapshot, record_mail_signal_lessons, run_clean_window_recovery
from .mailer_control_room import cleanup_mailer_digest_history, latest_mailer_business_kpi_history, latest_mailer_digest_trend_guard_summary, latest_mailer_policy_score_history, latest_mailer_policy_score_regression_guard_summary, latest_mailer_self_audit_matrix_history, mailer_business_kpi_snapshot, mailer_control_room_summary, mailer_digest_summary, mailer_digest_trend_guard, mailer_policy_score, mailer_policy_score_regression_guard, mailer_policy_score_retention_summary, mailer_self_audit_matrix_snapshot, monitoring_control_room_summary, write_owner_status_report
from .mailer_autonomy_ledger import mailer_autonomy_ledger
from .mailer_action_queue import enqueue_mailer_action, mailer_action_queue_summary, process_mailer_action_queue, send_customer_mail, transport_dry_run
from .mailer_closed_loop import mailer_closed_loop_summary, run_mailer_closed_loop
from .mailer_ops_actions import cleanup_synthetic_mailer_ops_runs, mailer_ops_action_summary, mailer_ops_retention_report_history, run_mailer_ops_action
from .mail_recovery import check_mail_clean_window, create_mailer_draft
from .reply_actions import plan_reply_action
from .reply_safety_rehearsal import run_reply_safety_rehearsal
from .inbox_integrity_gate import run_inbox_integrity_gate
from .customer_journey import customer_journey_snapshot
from .customer_mail_simulation import run_customer_mail_simulation
from .customer_revenue_watchdog import latest_paid_customer_watchdog_runs, run_paid_customer_watchdog
from .customer_access import customer_dashboard_by_token, ensure_customer_access_token
from .monitoring import ensure_monitoring_target, process_due_monitoring_targets, run_monitoring_check
from .owner_command_control import owner_command_control_summary
from .language_gate import check_no_ai_public_language
from .launch_readiness_scoreboard import launch_readiness_scoreboard
from .launch_activation import apply_launch_activation, latest_launch_activation_runs, launch_activation_readiness, launch_activation_runbook, prepare_launch_activation, rollback_live_outreach
from .launch_rehearsal import latest_launch_rehearsal_runs, run_launch_rehearsal
from .lead_stockpile_health import latest_lead_stockpile_health_runs, lead_stockpile_health_snapshot, run_lead_stockpile_health
from .lead_supply_autopilot import lead_supply_autopilot
from .outreach_live_queue import latest_outreach_send_runs, live_outreach_queue_candidates, stage_live_outreach_batch
from .canary_batch_quality import canary_batch_quality
from .canary_checkout_simulation import run_canary_checkout_simulation
from .canary_operator_packet import build_canary_operator_packet, latest_canary_operator_packet
from .canary_send_window_plan import build_canary_send_window_plan, latest_canary_send_window_plan
from .outreach_post_send_observer import latest_outreach_post_send_observer_runs, outreach_post_send_observer
from .launch_operating_lane import advance_launch_operating_lane, launch_operating_lane_snapshot
from .launch_repair_cycle import run_launch_repair_cycle
from .launch_repair_planner import execute_launch_repair_plan, launch_repair_plan
from .quality_plugins import latest_quality_summary, quality_plugin_manifest, record_quality_plugin_run
from .lead_discovery import lead_discovery_target_plan, overpass_lead_discovery, performance_guided_regional_discovery_cycle, performance_guided_target_plan, quality_aware_regional_target_plan, regional_lead_discovery_cycle
from .revenue_simulation import run_synthetic_lead_simulation
from .revenue_loop import prepare_revenue_loop, revenue_loop_snapshot
from .source_campaign_operator import advance_source_to_campaign, source_campaign_operator_snapshot
from .source_adapters import directory_rows_to_csv, domain_list_to_csv
from .scout_run_recovery import recover_stale_scout_runs, stale_scout_run_recovery_snapshot
from .scout_quality import cleanup_scout_campaign_quality_history, latest_scout_campaign_quality_history, latest_scout_quality_gate, run_scout_quality_gate, run_scout_self_check, score_scout_provenance, scout_campaign_quality_regression_guard, scout_campaign_quality_summary
from .scouts import cleanup_scout_source_readiness_checks, create_campaign, create_scout_run, create_scout_source, get_campaign, get_scout_run, latest_scout_source_readiness, latest_scout_source_readiness_regression_guard_summary, prepare_campaign, prepare_campaign_gated, prepare_scout_source_from_adapter, process_scout_run, process_scout_run_gated, queue_ready_scout_source_runs, ready_scout_source_queue_candidates, run_scout_source_readiness, scout_campaign_expansion_gate, scout_source_readiness_gate, scout_source_readiness_regression_guard, scout_source_readiness_summary
from .warmup_planner import apply_provider_spacing_when_safe, plan_provider_spaced_warmup, rollback_latest_spacing_repair
from .warmup_block_recovery import recover_blocked_warmup_slots, warmup_block_recovery_snapshot
from .warmup_post_send import latest_warmup_post_send_checks, observe_warmup_post_send
from .self_operating import (
    create_self_fix_task,
    queue_self_build,
    record_learning,
    run_self_audit,
    self_operating_summary,
)
from .self_closed_loop import latest_self_operating_cycles, run_self_operating_closed_loop

app = FastAPI(title="Vøiddo Rescue API", version="0.1.0")
settings = get_settings()
Path(settings.storage_root).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.storage_root), name="media")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_base_url, settings.product_base_url, "http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "voiddo-rescue-api",
        "dry_run": settings.outreach_dry_run,
        "kill_switch": settings.global_kill_switch,
        "outreach_paused": settings.outreach_paused,
        "scanning_paused": effective_pause_state("scanner", settings.scanning_paused),
    }


@app.get("/admin/metrics", dependencies=[Depends(require_admin)])
def admin_metrics():
    return {"ok": True, **admin_metrics_from_db()}


@app.post("/scanner/scan")
def scan(request: ScanRequest):
    if settings.global_kill_switch:
        return {"ok": False, "status": "blocked", "reason": "global_kill_switch"}
    if effective_pause_state("scanner", settings.scanning_paused) and not request.dry_run:
        return {"ok": False, "status": "blocked", "reason": "scanning_paused"}
    result = deterministic_safe_scan(str(request.url), request.business_name)
    return {"ok": True, "result": result.model_dump()}


@app.post("/scanner/jobs")
def scanner_job_create(request: ScanRequest):
    if settings.global_kill_switch:
        return {"ok": False, "status": "blocked", "reason": "global_kill_switch"}
    job = create_scanner_job(str(request.url), request.business_name, request.dry_run)
    return {"ok": True, "job": job, "processing_paused": effective_pause_state("scanner", settings.scanning_paused)}


@app.get("/scanner/jobs/{job_id}")
def scanner_job_get(job_id: str):
    job = get_scanner_job(job_id)
    if not job:
        return Response(status_code=404, content="scanner job not found")
    return {"ok": True, "job": job}


@app.get("/admin/scanner/queue-health", dependencies=[Depends(require_admin)])
def scanner_queue_health_get(limit: int = 20):
    return {"ok": True, "scanner": scanner_queue_health_snapshot(limit)}


@app.get("/admin/scanner/queue-hygiene", dependencies=[Depends(require_admin)])
def scanner_queue_hygiene_get(limit: int = 500):
    return {"ok": True, "hygiene": scanner_queue_hygiene_snapshot(limit)}


@app.post("/admin/scanner/archive-artifacts", dependencies=[Depends(require_admin)])
async def scanner_archive_artifacts(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "hygiene": archive_scanner_queue_artifacts(
            int(payload.get("limit", 500)),
            bool(payload.get("apply", False)),
        ),
    }


@app.post("/admin/scanner/retry-transient", dependencies=[Depends(require_admin)])
async def scanner_retry_transient_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "scanner": retry_transient_scanner_failures(
            int(payload.get("limit", 5)),
            bool(payload.get("dry_run", True)),
            bool(payload.get("allow_timeout_resilience_retry", False)),
        ),
    }


@app.get("/admin/scanner/stale-running", dependencies=[Depends(require_admin)])
def scanner_stale_running_get(limit: int = 20, older_than_minutes: int = 15):
    return {"ok": True, "scanner": scanner_stale_running_snapshot(limit, older_than_minutes)}


@app.get("/admin/scanner/stale-recovery-runs", dependencies=[Depends(require_admin)])
def scanner_stale_recovery_runs_get(limit: int = 10):
    return {"ok": True, "runs": latest_scanner_stale_recovery_runs(limit)}


@app.post("/admin/scanner/recover-stale-running", dependencies=[Depends(require_admin)])
async def scanner_recover_stale_running_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "scanner": recover_stale_running_scanner_jobs(
            int(payload.get("limit", 10)),
            int(payload.get("older_than_minutes", 15)),
            bool(payload.get("dry_run", True)),
            int(payload.get("max_requeue_count", 1)),
        ),
    }


@app.get("/admin/scanner/guided-backlog", dependencies=[Depends(require_admin)])
def scanner_guided_backlog_get(limit: int = 50):
    return {"ok": True, "backlog": scanner_guided_backlog(limit)}


@app.get("/admin/scanner/priority-runs", dependencies=[Depends(require_admin)])
def scanner_priority_runs_get(limit: int = 10):
    return {"ok": True, "runs": latest_scanner_priority_runs(limit)}


@app.post("/admin/scanner/prioritize-guided", dependencies=[Depends(require_admin)])
async def scanner_prioritize_guided_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "priority": prioritize_guided_scanner_jobs(
            int(payload.get("limit", 25)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.get("/admin/scanner/completion-watches", dependencies=[Depends(require_admin)])
def scanner_completion_watches_get(limit: int = 10):
    return {"ok": True, "watches": latest_scanner_completion_watches(limit)}


@app.post("/admin/scanner/completion-watch", dependencies=[Depends(require_admin)])
async def scanner_completion_watch_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "watch": scanner_completion_watch(
            int(payload.get("limit", 100)),
            int(payload.get("min_new_completed", 1)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.get("/admin/scanner/source-backlog", dependencies=[Depends(require_admin)])
def source_scanner_backlog_get(limit: int = 100, source_id: str | None = None):
    return {"ok": True, "backlog": source_scanner_backlog(limit, source_id)}


@app.get("/admin/scanner/source-queue-runs", dependencies=[Depends(require_admin)])
def source_scanner_queue_runs_get(limit: int = 10):
    return {"ok": True, "runs": latest_source_scanner_queue_runs(limit)}


@app.post("/admin/scanner/queue-source-leads", dependencies=[Depends(require_admin)])
async def source_scanner_queue_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "queue": queue_source_scanner_jobs(
            int(payload.get("limit", 100)),
            bool(payload.get("dry_run", True)),
            payload.get("source_id"),
        ),
    }


@app.get("/audits/{slug}")
def audit_get(slug: str):
    audit = get_audit_by_slug(slug)
    if not audit:
        return Response(status_code=404, content="audit not found")
    return {"ok": True, "audit": audit}


@app.post("/outreach/preview")
def outreach_preview(request: OutreachPreviewRequest):
    rendered = render_template(
        request.language,
        {
            "business_name": request.business_name,
            "domain": request.domain,
            "contact_name": request.contact_name or "",
            "main_issue_short": request.main_issue_short,
            "audit_url": request.audit_url,
            "unsubscribe_url": request.unsubscribe_url,
        },
    )
    return {"ok": True, "dry_run": True, **rendered}


@app.post("/outreach/quality-check")
async def outreach_quality_check(request: Request):
    payload = await request.json()
    result = check_email_quality(payload.get("subject", ""), payload.get("body", ""))
    return {"ok": True, "passed": result.passed, "score": result.score, "issues": result.issues}


@app.post("/visual/publish-gate")
async def visual_publish_gate(request: Request):
    payload = await request.json()
    result = check_visual_publish_gate(payload.get("artifact_dir", ""))
    return {"ok": True, "passed": result.passed, "issues": result.issues}


@app.get("/outreach/safety-check")
def outreach_safety_check():
    decision = outreach_allowed(settings, suppressed=False, sent_today=0, sent_this_domain_hour=0)
    return {"ok": True, "allowed": decision.allowed, "reason": decision.reason}


@app.post("/suppression")
def suppression(request: SuppressionRequest):
    return {
        "ok": True,
        "dry_run": True,
        "suppressed": {"email": request.email, "domain": request.domain, "reason": request.reason, "source": request.source},
    }


@app.get("/unsubscribe/{token}")
def unsubscribe(token: str):
    result = suppress_unsubscribe_token(token)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["status"])
    return {"ok": True, **result}


@app.post("/unsubscribe/{token}")
def unsubscribe_one_click(token: str):
    result = suppress_unsubscribe_token(token)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["status"])
    return {"ok": True, **result, "one_click": True}


@app.post("/inbox/classify")
async def inbox_classify(request: Request):
    payload = await request.json()
    return {"ok": True, **classify_reply(payload.get("subject", ""), payload.get("body", ""))}


@app.post("/inbox/persist")
async def inbox_persist(request: Request):
    payload = await request.json()
    return {"ok": True, **persist_inbound_message(payload)}


@app.post("/owner/commands", dependencies=[Depends(require_admin)])
async def owner_commands(request: Request):
    payload = await request.json()
    return {"ok": True, "command": store_owner_command(payload)}


@app.get("/owner/commands", dependencies=[Depends(require_admin)])
def owner_commands_summary(limit: int = 20):
    return {"ok": True, "owner_commands": owner_command_control_summary(limit)}


@app.get("/billing/config")
def billing_config():
    return {"ok": True, **checkout_config_status(settings)}


@app.get("/checkout/config/{product_key}")
def checkout_product_config(product_key: str, request: Request):
    if product_key not in PRODUCTS:
        return Response(status_code=404, content="unknown product")
    audit_slug = request.query_params.get("audit", "")
    email = request.query_params.get("email", "")
    config = product_checkout_config(settings, product_key, audit_slug, email)
    if not config["ready"]:
        return Response(
            status_code=503,
            content="checkout_not_configured",
            headers={"X-Voiddo-Rescue-Gate": "paddle_client_checkout_missing"},
        )
    return {"ok": True, **config}


@app.get("/checkout/{product_key}")
def checkout_redirect(product_key: str, request: Request):
    audit_slug = request.query_params.get("audit", "")
    email = request.query_params.get("email", "")
    if product_key not in PRODUCTS:
        return Response(status_code=404, content="unknown product")
    target = hosted_checkout_url(settings, product_key, audit_slug, email)
    if not target:
        config = product_checkout_config(settings, product_key, audit_slug, email)
        if config["ready"]:
            params = []
            if audit_slug:
                params.append(f"audit={audit_slug}")
            if email:
                params.append(f"email={email}")
            suffix = f"?{'&'.join(params)}" if params else ""
            return RedirectResponse(f"{settings.app_base_url}/checkout/{product_key}{suffix}", status_code=302)
        return Response(status_code=503, content="checkout_not_configured", headers={"X-Voiddo-Rescue-Gate": "paddle_checkout_missing"})
    return RedirectResponse(target, status_code=302)


@app.post("/webhooks/paddle")
async def paddle_webhook(request: Request):
    raw = await request.body()
    signature = request.headers.get("Paddle-Signature", "")
    verified = verify_paddle_signature(raw, signature, settings.paddle_webhook_secret)
    if not verified:
        return Response(status_code=401, content="invalid signature")
    payload = await request.json()
    event_type = payload.get("event_type", "unknown")
    result = handle_paddle_event(payload, settings.paddle_provisioning_paused)
    return {"ok": True, "verified": True, "event_type": event_type, **result}


@app.post("/qa/visual/run", dependencies=[Depends(require_admin)])
async def visual_qa_run(request: Request):
    payload = await request.json()
    result = record_visual_qa(
        payload.get("agent", "app_visual_agent"),
        payload.get("target_url", settings.app_base_url),
        payload.get("html", ""),
    )
    return {"ok": True, "run": result}


@app.post("/qa/mail/run", dependencies=[Depends(require_admin)])
def mail_qa_run():
    return {"ok": True, "run": run_mail_qa()}


@app.post("/warmup/prepare", dependencies=[Depends(require_admin)])
async def warmup_prepare(request: Request):
    payload = await request.json()
    return {"ok": True, "warmup": prepare_warmup(int(payload.get("recipient_pool_count", 0)), int(payload.get("day_number", 1)))}


@app.post("/warmup/recipients/import", dependencies=[Depends(require_admin)])
async def warmup_recipients_import(request: Request):
    payload = await request.json()
    return {"ok": True, "pool": import_warmup_recipients(payload.get("csv", ""), payload.get("mailbox", "audit@voiddorescue.com"))}


@app.post("/admin/warmup/run-due", dependencies=[Depends(require_admin)])
async def warmup_run_due(request: Request):
    payload = await request.json()
    return {"ok": True, "warmup": run_warmup_calendar_due(int(payload.get("limit", 2)))}


@app.get("/admin/warmup/block-recovery", dependencies=[Depends(require_admin)])
def warmup_block_recovery_get(limit: int = 50):
    return {"ok": True, "recovery": warmup_block_recovery_snapshot(limit)}


@app.post("/admin/warmup/recover-blocked", dependencies=[Depends(require_admin)])
async def warmup_recover_blocked(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "recovery": recover_blocked_warmup_slots(
            int(payload.get("limit", 25)),
            apply=bool(payload.get("apply", False)),
        ),
    }


@app.post("/deliverability/test-inboxes/import", dependencies=[Depends(require_admin)])
async def deliverability_test_inboxes_import(request: Request):
    payload = await request.json()
    return {"ok": True, "pool": import_test_inboxes(payload.get("csv", ""))}


@app.post("/leads/batches/import", dependencies=[Depends(require_admin)])
async def lead_batch_import(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "batch": import_lead_batch(
            payload.get("name", "manual-dry-run"),
            payload.get("csv", ""),
            payload.get("country"),
            payload.get("niche"),
            int(payload.get("score_threshold", 70)),
        ),
    }


@app.post("/outreach/preview-batch", dependencies=[Depends(require_admin)])
async def outreach_preview_batch(request: Request):
    payload = await request.json()
    return {"ok": True, "preview": prepare_outreach_preview(int(payload.get("limit", 20)))}


@app.post("/outreach/queue-preview", dependencies=[Depends(require_admin)])
async def outreach_queue_preview(request: Request):
    payload = await request.json()
    return {"ok": True, "queued": queue_outreach_preview(int(payload.get("limit", 20)))}


@app.post("/outreach/dedupe-preview", dependencies=[Depends(require_admin)])
async def outreach_dedupe_preview(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "dedupe": dedupe_outreach_preview_messages(
            int(payload.get("limit", 500)),
            apply=bool(payload.get("apply", True)),
        ),
    }


@app.get("/admin/outreach/live-queue", dependencies=[Depends(require_admin)])
def outreach_live_queue_get(limit: int = 20):
    return {
        "ok": True,
        "candidates": live_outreach_queue_candidates(limit),
        "quality": canary_batch_quality(limit, store=False),
        "history": latest_outreach_send_runs(10),
    }


@app.get("/admin/outreach/live-queue/quality", dependencies=[Depends(require_admin)])
def outreach_live_queue_quality_get(limit: int = 20):
    return {"ok": True, "quality": canary_batch_quality(limit)}


@app.post("/admin/outreach/live-queue/checkout-simulation", dependencies=[Depends(require_admin)])
def outreach_live_queue_checkout_simulation_post():
    return {"ok": True, "simulation": run_canary_checkout_simulation(cleanup_after=True)}


@app.post("/admin/outreach/live-queue/operator-packet", dependencies=[Depends(require_admin)])
async def outreach_live_queue_operator_packet_post(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "packet": build_canary_operator_packet(
            int(payload.get("limit", 20)),
            store=True,
            run_checkout_simulation=bool(payload.get("run_checkout_simulation", False)),
        ),
    }


@app.get("/admin/outreach/live-queue/operator-packet", dependencies=[Depends(require_admin)])
def outreach_live_queue_operator_packet_get(limit: int = 20):
    return {"ok": True, "packet": latest_canary_operator_packet()}


@app.post("/admin/outreach/live-queue/send-window-plan", dependencies=[Depends(require_admin)])
async def outreach_live_queue_send_window_plan_post(request: Request):
    payload = await request.json()
    return {"ok": True, "plan": build_canary_send_window_plan(int(payload.get("limit", 20)), store=True)}


@app.get("/admin/outreach/live-queue/send-window-plan", dependencies=[Depends(require_admin)])
def outreach_live_queue_send_window_plan_get(limit: int = 20):
    return {"ok": True, "plan": latest_canary_send_window_plan()}


@app.post("/admin/outreach/live-queue/stage", dependencies=[Depends(require_admin)])
async def outreach_live_queue_stage(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "queue": stage_live_outreach_batch(
            int(payload.get("limit", 20)),
            bool(payload.get("dry_run", True)),
            payload.get("requested_by", "operator"),
        ),
    }


@app.get("/admin/outreach/post-send-observer", dependencies=[Depends(require_admin)])
def outreach_post_send_observer_get(limit: int = 10):
    return {"ok": True, "history": latest_outreach_post_send_observer_runs(limit)}


@app.post("/admin/outreach/post-send-observer/run", dependencies=[Depends(require_admin)])
async def outreach_post_send_observer_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "observer": outreach_post_send_observer(
            int(payload.get("window_hours", 24)),
            apply_pause=bool(payload.get("apply_pause", True)),
        ),
    }


@app.post("/outreach/send")
async def outreach_send(request: Request):
    payload = await request.json()
    gate = transport_gate_status(payload)
    if not gate["allowed"]:
        return {"ok": False, "status": "blocked", "reason": gate["reason"], "checks": gate["checks"]}
    return {"ok": False, "status": "blocked", "reason": "transport_worker_not_started_by_operator", "checks": gate["checks"]}


@app.post("/codex-tasks", dependencies=[Depends(require_admin)])
async def codex_task(request: Request):
    payload = await request.json()
    path = create_task(
        "/app/codex_tasks",
        payload.get("type", "dashboard_bug"),
        payload.get("priority", "P2"),
        payload.get("title", "Rescue follow-up task"),
        payload.get("context", "No context supplied."),
        payload.get("evidence", "No evidence supplied."),
    )
    return {"ok": True, "path": str(path)}


@app.post("/admin/scouts/sources", dependencies=[Depends(require_admin)])
async def scout_source_create(request: Request):
    payload = await request.json()
    return {"ok": True, "source": create_scout_source(payload)}


@app.post("/admin/scouts/runs", dependencies=[Depends(require_admin)])
async def scout_run_create(request: Request):
    payload = await request.json()
    source_id = payload.get("source_id")
    run = create_scout_run(source_id, payload)
    if payload.get("process_now", False):
        return {"ok": True, "run": run, "result": process_scout_run_gated(str(run["id"]))}
    return {"ok": True, "run": run}


@app.get("/admin/scouts/runs/{run_id}", dependencies=[Depends(require_admin)])
def scout_run_get(run_id: str):
    run = get_scout_run(run_id)
    if not run:
        return Response(status_code=404, content="scout run not found")
    return {"ok": True, "run": run}


@app.post("/admin/campaigns", dependencies=[Depends(require_admin)])
async def campaign_create(request: Request):
    payload = await request.json()
    return {"ok": True, "campaign": create_campaign(payload)}


@app.post("/admin/campaigns/{campaign_id}/prepare", dependencies=[Depends(require_admin)])
async def campaign_prepare(campaign_id: str, request: Request):
    payload = await request.json()
    return {"ok": True, "result": prepare_campaign_gated(campaign_id, int(payload.get("threshold", 70)), int(payload.get("limit", 20)))}


@app.get("/admin/scouts/expansion-gate", dependencies=[Depends(require_admin)])
def scout_expansion_gate_get():
    return {"ok": True, "gate": scout_campaign_expansion_gate()}


@app.get("/admin/scouts/source-queue-candidates", dependencies=[Depends(require_admin)])
def scout_source_queue_candidates_get(limit: int = 20, source_id: str | None = None):
    return {"ok": True, "queue": ready_scout_source_queue_candidates(limit, source_id)}


@app.post("/admin/scouts/source-queue", dependencies=[Depends(require_admin)])
async def scout_source_queue_run(request: Request):
    payload = await request.json()
    return {"ok": True, "queue": queue_ready_scout_source_runs(int(payload.get("limit", 10)), bool(payload.get("dry_run", True)), payload.get("source_id"))}


@app.get("/admin/scouts/stale-runs", dependencies=[Depends(require_admin)])
def scout_stale_runs_get(limit: int = 50, older_than_minutes: int = 120):
    return {"ok": True, "recovery": stale_scout_run_recovery_snapshot(limit, older_than_minutes)}


@app.post("/admin/scouts/recover-stale-runs", dependencies=[Depends(require_admin)])
async def scout_recover_stale_runs(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "recovery": recover_stale_scout_runs(
            int(payload.get("limit", 25)),
            int(payload.get("older_than_minutes", 120)),
            bool(payload.get("apply", False)),
        ),
    }


@app.post("/admin/scouts/sources/{source_id}/readiness", dependencies=[Depends(require_admin)])
def scout_source_readiness_run(source_id: str):
    return {"ok": True, "readiness": run_scout_source_readiness(source_id)}


@app.get("/admin/scouts/sources/{source_id}/readiness", dependencies=[Depends(require_admin)])
def scout_source_readiness_get(source_id: str):
    return {"ok": True, "readiness": latest_scout_source_readiness(source_id)}


@app.get("/admin/scouts/sources/{source_id}/readiness-gate", dependencies=[Depends(require_admin)])
def scout_source_readiness_gate_get(source_id: str):
    return {"ok": True, "gate": scout_source_readiness_gate(source_id)}


@app.get("/admin/scouts/source-readiness-summary", dependencies=[Depends(require_admin)])
def scout_source_readiness_summary_get():
    return {"ok": True, "summary": scout_source_readiness_summary()}


@app.post("/admin/scouts/source-readiness-retention", dependencies=[Depends(require_admin)])
def scout_source_readiness_retention(keep: int = 120):
    return {"ok": True, "retention": cleanup_scout_source_readiness_checks(keep)}


@app.post("/admin/scouts/source-readiness-regression-guard", dependencies=[Depends(require_admin)])
def scout_source_readiness_regression_guard_run(limit: int = 12):
    return {"ok": True, "guard": scout_source_readiness_regression_guard(limit)}


@app.get("/admin/scouts/source-readiness-regression-guard/latest", dependencies=[Depends(require_admin)])
def scout_source_readiness_regression_guard_latest_get():
    return {"ok": True, "guard": latest_scout_source_readiness_regression_guard_summary()}


@app.get("/admin/scouts/campaign-quality-summary", dependencies=[Depends(require_admin)])
def scout_campaign_quality_summary_get():
    return {"ok": True, "summary": scout_campaign_quality_summary()}


@app.get("/admin/scouts/campaign-quality-history", dependencies=[Depends(require_admin)])
def scout_campaign_quality_history_get(limit: int = 10):
    return {"ok": True, "history": latest_scout_campaign_quality_history(limit)}


@app.post("/admin/scouts/campaign-quality-history/retention", dependencies=[Depends(require_admin)])
def scout_campaign_quality_history_retention(keep: int = 120):
    return {"ok": True, "retention": cleanup_scout_campaign_quality_history(keep)}


@app.post("/admin/scouts/campaign-quality-regression-guard", dependencies=[Depends(require_admin)])
def scout_campaign_quality_regression_guard_run(limit: int = 12):
    return {"ok": True, "guard": scout_campaign_quality_regression_guard(limit)}


@app.get("/admin/campaigns/{campaign_id}", dependencies=[Depends(require_admin)])
def campaign_get(campaign_id: str):
    try:
        UUID(campaign_id)
    except ValueError:
        return Response(status_code=404, content="campaign not found")
    campaign = get_campaign(campaign_id)
    if not campaign:
        return Response(status_code=404, content="campaign not found")
    return {"ok": True, "campaign": campaign}


@app.post("/admin/leads/{lead_id}/score", dependencies=[Depends(require_admin)])
async def lead_score_create(lead_id: str, request: Request):
    payload = await request.json()
    return {"ok": True, "score": score_lead(lead_id, payload.get("audit_id"))}


@app.post("/admin/leads/backfill-post-scan-scores", dependencies=[Depends(require_admin)])
async def lead_score_backfill_create(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "backfill": backfill_post_scan_lead_scores(
            int(payload.get("limit", 50)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.get("/admin/leads/quality-diagnostics", dependencies=[Depends(require_admin)])
def lead_quality_diagnostics_get(limit: int = 50):
    return {"ok": True, "diagnostics": lead_quality_diagnostics_snapshot(limit)}


@app.post("/admin/leads/quality-diagnostics", dependencies=[Depends(require_admin)])
async def lead_quality_diagnostics_record(request: Request):
    payload = await request.json()
    return {"ok": True, "diagnostics": record_lead_quality_diagnostics(int(payload.get("limit", 50)))}


@app.get("/admin/leads/quality-diagnostics/history", dependencies=[Depends(require_admin)])
def lead_quality_diagnostics_history_get(limit: int = 10):
    return {"ok": True, "history": latest_lead_quality_diagnostics_history(limit)}


@app.get("/admin/leads/contact-enrichment/candidates", dependencies=[Depends(require_admin)])
def lead_contact_enrichment_candidates_get(limit: int = 25):
    return {"ok": True, "enrichment": contact_enrichment_candidates(limit)}


@app.post("/admin/leads/contact-enrichment/run", dependencies=[Depends(require_admin)])
async def lead_contact_enrichment_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "enrichment": run_hunter_contact_enrichment(
            int(payload.get("limit", 10)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.post("/admin/leads/contact-enrichment/public-contact-pages", dependencies=[Depends(require_admin)])
async def lead_contact_public_page_enrichment_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "enrichment": run_public_contact_page_enrichment(
            int(payload.get("limit", 10)),
            bool(payload.get("dry_run", True)),
            int(payload.get("max_pages_per_domain", 4)),
            int(payload.get("max_seconds", 45)),
        ),
    }


@app.post("/admin/scouts/source-feedback", dependencies=[Depends(require_admin)])
async def scout_source_feedback_apply(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "feedback": apply_scout_source_feedback(
            int(payload.get("limit", 50)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.get("/admin/scouts/source-performance", dependencies=[Depends(require_admin)])
def scout_source_performance_get(limit: int = 20):
    return {"ok": True, "performance": latest_scout_source_performance(limit)}


@app.post("/admin/scouts/source-performance", dependencies=[Depends(require_admin)])
async def scout_source_performance_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "performance": scout_source_performance(
            int(payload.get("limit", 100)),
            bool(payload.get("store", True)),
        ),
    }


@app.post("/admin/agents/{agent}", dependencies=[Depends(require_admin)])
async def agent_run(agent: str, request: Request):
    payload = await request.json()
    return {"ok": True, "run": run_agent(agent, payload)}


@app.post("/admin/daily-loop/run", dependencies=[Depends(require_admin)])
def daily_loop_run():
    return {"ok": True, "loop": run_daily_loop()}


@app.post("/admin/economics/audit", dependencies=[Depends(require_admin)])
def economics_audit_run():
    return {"ok": True, "economics": run_economics_audit()}


@app.get("/admin/economics/summary", dependencies=[Depends(require_admin)])
def economics_summary_get():
    return {"ok": True, "summary": latest_economics_summary()}


@app.get("/admin/economics/{product_key}", dependencies=[Depends(require_admin)])
def economics_product_get(product_key: str):
    return {"ok": True, "economics": calculate_unit_economics(product_key)}


@app.post("/admin/self/audit", dependencies=[Depends(require_admin)])
async def self_audit_run(request: Request):
    payload = await request.json()
    return {"ok": True, "self_audit": run_self_audit(payload.get("scope", "full"))}


@app.get("/admin/self/summary", dependencies=[Depends(require_admin)])
def self_summary_get():
    return {"ok": True, "summary": self_operating_summary()}


@app.post("/admin/self/closed-loop", dependencies=[Depends(require_admin)])
async def self_closed_loop_run(request: Request):
    payload = await request.json()
    return {"ok": True, "cycle": run_self_operating_closed_loop(payload.get("scope", "manual"), int(payload.get("limit", 25)))}


@app.get("/admin/self/closed-loop", dependencies=[Depends(require_admin)])
def self_closed_loop_get(limit: int = 10):
    return {"ok": True, **latest_self_operating_cycles(limit)}


@app.post("/admin/self/fix-tasks", dependencies=[Depends(require_admin)])
async def self_fix_task_create(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "task": create_self_fix_task(
            payload.get("type", "manual_self_fix"),
            payload.get("title", "Self-fix task"),
            payload.get("priority", "P2"),
            payload.get("evidence") or {},
            payload.get("safety_level", "safe"),
        ),
    }


@app.post("/admin/self/learning", dependencies=[Depends(require_admin)])
async def self_learning_create(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "learning": record_learning(
            payload.get("signal_type", "manual"),
            payload.get("source", "admin"),
            payload.get("lesson", "No lesson supplied."),
            payload.get("prevention_rule", "Review before recurrence."),
            payload.get("severity", "info"),
            payload.get("payload") or {},
        ),
    }


@app.post("/admin/self/build-queue", dependencies=[Depends(require_admin)])
async def self_build_queue_create(request: Request):
    payload = await request.json()
    return {"ok": True, "item": queue_self_build(payload.get("module", "unknown"), payload.get("title", "Build item"), payload.get("priority", "P2"), payload.get("acceptance") or [])}


@app.post("/admin/mailer/autonomous-cycle", dependencies=[Depends(require_admin)])
def autonomous_mailer_cycle_run():
    return {"ok": True, "mailer": run_autonomous_mailer_cycle()}


@app.post("/admin/mailer/decide-outbound", dependencies=[Depends(require_admin)])
async def autonomous_mailer_outbound(request: Request):
    payload = await request.json()
    return {"ok": True, "decision": decide_outbound_mail(payload)}


@app.post("/admin/mailer/decide-inbound", dependencies=[Depends(require_admin)])
async def autonomous_mailer_inbound(request: Request):
    payload = await request.json()
    return {"ok": True, "decision": decide_inbound_mail(payload.get("subject", ""), payload.get("body", ""), payload.get("mailbox", "support@voiddorescue.com"))}


@app.post("/admin/mailer/outbound-decision", dependencies=[Depends(require_admin)])
async def outbound_message_decision(request: Request):
    payload = await request.json()
    return {"ok": True, "decision": evaluate_outbound_message(payload)}


@app.post("/admin/mailer/clean-window-transition", dependencies=[Depends(require_admin)])
async def mail_clean_window_transition_run(request: Request):
    payload = await request.json()
    return {"ok": True, "transition": run_clean_window_transition(int(payload.get("window_hours", 24)))}


@app.post("/admin/mailer/mailbox-health", dependencies=[Depends(require_admin)])
async def mailbox_health_run(request: Request):
    payload = await request.json()
    return {"ok": True, "health": mailbox_health_score(payload.get("mailbox", "audit@voiddorescue.com"))}


@app.post("/admin/mailer/sender-rotation", dependencies=[Depends(require_admin)])
def sender_rotation_run():
    return {"ok": True, "readiness": sender_rotation_ready()}


@app.get("/admin/mailer/status", dependencies=[Depends(require_admin)])
def mailer_status_run():
    return {"ok": True, "status": mailer_status_snapshot()}


@app.post("/admin/mailer/clean-window-recovery", dependencies=[Depends(require_admin)])
async def mailer_clean_window_recovery_run(request: Request):
    payload = await request.json()
    return {"ok": True, "recovery": run_clean_window_recovery(int(payload.get("window_hours", 24)))}


@app.get("/admin/mailer/clean-window-recheck", dependencies=[Depends(require_admin)])
def mailer_clean_window_recheck_get():
    return {"ok": True, "summary": clean_window_recheck_summary()}


@app.post("/admin/mailer/clean-window-recheck", dependencies=[Depends(require_admin)])
async def mailer_clean_window_recheck_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "recheck": clean_window_recheck(
            int(payload.get("window_hours", 24)),
            bool(payload.get("run_recovery_if_clear", True)),
        ),
    }


@app.get("/admin/mailer/post-window-recheck", dependencies=[Depends(require_admin)])
def mailer_post_window_recheck_get():
    return {"ok": True, "summary": post_window_recheck_summary()}


@app.post("/admin/mailer/post-window-recheck", dependencies=[Depends(require_admin)])
async def mailer_post_window_recheck_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "run": post_window_recheck_scheduler(
            int(payload.get("window_hours", 24)),
            run_recovery_if_due=bool(payload.get("run_recovery_if_due", True)),
        ),
    }


@app.post("/admin/mailer/learn-signals", dependencies=[Depends(require_admin)])
async def mailer_signal_learning_run(request: Request):
    payload = await request.json()
    return {"ok": True, "learning": record_mail_signal_lessons(int(payload.get("window_hours", 24)))}


@app.get("/admin/mailer/template-qa", dependencies=[Depends(require_admin)])
def mailer_template_qa_run():
    return {"ok": True, "template_qa": email_template_autonomy_qa()}


@app.get("/admin/mailer/control-room", dependencies=[Depends(require_admin)])
def mailer_control_room_get():
    return {"ok": True, "control_room": mailer_control_room_summary()}


@app.get("/admin/mailer/autonomy-ledger", dependencies=[Depends(require_admin)])
def mailer_autonomy_ledger_get():
    return {"ok": True, "ledger": mailer_autonomy_ledger()}


@app.get("/admin/mailer/action-queue", dependencies=[Depends(require_admin)])
def mailer_action_queue_get():
    return {"ok": True, "queue": mailer_action_queue_summary()}


@app.post("/admin/mailer/action-queue", dependencies=[Depends(require_admin)])
async def mailer_action_queue_create(request: Request):
    payload = await request.json()
    return {"ok": True, "action": enqueue_mailer_action(payload)}


@app.post("/admin/mailer/action-queue/process", dependencies=[Depends(require_admin)])
async def mailer_action_queue_process(request: Request):
    payload = await request.json()
    return {"ok": True, "result": process_mailer_action_queue(int(payload.get("limit", 10)))}


@app.post("/admin/mailer/action-queue/transport-dry-run", dependencies=[Depends(require_admin)])
async def mailer_action_queue_transport_dry_run(request: Request):
    payload = await request.json()
    return {"ok": True, "result": transport_dry_run(int(payload.get("limit", 10)))}


@app.post("/admin/mailer/action-queue/send-customer-mail", dependencies=[Depends(require_admin)])
async def mailer_action_queue_send_customer_mail(request: Request):
    payload = await request.json()
    return {"ok": True, "result": send_customer_mail(int(payload.get("limit", 10)))}


@app.get("/admin/mailer/closed-loop", dependencies=[Depends(require_admin)])
def mailer_closed_loop_get():
    return {"ok": True, "closed_loop": mailer_closed_loop_summary()}


@app.post("/admin/mailer/closed-loop/run", dependencies=[Depends(require_admin)])
async def mailer_closed_loop_run(request: Request):
    payload = await request.json()
    return {"ok": True, "result": run_mailer_closed_loop(int(payload.get("limit", 10)))}


@app.post("/admin/mailer/customer-simulation", dependencies=[Depends(require_admin)])
async def mailer_customer_simulation(request: Request):
    payload = await request.json()
    return {"ok": True, "simulation": run_customer_mail_simulation(bool(payload.get("write_report", True)))}


@app.get("/admin/mailer/customer-simulation", dependencies=[Depends(require_admin)])
def mailer_customer_simulation_summary():
    return {"ok": True, "simulation": run_customer_mail_simulation(False)}


@app.get("/admin/mailer/ops-actions", dependencies=[Depends(require_admin)])
def mailer_ops_actions_get():
    return {"ok": True, "ops_actions": mailer_ops_action_summary()}


@app.post("/admin/mailer/ops-actions", dependencies=[Depends(require_admin)])
async def mailer_ops_actions_post(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "ops_action": run_mailer_ops_action(
            str(payload.get("action", "")),
            int(payload.get("limit", 10)),
            str(payload.get("source", "admin")),
            payload.get("is_synthetic"),
        ),
    }


@app.post("/admin/mailer/ops-actions/cleanup-synthetic", dependencies=[Depends(require_admin)])
def mailer_ops_actions_cleanup_synthetic():
    return {"ok": True, "cleanup": cleanup_synthetic_mailer_ops_runs()}


@app.get("/admin/mailer/ops-retention-history", dependencies=[Depends(require_admin)])
def mailer_ops_retention_history_get(limit: int = 8):
    return {"ok": True, "history": mailer_ops_retention_report_history(limit)}


@app.post("/admin/mailer/owner-status-report", dependencies=[Depends(require_admin)])
async def mailer_owner_status_report(request: Request):
    payload = await request.json()
    return {"ok": True, "report": write_owner_status_report(bool(payload.get("send_if_safe", False)))}


@app.get("/admin/mailer/digest-summary", dependencies=[Depends(require_admin)])
def mailer_digest_summary_get():
    return {"ok": True, "digest": mailer_digest_summary()}


@app.post("/admin/mailer/digest-history/cleanup", dependencies=[Depends(require_admin)])
async def mailer_digest_history_cleanup(request: Request):
    payload = await request.json()
    return {"ok": True, "cleanup": cleanup_mailer_digest_history(int(payload.get("keep", 90)))}


@app.get("/admin/mailer/digest-trend-guard", dependencies=[Depends(require_admin)])
def mailer_digest_trend_guard_get(limit: int = 8):
    return {"ok": True, "trend_guard": mailer_digest_trend_guard(limit)}


@app.get("/admin/mailer/digest-trend-guard/latest", dependencies=[Depends(require_admin)])
def mailer_digest_trend_guard_latest_get():
    return {"ok": True, "trend_guard": latest_mailer_digest_trend_guard_summary()}


@app.get("/admin/mailer/policy-score", dependencies=[Depends(require_admin)])
def mailer_policy_score_get():
    return {"ok": True, "policy_score": mailer_policy_score()}


@app.get("/admin/mailer/policy-score/history", dependencies=[Depends(require_admin)])
def mailer_policy_score_history_get(limit: int = 5):
    return {"ok": True, "history": latest_mailer_policy_score_history(limit)}


@app.get("/admin/mailer/policy-score/retention", dependencies=[Depends(require_admin)])
def mailer_policy_score_retention_get():
    return {"ok": True, "retention": mailer_policy_score_retention_summary()}


@app.get("/admin/mailer/policy-score/regression-guard", dependencies=[Depends(require_admin)])
def mailer_policy_score_regression_guard_get(limit: int = 12):
    return {"ok": True, "guard": mailer_policy_score_regression_guard(limit)}


@app.get("/admin/mailer/policy-score/regression-guard/latest", dependencies=[Depends(require_admin)])
def mailer_policy_score_regression_guard_latest_get():
    return {"ok": True, "guard": latest_mailer_policy_score_regression_guard_summary()}


@app.get("/admin/mailer/business-kpi", dependencies=[Depends(require_admin)])
def mailer_business_kpi_get(limit: int = 5):
    return {"ok": True, "snapshot": mailer_business_kpi_snapshot(), "history": latest_mailer_business_kpi_history(limit)}


@app.get("/admin/mailer/self-audit-matrix", dependencies=[Depends(require_admin)])
def mailer_self_audit_matrix_get(limit: int = 5):
    return {"ok": True, "snapshot": mailer_self_audit_matrix_snapshot(), "history": latest_mailer_self_audit_matrix_history(limit)}


@app.get("/admin/customers/{customer_id}/journey", dependencies=[Depends(require_admin)])
def customer_journey_get(customer_id: str):
    return {"ok": True, "journey": customer_journey_snapshot(customer_id=customer_id)}


@app.post("/admin/customers/{customer_id}/access-token", dependencies=[Depends(require_admin)])
def customer_access_token_create(customer_id: str):
    return {"ok": True, "access": ensure_customer_access_token(customer_id)}


@app.get("/customer/dashboard/{token}")
def customer_dashboard_token_get(token: str):
    try:
        return {"ok": True, "dashboard": customer_dashboard_by_token(token)}
    except ValueError:
        return Response(status_code=404)


@app.post("/admin/customers/{customer_id}/monitoring-targets", dependencies=[Depends(require_admin)])
async def monitoring_target_create(customer_id: str, request: Request):
    payload = await request.json()
    return {"ok": True, "target": ensure_monitoring_target(customer_id, payload.get("site_url", ""))}


@app.get("/admin/customers/revenue-watchdog", dependencies=[Depends(require_admin)])
def customer_revenue_watchdog_get(limit: int = 10):
    return {"ok": True, "history": latest_paid_customer_watchdog_runs(limit)}


@app.post("/admin/customers/revenue-watchdog/run", dependencies=[Depends(require_admin)])
async def customer_revenue_watchdog_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "watchdog": run_paid_customer_watchdog(
            int(payload.get("limit", 25)),
            repair=bool(payload.get("repair", True)),
        ),
    }


@app.post("/admin/monitoring/run-due", dependencies=[Depends(require_admin)])
async def monitoring_due_run(request: Request):
    payload = await request.json()
    return {"ok": True, "result": process_due_monitoring_targets(int(payload.get("limit", 5)), bool(payload.get("dry_run", True)))}


@app.get("/admin/monitoring/summary", dependencies=[Depends(require_admin)])
def monitoring_summary_get():
    return {"ok": True, "summary": monitoring_control_room_summary()}


@app.post("/admin/monitoring/{target_id}/run", dependencies=[Depends(require_admin)])
async def monitoring_run_create(target_id: str, request: Request):
    payload = await request.json()
    return {"ok": True, "run": run_monitoring_check(target_id, bool(payload.get("dry_run", True)))}


@app.post("/admin/warmup/provider-spacing-plan", dependencies=[Depends(require_admin)])
async def warmup_provider_spacing_plan(request: Request):
    payload = await request.json()
    return {"ok": True, "plan": plan_provider_spaced_warmup(int(payload.get("limit", 50)), bool(payload.get("apply", False)))}


@app.post("/admin/warmup/provider-spacing-apply", dependencies=[Depends(require_admin)])
async def warmup_provider_spacing_apply(request: Request):
    payload = await request.json()
    return {"ok": True, "repair": apply_provider_spacing_when_safe(int(payload.get("limit", 50)))}


@app.post("/admin/warmup/provider-spacing-rollback", dependencies=[Depends(require_admin)])
def warmup_provider_spacing_rollback():
    return {"ok": True, "rollback": rollback_latest_spacing_repair()}


@app.get("/admin/warmup/post-send-checks", dependencies=[Depends(require_admin)])
def warmup_post_send_checks_get(limit: int = 10):
    return {"ok": True, "checks": latest_warmup_post_send_checks(limit)}


@app.post("/admin/warmup/post-send-observe", dependencies=[Depends(require_admin)])
async def warmup_post_send_observe_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "observation": observe_warmup_post_send(
            int(payload.get("limit", 10)),
            bool(payload.get("pause_on_blocker", True)),
        ),
    }


@app.post("/admin/replies/action-plan", dependencies=[Depends(require_admin)])
async def reply_action_plan_create(request: Request):
    payload = await request.json()
    return {"ok": True, "plan": plan_reply_action(payload.get("subject", ""), payload.get("body", ""), payload.get("mailbox", "support@voiddorescue.com"))}


@app.post("/admin/replies/safety-rehearsal", dependencies=[Depends(require_admin)])
def reply_action_rehearsal_create():
    return {"ok": True, "rehearsal": run_reply_safety_rehearsal()}


@app.post("/admin/inbox/integrity-gate", dependencies=[Depends(require_admin)])
async def inbox_integrity_gate_create(request: Request):
    payload = await request.json()
    return {"ok": True, "gate": run_inbox_integrity_gate(int(payload.get("window_hours", 24)))}


@app.get("/admin/quality/plugins", dependencies=[Depends(require_admin)])
def quality_plugins_get():
    return {"ok": True, "manifest": quality_plugin_manifest(), "summary": latest_quality_summary()}


@app.post("/admin/quality/plugins/record", dependencies=[Depends(require_admin)])
async def quality_plugin_record(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "run": record_quality_plugin_run(
            payload.get("tool", "huanshu"),
            payload.get("target", "/"),
            payload.get("status", "PASS"),
            int(payload.get("score", 100)),
            payload.get("issues") or [],
            payload.get("artifact_path", ""),
        ),
    }


@app.post("/admin/revenue/simulate", dependencies=[Depends(require_admin)])
async def revenue_simulate(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "simulation": run_synthetic_lead_simulation(
            int(payload.get("count", 100)),
            payload.get("country", "EE"),
            payload.get("niche", "dentists"),
            payload.get("product_key", "contact_form_repair"),
        ),
    }


@app.get("/admin/scenarios/buyer-journey", dependencies=[Depends(require_admin)])
def buyer_journey_scoreboard_get():
    return {"ok": True, "scoreboard": buyer_journey_readiness_scoreboard()}


@app.post("/admin/scenarios/buyer-journey/run", dependencies=[Depends(require_admin)])
async def buyer_journey_scenario_run(request: Request):
    payload = await request.json()
    return {"ok": True, "scenario": run_buyer_journey_scenario(bool(payload.get("cleanup", True)))}


@app.get("/admin/revenue-loop", dependencies=[Depends(require_admin)])
def revenue_loop_get(limit: int = 25):
    return {"ok": True, "revenue_loop": revenue_loop_snapshot(limit)}


@app.post("/admin/revenue-loop/prepare", dependencies=[Depends(require_admin)])
async def revenue_loop_prepare(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "revenue_loop": prepare_revenue_loop(
            int(payload.get("limit", 25)),
            bool(payload.get("dry_run", True)),
            bool(payload.get("activate_sources", False)),
            payload.get("source_id"),
            bool(payload.get("allow_bulk_source_activation", False)),
            bool(payload.get("prepare_campaigns", True)),
            bool(payload.get("prepare_customers", True)),
        ),
    }


@app.post("/admin/campaigns/{campaign_id}/economics", dependencies=[Depends(require_admin)])
async def campaign_economics_run(campaign_id: str, request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "economics": run_campaign_economics_check(
            campaign_id,
            payload.get("product_key", "contact_form_repair"),
            float(payload.get("expected_conversion_rate", 0.02)),
        ),
    }


@app.post("/admin/campaigns/{campaign_id}/readiness", dependencies=[Depends(require_admin)])
def campaign_readiness_run(campaign_id: str):
    return {"ok": True, "readiness": campaign_readiness_snapshot(campaign_id)}


@app.post("/admin/campaigns/{campaign_id}/preview-quality", dependencies=[Depends(require_admin)])
async def campaign_preview_quality_run(campaign_id: str, request: Request):
    payload = await request.json()
    return {"ok": True, "quality": campaign_preview_quality_pack(campaign_id, int(payload.get("limit", 20)))}


@app.get("/admin/campaign-control-room", dependencies=[Depends(require_admin)])
def campaign_control_room_get(limit: int = 100, threshold: int = 70):
    return {"ok": True, "control_room": campaign_control_room_snapshot(limit, threshold)}


@app.get("/admin/campaign-control-room/preview-rows", dependencies=[Depends(require_admin)])
def campaign_control_room_preview_rows_get(limit: int = 25):
    return {"ok": True, "preview_rows": campaign_preview_rows(limit)}


@app.get("/admin/campaign-control-room/reviews", dependencies=[Depends(require_admin)])
def campaign_control_room_reviews_get(limit: int = 25):
    return {"ok": True, "reviews": latest_campaign_preview_reviews(limit)}


@app.post("/admin/campaign-control-room/review", dependencies=[Depends(require_admin)])
async def campaign_control_room_review_post(request: Request):
    payload = await request.json()
    review = review_campaign_preview(
        payload.get("campaign_lead_id", ""),
        payload.get("action", "held"),
        payload.get("reason", ""),
        payload.get("actor", "admin"),
    )
    return {"ok": True, "review": review}


@app.post("/admin/campaign-control-room/auto-review", dependencies=[Depends(require_admin)])
async def campaign_control_room_auto_review_post(request: Request):
    payload = await request.json()
    result = auto_review_campaign_previews(
        int(payload.get("limit", 25)),
        apply=bool(payload.get("apply", True)),
        campaign_id=payload.get("campaign_id") or None,
        reconsider_held=bool(payload.get("reconsider_held", False)),
    )
    return {"ok": True, "auto_review": result}


@app.get("/admin/campaign-control-room/held-remediation", dependencies=[Depends(require_admin)])
def campaign_control_room_held_remediation_get(limit: int = 25):
    return {"ok": True, "held_remediation": held_preview_remediation_candidates(limit)}


@app.post("/admin/campaign-control-room/remediate-held", dependencies=[Depends(require_admin)])
async def campaign_control_room_remediate_held_post(request: Request):
    payload = await request.json()
    result = remediate_held_preview_reviews(
        int(payload.get("limit", 25)),
        dry_run=bool(payload.get("dry_run", True)),
    )
    return {"ok": True, "held_remediation": result}


@app.post("/admin/campaign-control-room/prepare", dependencies=[Depends(require_admin)])
async def campaign_control_room_prepare(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "control_room": prepare_campaign_control_room(
            int(payload.get("limit", 100)),
            int(payload.get("threshold", 70)),
            bool(payload.get("dry_run", True)),
            payload.get("offer_key", "contact_form_repair"),
            int(payload.get("max_segments", 3)),
        ),
    }


@app.get("/admin/campaign-actions", dependencies=[Depends(require_admin)])
def campaign_actions_get(limit: int = 20):
    return {"ok": True, "actions": campaign_actions_summary(limit)}


@app.post("/admin/campaign-actions/run", dependencies=[Depends(require_admin)])
async def campaign_actions_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "action": run_campaign_action(
            str(payload.get("action", "")),
            payload.get("campaign_id"),
            int(payload.get("limit", 100)),
            bool(payload.get("dry_run", False)),
        ),
    }


@app.get("/admin/campaign-preview/hygiene", dependencies=[Depends(require_admin)])
def campaign_preview_hygiene_get(limit: int = 500):
    return {"ok": True, "hygiene": campaign_preview_hygiene_snapshot(limit)}


@app.post("/admin/campaign-preview/archive-artifacts", dependencies=[Depends(require_admin)])
async def campaign_preview_archive_artifacts(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "hygiene": archive_campaign_preview_artifacts(
            int(payload.get("limit", 500)),
            bool(payload.get("apply", False)),
        ),
    }


@app.get("/admin/campaign-shell-hygiene", dependencies=[Depends(require_admin)])
def campaign_shell_hygiene_get(limit: int = 500):
    return {"ok": True, "hygiene": campaign_shell_hygiene_snapshot(limit)}


@app.post("/admin/campaign-shell-hygiene/archive-artifacts", dependencies=[Depends(require_admin)])
async def campaign_shell_archive_artifacts(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "hygiene": archive_campaign_shell_artifacts(
            int(payload.get("limit", 500)),
            bool(payload.get("apply", False)),
        ),
    }


@app.get("/admin/scouts/sensitive-targets", dependencies=[Depends(require_admin)])
def scout_sensitive_targets_get(limit: int = 200):
    return {"ok": True, "hygiene": scout_sensitive_target_snapshot(limit)}


@app.post("/admin/scouts/archive-sensitive-targets", dependencies=[Depends(require_admin)])
async def scout_sensitive_targets_archive(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "hygiene": archive_sensitive_scout_targets(
            int(payload.get("limit", 200)),
            bool(payload.get("apply", False)),
        ),
    }


@app.get("/admin/campaign-pipeline/gaps", dependencies=[Depends(require_admin)])
def campaign_pipeline_gaps_get(limit: int = 100):
    return {"ok": True, "pipeline": campaign_pipeline_gap_snapshot(limit)}


@app.post("/admin/campaign-pipeline/repair", dependencies=[Depends(require_admin)])
async def campaign_pipeline_repair_run(request: Request):
    payload = await request.json()
    return {"ok": True, "pipeline": repair_campaign_pipeline(int(payload.get("limit", 100)), bool(payload.get("dry_run", True)))}


@app.get("/admin/campaign-preview/refresh-snapshot", dependencies=[Depends(require_admin)])
def campaign_preview_refresh_snapshot_get(limit: int = 100, stale_hours: int = 24):
    return {"ok": True, "snapshot": campaign_preview_refresh_snapshot(limit, stale_hours)}


@app.get("/admin/campaign-preview/refresh-runs", dependencies=[Depends(require_admin)])
def campaign_preview_refresh_runs_get(limit: int = 10):
    return {"ok": True, "runs": latest_campaign_preview_refresh_runs(limit)}


@app.post("/admin/campaign-preview/refresh", dependencies=[Depends(require_admin)])
async def campaign_preview_refresh_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "refresh": refresh_campaign_previews_if_needed(
            int(payload.get("limit", 100)),
            int(payload.get("stale_hours", 24)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.get("/admin/campaign-preflight/runs", dependencies=[Depends(require_admin)])
def campaign_preflight_runs_get(limit: int = 10):
    return {"ok": True, "runs": latest_campaign_preflight_runs(limit)}


@app.post("/admin/campaign-preflight/run", dependencies=[Depends(require_admin)])
async def campaign_preflight_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "preflight": campaign_preflight_batch(
            int(payload.get("limit", 20)),
            payload.get("campaign_id"),
        ),
    }


@app.post("/admin/campaign-preflight/orphan-hygiene", dependencies=[Depends(require_admin)])
async def campaign_preflight_orphan_hygiene_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "hygiene": campaign_preflight_orphan_hygiene(
            int(payload.get("limit", 100)),
            apply=bool(payload.get("apply", True)),
        ),
    }


@app.get("/admin/campaign-remediation/plans", dependencies=[Depends(require_admin)])
def campaign_remediation_plans_get(limit: int = 10):
    return {"ok": True, "plans": latest_campaign_remediation_plans(limit)}


@app.post("/admin/campaign-remediation/plan", dependencies=[Depends(require_admin)])
async def campaign_remediation_plan_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "remediation": campaign_remediation_plan(
            int(payload.get("limit", 25)),
            bool(payload.get("create_tasks", True)),
        ),
    }


@app.get("/admin/campaign-remediation/executions", dependencies=[Depends(require_admin)])
def campaign_remediation_executions_get(limit: int = 10):
    return {"ok": True, "executions": latest_campaign_remediation_executions(limit)}


@app.post("/admin/campaign-remediation/execute", dependencies=[Depends(require_admin)])
async def campaign_remediation_execute_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "execution": execute_campaign_remediation(
            int(payload.get("limit", 10)),
            bool(payload.get("rerun_preflight", True)),
        ),
    }


@app.get("/admin/campaign-remediation/feedback", dependencies=[Depends(require_admin)])
def campaign_remediation_feedback_get(limit: int = 10):
    return {"ok": True, "feedback": latest_campaign_remediation_feedback(limit)}


@app.post("/admin/campaign-remediation/feedback", dependencies=[Depends(require_admin)])
async def campaign_remediation_feedback_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "feedback": campaign_remediation_feedback(
            int(payload.get("limit", 25)),
            int(payload.get("repeated_threshold", 3)),
        ),
    }


@app.get("/admin/audit-evidence/remediation-candidates", dependencies=[Depends(require_admin)])
def audit_evidence_candidates_get(limit: int = 25):
    return {"ok": True, "candidates": audit_evidence_candidates(limit)}


@app.get("/admin/audit-evidence/remediation-runs", dependencies=[Depends(require_admin)])
def audit_evidence_remediation_runs_get(limit: int = 10):
    return {"ok": True, "runs": latest_audit_evidence_remediation_runs(limit)}


@app.post("/admin/audit-evidence/remediate", dependencies=[Depends(require_admin)])
async def audit_evidence_remediation_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "remediation": audit_evidence_remediation(
            int(payload.get("limit", 25)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.get("/admin/audit-refresh/drain", dependencies=[Depends(require_admin)])
def audit_refresh_drain_get(limit: int = 25):
    return {"ok": True, "drain": audit_refresh_drain_snapshot(limit)}


@app.get("/admin/audit-refresh/drain-runs", dependencies=[Depends(require_admin)])
def audit_refresh_drain_runs_get(limit: int = 10):
    return {"ok": True, "runs": latest_audit_refresh_drain_runs(limit)}


@app.post("/admin/audit-refresh/prioritize", dependencies=[Depends(require_admin)])
async def audit_refresh_prioritize_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "priority": prioritize_audit_refresh_jobs(
            int(payload.get("limit", 25)),
            bool(payload.get("dry_run", True)),
            int(payload.get("priority", 220)),
        ),
    }


@app.get("/admin/audit-refresh/completion-watches", dependencies=[Depends(require_admin)])
def audit_refresh_completion_watches_get(limit: int = 10):
    return {"ok": True, "watches": latest_audit_refresh_completion_watches(limit)}


@app.post("/admin/audit-refresh/completion-watch", dependencies=[Depends(require_admin)])
async def audit_refresh_completion_watch_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "watch": audit_refresh_completion_watch(
            int(payload.get("limit", 25)),
            int(payload.get("min_new_completed", 1)),
            bool(payload.get("dry_run", True)),
            bool(payload.get("force", False)),
        ),
    }


@app.get("/admin/audit-refresh/failures", dependencies=[Depends(require_admin)])
def audit_refresh_failures_get(limit: int = 25):
    return {"ok": True, "failures": audit_refresh_failure_snapshot(limit)}


@app.get("/admin/audit-refresh/failure-runs", dependencies=[Depends(require_admin)])
def audit_refresh_failure_runs_get(limit: int = 10):
    return {"ok": True, "runs": latest_audit_refresh_failure_runs(limit)}


@app.get("/admin/audit-refresh/attachment-repair", dependencies=[Depends(require_admin)])
def audit_refresh_attachment_repair_get(limit: int = 25):
    return {"ok": True, "repair": audit_refresh_attachment_repair_snapshot(limit)}


@app.post("/admin/audit-refresh/attachment-repair", dependencies=[Depends(require_admin)])
async def audit_refresh_attachment_repair_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "repair": repair_audit_refresh_attachments(
            int(payload.get("limit", 25)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.post("/admin/audit-refresh/retry-failures", dependencies=[Depends(require_admin)])
async def audit_refresh_retry_failures_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "retry": retry_failed_audit_refresh_jobs(
            int(payload.get("limit", 10)),
            bool(payload.get("dry_run", True)),
            int(payload.get("priority", 260)),
            bool(payload.get("allow_scanner_fix_retry", False)),
        ),
    }


@app.get("/admin/studio-mail/messages", dependencies=[Depends(require_admin)])
def studio_mail_messages_get(limit: int = 20):
    return {"ok": True, "studio_mail": latest_studio_mail_messages(limit)}


@app.get("/admin/studio-mail/runs", dependencies=[Depends(require_admin)])
def studio_mail_runs_get(limit: int = 10):
    return {"ok": True, "runs": latest_studio_mail_runs(limit)}


@app.post("/admin/studio-mail/ingest", dependencies=[Depends(require_admin)])
async def studio_mail_ingest_run(request: Request):
    payload = await request.json()
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    return {"ok": True, "ingest": ingest_studio_mail_messages(messages, bool(payload.get("dry_run", False)))}


@app.get("/admin/post-scan-campaign-cycles", dependencies=[Depends(require_admin)])
def post_scan_campaign_cycles_get(limit: int = 10):
    return {"ok": True, "cycles": latest_post_scan_campaign_cycles(limit)}


@app.post("/admin/post-scan-campaign-cycle", dependencies=[Depends(require_admin)])
async def post_scan_campaign_cycle_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "cycle": post_scan_campaign_cycle(
            int(payload.get("limit", 100)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.get("/admin/source-campaign-operator", dependencies=[Depends(require_admin)])
def source_campaign_operator_get(limit: int = 25, source_id: str | None = None):
    return {"ok": True, "operator": source_campaign_operator_snapshot(limit, source_id)}


@app.post("/admin/source-campaign-operator/advance", dependencies=[Depends(require_admin)])
async def source_campaign_operator_advance(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "operator": advance_source_to_campaign(
            payload.get("source_id"),
            int(payload.get("limit", 25)),
            bool(payload.get("dry_run", True)),
            bool(payload.get("process_scout", False)),
            bool(payload.get("prepare_campaigns", True)),
        ),
    }


@app.get("/admin/lead-stockpile-health", dependencies=[Depends(require_admin)])
def lead_stockpile_health_get(target_preview_count: int = 50, canary_count: int = 20, limit: int = 100):
    return {
        "ok": True,
        "health": lead_stockpile_health_snapshot(target_preview_count, canary_count, limit),
        "history": latest_lead_stockpile_health_runs(5),
    }


@app.post("/admin/lead-stockpile-health/run", dependencies=[Depends(require_admin)])
async def lead_stockpile_health_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "health": run_lead_stockpile_health(
            int(payload.get("target_preview_count", 50)),
            int(payload.get("canary_count", 20)),
            int(payload.get("limit", 100)),
            bool(payload.get("apply", False)),
        ),
    }


@app.get("/admin/lead-supply-autopilot", dependencies=[Depends(require_admin)])
def lead_supply_autopilot_get(target_preview_count: int = 100, canary_count: int = 20, limit: int = 120):
    return {"ok": True, "supply": lead_supply_autopilot(target_preview_count, canary_count, limit, apply=False)}


@app.post("/admin/lead-supply-autopilot/run", dependencies=[Depends(require_admin)])
async def lead_supply_autopilot_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "supply": lead_supply_autopilot(
            int(payload.get("target_preview_count", 100)),
            int(payload.get("canary_count", 20)),
            int(payload.get("limit", 120)),
            apply=bool(payload.get("apply", False)),
            enrichment_limit=int(payload.get("enrichment_limit", 10)),
            enrichment_seconds=int(payload.get("enrichment_seconds", 90)),
        ),
    }


@app.get("/admin/launch-readiness-scoreboard", dependencies=[Depends(require_admin)])
def launch_readiness_scoreboard_get(limit: int = 25):
    return {"ok": True, "scoreboard": launch_readiness_scoreboard(limit)}


@app.get("/admin/launch-activation", dependencies=[Depends(require_admin)])
def launch_activation_get(limit: int = 25):
    return {"ok": True, "activation": launch_activation_readiness(limit), "history": latest_launch_activation_runs(10)}


@app.post("/admin/launch-activation/prepare", dependencies=[Depends(require_admin)])
async def launch_activation_prepare(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "activation": prepare_launch_activation(
            int(payload.get("limit", 25)),
            payload.get("requested_by", "operator"),
        ),
    }


@app.post("/admin/launch-activation/apply", dependencies=[Depends(require_admin)])
async def launch_activation_apply(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "activation": apply_launch_activation(
            payload.get("confirm_text", ""),
            payload.get("requested_by", "operator"),
            int(payload.get("limit", 25)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.get("/admin/launch-activation/runbook", dependencies=[Depends(require_admin)])
def launch_activation_runbook_get(limit: int = 25):
    return {"ok": True, "runbook": launch_activation_runbook(limit)}


@app.post("/admin/launch-activation/rollback", dependencies=[Depends(require_admin)])
async def launch_activation_rollback(request: Request):
    payload = await request.json()
    return {"ok": True, "rollback": rollback_live_outreach(payload.get("reason", "admin_requested"))}


@app.get("/admin/launch-rehearsal", dependencies=[Depends(require_admin)])
def launch_rehearsal_get(limit: int = 10):
    return {"ok": True, "history": latest_launch_rehearsal_runs(limit)}


@app.post("/admin/launch-rehearsal/run", dependencies=[Depends(require_admin)])
async def launch_rehearsal_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "rehearsal": run_launch_rehearsal(
            int(payload.get("limit", 20)),
            apply_pause=bool(payload.get("apply_pause", False)),
        ),
    }


@app.get("/admin/launch-repair-plan", dependencies=[Depends(require_admin)])
def launch_repair_plan_get(limit: int = 25):
    return {"ok": True, "plan": launch_repair_plan(limit)}


@app.post("/admin/launch-repair-plan/execute", dependencies=[Depends(require_admin)])
async def launch_repair_plan_execute(request: Request):
    payload = await request.json()
    return {"ok": True, "plan": execute_launch_repair_plan(int(payload.get("limit", 25)), bool(payload.get("dry_run", True)))}


@app.post("/admin/launch-repair-cycle", dependencies=[Depends(require_admin)])
async def launch_repair_cycle_run(request: Request):
    payload = await request.json()
    return {"ok": True, "cycle": run_launch_repair_cycle(int(payload.get("limit", 25)), bool(payload.get("execute_safe_auto", False)))}


@app.get("/admin/launch-operating-lane", dependencies=[Depends(require_admin)])
def launch_operating_lane_get(limit: int = 25):
    return {"ok": True, "lane": launch_operating_lane_snapshot(limit)}


@app.post("/admin/launch-operating-lane/advance", dependencies=[Depends(require_admin)])
async def launch_operating_lane_advance(request: Request):
    payload = await request.json()
    return {"ok": True, "lane": advance_launch_operating_lane(int(payload.get("limit", 25)), bool(payload.get("execute_safe_auto", False)))}


@app.post("/admin/mail/clean-window", dependencies=[Depends(require_admin)])
async def mail_clean_window_run(request: Request):
    payload = await request.json()
    return {"ok": True, "check": check_mail_clean_window(int(payload.get("window_hours", 24)))}


@app.post("/admin/mailer/drafts", dependencies=[Depends(require_admin)])
async def mailer_draft_create(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "draft": create_mailer_draft(
            payload.get("template_key", "reply_ask_price"),
            payload.get("category", "ask_price"),
            payload.get("mailbox", "audit@voiddorescue.com"),
            payload.get("recipient_email", ""),
            payload.get("language", "en"),
            payload.get("data") or {},
        ),
    }


@app.post("/admin/source-adapters/domain-list", dependencies=[Depends(require_admin)])
async def source_adapter_domain_list(request: Request):
    payload = await request.json()
    return {"ok": True, "csv": domain_list_to_csv(payload.get("text", ""), payload.get("country", ""), payload.get("niche", ""), payload.get("language", "en"))}


@app.post("/admin/source-adapters/domain-list/source", dependencies=[Depends(require_admin)])
async def source_adapter_domain_list_source(request: Request):
    payload = await request.json()
    return {"ok": True, "result": prepare_scout_source_from_adapter("domain_list", payload)}


@app.post("/admin/source-adapters/directory", dependencies=[Depends(require_admin)])
async def source_adapter_directory(request: Request):
    payload = await request.json()
    return {"ok": True, "csv": directory_rows_to_csv(payload.get("csv", ""), payload.get("country", ""), payload.get("niche", ""), payload.get("language", "en"))}


@app.post("/admin/source-adapters/directory/source", dependencies=[Depends(require_admin)])
async def source_adapter_directory_source(request: Request):
    payload = await request.json()
    return {"ok": True, "result": prepare_scout_source_from_adapter("directory", payload)}


@app.post("/admin/lead-discovery/overpass", dependencies=[Depends(require_admin)])
async def lead_discovery_overpass_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "discovery": overpass_lead_discovery(
            payload.get("country", "US"),
            payload.get("city", "Boise"),
            payload.get("niche", "dentists"),
            payload.get("language", "en"),
            int(payload.get("limit", 50)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.post("/admin/lead-discovery/regional-cycle", dependencies=[Depends(require_admin)])
async def lead_discovery_regional_cycle_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "cycle": regional_lead_discovery_cycle(
            int(payload.get("limit_targets", 2)),
            int(payload.get("per_target_limit", 30)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.get("/admin/lead-discovery/targets", dependencies=[Depends(require_admin)])
def lead_discovery_targets(include_secondary: bool = False):
    return {"ok": True, "plan": lead_discovery_target_plan(include_secondary)}


@app.get("/admin/lead-discovery/quality-aware-regional-targets", dependencies=[Depends(require_admin)])
def lead_discovery_quality_aware_regional_targets(limit_targets: int = 5):
    return {"ok": True, "plan": quality_aware_regional_target_plan(limit_targets)}


@app.get("/admin/lead-discovery/performance-guided-targets", dependencies=[Depends(require_admin)])
def lead_discovery_performance_guided_targets(limit_targets: int = 5):
    return {"ok": True, "plan": performance_guided_target_plan(limit_targets)}


@app.post("/admin/lead-discovery/performance-guided-cycle", dependencies=[Depends(require_admin)])
async def lead_discovery_performance_guided_cycle_run(request: Request):
    payload = await request.json()
    return {
        "ok": True,
        "cycle": performance_guided_regional_discovery_cycle(
            int(payload.get("limit_targets", 3)),
            int(payload.get("per_target_limit", 30)),
            bool(payload.get("dry_run", True)),
        ),
    }


@app.post("/admin/scouts/runs/{run_id}/self-check", dependencies=[Depends(require_admin)])
def scout_self_check(run_id: str):
    return {"ok": True, "check": run_scout_self_check(run_id)}


@app.post("/admin/scouts/runs/{run_id}/provenance", dependencies=[Depends(require_admin)])
def scout_provenance_run(run_id: str):
    return {"ok": True, "provenance": score_scout_provenance(run_id)}


@app.post("/admin/scouts/runs/{run_id}/quality", dependencies=[Depends(require_admin)])
def scout_quality_run(run_id: str):
    return {"ok": True, "quality": run_scout_quality_gate(run_id)}


@app.get("/admin/scouts/runs/{run_id}/quality", dependencies=[Depends(require_admin)])
def scout_quality_get(run_id: str):
    return {"ok": True, "quality": latest_scout_quality_gate(run_id)}


@app.post("/admin/audits/{audit_id}/strength", dependencies=[Depends(require_admin)])
def audit_strength_run(audit_id: str):
    return {"ok": True, "strength": score_audit_strength(audit_id)}


@app.post("/admin/language/no-ai-gate", dependencies=[Depends(require_admin)])
async def language_gate_run(request: Request):
    payload = await request.json()
    samples = payload.get("samples")
    return {"ok": True, "gate": check_no_ai_public_language(samples, payload.get("scope", "manual"))}


@app.post("/admin/mail/throttle-check", dependencies=[Depends(require_admin)])
async def mail_throttle_check(request: Request):
    payload = await request.json()
    return {"ok": True, "throttle": throttle_decision(payload.get("scope", "global"), payload.get("scope_key", "diagnostic"), int(payload.get("min_delay_seconds", 600)))}


@app.post("/email-templates/render", dependencies=[Depends(require_admin)])
async def email_template_render(request: Request):
    payload = await request.json()
    rendered = render_email_template(payload.get("template_key", "first_audit_notice"), payload.get("language", "en"), payload.get("data") or {})
    return {"ok": True, "rendered": rendered, "qa": qa_email_template(rendered)}


@app.get("/email-templates/samples", dependencies=[Depends(require_admin)])
def email_template_samples():
    samples = render_all_samples()
    return {"ok": True, "count": len(samples), "all_pass": all(item["qa"]["passed"] for item in samples), "samples": samples}
