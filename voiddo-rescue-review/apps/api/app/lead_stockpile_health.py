from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .campaign_control_room import campaign_control_room_snapshot
from .campaign_preflight import campaign_preflight_batch
from .campaign_preview_reviews import auto_review_campaign_previews
from .campaign_preview_refresh import refresh_campaign_previews_if_needed
from .db import execute, fetch_all, fetch_one
from .lead_discovery import regional_lead_discovery_cycle
from .outreach_live_queue import live_outreach_queue_candidates
from .p0 import json_safe, queue_outreach_preview
from .source_campaign_operator import advance_source_to_campaign, source_campaign_operator_snapshot

TEST_COUNTRY_PATTERN = r"^(P7|P8|P9|P10|P11|P12|P59|P60|P61|P62|P63|P68|P72|P73|P74)"
SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"] or 0) if row else 0


def _preview_counts() -> dict[str, int]:
    row = fetch_one(
        """
        WITH latest_reviews AS (
          SELECT DISTINCT ON (campaign_lead_id) campaign_lead_id, action
          FROM campaign_preview_reviews
          ORDER BY campaign_lead_id, created_at DESC
        )
        SELECT
          count(*) FILTER (WHERE cl.status = 'preview') AS active_preview_count,
          count(*) FILTER (WHERE cl.status = 'preview' AND lr.action = 'approved') AS approved_preview_count,
          count(*) FILTER (WHERE cl.status = 'preview' AND lr.action = 'held') AS held_preview_count,
          count(*) FILTER (WHERE cl.status = 'preview' AND lr.action = 'rejected') AS rejected_preview_count,
          count(*) FILTER (WHERE cl.status = 'preview' AND lr.action IS NULL) AS unreviewed_preview_count
        FROM campaign_leads cl
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN leads l ON l.id = cl.lead_id
        JOIN businesses b ON b.id = l.business_id
        LEFT JOIN latest_reviews lr ON lr.campaign_lead_id = cl.id
        WHERE upper(COALESCE(c.country, '')) !~ %s
          AND lower(COALESCE(l.source, '')) NOT LIKE 'p%%\\_test' ESCAPE '\\'
          AND lower(COALESCE(b.domain, '')) NOT LIKE '%%.example.test'
          AND lower(COALESCE(l.email, '')) NOT LIKE '%%.example.test'
          AND COALESCE(l.status, '') NOT IN ('excluded_sensitive_target', 'suppressed', 'unsubscribed')
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(s.email) = lower(l.email))
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(COALESCE(s.domain, '')) = lower(COALESCE(b.domain, '')))
        """,
        (TEST_COUNTRY_PATTERN,),
    )
    return {key: int(row[key] or 0) for key in row.keys()} if row else {}


def _preflight_counts() -> dict[str, int]:
    rows = fetch_all(
        """
        SELECT latest.decision, count(*) AS count
        FROM campaigns c
        JOIN LATERAL (
          SELECT decision
          FROM campaign_preflight_runs
          WHERE campaign_id = c.id
          ORDER BY created_at DESC
          LIMIT 1
        ) latest ON true
        WHERE c.status IN ('draft', 'preview_ready')
          AND upper(COALESCE(c.country, '')) !~ %s
        GROUP BY latest.decision
        """,
        (TEST_COUNTRY_PATTERN,),
    )
    counts = {"preflight_pass_count": 0, "preflight_failed_count": 0}
    for row in rows:
        decision = str(row["decision"] or "")
        if decision == "PASS_NO_SEND_PREFLIGHT":
            counts["preflight_pass_count"] += int(row["count"] or 0)
        else:
            counts["preflight_failed_count"] += int(row["count"] or 0)
    return counts


def _scanner_counts() -> dict[str, int]:
    return {
        "scanner_queued_count": _count("SELECT count(*) FROM scanner_jobs WHERE status = 'queued'"),
        "scanner_running_count": _count("SELECT count(*) FROM scanner_jobs WHERE status = 'running'"),
        "scanner_failed_count": _count("SELECT count(*) FROM scanner_jobs WHERE status = 'failed'"),
    }


def lead_stockpile_health_snapshot(target_preview_count: int = 50, canary_count: int = 20, limit: int = 100) -> dict[str, Any]:
    target = max(20, min(int(target_preview_count or 50), 500))
    canary = max(1, min(int(canary_count or 20), target))
    safe_limit = max(1, min(int(limit or 100), 250))
    previews = _preview_counts()
    preflight = _preflight_counts()
    scanners = _scanner_counts()
    source_operator = source_campaign_operator_snapshot(min(safe_limit, 25))
    campaign_room = campaign_control_room_snapshot(safe_limit, 70)
    live_queue = live_outreach_queue_candidates(canary)

    approved = int(previews.get("approved_preview_count", 0))
    active = int(previews.get("active_preview_count", 0))
    source_candidates = int(source_operator.get("candidate_count", 0) or 0)
    scanner_active = int(scanners["scanner_queued_count"] + scanners["scanner_running_count"])
    candidate_count = int(campaign_room.get("candidate_count", 0) or 0)
    ready_candidate_count = int(campaign_room.get("ready_candidate_count", 0) or 0)
    live_candidates = int(live_queue.get("candidate_count", 0) or 0)

    blockers: list[str] = []
    next_actions: list[str] = []
    if approved < canary:
        blockers.append("approved_preview_count_below_canary")
        next_actions.append("refresh_campaign_previews_and_self_review")
    if approved < target:
        next_actions.append("continue_source_expansion_until_target_preview_count")
    if scanner_active > 0:
        blockers.append("scanner_jobs_still_active")
        next_actions.append("wait_for_worker_or_run_bounded_scanner_drain")
    if source_candidates > 0:
        next_actions.append("advance_ready_scout_source")
    if ready_candidate_count > active:
        next_actions.append("prepare_campaign_control_room")
    if int(previews.get("held_preview_count", 0)) > 0 or int(previews.get("unreviewed_preview_count", 0)) > 0:
        next_actions.append("run_preview_self_review_and_remediation")
    if int(preflight.get("preflight_failed_count", 0)) > 0:
        blockers.append("campaign_preflight_failures_present")
        next_actions.append("rerun_campaign_preflight_after_preview_refresh")
    if live_candidates < canary:
        blockers.append("live_queue_candidates_below_canary")
        next_actions.append("queue_or_refresh_dry_run_outreach_previews")

    if approved >= target and live_candidates >= canary and not blockers:
        decision = "STOCKPILE_TARGET_READY"
    elif approved >= canary and live_candidates >= canary and not [b for b in blockers if b != "scanner_jobs_still_active"]:
        decision = "STOCKPILE_READY_FOR_CANARY"
    elif source_candidates > 0:
        decision = "STOCKPILE_NEEDS_SOURCE_ADVANCE"
    elif scanner_active > 0:
        decision = "STOCKPILE_NEEDS_SCANNER_DRAIN"
    elif active == 0 or ready_candidate_count > active:
        decision = "STOCKPILE_NEEDS_PREVIEW_REFRESH"
    elif int(previews.get("held_preview_count", 0)) > 0 or int(previews.get("unreviewed_preview_count", 0)) > 0:
        decision = "STOCKPILE_NEEDS_PREVIEW_REVIEW"
    else:
        decision = "STOCKPILE_NEEDS_MORE_SOURCES"

    return json_safe(
        {
            "status": "snapshot",
            "decision": decision,
            "target_preview_count": target,
            "canary_count": canary,
            "active_preview_count": active,
            "approved_preview_count": approved,
            "held_preview_count": int(previews.get("held_preview_count", 0)),
            "rejected_preview_count": int(previews.get("rejected_preview_count", 0)),
            "unreviewed_preview_count": int(previews.get("unreviewed_preview_count", 0)),
            "candidate_count": candidate_count,
            "ready_candidate_count": ready_candidate_count,
            "source_candidate_count": source_candidates,
            "scanner": scanners,
            "scanner_active_count": scanner_active,
            "preflight": preflight,
            "live_queue_candidate_count": live_candidates,
            "blockers": blockers,
            "next_actions": list(dict.fromkeys(next_actions)),
            "source_operator": {
                "candidate_count": source_candidates,
                "queued_or_running_runs": len(source_operator.get("queued_or_running_runs", [])),
            },
            "campaign_control_room": {
                "candidate_count": candidate_count,
                "ready_candidate_count": ready_candidate_count,
                "first_batch_preview_count": int(campaign_room.get("first_batch_preview_count", 0) or 0),
            },
            **SAFE_FLAGS,
        }
    )


def run_lead_stockpile_health(
    target_preview_count: int = 50,
    canary_count: int = 20,
    limit: int = 100,
    apply: bool = False,
) -> dict[str, Any]:
    before = lead_stockpile_health_snapshot(target_preview_count, canary_count, limit)
    actions: dict[str, Any] = {"apply": bool(apply), "executed": []}
    if apply:
        if before["approved_preview_count"] < before["target_preview_count"] and before["source_candidate_count"] == 0:
            actions["executed"].append(
                {
                    "name": "regional_lead_discovery_cycle",
                    "result": regional_lead_discovery_cycle(limit_targets=3, per_target_limit=25, dry_run=False),
                }
            )
        if before["source_candidate_count"] > 0 and before["scanner_active_count"] <= 3:
            actions["executed"].append(
                {
                    "name": "advance_source_to_campaign",
                    "result": advance_source_to_campaign(None, min(limit, 25), dry_run=False, process_scout=True, prepare_campaigns=True),
                }
            )
        post_discovery = lead_stockpile_health_snapshot(target_preview_count, canary_count, limit)
        extra_advances = min(int(post_discovery.get("source_candidate_count", 0) or 0), 3)
        for _ in range(extra_advances):
            actions["executed"].append(
                {
                    "name": "advance_source_to_campaign",
                    "result": advance_source_to_campaign(None, min(limit, 25), dry_run=False, process_scout=True, prepare_campaigns=True),
                }
            )
        actions["executed"].append(
            {
                "name": "refresh_campaign_previews_if_needed",
                "result": refresh_campaign_previews_if_needed(min(limit, 100), stale_hours=12, dry_run=False),
            }
        )
        actions["executed"].append(
            {
                "name": "auto_review_campaign_previews",
                "result": auto_review_campaign_previews(min(limit, 50), apply=True, reconsider_held=True),
            }
        )
        actions["executed"].append({"name": "queue_outreach_preview", "result": queue_outreach_preview(min(canary_count, 20))})
        actions["executed"].append({"name": "campaign_preflight_batch", "result": campaign_preflight_batch(min(limit, 25))})

    after = lead_stockpile_health_snapshot(target_preview_count, canary_count, limit)
    row = execute(
        """
        INSERT INTO lead_stockpile_health_runs(
          status, decision, approved_preview_count, target_preview_count,
          candidate_count, source_candidate_count, scanner_active_count,
          action_json, result_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            "completed",
            after["decision"],
            after["approved_preview_count"],
            after["target_preview_count"],
            after["candidate_count"],
            after["source_candidate_count"],
            after["scanner_active_count"],
            Jsonb(actions),
            Jsonb({"before": before, "after": after, **SAFE_FLAGS}),
        ),
    )
    return json_safe(
        {
            "status": "completed",
            "run_id": str(row["id"]),
            "created_at": row["created_at"],
            "before": before,
            "after": after,
            "actions": actions,
            **SAFE_FLAGS,
        }
    )


def latest_lead_stockpile_health_runs(limit: int = 10) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 10), 50))
    rows = fetch_all(
        """
        SELECT id, status, decision, approved_preview_count, target_preview_count,
               candidate_count, source_candidate_count, scanner_active_count,
               action_json, result_json, created_at
        FROM lead_stockpile_health_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    return json_safe(
        {
            "status": "history",
            "runs": [
                {
                    "id": str(row["id"]),
                    "status": row["status"],
                    "decision": row["decision"],
                    "approved_preview_count": int(row["approved_preview_count"] or 0),
                    "target_preview_count": int(row["target_preview_count"] or 0),
                    "candidate_count": int(row["candidate_count"] or 0),
                    "source_candidate_count": int(row["source_candidate_count"] or 0),
                    "scanner_active_count": int(row["scanner_active_count"] or 0),
                    "action_json": row["action_json"] or {},
                    "result_json": row["result_json"] or {},
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
            **SAFE_FLAGS,
        }
    )
