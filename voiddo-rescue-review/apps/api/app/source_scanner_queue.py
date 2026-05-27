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


def source_scanner_backlog(limit: int = 100, source_id: str | None = None) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 250))
    rows = fetch_all(
        """
        SELECT
          sl.id AS scout_lead_id,
          sl.business_name,
          sl.domain,
          sl.website_url,
          sl.country,
          sl.city,
          sl.language,
          sl.niche,
          ss.id AS source_id,
          ss.name AS source_name,
          COALESCE(perf.recommendation, 'missing') AS recommendation,
          COALESCE(perf.qualified_rate, 0) AS qualified_rate,
          COALESCE(perf.average_final_score, 0) AS average_final_score
        FROM scout_leads sl
        JOIN scout_runs sr ON sr.id = sl.scout_run_id
        JOIN scout_sources ss ON ss.id = sr.source_id
        LEFT JOIN LATERAL (
          SELECT recommendation, qualified_rate, average_final_score
          FROM scout_source_performance_scores ssp
          WHERE ssp.source_id = ss.id
          ORDER BY created_at DESC
          LIMIT 1
        ) perf ON true
        WHERE sl.status = 'accepted'
          AND sl.website_url IS NOT NULL
          AND sl.website_url <> ''
          AND (%s::uuid IS NULL OR ss.id = %s::uuid)
          AND COALESCE(ss.status, '') NOT IN ('blocked', 'quality_deprioritized')
          AND NOT EXISTS (
            SELECT 1 FROM scanner_jobs sj
            WHERE sj.result_json->>'scout_lead_id' = sl.id::text
               OR lower(sj.url) = lower(sl.website_url)
          )
        ORDER BY
          CASE COALESCE(perf.recommendation, 'missing')
            WHEN 'PROMOTE_SOURCE_FOR_MORE_SCOUTING' THEN 0
            WHEN 'KEEP_TESTING_WITH_SMALL_BATCHES' THEN 1
            WHEN 'KEEP_TESTING' THEN 2
            ELSE 3
          END,
          COALESCE(perf.qualified_rate, 0) DESC,
          COALESCE(perf.average_final_score, 0) DESC,
          sl.created_at ASC
        LIMIT %s
        """,
        (source_id or None, source_id or None, safe_limit),
    )
    candidates = [
        {
            "scout_lead_id": str(row["scout_lead_id"]),
            "business_name": row["business_name"],
            "domain": row["domain"],
            "website_url": row["website_url"],
            "country": row["country"],
            "city": row["city"],
            "language": row["language"],
            "niche": row["niche"],
            "source_id": str(row["source_id"]),
            "source_name": row["source_name"],
            "recommendation": row["recommendation"],
            "qualified_rate": float(row["qualified_rate"] or 0),
            "average_final_score": float(row["average_final_score"] or 0),
        }
        for row in rows
    ]
    source_counts: dict[str, int] = {}
    for item in candidates:
        key = item["source_id"]
        source_counts[key] = source_counts.get(key, 0) + 1
    return {
        "status": "ready" if candidates else "empty",
        "candidate_count": len(candidates),
        "source_count": len(source_counts),
        "candidates": candidates[:safe_limit],
        **SAFE_FLAGS,
    }


def queue_source_scanner_jobs(limit: int = 100, dry_run: bool = True, source_id: str | None = None) -> dict[str, Any]:
    backlog = source_scanner_backlog(limit, source_id)
    candidates = backlog["candidates"]
    queued: list[dict[str, Any]] = []
    duplicates = 0
    if not dry_run:
        for item in candidates:
            inserted = execute(
                """
                INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, result_json)
                SELECT %s, %s, false, 'queued', 125, %s
                WHERE NOT EXISTS (
                  SELECT 1 FROM scanner_jobs sj
                  WHERE sj.result_json->>'scout_lead_id' = %s
                     OR lower(sj.url) = lower(%s)
                )
                RETURNING id, priority
                """,
                (
                    item["website_url"],
                    item["business_name"],
                    Jsonb(
                        {
                            "scout_lead_id": item["scout_lead_id"],
                            "source_id": item["source_id"],
                            "source_name": item["source_name"],
                            "source_scanner_queue_reason": "accepted_scout_lead_without_scan",
                        }
                    ),
                    item["scout_lead_id"],
                    item["website_url"],
                ),
            )
            if inserted:
                queued.append(
                    {
                        "job_id": str(inserted["id"]),
                        "scout_lead_id": item["scout_lead_id"],
                        "source_id": item["source_id"],
                        "domain": item["domain"],
                        "priority": int(inserted["priority"] or 0),
                    }
                )
            else:
                duplicates += 1

    status = "dry_run" if dry_run else ("queued" if queued else "idle")
    result = json_safe(
        {
            "status": status,
            "dry_run": dry_run,
            "candidate_count": len(candidates),
            "queued_count": 0 if dry_run else len(queued),
            "duplicate_skipped_count": duplicates,
            "queued": queued[:50],
            "backlog": {
                "source_count": backlog["source_count"],
                "candidate_count": backlog["candidate_count"],
            },
            **SAFE_FLAGS,
        }
    )
    row = execute(
        """
        INSERT INTO source_scanner_queue_runs(
          status, dry_run, candidate_count, queued_count, duplicate_skipped_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (
            result["status"],
            dry_run,
            result["candidate_count"],
            result["queued_count"],
            result["duplicate_skipped_count"],
            Jsonb(result),
        ),
    )
    result["run_id"] = str(row["id"])
    result["created_at"] = row["created_at"].isoformat()
    return result


def latest_source_scanner_queue_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, dry_run, candidate_count, queued_count, duplicate_skipped_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM source_scanner_queue_runs
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
                "candidate_count": int(row["candidate_count"] or 0),
                "queued_count": int(row["queued_count"] or 0),
                "duplicate_skipped_count": int(row["duplicate_skipped_count"] or 0),
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
