from __future__ import annotations

from typing import Any

from .campaign_preflight import campaign_preflight_batch
from .canary_batch_quality import canary_batch_quality
from .canary_clean_window_forecast import canary_clean_window_forecast
from .canary_operator_packet import build_canary_operator_packet
from .db import execute
from .launch_activation import launch_activation_readiness
from .outreach_live_queue import live_outreach_queue_candidates
from .p0 import json_safe
from psycopg.types.json import Jsonb


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "sends_started": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def build_post_clean_activation_packet(limit: int = 20, store: bool = True) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 20))
    clean_window = canary_clean_window_forecast(24, store=store)
    if clean_window.get("status") != "clean":
        result = json_safe(
            {
                "status": "not_due",
                "decision": "WAIT_CLEAN_WINDOW",
                "clean_window_status": clean_window.get("status"),
                "eligible_after": clean_window.get("eligible_after"),
                "seconds_remaining": int(clean_window.get("seconds_remaining") or 0),
                "blockers": ["recent_mail_risk_signal_window_not_clear"],
                **SAFE_FLAGS,
            }
        )
        if store:
            execute(
                """
                INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at)
                VALUES ('post_clean_activation_packet_agent', 'blocked', %s, now(), now())
                """,
                (Jsonb(result),),
            )
        return result

    preflight = campaign_preflight_batch(safe_limit)
    quality = canary_batch_quality(safe_limit, store=store)
    activation = launch_activation_readiness(safe_limit)
    packet = build_canary_operator_packet(safe_limit, store=store, run_checkout_simulation=False)
    queue = live_outreach_queue_candidates(safe_limit)

    blockers: list[str] = []
    if preflight.get("status") != "completed" or int(preflight.get("failed_count") or 0) > 0:
        blockers.append("campaign_preflight_not_clean")
    if int(preflight.get("passed_count") or 0) <= 0:
        blockers.append("campaign_preflight_pass_missing")
    if quality.get("decision") != "PASS_CANARY_BATCH_QUALITY":
        blockers.append("canary_quality_not_pass")
    if activation.get("decision") != "READY_FOR_OPERATOR_ENV_ACTIVATION":
        blockers.append("activation_not_ready")
    if packet.get("decision") != "READY_FOR_REDACTED_CANARY_OPERATOR_REVIEW":
        blockers.append("operator_packet_not_ready")
    if int(queue.get("candidate_count") or 0) < safe_limit:
        blockers.append("live_queue_candidate_count_below_limit")

    result = json_safe(
        {
            "status": "ready" if not blockers else "blocked",
            "decision": "READY_NO_SEND_ACTIVATION_PACKET" if not blockers else "BLOCKED_NO_SEND_ACTIVATION_PACKET",
            "limit": safe_limit,
            "blockers": sorted(set(blockers)),
            "clean_window_status": clean_window.get("status"),
            "campaign_preflight_status": preflight.get("status"),
            "campaign_preflight_campaign_count": int(preflight.get("campaign_count") or 0),
            "campaign_preflight_passed_count": int(preflight.get("passed_count") or 0),
            "campaign_preflight_failed_count": int(preflight.get("failed_count") or 0),
            "canary_quality_decision": quality.get("decision"),
            "canary_candidate_count": int(quality.get("candidate_count") or 0),
            "activation_decision": activation.get("decision"),
            "activation_blockers": activation.get("blockers") or [],
            "operator_packet_decision": packet.get("decision"),
            "operator_packet_blockers": packet.get("blockers") or [],
            "live_queue_candidate_count": int(queue.get("candidate_count") or 0),
            "next_action": "keep_live_flags_locked_until_operator_policy_allows_activation" if not blockers else "repair_activation_packet_blockers",
            **SAFE_FLAGS,
        }
    )
    if store:
        execute(
            """
            INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at)
            VALUES ('post_clean_activation_packet_agent', %s, %s, now(), now())
            """,
            ("completed" if not blockers else "blocked", Jsonb(result)),
        )
    return result
