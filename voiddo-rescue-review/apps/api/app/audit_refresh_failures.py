from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import json_safe
from .scanner_ops import TRANSIENT_SCANNER_ERRORS


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _retry_count(value: Any) -> int:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = {}
    if not isinstance(value, dict):
        return 0
    try:
        return int(value.get("scanner_retry_count") or 0)
    except (TypeError, ValueError):
        return 0


def _scanner_fix_retry_count(value: Any) -> int:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = {}
    if not isinstance(value, dict):
        return 0
    try:
        return int(value.get("scanner_fix_retry_count") or 0)
    except (TypeError, ValueError):
        return 0


def _failed_jobs(limit: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, audit_id, status, priority, error, result_json, completed_at, updated_at
        FROM scanner_jobs
        WHERE result_json->>'reason' = 'audit_evidence_remediation'
          AND status = 'failed'
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 25), 100)),),
    )
    jobs = []
    for row in rows:
        retry_count = _retry_count(row.get("result_json"))
        fix_retry_count = _scanner_fix_retry_count(row.get("result_json"))
        retryable = str(row.get("error") or "") in TRANSIENT_SCANNER_ERRORS and retry_count < 1
        scanner_fix_retryable = (
            str(row.get("error") or "") in TRANSIENT_SCANNER_ERRORS
            and retry_count >= 1
            and fix_retry_count < 1
        )
        jobs.append(
            {
                "job_id": str(row["id"]),
                "audit_id": str(row["audit_id"]) if row.get("audit_id") else None,
                "priority": int(row["priority"] or 0),
                "error": row.get("error") or "unknown",
                "retry_count": retry_count,
                "scanner_fix_retry_count": fix_retry_count,
                "retryable": retryable,
                "scanner_fix_retryable": scanner_fix_retryable,
                "exhausted": retry_count >= 1,
                "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
            }
        )
    return jobs


def audit_refresh_failure_snapshot(limit: int = 25) -> dict[str, Any]:
    jobs = _failed_jobs(limit)
    retryable = [job for job in jobs if job["retryable"]]
    scanner_fix_retryable = [job for job in jobs if job["scanner_fix_retryable"]]
    exhausted = [job for job in jobs if job["exhausted"] or not job["retryable"]]
    return json_safe(
        {
            "status": "ready",
            "failed_count": len(jobs),
            "retryable_count": len(retryable),
            "scanner_fix_retryable_count": len(scanner_fix_retryable),
            "exhausted_count": len(exhausted),
            "errors": sorted({job["error"] for job in jobs}),
            "jobs": jobs,
            **SAFE_FLAGS,
        }
    )


def retry_failed_audit_refresh_jobs(
    limit: int = 10,
    dry_run: bool = True,
    priority: int = 260,
    allow_scanner_fix_retry: bool = False,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 10), 25))
    safe_priority = max(100, min(int(priority or 260), 300))
    snapshot = audit_refresh_failure_snapshot(safe_limit * 2)
    candidates = [job for job in snapshot["jobs"] if job["retryable"]][:safe_limit]
    if allow_scanner_fix_retry and len(candidates) < safe_limit:
        remaining = safe_limit - len(candidates)
        candidates.extend([job for job in snapshot["jobs"] if job["scanner_fix_retryable"]][:remaining])
    requeued: list[dict[str, Any]] = []
    if not dry_run:
        for job in candidates:
            current = fetch_all("SELECT result_json FROM scanner_jobs WHERE id = %s", (job["job_id"],))
            meta = current[0]["result_json"] if current and isinstance(current[0].get("result_json"), dict) else {}
            merged = dict(meta or {})
            if job.get("scanner_fix_retryable") and not job.get("retryable"):
                retry_count = _retry_count(meta)
                fix_retry_count = _scanner_fix_retry_count(meta) + 1
                scanner_retry_reason = "audit_evidence_remediation_after_scanner_navigation_fix"
            else:
                retry_count = _retry_count(meta) + 1
                fix_retry_count = _scanner_fix_retry_count(meta)
                scanner_retry_reason = "audit_evidence_remediation_transient_failure"
            merged.update(
                {
                    "scanner_retry_count": retry_count,
                    "scanner_fix_retry_count": fix_retry_count,
                    "scanner_retry_reason": scanner_retry_reason,
                    "scanner_last_error": job["error"],
                    **SAFE_FLAGS,
                }
            )
            updated = execute(
                """
                UPDATE scanner_jobs
                SET status = 'queued',
                    priority = GREATEST(priority, %s),
                    error = NULL,
                    started_at = NULL,
                    completed_at = NULL,
                    updated_at = now(),
                    result_json = %s
                WHERE id = %s
                  AND status = 'failed'
                RETURNING id, audit_id, priority, status
                """,
                (safe_priority, Jsonb(merged), job["job_id"]),
            )
            if updated:
                requeued.append(
                    {
                        "job_id": str(updated["id"]),
                        "audit_id": str(updated["audit_id"]) if updated.get("audit_id") else None,
                        "priority": int(updated["priority"] or 0),
                        "status": updated["status"],
                    }
                )

    result = json_safe(
        {
            "status": "dry_run" if dry_run else ("requeued" if requeued else "idle_no_retryable_failures"),
            "dry_run": dry_run,
            "allow_scanner_fix_retry": allow_scanner_fix_retry,
            "failed_count": snapshot["failed_count"],
            "retryable_count": len(candidates),
            "requeued_count": 0 if dry_run else len(requeued),
            "exhausted_count": snapshot["exhausted_count"],
            "scanner_fix_retryable_count": snapshot["scanner_fix_retryable_count"],
            "candidate_errors": sorted({job["error"] for job in candidates}),
            "requeued": requeued,
            **SAFE_FLAGS,
        }
    )
    row = execute(
        """
        INSERT INTO audit_refresh_failure_runs(
          status, dry_run, failed_count, retryable_count, requeued_count, exhausted_count,
          result_json, send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (
            result["status"],
            dry_run,
            result["failed_count"],
            result["retryable_count"],
            result["requeued_count"],
            result["exhausted_count"],
            Jsonb(result),
        ),
    )
    result["run_id"] = str(row["id"])
    result["created_at"] = row["created_at"].isoformat()
    return result


def latest_audit_refresh_failure_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, dry_run, failed_count, retryable_count, requeued_count,
               exhausted_count, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM audit_refresh_failure_runs
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
                "failed_count": int(row["failed_count"] or 0),
                "retryable_count": int(row["retryable_count"] or 0),
                "requeued_count": int(row["requeued_count"] or 0),
                "exhausted_count": int(row["exhausted_count"] or 0),
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
