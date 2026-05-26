from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .billing import checkout_config_status
from .codex_tasks import create_task
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
    store_owner_command,
)
from .outreach import outreach_allowed, render_template
from .scanner import deterministic_safe_scan
from .security import verify_paddle_signature
from .visual_quality import check_visual_publish_gate

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
        "scanning_paused": settings.scanning_paused,
    }


@app.get("/admin/metrics")
def admin_metrics():
    return {"ok": True, **admin_metrics_from_db()}


@app.post("/scanner/scan")
def scan(request: ScanRequest):
    if settings.global_kill_switch:
        return {"ok": False, "status": "blocked", "reason": "global_kill_switch"}
    if settings.scanning_paused and not request.dry_run:
        return {"ok": False, "status": "blocked", "reason": "scanning_paused"}
    result = deterministic_safe_scan(str(request.url), request.business_name)
    return {"ok": True, "result": result.model_dump()}


@app.post("/scanner/jobs")
def scanner_job_create(request: ScanRequest):
    if settings.global_kill_switch:
        return {"ok": False, "status": "blocked", "reason": "global_kill_switch"}
    job = create_scanner_job(str(request.url), request.business_name, request.dry_run)
    return {"ok": True, "job": job, "processing_paused": settings.scanning_paused}


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


@app.post("/owner/commands")
async def owner_commands(request: Request):
    payload = await request.json()
    return {"ok": True, "command": store_owner_command(payload)}


@app.get("/billing/config")
def billing_config():
    return {"ok": True, **checkout_config_status(settings)}


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


@app.post("/qa/visual/run")
async def visual_qa_run(request: Request):
    payload = await request.json()
    result = record_visual_qa(
        payload.get("agent", "app_visual_agent"),
        payload.get("target_url", settings.app_base_url),
        payload.get("html", ""),
    )
    return {"ok": True, "run": result}


@app.post("/qa/mail/run")
def mail_qa_run():
    return {"ok": True, "run": run_mail_qa()}


@app.post("/warmup/prepare")
async def warmup_prepare(request: Request):
    payload = await request.json()
    return {"ok": True, "warmup": prepare_warmup(int(payload.get("recipient_pool_count", 0)), int(payload.get("day_number", 1)))}


@app.post("/leads/batches/import")
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


@app.post("/outreach/send")
async def outreach_send(request: Request):
    await request.json()
    if not settings.first_live_send_flag or settings.outreach_dry_run or settings.outreach_paused:
        return {"ok": False, "status": "blocked", "reason": "live_outreach_not_approved"}
    return {"ok": False, "status": "blocked", "reason": "send_transport_not_enabled_in_mvp"}


@app.post("/codex-tasks")
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
