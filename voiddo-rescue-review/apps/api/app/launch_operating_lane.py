from __future__ import annotations

from typing import Any

from .launch_readiness_scoreboard import launch_readiness_scoreboard
from .launch_repair_cycle import run_launch_repair_cycle
from .launch_repair_planner import launch_repair_plan
from .p0 import json_safe


PRIORITY = {
    "transport_gate_unexpectedly_allows_live_send": 100,
    "live_outreach_flags_not_blocked": 100,
    "global_kill_switch_enabled": 95,
    "mail_qa_not_pass": 90,
    "recent_spam_signal": 90,
    "recent_bounce_or_dsn": 85,
    "recent_rate_limit": 80,
    "checkout_not_ready": 75,
    "visual_qa_not_pass": 70,
    "huanshu_not_pass": 70,
    "secondary_design_plugins_not_pass": 65,
    "mailer_policy_score_not_ready": 60,
    "campaign_preview_pipeline_empty": 50,
    "buyer_journey_campaign_preview_missing": 45,
    "warmup_schedule_missing": 40,
}

LANES = {
    "transport_gate_unexpectedly_allows_live_send": "safety",
    "live_outreach_flags_not_blocked": "safety",
    "global_kill_switch_enabled": "runtime_controls",
    "mail_qa_not_pass": "mail_trust",
    "recent_spam_signal": "mail_signals",
    "recent_bounce_or_dsn": "mail_signals",
    "recent_rate_limit": "mail_signals",
    "checkout_not_ready": "checkout",
    "visual_qa_not_pass": "visual_quality",
    "huanshu_not_pass": "visual_quality",
    "secondary_design_plugins_not_pass": "visual_quality",
    "mailer_policy_score_not_ready": "mailer_policy",
    "campaign_preview_pipeline_empty": "campaign_pipeline",
    "buyer_journey_campaign_preview_missing": "scenario_pipeline",
    "warmup_schedule_missing": "warmup",
}


def _ranked_actions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = []
    for item in plan.get("actions") or []:
        code = item.get("blocker_code", "unknown")
        ranked.append(
            {
                **item,
                "priority_score": PRIORITY.get(code, 30),
                "lane": LANES.get(code, "review"),
                "next_step_type": "safe_auto" if item.get("auto_executable") else "review_task",
            }
        )
    ranked.sort(key=lambda row: (int(row["priority_score"]), row["next_step_type"] == "safe_auto"), reverse=True)
    return ranked


def launch_operating_lane_snapshot(limit: int = 25) -> dict[str, Any]:
    scoreboard = launch_readiness_scoreboard(limit)
    plan = launch_repair_plan(limit)
    ranked = _ranked_actions(plan)
    top = ranked[0] if ranked else None
    if not top:
        next_action = "keep_no_send_daily_loop_running_and_wait_for_explicit_launch_approval"
    elif top["next_step_type"] == "safe_auto":
        next_action = f"run_safe_auto:{top['action']}"
    else:
        next_action = f"create_review_task:{top['action']}"
    return json_safe(
        {
            "status": "blocked_work_available" if top else "no_blocked_work",
            "scoreboard_state": scoreboard.get("state"),
            "score": scoreboard.get("score"),
            "blocker_count": scoreboard.get("blocker_count"),
            "top_work_item": top,
            "ranked_work_items": ranked[:10],
            "next_action": next_action,
            "safe_auto_available": any(item["next_step_type"] == "safe_auto" for item in ranked),
            "review_required_available": any(item["next_step_type"] == "review_task" for item in ranked),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def advance_launch_operating_lane(limit: int = 25, execute_safe_auto: bool = False) -> dict[str, Any]:
    before = launch_operating_lane_snapshot(limit)
    cycle = run_launch_repair_cycle(limit, execute_safe_auto=execute_safe_auto and before["safe_auto_available"])
    after = launch_operating_lane_snapshot(limit)
    return json_safe(
        {
            "status": "advanced" if execute_safe_auto else "dry_run",
            "execute_safe_auto_requested": execute_safe_auto,
            "execute_safe_auto_applied": bool(execute_safe_auto and before["safe_auto_available"]),
            "before": before,
            "cycle": {
                "decision": cycle.get("decision"),
                "execution": cycle.get("execution"),
                "score_delta": cycle.get("score_delta"),
                "blocker_delta": cycle.get("blocker_delta"),
            },
            "after": after,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
