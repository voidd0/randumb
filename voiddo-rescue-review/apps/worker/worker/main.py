import json
import os
import time
from datetime import datetime, timezone
from urllib import error, request

from .inbox_engine import poll_all
from .outreach_transport import process_outreach_queue
from .pipeline import process_scanner_jobs
from .scouts import process_one_scout_run
from .studio_mail_monitor import poll_studio_mailbox


def log(event: str, **payload):
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "event": event, **payload}, sort_keys=True), flush=True)


def run_post_send_observer_after_outreach(sent_count: int) -> dict:
    if sent_count <= 0:
        return {"attempted": False, "reason": "no_sent_messages"}
    token = os.environ.get("ADMIN_AUTH_TOKEN", "")
    if not token:
        return {"attempted": False, "reason": "admin_auth_token_missing"}
    base_url = (
        os.environ.get("RESCUE_API_INTERNAL_URL")
        or os.environ.get("API_INTERNAL_URL")
        or os.environ.get("API_INTERNAL_BASE_URL")
        or "http://api:8080"
    ).rstrip("/")
    payload = json.dumps({"window_hours": 24, "apply_pause": True}).encode("utf-8")
    req = request.Request(
        f"{base_url}/admin/outreach/post-send-observer/run",
        data=payload,
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
        method="POST",
    )
    timeout = max(5, min(int(os.environ.get("POST_SEND_OBSERVER_TIMEOUT_SECONDS", "30") or "30"), 120))
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except error.HTTPError as exc:
        return {"attempted": True, "ok": False, "reason": "http_error", "status": exc.code}
    except Exception as exc:
        return {"attempted": True, "ok": False, "reason": type(exc).__name__}
    observer = body.get("observer") or {}
    result = observer.get("result") or {}
    return {
        "attempted": True,
        "ok": bool(body.get("ok")),
        "decision": result.get("decision") or observer.get("decision"),
        "pause_outreach_applied": bool(result.get("pause_outreach_applied") or observer.get("pause_outreach_applied")),
        "blocker_count": len(result.get("blockers") or observer.get("blockers") or []),
    }


def main():
    tick_seconds = max(5, min(int(os.environ.get("WORKER_TICK_SECONDS", "20") or "20"), 300))
    log("worker_started", dry_run=os.environ.get("OUTREACH_DRY_RUN", "true"), tick_seconds=tick_seconds)
    while True:
        if os.environ.get("GLOBAL_KILL_SWITCH", "false").lower() == "true":
            log("worker_paused", reason="global_kill_switch")
        else:
            log("worker_tick", scanning_paused=os.environ.get("SCANNING_PAUSED", "true"))
            if os.environ.get("SCANNING_PAUSED", "true").lower() != "true":
                scout_result = process_one_scout_run()
                if scout_result.get("processed"):
                    log("scout_run_processed", **scout_result)
                jobs_per_tick = max(1, min(int(os.environ.get("SCANNER_JOBS_PER_TICK", "1") or "1"), 5))
                result = process_scanner_jobs(jobs_per_tick)
                if result.get("processed"):
                    log("scanner_jobs_processed", **result)
            if os.environ.get("INBOX_WORKER_ENABLED", "false").lower() == "true":
                try:
                    messages = poll_all()
                    log("inbox_poll_complete", messages=len(messages), auto_replies_paused=os.environ.get("AUTO_REPLIES_PAUSED", "true"))
                except Exception as exc:
                    log("inbox_poll_failed", error=type(exc).__name__)
            if os.environ.get("STUDIO_MAIL_MONITOR_ENABLED", "false").lower() == "true":
                try:
                    result = poll_studio_mailbox(int(os.environ.get("STUDIO_MAIL_MESSAGES_PER_TICK", "20") or "20"))
                    if result.get("scanned") or result.get("error"):
                        log(
                            "studio_mail_poll_complete",
                            scanned=result.get("scanned", 0),
                            stored=result.get("stored", 0),
                            owner_commands=result.get("owner_commands", 0),
                            marked_seen=result.get("marked_seen", 0),
                            error=result.get("error", ""),
                        )
                except Exception as exc:
                    log("studio_mail_poll_failed", error=type(exc).__name__)
            if os.environ.get("OUTREACH_WORKER_ENABLED", "false").lower() == "true":
                try:
                    result = process_outreach_queue(int(os.environ.get("OUTREACH_MESSAGES_PER_TICK", "1") or "1"))
                    if result.get("processed"):
                        log("outreach_queue_processed", **result)
                    if int(result.get("sent") or 0) > 0:
                        observer = run_post_send_observer_after_outreach(int(result.get("sent") or 0))
                        log("outreach_post_send_observer_complete", **observer)
                except Exception as exc:
                    log("outreach_queue_failed", error=type(exc).__name__)
        time.sleep(tick_seconds)


if __name__ == "__main__":
    main()
