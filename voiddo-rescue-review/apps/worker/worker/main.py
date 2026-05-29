import json
import os
import time
from datetime import datetime, timezone

from .inbox_engine import poll_all
from .outreach_transport import process_outreach_queue
from .pipeline import process_scanner_jobs
from .scouts import process_one_scout_run
from .studio_mail_monitor import poll_studio_mailbox


def log(event: str, **payload):
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "event": event, **payload}, sort_keys=True), flush=True)


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
                except Exception as exc:
                    log("outreach_queue_failed", error=type(exc).__name__)
        time.sleep(tick_seconds)


if __name__ == "__main__":
    main()
