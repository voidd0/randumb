from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def audit_refresh_drain_snapshot(limit: int = 25) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, audit_id, url, business_name, status, priority, error, queued_at, updated_at, completed_at
        FROM scanner_jobs
        WHERE result_json->>'reason' = 'audit_evidence_remediation'
        ORDER BY
          CASE status WHEN 'queued' THEN 0 WHEN 'running' THEN 1 WHEN 'failed' THEN 2 ELSE 3 END,
          priority DESC,
          queued_at
        LIMIT %s
        """,
        (max(1, min(int(limit or 25), 100)),),
    )
    counts = {row["status"]: int(row["count"]) for row in fetch_all(
        """
        SELECT status, count(*) AS count
        FROM scanner_jobs
        WHERE result_json->>'reason' = 'audit_evidence_remediation'
        GROUP BY status
        """
    )}
    return json_safe(
        {
            "status": "ready",
            "queued_count": counts.get("queued", 0),
            "running_count": counts.get("running", 0),
            "completed_count": counts.get("completed", 0),
            "failed_count": counts.get("failed", 0),
            "jobs": [
                {
                    "id": str(row["id"]),
                    "audit_id": str(row["audit_id"]) if row.get("audit_id") else None,
                    "status": row["status"],
                    "priority": int(row["priority"] or 0),
                    "queued_at": row["queued_at"].isoformat() if row.get("queued_at") else None,
                    "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
                    "has_error": bool(row.get("error")),
                }
                for row in rows
            ],
            **SAFE_FLAGS,
        }
    )


def prioritize_audit_refresh_jobs(limit: int = 25, dry_run: bool = True, priority: int = 220) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    safe_priority = max(100, min(int(priority or 220), 300))
    snapshot = audit_refresh_drain_snapshot(safe_limit)
    candidates = [job for job in snapshot["jobs"] if job["status"] == "queued" and int(job["priority"] or 0) < safe_priority]
    prioritized: list[dict[str, Any]] = []
    if not dry_run:
        for job in candidates[:safe_limit]:
            row = execute(
                """
                UPDATE scanner_jobs
                SET priority = %s,
                    result_json = result_json || %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                RETURNING id, audit_id, status, priority
                """,
                (
                    safe_priority,
                    Jsonb({"audit_refresh_drain_prioritized": True, **SAFE_FLAGS}),
                    job["id"],
                ),
            )
            prioritized.append({"id": str(row["id"]), "audit_id": str(row["audit_id"]) if row.get("audit_id") else None, "status": row["status"], "priority": int(row["priority"])})
    result = json_safe(
        {
            "status": "dry_run" if dry_run else "prioritized",
            "queued_count": snapshot["queued_count"],
            "completed_count": snapshot["completed_count"],
            "failed_count": snapshot["failed_count"],
            "candidate_count": len(candidates),
            "prioritized_count": 0 if dry_run else len(prioritized),
            "prioritized": prioritized,
            **SAFE_FLAGS,
        }
    )
    saved = execute(
        """
        INSERT INTO audit_refresh_drain_runs(
          status, queued_count, prioritized_count, completed_count, failed_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (result["status"], result["queued_count"], result["prioritized_count"], result["completed_count"], result["failed_count"], Jsonb(result)),
    )
    result["run_id"] = str(saved["id"])
    result["created_at"] = saved["created_at"].isoformat()
    return result


def latest_audit_refresh_drain_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, queued_count, prioritized_count, completed_count, failed_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM audit_refresh_drain_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 100)),),
    )
    return json_safe(
        {
            "count": len(rows),
            "history": [
                {
                    "id": str(row["id"]),
                    "status": row["status"],
                    "queued_count": int(row["queued_count"] or 0),
                    "prioritized_count": int(row["prioritized_count"] or 0),
                    "completed_count": int(row["completed_count"] or 0),
                    "failed_count": int(row["failed_count"] or 0),
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
    )
