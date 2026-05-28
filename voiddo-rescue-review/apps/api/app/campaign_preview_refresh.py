from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .campaign_control_room import campaign_control_room_snapshot, prepare_campaign_control_room
from .db import execute, fetch_all, fetch_one
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def campaign_preview_refresh_snapshot(limit: int = 100, stale_hours: int = 24) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 250))
    safe_hours = max(1, min(int(stale_hours or 24), 168))
    control = campaign_control_room_snapshot(safe_limit, 70)
    preview_count = _count("SELECT count(*) FROM campaign_leads WHERE status = 'preview'")
    stale_by_age = _count(
        """
        SELECT count(*)
        FROM campaign_leads
        WHERE status = 'preview'
          AND updated_at < now() - (%s || ' hours')::interval
        """,
        (safe_hours,),
    )
    latest_cycle_newer = _count(
        """
        SELECT count(*)
        FROM post_scan_campaign_cycles psc
        WHERE psc.dry_run = false
          AND psc.created_at > COALESCE((SELECT max(updated_at) FROM campaign_leads WHERE status = 'preview'), '-infinity'::timestamptz)
        """
    )
    ready = int(control.get("ready_candidate_count") or 0)
    missing = max(0, ready - preview_count)
    stale = stale_by_age + latest_cycle_newer
    should_refresh = stale > 0 or missing > 0
    return {
        "status": "refresh_recommended" if should_refresh else "fresh",
        "ready_candidate_count": ready,
        "preview_count": preview_count,
        "stale_preview_count": stale_by_age,
        "post_scan_cycle_newer_than_preview": latest_cycle_newer > 0,
        "missing_preview_count": missing,
        "stale_hours": safe_hours,
        "should_refresh": should_refresh,
        **SAFE_FLAGS,
    }


def refresh_campaign_previews_if_needed(limit: int = 100, stale_hours: int = 24, dry_run: bool = True) -> dict[str, Any]:
    snapshot = campaign_preview_refresh_snapshot(limit, stale_hours)
    prepared: dict[str, Any] | None = None
    refreshed = 0
    status = "dry_run_refresh_recommended" if snapshot["should_refresh"] and dry_run else "fresh_noop"
    if snapshot["should_refresh"] and not dry_run:
        prepared = prepare_campaign_control_room(limit, 70, dry_run=False, offer_key="contact_form_repair", max_segments=8)
        refreshed = int(prepared.get("campaign_previews_prepared") or 0)
        touched = fetch_all(
            """
            WITH stale AS (
              SELECT id
              FROM campaign_leads
              WHERE status = 'preview'
                AND updated_at < now() - (%s || ' hours')::interval
              ORDER BY updated_at
              LIMIT %s
            )
            UPDATE campaign_leads cl
            SET updated_at = now()
            FROM stale
            WHERE cl.id = stale.id
            RETURNING cl.id
            """,
            (max(1, min(int(stale_hours or 24), 168)), max(1, min(int(limit or 100), 250))),
        )
        refreshed = max(refreshed, len(touched))
        status = "refreshed_no_send" if prepared.get("status") == "prepared" else "refresh_blocked"
    result = json_safe(
        {
            "status": status,
            "dry_run": dry_run,
            "snapshot": snapshot,
            "stale_preview_count": snapshot["stale_preview_count"],
            "missing_preview_count": snapshot["missing_preview_count"],
            "refreshed_preview_count": refreshed,
            "prepared": prepared,
            **SAFE_FLAGS,
        }
    )
    row = execute(
        """
        INSERT INTO campaign_preview_refresh_runs(
          status, dry_run, stale_preview_count, missing_preview_count, refreshed_preview_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (
            result["status"],
            dry_run,
            result["stale_preview_count"],
            result["missing_preview_count"],
            result["refreshed_preview_count"],
            Jsonb(result),
        ),
    )
    result["run_id"] = str(row["id"])
    result["created_at"] = row["created_at"].isoformat()
    return result


def latest_campaign_preview_refresh_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, dry_run, stale_preview_count, missing_preview_count,
               refreshed_preview_count, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM campaign_preview_refresh_runs
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
                "stale_preview_count": int(row["stale_preview_count"] or 0),
                "missing_preview_count": int(row["missing_preview_count"] or 0),
                "refreshed_preview_count": int(row["refreshed_preview_count"] or 0),
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
