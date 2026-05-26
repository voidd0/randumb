import json
import os
import time
from datetime import datetime, timezone

from .inbox_engine import poll_all
from .pipeline import process_one_scanner_job
from .scouts import process_one_scout_run


def log(event: str, **payload):
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "event": event, **payload}, sort_keys=True), flush=True)


def main():
    log("worker_started", dry_run=os.environ.get("OUTREACH_DRY_RUN", "true"))
    while True:
        if os.environ.get("GLOBAL_KILL_SWITCH", "false").lower() == "true":
            log("worker_paused", reason="global_kill_switch")
        else:
            log("worker_tick", scanning_paused=os.environ.get("SCANNING_PAUSED", "true"))
            if os.environ.get("SCANNING_PAUSED", "true").lower() != "true":
                scout_result = process_one_scout_run()
                if scout_result.get("processed"):
                    log("scout_run_processed", **scout_result)
                result = process_one_scanner_job()
                if result.get("processed"):
                    log("scanner_job_processed", **result)
            if os.environ.get("INBOX_WORKER_ENABLED", "false").lower() == "true":
                try:
                    messages = poll_all()
                    log("inbox_poll_complete", messages=len(messages), auto_replies_paused=os.environ.get("AUTO_REPLIES_PAUSED", "true"))
                except Exception as exc:
                    log("inbox_poll_failed", error=type(exc).__name__)
        time.sleep(60)


if __name__ == "__main__":
    main()
