from __future__ import annotations

from typing import Any

from .campaign_control_room import campaign_control_room_snapshot, prepare_campaign_control_room
from .db import fetch_all, fetch_one
from .p0 import json_safe
from .scouts import (
    process_queued_scout_runs,
    queue_ready_scout_source_runs,
    ready_scout_source_queue_candidates,
    run_scout_source_readiness,
    scout_campaign_expansion_gate,
    scout_source_readiness_gate,
)


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def source_campaign_operator_snapshot(limit: int = 25, source_id: str | None = None) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    candidates = ready_scout_source_queue_candidates(safe_limit, source_id)
    queued_runs = fetch_all(
        """
        SELECT id, source_id, status, country, language, niche, created_at
        FROM scout_runs
        WHERE status IN ('queued', 'running')
          AND (%s::uuid IS NULL OR source_id = %s::uuid)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (source_id or None, source_id or None, safe_limit),
    )
    return json_safe(
        {
            "status": "snapshot",
            "source_id": source_id,
            "candidate_count": candidates["candidate_count"],
            "candidates": candidates["candidates"][:safe_limit],
            "queued_or_running_runs": [
                {
                    "id": str(row["id"]),
                    "source_id": str(row["source_id"]) if row["source_id"] else None,
                    "status": row["status"],
                    "country": row["country"],
                    "language": row["language"],
                    "niche": row["niche"],
                    "created_at": row["created_at"],
                }
                for row in queued_runs
            ],
            "scanner_jobs": {
                "queued": _count("SELECT count(*) FROM scanner_jobs WHERE status = 'queued'"),
                "running": _count("SELECT count(*) FROM scanner_jobs WHERE status = 'running'"),
                "completed": _count("SELECT count(*) FROM scanner_jobs WHERE status = 'completed'"),
                "failed": _count("SELECT count(*) FROM scanner_jobs WHERE status = 'failed'"),
            },
            "campaign_control_room": campaign_control_room_snapshot(safe_limit, 70),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def advance_source_to_campaign(
    source_id: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    process_scout: bool = False,
    prepare_campaigns: bool = True,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    blockers: list[str] = []
    readiness: dict[str, Any] = {"status": "skipped", "reason": "source_id_missing"}
    queue_result: dict[str, Any] = {"status": "skipped", "queued_count": 0, "created_scanner_jobs": 0}
    process_result: dict[str, Any] = {"status": "skipped", "processed": 0}
    campaign_result: dict[str, Any] = {"status": "skipped"}

    if not source_id:
        blockers.append("explicit_source_id_required")
    else:
        readiness = run_scout_source_readiness(source_id)
        readiness_gate = scout_source_readiness_gate(source_id)
        expansion_gate = scout_campaign_expansion_gate()
        if not readiness_gate["allowed"]:
            blockers.append("source_readiness_not_pass")
        if not expansion_gate["allowed"]:
            blockers.append("self_audit_expansion_gate_not_pass")
        if dry_run:
            queue_result = queue_ready_scout_source_runs(safe_limit, dry_run=True, source_id=source_id)
        elif not blockers:
            queue_result = queue_ready_scout_source_runs(1, dry_run=False, source_id=source_id)
            if process_scout:
                process_result = process_queued_scout_runs(1)
        else:
            queue_result = {"status": "blocked", "queued_count": 0, "created_scanner_jobs": 0}

    if prepare_campaigns:
        campaign_result = prepare_campaign_control_room(
            safe_limit,
            70,
            dry_run=True if dry_run or blockers else False,
            offer_key="contact_form_repair",
            max_segments=3,
        )

    status = "blocked" if blockers else ("preview_only" if dry_run else "advanced")
    return json_safe(
        {
            "status": status,
            "dry_run": dry_run,
            "source_id": source_id,
            "blockers": blockers,
            "readiness": readiness,
            "source_queue": queue_result,
            "scout_processing": process_result,
            "campaign_control_room": campaign_result,
            "snapshot": source_campaign_operator_snapshot(safe_limit, source_id),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
