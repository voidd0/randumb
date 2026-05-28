from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from .canary_operator_packet import build_canary_operator_packet
from .db import execute, fetch_one
from .outreach_live_queue import live_outreach_queue_candidates
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _next_business_window_start(now: datetime | None = None) -> datetime:
    tz = ZoneInfo("Asia/Jerusalem")
    current = (now or datetime.now(tz)).astimezone(tz)
    start = datetime.combine(current.date(), time(9, 30), tzinfo=tz)
    end = datetime.combine(current.date(), time(16, 30), tzinfo=tz)
    if current <= start:
        return start
    if current <= end:
        return current.replace(second=0, microsecond=0) + timedelta(minutes=20)
    return start + timedelta(days=1)


def build_canary_send_window_plan(limit: int = 20, store: bool = True) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 20))
    packet = build_canary_operator_packet(safe_limit, store=True, run_checkout_simulation=False)
    queue = live_outreach_queue_candidates(safe_limit)
    candidates = list(queue.get("candidates") or [])[:safe_limit]
    start = _next_business_window_start()
    spacing = timedelta(minutes=24)
    plan: list[dict[str, Any]] = []
    domain_hour_counts: dict[tuple[str, str], int] = {}
    blockers: list[str] = []
    if packet.get("decision") != "READY_FOR_REDACTED_CANARY_OPERATOR_REVIEW":
        blockers.append("operator_packet_not_ready")
    if len(candidates) < safe_limit:
        blockers.append("insufficient_canary_candidates")

    for index, candidate in enumerate(candidates):
        scheduled_for = start + spacing * index
        hour_key = scheduled_for.strftime("%Y-%m-%dT%H")
        domain_hash = str(candidate.get("recipient_domain_hash") or "")
        key = (domain_hash, hour_key)
        domain_hour_counts[key] = domain_hour_counts.get(key, 0) + 1
        if domain_hour_counts[key] > 5:
            blockers.append("hourly_domain_cap_exceeded_in_plan")
        plan.append(
            {
                "slot": index + 1,
                "scheduled_for": scheduled_for.astimezone(timezone.utc).isoformat(),
                "local_time": scheduled_for.isoformat(),
                "outreach_message_id": candidate.get("outreach_message_id"),
                "campaign_id": candidate.get("campaign_id"),
                "audit_slug": candidate.get("audit_slug"),
                "public_domain": candidate.get("domain"),
                "recipient_domain_hash": domain_hash,
                "post_send_observer_after_minutes": 30,
                "rollback_if_blocker": True,
            }
        )

    result = json_safe(
        {
            "status": "ready" if not blockers else "blocked",
            "decision": "READY_NO_SEND_CANARY_WINDOW_PLAN" if not blockers else "BLOCKED_CANARY_WINDOW_PLAN",
            "limit": safe_limit,
            "planned_count": len(plan),
            "blockers": sorted(set(blockers)),
            "operator_packet_decision": packet.get("decision"),
            "launch_score": packet.get("launch_score"),
            "rehearsal_steps": packet.get("rehearsal_steps"),
            "first_slot_utc": plan[0]["scheduled_for"] if plan else None,
            "last_slot_utc": plan[-1]["scheduled_for"] if plan else None,
            "max_hourly_domain_count": max(domain_hour_counts.values()) if domain_hour_counts else 0,
            "daily_cap": 20,
            "hourly_domain_cap": 5,
            "observer_policy": "run_post_send_observer_30_minutes_after_each_send_and_pause_on_blocker",
            "rollback_policy": "set_OUTREACH_PAUSED_true_and_FIRST_LIVE_SEND_FLAG_false_on_any_blocker",
            "plan": plan,
            **SAFE_FLAGS,
        }
    )
    if store:
        execute(
            "INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at) VALUES ('canary_send_window_plan_agent', %s, %s, now(), now())",
            ("completed" if not blockers else "blocked", Jsonb(result)),
        )
    return result


def latest_canary_send_window_plan() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT result_json
        FROM agent_runs
        WHERE agent = 'canary_send_window_plan_agent'
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    return dict(row["result_json"]) if row and row.get("result_json") else {"decision": "MISSING_CANARY_WINDOW_PLAN", "blockers": ["window_plan_not_generated"], **SAFE_FLAGS}
