from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import json_safe


TRANSIENT_SCANNER_ERRORS = {"TimeoutError", "Error", "PlaywrightTimeoutError", "NetworkError"}


def _scanner_counts() -> dict[str, int]:
    rows = fetch_all("SELECT status, count(*) AS count FROM scanner_jobs GROUP BY status")
    return {str(row["status"]): int(row["count"] or 0) for row in rows}


def _recent_errors(hours: int = 24) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT error, count(*) AS count
        FROM scanner_jobs
        WHERE status = 'failed'
          AND updated_at >= now() - (%s::text || ' hours')::interval
        GROUP BY error
        ORDER BY count DESC, error NULLS LAST
        """,
        (max(1, min(int(hours or 24), 168)),),
    )
    return [dict(row) for row in rows]


def _retry_count(result_json: Any) -> int:
    if isinstance(result_json, str):
        try:
            result_json = json.loads(result_json)
        except Exception:
            result_json = {}
    if not isinstance(result_json, dict):
        return 0
    try:
        return int(result_json.get("scanner_retry_count") or 0)
    except (TypeError, ValueError):
        return 0


def _timeout_resilience_retry_count(result_json: Any) -> int:
    if isinstance(result_json, str):
        try:
            result_json = json.loads(result_json)
        except Exception:
            result_json = {}
    if not isinstance(result_json, dict):
        return 0
    try:
        return int(result_json.get("scanner_timeout_resilience_retry_count") or 0)
    except (TypeError, ValueError):
        return 0


def scanner_queue_health_snapshot(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 100))
    failed = fetch_all(
        """
        SELECT id, url, business_name, error, result_json, updated_at
        FROM scanner_jobs
        WHERE status = 'failed'
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    retryable = [
        row
        for row in failed
        if str(row.get("error") or "") in TRANSIENT_SCANNER_ERRORS and _retry_count(row.get("result_json")) < 1
    ]
    return json_safe(
        {
            "status": "ready",
            "counts": _scanner_counts(),
            "recent_errors": _recent_errors(24),
            "stale_running": scanner_stale_running_snapshot(limit),
            "failed_sample_count": len(failed),
            "retryable_transient_count": len(retryable),
            "retry_policy": {
                "max_retry_count": 1,
                "transient_errors": sorted(TRANSIENT_SCANNER_ERRORS),
                "non_retryable_errors": ["WorkerKilledDuringManualBatch"],
            },
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def _stale_recovery_count(result_json: Any) -> int:
    if isinstance(result_json, str):
        try:
            result_json = json.loads(result_json)
        except Exception:
            result_json = {}
    if not isinstance(result_json, dict):
        return 0
    try:
        return int(result_json.get("scanner_stale_recovery_count") or 0)
    except (TypeError, ValueError):
        return 0


def scanner_stale_running_snapshot(limit: int = 20, older_than_minutes: int = 15) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 100))
    safe_minutes = max(5, min(int(older_than_minutes or 15), 24 * 60))
    rows = fetch_all(
        """
        SELECT id, url, business_name, started_at, updated_at, result_json,
               now() - COALESCE(started_at, updated_at) AS age
        FROM scanner_jobs
        WHERE status = 'running'
          AND COALESCE(started_at, updated_at) < now() - (%s::text || ' minutes')::interval
        ORDER BY COALESCE(started_at, updated_at)
        LIMIT %s
        """,
        (safe_minutes, safe_limit),
    )
    return json_safe(
        {
            "status": "ready",
            "older_than_minutes": safe_minutes,
            "candidate_count": len(rows),
            "candidates": [
                {
                    "id": str(row["id"]),
                    "url": row["url"],
                    "business_name": row["business_name"],
                    "age": str(row["age"]),
                    "recovery_count": _stale_recovery_count(row.get("result_json")),
                }
                for row in rows
            ],
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def recover_stale_running_scanner_jobs(
    limit: int = 10,
    older_than_minutes: int = 15,
    dry_run: bool = True,
    max_requeue_count: int = 1,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 10), 25))
    safe_minutes = max(5, min(int(older_than_minutes or 15), 24 * 60))
    safe_max_requeue = max(0, min(int(max_requeue_count or 1), 3))
    rows = fetch_all(
        """
        SELECT id, url, business_name, result_json, started_at, updated_at,
               now() - COALESCE(started_at, updated_at) AS age
        FROM scanner_jobs
        WHERE status = 'running'
          AND COALESCE(started_at, updated_at) < now() - (%s::text || ' minutes')::interval
        LIMIT %s
        """,
        (safe_minutes, safe_limit),
    )
    candidates = [
        {
            "id": str(row["id"]),
            "url": row["url"],
            "business_name": row["business_name"],
            "age": str(row["age"]),
            "recovery_count": _stale_recovery_count(row.get("result_json")),
        }
        for row in rows
    ]
    if dry_run:
        result = {
            "status": "dry_run",
            "dry_run": True,
            "older_than_minutes": safe_minutes,
            "candidate_count": len(rows),
            "requeued_count": 0,
            "failed_count": 0,
            "candidates": candidates,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
        row = execute(
            """
            INSERT INTO scanner_stale_recovery_runs(
              status, dry_run, candidate_count, requeued_count, failed_count,
              older_than_minutes, result_json
            )
            VALUES (%s, true, %s, 0, 0, %s, %s)
            RETURNING id, created_at
            """,
            (result["status"], len(rows), safe_minutes, Jsonb(result)),
        )
        result["run_id"] = str(row["id"])
        result["created_at"] = row["created_at"].isoformat()
        return json_safe(result)

    requeued: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for row in rows:
        current = row.get("result_json") if isinstance(row.get("result_json"), dict) else {}
        count = _stale_recovery_count(current)
        merged = dict(current or {})
        merged.update(
            {
                "scanner_stale_recovery_count": count + 1,
                "scanner_stale_recovery_reason": "running_job_exceeded_age_window",
                "scanner_stale_recovery_older_than_minutes": safe_minutes,
            }
        )
        if count < safe_max_requeue:
            updated = execute(
                """
                UPDATE scanner_jobs
                SET status = 'queued',
                    priority = GREATEST(priority, 180),
                    started_at = NULL,
                    completed_at = NULL,
                    error = NULL,
                    updated_at = now(),
                    result_json = %s
                WHERE id = %s
                  AND status = 'running'
                  AND COALESCE(started_at, updated_at) < now() - (%s::text || ' minutes')::interval
                RETURNING id, url, status
                """,
                (Jsonb(merged), row["id"], safe_minutes),
            )
            if updated:
                requeued.append({"id": str(updated["id"]), "status": updated["status"]})
        else:
            updated = execute(
                """
                UPDATE scanner_jobs
                SET status = 'failed',
                    error = 'StaleRunningScannerJob',
                    completed_at = now(),
                    updated_at = now(),
                    result_json = %s
                WHERE id = %s
                  AND status = 'running'
                  AND COALESCE(started_at, updated_at) < now() - (%s::text || ' minutes')::interval
                RETURNING id, url, status
                """,
                (Jsonb(merged), row["id"], safe_minutes),
            )
            if updated:
                failed.append({"id": str(updated["id"]), "status": updated["status"]})

    status = "recovered" if requeued or failed else "idle"
    result = {
        "status": status,
        "dry_run": False,
        "older_than_minutes": safe_minutes,
        "candidate_count": len(rows),
        "requeued_count": len(requeued),
        "failed_count": len(failed),
        "requeued": requeued,
        "failed": failed,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
    run = execute(
        """
        INSERT INTO scanner_stale_recovery_runs(
          status, dry_run, candidate_count, requeued_count, failed_count,
          older_than_minutes, result_json
        )
        VALUES (%s, false, %s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (status, len(rows), len(requeued), len(failed), safe_minutes, Jsonb(result)),
    )
    result["run_id"] = str(run["id"])
    result["created_at"] = run["created_at"].isoformat()
    return json_safe(result)


def latest_scanner_stale_recovery_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, dry_run, candidate_count, requeued_count, failed_count,
               older_than_minutes, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM scanner_stale_recovery_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 100)),),
    )
    return {
        "count": len(rows),
        "runs": [
            {
                "id": str(row["id"]),
                "status": row["status"],
                "dry_run": bool(row["dry_run"]),
                "candidate_count": int(row["candidate_count"] or 0),
                "requeued_count": int(row["requeued_count"] or 0),
                "failed_count": int(row["failed_count"] or 0),
                "older_than_minutes": int(row["older_than_minutes"] or 0),
                "send_mail": bool(row["send_mail"]),
                "smtp_called": bool(row["smtp_called"]),
                "live_outreach_allowed": bool(row["live_outreach_allowed"]),
                "raw_recipient_addresses_included": bool(row["raw_recipient_addresses_included"]),
                "secrets_included": bool(row["secrets_included"]),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def retry_transient_scanner_failures(
    limit: int = 5,
    dry_run: bool = True,
    allow_timeout_resilience_retry: bool = False,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 5), 25))
    candidates = fetch_all(
        """
        SELECT id, url, business_name, error, result_json
        FROM scanner_jobs
        WHERE status = 'failed'
          AND error = ANY(%s)
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        (list(TRANSIENT_SCANNER_ERRORS), safe_limit * 3),
    )
    selected = []
    for row in candidates:
        retry_count = _retry_count(row.get("result_json"))
        timeout_resilience_retry = (
            allow_timeout_resilience_retry
            and str(row.get("error") or "") == "TimeoutError"
            and retry_count >= 1
            and _timeout_resilience_retry_count(row.get("result_json")) < 1
        )
        if retry_count >= 1 and not timeout_resilience_retry:
            continue
        selected.append(row)
        if len(selected) >= safe_limit:
            break
    if dry_run:
        return json_safe(
            {
                "status": "dry_run",
                "candidate_count": len(selected),
                "requeued_count": 0,
                "candidate_errors": sorted({str(row.get("error") or "") for row in selected}),
                "timeout_resilience_retry_enabled": bool(allow_timeout_resilience_retry),
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
                "raw_recipient_addresses_included": False,
                "secrets_included": False,
            }
        )

    requeued = []
    for row in selected:
        current = row.get("result_json") if isinstance(row.get("result_json"), dict) else {}
        retry_count = _retry_count(current) + 1
        merged = dict(current or {})
        timeout_resilience_retry = (
            allow_timeout_resilience_retry
            and str(row.get("error") or "") == "TimeoutError"
            and _retry_count(current) >= 1
            and _timeout_resilience_retry_count(current) < 1
        )
        merged.update(
            {
                "scanner_retry_count": retry_count,
                "scanner_retry_reason": "timeout_resilience_fix" if timeout_resilience_retry else "transient_failure",
                "scanner_last_error": row.get("error"),
            }
        )
        if timeout_resilience_retry:
            merged["scanner_timeout_resilience_retry_count"] = _timeout_resilience_retry_count(current) + 1
        updated = execute(
            """
            UPDATE scanner_jobs
            SET status = 'queued',
                priority = GREATEST(priority, 150),
                error = NULL,
                started_at = NULL,
                completed_at = NULL,
                updated_at = now(),
                result_json = %s
            WHERE id = %s
              AND status = 'failed'
            RETURNING id, url, status
            """,
            (Jsonb(merged), row["id"]),
        )
        if updated:
            requeued.append({"id": str(updated["id"]), "status": updated["status"]})
    return json_safe(
        {
            "status": "requeued" if requeued else "idle",
            "candidate_count": len(selected),
            "requeued_count": len(requeued),
            "requeued": requeued,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
