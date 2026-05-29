from __future__ import annotations

import time
from typing import Any

from .campaign_preflight import campaign_preflight_batch
from .campaign_preview_refresh import refresh_campaign_previews_if_needed
from .campaign_preview_reviews import auto_review_campaign_previews
from .lead_discovery import regional_lead_discovery_cycle, stockpile_expansion_discovery_cycle
from .lead_stockpile_health import lead_stockpile_health_snapshot
from .lead_supply_autopilot import lead_supply_autopilot
from .p0 import json_safe, queue_outreach_preview
from .scanner_completion_watch import scanner_completion_watch
from .source_campaign_operator import advance_source_to_campaign


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": snapshot.get("decision"),
        "target_preview_count": int(snapshot.get("target_preview_count") or 0),
        "approved_preview_count": int(snapshot.get("approved_preview_count") or 0),
        "active_preview_count": int(snapshot.get("active_preview_count") or 0),
        "held_preview_count": int(snapshot.get("held_preview_count") or 0),
        "unreviewed_preview_count": int(snapshot.get("unreviewed_preview_count") or 0),
        "candidate_count": int(snapshot.get("candidate_count") or 0),
        "ready_candidate_count": int(snapshot.get("ready_candidate_count") or 0),
        "source_candidate_count": int(snapshot.get("source_candidate_count") or 0),
        "scanner_active_count": int(snapshot.get("scanner_active_count") or 0),
        "live_queue_candidate_count": int(snapshot.get("live_queue_candidate_count") or 0),
        "blockers": list(snapshot.get("blockers") or []),
        "next_actions": list(snapshot.get("next_actions") or []),
        **SAFE_FLAGS,
    }


def _progress_key(snapshot: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (
        int(snapshot.get("approved_preview_count") or 0),
        int(snapshot.get("active_preview_count") or 0),
        int(snapshot.get("candidate_count") or 0),
        int(snapshot.get("source_candidate_count") or 0),
        -int(snapshot.get("scanner_active_count") or 0),
    )


def _stockpile_ready(snapshot: dict[str, Any], target: int, canary: int) -> bool:
    approved = int(snapshot.get("approved_preview_count") or 0)
    ready_candidates = int(snapshot.get("ready_candidate_count") or 0)
    live_queue = int(snapshot.get("live_queue_candidate_count") or 0)
    return approved >= target and (live_queue >= canary or ready_candidates >= canary)


def _action_summary(action: dict[str, Any]) -> dict[str, Any]:
    source_queue = action.get("source_queue") or {}
    scout_processing = action.get("scout_processing") or {}
    campaign_control_room = action.get("campaign_control_room") or {}
    preview_generation = campaign_control_room.get("preview_generation") or {}
    scout_results = scout_processing.get("results") or []
    scout_found = sum(int(item.get("found") or item.get("found_count") or 0) for item in scout_results if isinstance(item, dict))
    scout_accepted = sum(int(item.get("accepted") or item.get("accepted_count") or 0) for item in scout_results if isinstance(item, dict))
    scout_jobs = sum(int(item.get("scanner_jobs") or item.get("created_scanner_jobs") or 0) for item in scout_results if isinstance(item, dict))
    blockers = action.get("blockers") or []
    errors = action.get("errors") or []
    return {
        "name": action.get("name"),
        "status": action.get("status") or action.get("decision") or "completed",
        "decision": action.get("decision"),
        "created_sources": int(action.get("created_sources") or 0),
        "non_empty_sources": int(action.get("non_empty_sources") or 0),
        "accepted_count": int(
            action.get("accepted_count") or scout_processing.get("accepted_count") or scout_processing.get("accepted") or scout_accepted or 0
        ),
        "found_count": int(action.get("found_count") or scout_processing.get("found_count") or scout_processing.get("found") or scout_found or 0),
        "created_scanner_jobs": int(
            action.get("created_scanner_jobs")
            or source_queue.get("created_scanner_jobs")
            or scout_processing.get("created_scanner_jobs")
            or scout_processing.get("scanner_jobs")
            or scout_jobs
            or 0
        ),
        "queued_count": int(action.get("queued_count") or source_queue.get("queued_count") or 0),
        "processed": int(action.get("processed") or scout_processing.get("processed") or 0),
        "campaign_previews_created": int(action.get("campaign_previews_created") or preview_generation.get("created") or 0),
        "blocker_count": len(blockers),
        "error_count": len(errors),
        "error_types": sorted({str(item.get("error") or item.get("error_type") or "unknown") for item in errors if isinstance(item, dict)})[:5],
        **SAFE_FLAGS,
    }


def _first_ready_source_id(result: dict[str, Any]) -> str | None:
    for item in result.get("results") or []:
        if not isinstance(item, dict):
            continue
        source_id = item.get("source_id")
        readiness = item.get("readiness") or {}
        if source_id and item.get("source_status") in {"preflight_ready", None} and readiness.get("status") == "PASS_SOURCE_READY":
            return str(source_id)
    return None


def _remaining_seconds(started: float, budget_seconds: int) -> int:
    return max(0, int(budget_seconds - (time.monotonic() - started)))


def _wait_for_scanner_worker_progress(
    target: int,
    canary: int,
    safe_limit: int,
    max_wait_seconds: int,
) -> dict[str, Any]:
    wait_budget = max(0, min(int(max_wait_seconds or 0), 180))
    if wait_budget <= 0:
        return {"name": "scanner_worker_progress_wait", "status": "skipped_no_budget", **SAFE_FLAGS}
    before = lead_stockpile_health_snapshot(target, canary, safe_limit)
    before_active = int(before.get("scanner_active_count") or 0)
    if before_active <= 0:
        return {"name": "scanner_worker_progress_wait", "status": "skipped_no_active_scanner_jobs", "before_active": before_active, **SAFE_FLAGS}
    started = time.monotonic()
    watches: list[dict[str, Any]] = []
    after = before
    while time.monotonic() - started < wait_budget:
        time.sleep(min(10, max(1, wait_budget - int(time.monotonic() - started))))
        watch = scanner_completion_watch(safe_limit, min_new_completed=1, dry_run=False)
        watches.append(_action_summary({"name": "scanner_completion_watch_wait", **watch}))
        after = lead_stockpile_health_snapshot(target, canary, safe_limit)
        if int(after.get("scanner_active_count") or 0) < before_active:
            break
        if int(after.get("approved_preview_count") or 0) > int(before.get("approved_preview_count") or 0):
            break
        if int(after.get("ready_candidate_count") or 0) > int(before.get("ready_candidate_count") or 0):
            break
    return {
        "name": "scanner_worker_progress_wait",
        "status": "completed",
        "waited_seconds": int(time.monotonic() - started),
        "before_active": before_active,
        "after_active": int(after.get("scanner_active_count") or 0),
        "before_approved": int(before.get("approved_preview_count") or 0),
        "after_approved": int(after.get("approved_preview_count") or 0),
        "before_ready": int(before.get("ready_candidate_count") or 0),
        "after_ready": int(after.get("ready_candidate_count") or 0),
        "watches": watches[-3:],
        **SAFE_FLAGS,
    }


def lead_supply_buildout(
    target_preview_count: int = 100,
    canary_count: int = 20,
    limit: int = 120,
    max_cycles: int = 4,
    max_seconds: int = 240,
    enrichment_limit: int = 0,
    apply: bool = False,
) -> dict[str, Any]:
    target = max(20, min(int(target_preview_count or 100), 500))
    canary = max(1, min(int(canary_count or 20), target))
    safe_limit = max(1, min(int(limit or 120), 250))
    cycles = max(1, min(int(max_cycles or 4), 10))
    seconds = max(15, min(int(max_seconds or 240), 900))
    safe_enrichment_limit = max(0, min(int(enrichment_limit or 0), 25))
    started = time.monotonic()
    before = lead_stockpile_health_snapshot(target, canary, safe_limit)
    current = before
    cycle_results: list[dict[str, Any]] = []
    previous_key = _progress_key(before)
    stop_reason = "max_cycles_reached"

    if not apply:
        return json_safe(
            {
                "status": "snapshot",
                "decision": "SUPPLY_BUILDOUT_DRY_RUN_NO_SEND",
                "apply": False,
                "target_preview_count": target,
                "canary_count": canary,
                "max_cycles": cycles,
                "max_seconds": seconds,
                "enrichment_limit": safe_enrichment_limit,
                "before": _compact_snapshot(before),
                "after": _compact_snapshot(before),
                "cycles": [],
                **SAFE_FLAGS,
            }
        )

    for index in range(cycles):
        if time.monotonic() - started > seconds:
            stop_reason = "time_budget_exhausted"
            break
        if _stockpile_ready(current, target, canary):
            stop_reason = "target_ready"
            break

        actions: list[dict[str, Any]] = []
        new_source_hint = False
        source_hint_id: str | None = None
        if _remaining_seconds(started, seconds) <= 8:
            stop_reason = "time_budget_exhausted"
            break
        if safe_enrichment_limit > 0 and _remaining_seconds(started, seconds) > 15:
            autopilot = lead_supply_autopilot(
                target,
                canary,
                safe_limit,
                apply=True,
                enrichment_limit=safe_enrichment_limit,
                enrichment_seconds=min(20, max(8, _remaining_seconds(started, seconds) // 3)),
            )
            actions.append(
                {
                    "name": "lead_supply_autopilot_enrichment",
                    "status": autopilot.get("status"),
                    "decision": autopilot.get("decision"),
                    "before": autopilot.get("before"),
                    "after": autopilot.get("after"),
                    **SAFE_FLAGS,
                }
            )
            current = lead_stockpile_health_snapshot(target, canary, safe_limit)

        if (
            int(current.get("approved_preview_count") or 0) < target
            and int(current.get("approved_preview_count") or 0) >= canary
            and int(current.get("source_candidate_count") or 0) == 0
        ):
            remaining_seconds = _remaining_seconds(started, seconds)
            if remaining_seconds <= 15:
                stop_reason = "time_budget_exhausted"
                break
            expansion = stockpile_expansion_discovery_cycle(
                limit_targets=1,
                per_target_limit=20,
                dry_run=False,
                max_seconds=min(25, remaining_seconds),
            )
            expansion_summary = _action_summary({"name": "stockpile_expansion_discovery_cycle", **expansion})
            actions.append(expansion_summary)
            source_hint_id = source_hint_id or _first_ready_source_id(expansion)
            new_source_hint = (
                new_source_hint
                or bool(source_hint_id)
                or int(expansion_summary.get("non_empty_sources") or 0) > 0
                or int(expansion_summary.get("found_count") or 0) > 0
            )
            current = lead_stockpile_health_snapshot(target, canary, safe_limit)

        if (
            int(current.get("approved_preview_count") or 0) < target
            and int(current.get("source_candidate_count") or 0) == 0
            and not new_source_hint
            and _remaining_seconds(started, seconds) > 28
        ):
            discovery = regional_lead_discovery_cycle(limit_targets=1, per_target_limit=15, dry_run=False)
            discovery_summary = _action_summary({"name": "regional_lead_discovery_cycle", **discovery})
            actions.append(discovery_summary)
            source_hint_id = source_hint_id or _first_ready_source_id(discovery)
            new_source_hint = (
                new_source_hint
                or bool(source_hint_id)
                or int(discovery_summary.get("non_empty_sources") or 0) > 0
                or int(discovery_summary.get("found_count") or 0) > 0
            )

        refreshed = lead_stockpile_health_snapshot(target, canary, safe_limit)
        if (
            (int(refreshed.get("source_candidate_count") or 0) > 0 or new_source_hint)
            and int(refreshed.get("scanner_active_count") or 0) <= 3
            and _remaining_seconds(started, seconds) > 10
        ):
            advance = advance_source_to_campaign(
                source_hint_id,
                min(safe_limit, 20),
                dry_run=False,
                process_scout=True,
                prepare_campaigns=True,
            )
            actions.append(_action_summary({"name": "advance_source_to_campaign", **advance}))

        if _remaining_seconds(started, seconds) > 8:
            watch = scanner_completion_watch(safe_limit, min_new_completed=1, dry_run=False)
            actions.append(_action_summary({"name": "scanner_completion_watch", **watch}))

        refreshed = lead_stockpile_health_snapshot(target, canary, safe_limit)
        if int(refreshed.get("scanner_active_count") or 0) > 0 and _remaining_seconds(started, seconds) > 15:
            wait = _wait_for_scanner_worker_progress(target, canary, safe_limit, min(20, _remaining_seconds(started, seconds) - 8))
            actions.append(wait)
            refreshed = lead_stockpile_health_snapshot(target, canary, safe_limit)
        if int(refreshed.get("ready_candidate_count") or 0) > int(refreshed.get("active_preview_count") or 0):
            refresh = refresh_campaign_previews_if_needed(min(safe_limit, 80), stale_hours=12, dry_run=False)
            actions.append(_action_summary({"name": "refresh_campaign_previews_if_needed", **refresh}))
        if int(refreshed.get("held_preview_count") or 0) > 0 or int(refreshed.get("unreviewed_preview_count") or 0) > 0:
            review = auto_review_campaign_previews(min(safe_limit, 40), apply=True, reconsider_held=True)
            actions.append(_action_summary({"name": "auto_review_campaign_previews", **review}))
        if int(refreshed.get("live_queue_candidate_count") or 0) < canary:
            preview = queue_outreach_preview(min(canary, 20))
            actions.append(_action_summary({"name": "queue_outreach_preview", **preview}))
        preflight = campaign_preflight_batch(min(safe_limit, 15))
        actions.append(_action_summary({"name": "campaign_preflight_batch", **preflight}))

        current = lead_stockpile_health_snapshot(target, canary, safe_limit)
        current_key = _progress_key(current)
        cycle_results.append(
            {
                "cycle": index + 1,
                "actions": actions,
                "snapshot": _compact_snapshot(current),
                "progress_key": list(current_key),
                **SAFE_FLAGS,
            }
        )
        if current_key <= previous_key and int(current.get("scanner_active_count") or 0) > 0:
            stop_reason = "waiting_for_scanner_worker"
            break
        if current_key <= previous_key and int(current.get("source_candidate_count") or 0) == 0:
            stop_reason = "no_safe_progress_available"
            break
        previous_key = current_key

    after = lead_stockpile_health_snapshot(target, canary, safe_limit)
    approved = int(after.get("approved_preview_count") or 0)
    live_queue = int(after.get("live_queue_candidate_count") or 0)
    ready_candidates = int(after.get("ready_candidate_count") or 0)
    if approved >= target and (live_queue >= canary or ready_candidates >= canary):
        decision = "SUPPLY_BUILDOUT_TARGET_READY_NO_SEND"
    elif approved >= canary and live_queue >= canary:
        decision = "SUPPLY_BUILDOUT_CANARY_READY_NO_SEND"
    else:
        decision = "SUPPLY_BUILDOUT_NEEDS_MORE_CYCLES_NO_SEND"

    return json_safe(
        {
            "status": "completed",
            "decision": decision,
            "apply": True,
            "stop_reason": stop_reason,
            "target_preview_count": target,
            "canary_count": canary,
            "max_cycles": cycles,
            "max_seconds": seconds,
            "enrichment_limit": safe_enrichment_limit,
            "cycle_count": len(cycle_results),
            "before": _compact_snapshot(before),
            "after": _compact_snapshot(after),
            "cycles": cycle_results,
            **SAFE_FLAGS,
        }
    )
