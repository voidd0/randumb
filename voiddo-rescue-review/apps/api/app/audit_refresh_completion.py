from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .audit_strength import score_audit_strength
from .campaign_preflight import campaign_preflight
from .db import execute, fetch_all, fetch_one
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _counts() -> dict[str, int]:
    rows = fetch_all(
        """
        SELECT status, count(*) AS count
        FROM scanner_jobs
        WHERE COALESCE(result_json->>'reason', result_json->'job_meta'->>'reason') = 'audit_evidence_remediation'
        GROUP BY status
        """
    )
    result = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
    for row in rows:
        status = str(row["status"] or "")
        if status in result:
            result[status] = int(row["count"] or 0)
    return result


def _latest_processed_completed_count() -> int:
    row = fetch_one(
        """
        SELECT completed_count
        FROM audit_refresh_completion_watches
        WHERE dry_run = false
          AND status IN ('refreshed_no_send', 'force_refreshed_no_send', 'refresh_failed_or_blocked')
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    return int(row["completed_count"] or 0) if row else 0


def _completed_jobs(limit: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, audit_id, status, priority, completed_at
        FROM scanner_jobs
        WHERE COALESCE(result_json->>'reason', result_json->'job_meta'->>'reason') = 'audit_evidence_remediation'
          AND status = 'completed'
          AND audit_id IS NOT NULL
        ORDER BY completed_at DESC NULLS LAST, updated_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 25), 100)),),
    )
    return [
        {
            "job_id": str(row["id"]),
            "audit_id": str(row["audit_id"]),
            "status": row["status"],
            "priority": int(row["priority"] or 0),
            "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
        }
        for row in rows
    ]


def _campaign_ids_for_audits(audit_ids: list[str]) -> list[str]:
    if not audit_ids:
        return []
    rows = fetch_all(
        """
        SELECT DISTINCT campaign_id
        FROM campaign_leads
        WHERE audit_id = ANY(%s::uuid[])
          AND campaign_id IS NOT NULL
        ORDER BY campaign_id
        """,
        (audit_ids,),
    )
    return [str(row["campaign_id"]) for row in rows]


def audit_refresh_completion_watch(limit: int = 25, min_new_completed: int = 1, dry_run: bool = True, force: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    threshold = max(1, min(int(min_new_completed or 1), safe_limit))
    counts = _counts()
    previous_completed = _latest_processed_completed_count()
    new_completed = max(0, counts["completed"] - previous_completed)
    jobs = _completed_jobs(safe_limit)
    should_trigger = (new_completed >= threshold) or (force and bool(jobs))
    status = "dry_run_ready" if should_trigger else "idle_waiting_for_completions"
    if counts["completed"] <= previous_completed:
        status = "idle_no_new_completions"
    if counts["completed"] == 0:
        status = "idle_no_completed_refresh_jobs"
    if force and jobs:
        status = "force_ready"

    rescored: list[dict[str, Any]] = []
    preflights: list[dict[str, Any]] = []
    if should_trigger and not dry_run:
        audit_ids = []
        batch_size = safe_limit if force else (new_completed or safe_limit)
        for job in jobs[:batch_size]:
            if job["audit_id"] not in audit_ids:
                audit_ids.append(job["audit_id"])
        for audit_id in audit_ids:
            score = score_audit_strength(audit_id)
            rescored.append(
                {
                    "audit_id": audit_id,
                    "final_score": int(score.get("final_score") or 0),
                    "issue_count": len(score.get("issues_json") or []),
                }
            )
        for campaign_id in _campaign_ids_for_audits(audit_ids):
            preflight = campaign_preflight(campaign_id, 20)
            preflights.append(
                {
                    "campaign_id": campaign_id,
                    "decision": preflight.get("decision"),
                    "checked_count": int(preflight.get("checked_count") or 0),
                    "ready_count": int(preflight.get("ready_count") or 0),
                    "blocker_count": int(preflight.get("blocker_count") or 0),
                }
            )
        status = "refreshed_no_send"
        if force:
            status = "force_refreshed_no_send"
        if any(item.get("decision") not in {"PASS_NO_SEND_PREFLIGHT", "FAIL_BLOCK_LAUNCH"} for item in preflights):
            status = "refresh_failed_or_blocked"

    result = json_safe(
        {
            "status": status,
            "dry_run": dry_run,
            "force": force,
            "tracked_count": len(jobs),
            "queued_count": counts["queued"],
            "running_count": counts["running"],
            "completed_count": counts["completed"],
            "failed_count": counts["failed"],
            "previous_completed_count": previous_completed,
            "new_completed_count": new_completed,
            "min_new_completed": threshold,
            "trigger_ready": should_trigger,
            "jobs": jobs,
            "rescored_audits": rescored,
            "preflight_runs": preflights,
            **SAFE_FLAGS,
        }
    )
    row = execute(
        """
        INSERT INTO audit_refresh_completion_watches(
          status, dry_run, tracked_count, queued_count, running_count, completed_count,
          failed_count, new_completed_count, rescored_audit_count, preflight_run_count,
          result_json, send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                false, false, false, false, false)
        RETURNING id, created_at
        """,
        (
            result["status"],
            dry_run,
            result["tracked_count"],
            result["queued_count"],
            result["running_count"],
            result["completed_count"],
            result["failed_count"],
            result["new_completed_count"],
            len(rescored),
            len(preflights),
            Jsonb(result),
        ),
    )
    result["watch_id"] = str(row["id"])
    result["created_at"] = row["created_at"].isoformat()
    return result


def latest_audit_refresh_completion_watches(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, dry_run, tracked_count, queued_count, running_count,
               completed_count, failed_count, new_completed_count,
               rescored_audit_count, preflight_run_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM audit_refresh_completion_watches
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
                "tracked_count": int(row["tracked_count"] or 0),
                "queued_count": int(row["queued_count"] or 0),
                "running_count": int(row["running_count"] or 0),
                "completed_count": int(row["completed_count"] or 0),
                "failed_count": int(row["failed_count"] or 0),
                "new_completed_count": int(row["new_completed_count"] or 0),
                "rescored_audit_count": int(row["rescored_audit_count"] or 0),
                "preflight_run_count": int(row["preflight_run_count"] or 0),
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
