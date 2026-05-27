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


def stale_scout_run_recovery_snapshot(limit: int = 50, older_than_minutes: int = 120) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 50), 200))
    safe_minutes = max(15, min(int(older_than_minutes or 120), 1440))
    rows = fetch_all(
        """
        SELECT sr.id, sr.country, sr.niche, sr.language, sr.started_at, sr.result_json,
               ss.name AS source_name, ss.source_type
        FROM scout_runs sr
        LEFT JOIN scout_sources ss ON ss.id = sr.source_id
        WHERE sr.status = 'running'
          AND sr.started_at < now() - (%s::text || ' minutes')::interval
        ORDER BY sr.started_at ASC
        LIMIT %s
        """,
        (safe_minutes, safe_limit),
    )
    return json_safe(
        {
            "status": "stale_running_found" if rows else "clean",
            "stale_count": len(rows),
            "older_than_minutes": safe_minutes,
            "runs": [
                {
                    "scout_run_id": str(row["id"]),
                    "country": row["country"],
                    "niche": row["niche"],
                    "language": row["language"],
                    "source_type": row["source_type"],
                    "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
                }
                for row in rows
            ],
            **SAFE_FLAGS,
        }
    )


def recover_stale_scout_runs(limit: int = 25, older_than_minutes: int = 120, apply: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    safe_minutes = max(15, min(int(older_than_minutes or 120), 1440))
    rows = fetch_all(
        """
        SELECT id, country, niche, language, started_at, result_json
        FROM scout_runs
        WHERE status = 'running'
          AND started_at < now() - (%s::text || ' minutes')::interval
        ORDER BY started_at ASC
        LIMIT %s
        """,
        (safe_minutes, safe_limit),
    )
    recovered = []
    for row in rows:
        previous_retries = int((row.get("result_json") or {}).get("stale_recovery_count") or 0)
        new_status = "queued" if previous_retries < 2 else "review_required"
        item = {
            "scout_run_id": str(row["id"]),
            "old_status": "running",
            "new_status": new_status,
            "stale_recovery_count": previous_retries + 1,
            "country": row["country"],
            "niche": row["niche"],
            **SAFE_FLAGS,
        }
        if apply:
            execute(
                """
                UPDATE scout_runs
                SET status = %s,
                    started_at = CASE WHEN %s = 'queued' THEN NULL ELSE started_at END,
                    error = CASE WHEN %s = 'review_required' THEN 'stale_running_recovery_limit' ELSE NULL END,
                    result_json = COALESCE(result_json, '{}'::jsonb) || %s::jsonb
                WHERE id = %s AND status = 'running'
                """,
                (
                    new_status,
                    new_status,
                    new_status,
                    Jsonb(
                        {
                            "stale_recovery": {
                                "applied": True,
                                "send_mail": False,
                                "live_outreach_allowed": False,
                            },
                            "stale_recovery_count": previous_retries + 1,
                        }
                    ),
                    row["id"],
                ),
            )
        recovered.append(item)
    result = json_safe(
        {
            "status": "applied" if apply and recovered else ("planned" if recovered else "clean"),
            "applied": bool(apply),
            "older_than_minutes": safe_minutes,
            "inspected_count": len(rows),
            "recovered_count": len([item for item in recovered if item["new_status"] == "queued"]),
            "review_required_count": len([item for item in recovered if item["new_status"] == "review_required"]),
            "runs": recovered,
            **SAFE_FLAGS,
        }
    )
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('scout_run.stale_recovery', %s, 'Stale scout run recovery evaluated', %s)
        """,
        ("warning" if recovered else "info", Jsonb(result)),
    )
    return result
