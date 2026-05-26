from __future__ import annotations

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .billing import checkout_config_status, hosted_checkout_url, PRODUCTS
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


@app.get("/checkout/{product_key}")
def checkout_redirect(product_key: str, request: Request):
    audit_slug = request.query_params.get("audit", "")
    email = request.query_params.get("email", "")
    if product_key not in PRODUCTS:
        return Response(status_code=404, content="unknown product")
    target = hosted_checkout_url(settings, product_key, audit_slug, email)
    if not target:
        return Response(
            status_code=503,
            content="checkout_not_configured",
            headers={"X-Voiddo-Rescue-Gate": "paddle_hosted_checkout_missing"},
        )
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
