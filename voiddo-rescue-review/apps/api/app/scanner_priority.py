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


def scanner_guided_backlog(limit: int = 50) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 50), 250))
    rows = fetch_all(
        """
        SELECT
          ss.id AS source_id,
          ss.name AS source_name,
          ss.country,
          ss.niche,
          count(sj.id) AS job_count,
          count(sj.id) FILTER (WHERE sj.status = 'queued') AS queued_count,
          count(sj.id) FILTER (WHERE sj.status = 'running') AS running_count,
          count(sj.id) FILTER (WHERE sj.status = 'completed') AS completed_count,
          count(sj.id) FILTER (WHERE sj.status = 'failed') AS failed_count,
          max(sj.priority) FILTER (WHERE sj.status = 'queued') AS max_queued_priority,
          perf.recommendation AS latest_recommendation,
          perf.qualified_rate AS latest_qualified_rate,
          perf.average_final_score AS latest_average_score
        FROM scanner_jobs sj
        JOIN scout_leads sl ON sl.id::text = sj.result_json->>'scout_lead_id'
        JOIN scout_runs sr ON sr.id = sl.scout_run_id
        JOIN scout_sources ss ON ss.id = sr.source_id
        LEFT JOIN LATERAL (
          SELECT recommendation, qualified_rate, average_final_score
          FROM scout_source_performance_scores ssp
          WHERE ssp.source_id = ss.id
          ORDER BY created_at DESC
          LIMIT 1
        ) perf ON true
        GROUP BY ss.id, ss.name, ss.country, ss.niche, perf.recommendation, perf.qualified_rate, perf.average_final_score
        HAVING count(sj.id) FILTER (WHERE sj.status = 'queued') > 0
        ORDER BY
          CASE perf.recommendation
            WHEN 'PROMOTE_SOURCE_FOR_MORE_SCOUTING' THEN 0
            WHEN 'KEEP_TESTING_WITH_SMALL_BATCHES' THEN 1
            ELSE 2
          END,
          count(sj.id) FILTER (WHERE sj.status = 'queued') DESC,
          max(sj.queued_at) DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    sources = [
        {
            "source_id": str(row["source_id"]),
            "source_name": row["source_name"],
            "country": row["country"],
            "niche": row["niche"],
            "job_count": int(row["job_count"] or 0),
            "queued_count": int(row["queued_count"] or 0),
            "running_count": int(row["running_count"] or 0),
            "completed_count": int(row["completed_count"] or 0),
            "failed_count": int(row["failed_count"] or 0),
            "max_queued_priority": int(row["max_queued_priority"] or 0),
            "latest_recommendation": row["latest_recommendation"] or "missing",
            "latest_qualified_rate": float(row["latest_qualified_rate"] or 0),
            "latest_average_score": float(row["latest_average_score"] or 0),
        }
        for row in rows
    ]
    return {
        "status": "ready" if sources else "empty",
        "source_count": len(sources),
        "queued_job_count": sum(item["queued_count"] for item in sources),
        "sources": sources,
        **SAFE_FLAGS,
    }


def prioritize_guided_scanner_jobs(limit: int = 25, dry_run: bool = True) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    rows = fetch_all(
        """
        SELECT
          sj.id,
          sj.priority,
          sj.result_json,
          ss.id AS source_id,
          ss.name AS source_name,
          ss.country,
          ss.niche,
          COALESCE(perf.recommendation, 'missing') AS recommendation,
          COALESCE(perf.qualified_rate, 0) AS qualified_rate,
          COALESCE(perf.average_final_score, 0) AS average_final_score
        FROM scanner_jobs sj
        JOIN scout_leads sl ON sl.id::text = sj.result_json->>'scout_lead_id'
        JOIN scout_runs sr ON sr.id = sl.scout_run_id
        JOIN scout_sources ss ON ss.id = sr.source_id
        LEFT JOIN LATERAL (
          SELECT recommendation, qualified_rate, average_final_score
          FROM scout_source_performance_scores ssp
          WHERE ssp.source_id = ss.id
          ORDER BY created_at DESC
          LIMIT 1
        ) perf ON true
        WHERE sj.status = 'queued'
          AND sj.dry_run = false
        ORDER BY
          CASE COALESCE(perf.recommendation, 'missing')
            WHEN 'PROMOTE_SOURCE_FOR_MORE_SCOUTING' THEN 0
            WHEN 'KEEP_TESTING_WITH_SMALL_BATCHES' THEN 1
            WHEN 'KEEP_TESTING' THEN 2
            ELSE 3
          END,
          COALESCE(perf.qualified_rate, 0) DESC,
          COALESCE(perf.average_final_score, 0) DESC,
          sj.queued_at ASC
        LIMIT %s
        """,
        (safe_limit,),
    )
    candidates = [
        {
            "job_id": str(row["id"]),
            "source_id": str(row["source_id"]),
            "source_name": row["source_name"],
            "country": row["country"],
            "niche": row["niche"],
            "old_priority": int(row["priority"] or 0),
            "new_priority": max(int(row["priority"] or 0), 175),
            "recommendation": row["recommendation"],
            "qualified_rate": float(row["qualified_rate"] or 0),
            "average_final_score": float(row["average_final_score"] or 0),
        }
        for row in rows
    ]
    prioritized: list[dict[str, Any]] = []
    if not dry_run:
        for row, candidate in zip(rows, candidates, strict=False):
            current = row.get("result_json") if isinstance(row.get("result_json"), dict) else {}
            merged = dict(current or {})
            merged.update(
                {
                    "scanner_priority_reason": "performance_guided_source_backlog",
                    "scanner_priority_source_id": str(row["source_id"]),
                    "scanner_priority_recommendation": row["recommendation"],
                }
            )
            updated = execute(
                """
                UPDATE scanner_jobs
                SET priority = GREATEST(priority, 175),
                    result_json = %s,
                    updated_at = now()
                WHERE id = %s
                  AND status = 'queued'
                RETURNING id, priority
                """,
                (Jsonb(merged), row["id"]),
            )
            if updated:
                prioritized.append({**candidate, "new_priority": int(updated["priority"] or 0)})
    result = json_safe(
        {
            "status": "dry_run" if dry_run else ("prioritized" if prioritized else "idle"),
            "dry_run": dry_run,
            "candidate_count": len(candidates),
            "prioritized_count": 0 if dry_run else len(prioritized),
            "candidates": candidates[:50],
            "prioritized": prioritized[:50],
            **SAFE_FLAGS,
        }
    )
    row = execute(
        """
        INSERT INTO scanner_priority_runs(
          status, dry_run, candidate_count, prioritized_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (result["status"], dry_run, result["candidate_count"], result["prioritized_count"], Jsonb(result)),
    )
    result["run_id"] = str(row["id"])
    result["created_at"] = row["created_at"].isoformat()
    return result


def latest_scanner_priority_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, dry_run, candidate_count, prioritized_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM scanner_priority_runs
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
                "prioritized_count": int(row["prioritized_count"] or 0),
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
