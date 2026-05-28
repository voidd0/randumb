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
