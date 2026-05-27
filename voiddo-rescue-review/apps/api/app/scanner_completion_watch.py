from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import json_safe
from .post_scan_campaign_cycle import post_scan_campaign_cycle


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _latest_priority_run() -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT id, result_json, prioritized_count, created_at
        FROM scanner_priority_runs
        WHERE dry_run = false
          AND prioritized_count > 0
          AND send_mail = false
          AND smtp_called = false
          AND live_outreach_allowed = false
        ORDER BY created_at DESC
        LIMIT 1
        """
    )


def _job_ids_from_priority_run(row: dict[str, Any]) -> list[str]:
    result = row.get("result_json") if isinstance(row.get("result_json"), dict) else {}
    raw_items = result.get("prioritized") if isinstance(result.get("prioritized"), list) else []
    job_ids: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        job_id = item.get("job_id")
        if job_id and job_id not in job_ids:
            job_ids.append(str(job_id))
    return job_ids


def _status_counts(job_ids: list[str]) -> dict[str, int]:
    if not job_ids:
        return {"queued": 0, "running": 0, "completed": 0, "failed": 0}
    rows = fetch_all(
        """
        SELECT status, count(*) AS count
        FROM scanner_jobs
        WHERE id = ANY(%s::uuid[])
        GROUP BY status
        """,
        (job_ids,),
    )
    counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
    for row in rows:
        status = str(row["status"] or "")
        if status in counts:
            counts[status] = int(row["count"] or 0)
    return counts


def _last_watch(priority_run_id: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT id, status, completed_count, triggered_cycle_id, created_at
        FROM scanner_completion_watches
        WHERE priority_run_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (priority_run_id,),
    )


def scanner_completion_watch(limit: int = 100, min_new_completed: int = 1, dry_run: bool = True) -> dict[str, Any]:
    priority_run = _latest_priority_run()
    if not priority_run:
        result = {"status": "idle_no_priority_run", "dry_run": dry_run, "reason": "no_non_dry_priority_run", **SAFE_FLAGS}
        row = execute(
            """
            INSERT INTO scanner_completion_watches(status, dry_run, result_json)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (result["status"], dry_run, Jsonb(result)),
        )
        result["watch_id"] = str(row["id"])
        result["created_at"] = row["created_at"].isoformat()
        return result

    safe_limit = max(1, min(int(limit or 100), 250))
    threshold = max(1, min(int(min_new_completed or 1), safe_limit))
    priority_run_id = str(priority_run["id"])
    tracked_job_ids = _job_ids_from_priority_run(priority_run)[:safe_limit]
    counts = _status_counts(tracked_job_ids)
    previous = _last_watch(priority_run_id)
    previous_completed = int(previous["completed_count"] or 0) if previous else 0
    new_completed = max(0, counts["completed"] - previous_completed)
    should_trigger = new_completed >= threshold

    cycle: dict[str, Any] | None = None
    status = "dry_run_ready" if should_trigger else "idle_waiting_for_completions"
    if previous and counts["completed"] <= previous_completed:
        status = "idle_no_new_completions"
    if not tracked_job_ids:
        status = "idle_no_tracked_jobs"
    if should_trigger and not dry_run:
        cycle = post_scan_campaign_cycle(safe_limit, dry_run=False)
        status = "refreshed_no_send" if cycle.get("status") == "completed_no_send" else "refresh_failed_or_blocked"

    result = json_safe(
        {
            "status": status,
            "dry_run": dry_run,
            "priority_run_id": priority_run_id,
            "tracked_count": len(tracked_job_ids),
            "queued_count": counts["queued"],
            "running_count": counts["running"],
            "completed_count": counts["completed"],
            "failed_count": counts["failed"],
            "previous_completed_count": previous_completed,
            "new_completed_count": new_completed,
            "min_new_completed": threshold,
            "trigger_ready": should_trigger,
            "cycle": cycle,
            **SAFE_FLAGS,
        }
    )
    row = execute(
        """
        INSERT INTO scanner_completion_watches(
          status, dry_run, priority_run_id, tracked_count, queued_count, running_count,
          completed_count, failed_count, triggered_cycle_id, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (
            result["status"],
            dry_run,
            priority_run_id,
            result["tracked_count"],
            result["queued_count"],
            result["running_count"],
            result["completed_count"],
            result["failed_count"],
            (cycle or {}).get("cycle_id"),
            Jsonb(result),
        ),
    )
    result["watch_id"] = str(row["id"])
    result["created_at"] = row["created_at"].isoformat()
    return result


def latest_scanner_completion_watches(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, dry_run, priority_run_id, tracked_count, queued_count,
               running_count, completed_count, failed_count, triggered_cycle_id,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM scanner_completion_watches
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 100)),),
    )
    return {
        "count": len(rows),
        "history": [
            {
                "id": str(row["id"]),
                "status": row["status"],
                "dry_run": bool(row["dry_run"]),
                "priority_run_id": str(row["priority_run_id"]) if row.get("priority_run_id") else None,
                "tracked_count": int(row["tracked_count"] or 0),
                "queued_count": int(row["queued_count"] or 0),
                "running_count": int(row["running_count"] or 0),
                "completed_count": int(row["completed_count"] or 0),
                "failed_count": int(row["failed_count"] or 0),
                "triggered_cycle_id": str(row["triggered_cycle_id"]) if row.get("triggered_cycle_id") else None,
                "send_mail": bool(row["send_mail"]),
                "smtp_called": bool(row["smtp_called"]),
                "live_outreach_allowed": bool(row["live_outreach_allowed"]),
                "raw_recipient_addresses_included": bool(row["raw_recipient_addresses_included"]),
                "secrets_included": bool(row["secrets_included"]),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ],
        **SAFE_FLAGS,
    }
