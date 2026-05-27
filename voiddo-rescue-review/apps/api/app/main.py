from __future__ import annotations

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

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
    prepare_outreach_preview,
    queue_outreach_preview,
    store_owner_command,
    transport_gate_status,
    effective_pause_state,
)
from .outreach import outreach_allowed, render_template
from .scanner import deterministic_safe_scan
from .security import verify_paddle_signature
from .visual_quality import check_visual_publish_gate
from .autonomous_agents import run_agent, run_daily_loop
from .email_templates import render_email_template, qa_email_template, render_all_samples
from .lead_scoring import score_lead
from .audit_strength import score_audit_strength
from .mailer_throttle import throttle_decision
from .campaign_economics import run_campaign_economics_check
from .campaign_control import campaign_readiness_snapshot
from .clean_window_recheck import clean_window_recheck, clean_window_recheck_summary, post_window_recheck_scheduler, post_window_recheck_summary
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
from .customer_journey import customer_journey_snapshot
from .customer_mail_simulation import run_customer_mail_simulation
from .customer_access import customer_dashboard_by_token, ensure_customer_access_token
from .monitoring import ensure_monitoring_target, process_due_monitoring_targets, run_monitoring_check
from .language_gate import check_no_ai_public_language
from .quality_plugins import latest_quality_summary, quality_plugin_manifest, record_quality_plugin_run
from .revenue_simulation import run_synthetic_lead_simulation
from .source_adapters import directory_rows_to_csv, domain_list_to_csv
from .scout_quality import cleanup_scout_campaign_quality_history, latest_scout_campaign_quality_history, latest_scout_quality_gate, run_scout_quality_gate, run_scout_self_check, score_scout_provenance, scout_campaign_quality_regression_guard, scout_campaign_quality_summary
from .scouts import create_campaign, create_scout_run, create_scout_source, get_campaign, get_scout_run, latest_scout_source_readiness, prepare_campaign, prepare_campaign_gated, process_scout_run, process_scout_run_gated, run_scout_source_readiness, scout_campaign_expansion_gate, scout_source_readiness_gate, scout_source_readiness_summary
from .warmup_planner import apply_provider_spacing_when_safe, plan_provider_spaced_warmup, rollback_latest_spacing_repair
from .self_operating import (
    create_self_fix_task,
    queue_self_build,
    record_learning,
    run_self_audit,
    self_operating_summary,
)

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
    return {"ok": True, "status": "suppressed", "token": token, "dry_run": True}


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
    campaign = get_campaign(campaign_id)
    if not campaign:
        return Response(status_code=404, content="campaign not found")
    return {"ok": True, "campaign": campaign}


@app.post("/admin/leads/{lead_id}/score", dependencies=[Depends(require_admin)])
async def lead_score_create(lead_id: str, request: Request):
    payload = await request.json()
    return {"ok": True, "score": score_lead(lead_id, payload.get("audit_id"))}


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


@app.post("/admin/replies/action-plan", dependencies=[Depends(require_admin)])
async def reply_action_plan_create(request: Request):
    payload = await request.json()
    return {"ok": True, "plan": plan_reply_action(payload.get("subject", ""), payload.get("body", ""), payload.get("mailbox", "support@voiddorescue.com"))}


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


@app.post("/admin/source-adapters/directory", dependencies=[Depends(require_admin)])
async def source_adapter_directory(request: Request):
    payload = await request.json()
    return {"ok": True, "csv": directory_rows_to_csv(payload.get("csv", ""), payload.get("country", ""), payload.get("niche", ""), payload.get("language", "en"))}


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
