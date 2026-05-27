from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .campaign_actions import run_campaign_operator_cycle
from .campaign_control_room import campaign_control_room_snapshot, prepare_campaign_control_room
from .campaign_pipeline_repair import repair_campaign_pipeline
from .db import execute, fetch_all, fetch_one
from .lead_quality_diagnostics import scout_source_performance
from .lead_scoring import backfill_post_scan_lead_scores
from .p0 import json_safe
from .scanner_ops import scanner_queue_health_snapshot


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _scanner_count(snapshot: dict[str, Any], status: str) -> int:
    counts = snapshot.get("counts") if isinstance(snapshot.get("counts"), dict) else {}
    return int(counts.get(status) or 0)


def _preview_count() -> int:
    row = fetch_one("SELECT count(*) AS count FROM campaign_leads WHERE status = 'preview'")
    return int(row["count"]) if row else 0


def post_scan_campaign_cycle(limit: int = 100, dry_run: bool = True) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 250))
    before_scanner = scanner_queue_health_snapshot(20)
    before_campaign = campaign_control_room_snapshot(safe_limit, 70)
    preview_before = _preview_count()

    backfill = backfill_post_scan_lead_scores(safe_limit, dry_run=dry_run)
    source_perf = scout_source_performance(safe_limit, store=not dry_run)
    pipeline = repair_campaign_pipeline(safe_limit, dry_run=dry_run, prepare_previews=False)
    prepared = (
        prepare_campaign_control_room(safe_limit, 70, dry_run=False, offer_key="contact_form_repair", max_segments=8)
        if not dry_run
        else {"status": "dry_run", "campaign_previews_prepared": 0, **SAFE_FLAGS}
    )
    operator = run_campaign_operator_cycle(min(safe_limit, 50), refresh_previews=False) if not dry_run else {"status": "dry_run", **SAFE_FLAGS}
    after_campaign = campaign_control_room_snapshot(safe_limit, 70)
    after_scanner = scanner_queue_health_snapshot(20)
    preview_after = _preview_count()

    status = "completed_no_send" if not dry_run else "dry_run_no_send"
    if any(
        bool((item or {}).get(flag))
        for item in [backfill, source_perf, pipeline, prepared, operator, after_campaign]
        for flag in ["send_mail", "smtp_called", "live_outreach_allowed", "raw_recipient_addresses_included", "secrets_included"]
    ):
        status = "failed_send_flag_regression"

    result = json_safe(
        {
            "status": status,
            "dry_run": dry_run,
            "before": {
                "scanner": before_scanner,
                "campaign": before_campaign,
                "campaign_preview_count": preview_before,
            },
            "steps": {
                "backfill": backfill,
                "source_performance": {
                    "status": source_perf.get("status"),
                    "source_count": source_perf.get("source_count", 0),
                    "promote_count": source_perf.get("promote_count", 0),
                    "pause_review_count": source_perf.get("pause_review_count", 0),
                    "next_actions": source_perf.get("next_actions", {}),
                    **SAFE_FLAGS,
                },
                "pipeline_repair": pipeline,
                "campaign_prepare": prepared,
                "campaign_operator": operator,
            },
            "after": {
                "scanner": after_scanner,
                "campaign": after_campaign,
                "campaign_preview_count": preview_after,
            },
            **SAFE_FLAGS,
        }
    )

    row = execute(
        """
        INSERT INTO post_scan_campaign_cycles(
          status, dry_run, scanner_completed_count, scanner_queued_count,
          backfill_scored_count, backfill_qualified_count,
          source_performance_count, source_promote_count, source_pause_review_count,
          campaign_preview_count_before, campaign_preview_count_after,
          ready_candidate_count_after, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                false, false, false, false, false)
        RETURNING id, created_at
        """,
        (
            status,
            dry_run,
            _scanner_count(after_scanner, "completed"),
            _scanner_count(after_scanner, "queued"),
            int(backfill.get("scored_count") or 0),
            int(backfill.get("qualified_count") or 0),
            int(source_perf.get("source_count") or 0),
            int(source_perf.get("promote_count") or 0),
            int(source_perf.get("pause_review_count") or 0),
            preview_before,
            preview_after,
            int(after_campaign.get("ready_candidate_count") or 0),
            Jsonb(result),
        ),
    )
    result["cycle_id"] = str(row["id"])
    result["created_at"] = row["created_at"].isoformat()
    return result


def latest_post_scan_campaign_cycles(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, dry_run, scanner_completed_count, scanner_queued_count,
               backfill_scored_count, backfill_qualified_count,
               source_performance_count, source_promote_count, source_pause_review_count,
               campaign_preview_count_before, campaign_preview_count_after,
               ready_candidate_count_after, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM post_scan_campaign_cycles
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
                "scanner_completed_count": int(row["scanner_completed_count"] or 0),
                "scanner_queued_count": int(row["scanner_queued_count"] or 0),
                "backfill_scored_count": int(row["backfill_scored_count"] or 0),
                "backfill_qualified_count": int(row["backfill_qualified_count"] or 0),
                "source_performance_count": int(row["source_performance_count"] or 0),
                "source_promote_count": int(row["source_promote_count"] or 0),
                "source_pause_review_count": int(row["source_pause_review_count"] or 0),
                "campaign_preview_count_before": int(row["campaign_preview_count_before"] or 0),
                "campaign_preview_count_after": int(row["campaign_preview_count_after"] or 0),
                "ready_candidate_count_after": int(row["ready_candidate_count_after"] or 0),
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
