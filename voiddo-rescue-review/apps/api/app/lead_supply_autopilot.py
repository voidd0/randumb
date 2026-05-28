from __future__ import annotations

from typing import Any

from .contact_enrichment import contact_enrichment_candidates, run_public_contact_page_enrichment
from .lead_stockpile_health import lead_stockpile_health_snapshot, run_lead_stockpile_health
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _health_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": snapshot.get("decision"),
        "target_preview_count": int(snapshot.get("target_preview_count") or 0),
        "active_preview_count": int(snapshot.get("active_preview_count") or 0),
        "approved_preview_count": int(snapshot.get("approved_preview_count") or 0),
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


def _enrichment_summary(result: dict[str, Any]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    for item in result.get("results") or []:
        status = str(item.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "status": result.get("status"),
        "candidate_count": int(result.get("candidate_count") or 0),
        "scanned_count": int(result.get("scanned_count") or 0),
        "enriched_count": int(result.get("enriched_count") or 0),
        "skipped_count": int(result.get("skipped_count") or 0),
        "time_budget_exhausted": bool(result.get("time_budget_exhausted")),
        "result_status_counts": statuses,
        **SAFE_FLAGS,
    }


def _stockpile_action_summary(result: dict[str, Any]) -> dict[str, Any]:
    executed = []
    for action in (result.get("actions") or {}).get("executed", []) or []:
        action_result = action.get("result") or {}
        executed.append(
            {
                "name": action.get("name"),
                "status": action_result.get("status") or action_result.get("decision") or "completed",
                "created_sources": int(action_result.get("created_sources") or 0),
                "non_empty_sources": int(action_result.get("non_empty_sources") or 0),
                "found_count": int(action_result.get("found_count") or 0),
                "with_email_count": int(action_result.get("with_email_count") or 0),
                "created_scanner_jobs": int(action_result.get("created_scanner_jobs") or 0),
                "queued_count": int(action_result.get("queued_count") or 0),
                "processed": int(action_result.get("processed") or 0),
                **SAFE_FLAGS,
            }
        )
    return {
        "status": result.get("status"),
        "before": _health_summary(result.get("before") or {}),
        "after": _health_summary(result.get("after") or {}),
        "executed": executed,
        **SAFE_FLAGS,
    }


def lead_supply_autopilot(
    target_preview_count: int = 100,
    canary_count: int = 20,
    limit: int = 120,
    apply: bool = False,
    enrichment_limit: int = 10,
    enrichment_seconds: int = 90,
) -> dict[str, Any]:
    target = max(20, min(int(target_preview_count or 100), 500))
    canary = max(1, min(int(canary_count or 20), target))
    safe_limit = max(1, min(int(limit or 120), 250))
    safe_enrichment_limit = max(0, min(int(enrichment_limit or 0), 50))
    safe_enrichment_seconds = max(10, min(int(enrichment_seconds or 90), 180))
    before = lead_stockpile_health_snapshot(target, canary, safe_limit)
    actions: list[dict[str, Any]] = []

    if apply and int(before.get("approved_preview_count") or 0) < target and safe_enrichment_limit:
        candidates = contact_enrichment_candidates(safe_enrichment_limit)
        actions.append(
            {
                "name": "contact_enrichment_candidates",
                "candidate_count": int(candidates.get("candidate_count") or 0),
                **SAFE_FLAGS,
            }
        )
        if int(candidates.get("candidate_count") or 0) > 0:
            enrichment = run_public_contact_page_enrichment(
                safe_enrichment_limit,
                dry_run=False,
                max_pages_per_domain=4,
                max_seconds=safe_enrichment_seconds,
            )
            actions.append({"name": "public_contact_page_enrichment", "result": _enrichment_summary(enrichment), **SAFE_FLAGS})

    if apply:
        stockpile = run_lead_stockpile_health(target, canary, safe_limit, apply=True)
        actions.append({"name": "lead_stockpile_health_advance", "result": _stockpile_action_summary(stockpile), **SAFE_FLAGS})

    after = lead_stockpile_health_snapshot(target, canary, safe_limit)
    if int(after.get("approved_preview_count") or 0) >= target:
        decision = "SUPPLY_TARGET_READY_NO_SEND"
    elif int(after.get("approved_preview_count") or 0) >= canary and int(after.get("live_queue_candidate_count") or 0) >= canary:
        decision = "SUPPLY_CANARY_READY_BUILD_STOCKPILE_NO_SEND"
    else:
        decision = "SUPPLY_NEEDS_MORE_SAFE_DISCOVERY"

    return json_safe(
        {
            "status": "completed" if apply else "snapshot",
            "decision": decision,
            "apply": bool(apply),
            "before": _health_summary(before),
            "after": _health_summary(after),
            "actions": actions,
            **SAFE_FLAGS,
        }
    )
