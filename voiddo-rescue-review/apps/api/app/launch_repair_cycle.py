from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute
from .launch_readiness_scoreboard import launch_readiness_scoreboard
from .launch_repair_planner import execute_launch_repair_plan, launch_repair_plan
from .p0 import json_safe


def _compact_scoreboard(scoreboard: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": scoreboard.get("state"),
        "score": int(scoreboard.get("score") or 0),
        "blocker_count": int(scoreboard.get("blocker_count") or 0),
        "blocker_codes": [item.get("code") for item in scoreboard.get("blockers") or []],
        "live_outreach_allowed": bool(scoreboard.get("live_outreach_allowed", False)),
        "send_mail": bool(scoreboard.get("send_mail", False)),
        "smtp_called": bool(scoreboard.get("smtp_called", False)),
        "raw_recipient_addresses_included": bool(scoreboard.get("raw_recipient_addresses_included", False)),
        "secrets_included": bool(scoreboard.get("secrets_included", False)),
    }


def run_launch_repair_cycle(limit: int = 25, execute_safe_auto: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    before = launch_readiness_scoreboard(safe_limit)
    plan = launch_repair_plan(safe_limit)
    execution = execute_launch_repair_plan(safe_limit, dry_run=not execute_safe_auto)
    after = launch_readiness_scoreboard(safe_limit)
    before_compact = _compact_scoreboard(before)
    after_compact = _compact_scoreboard(after)
    score_delta = after_compact["score"] - before_compact["score"]
    blocker_delta = before_compact["blocker_count"] - after_compact["blocker_count"]
    unexpected_send_flags = any(
        [
            before_compact["send_mail"],
            before_compact["smtp_called"],
            before_compact["live_outreach_allowed"],
            after_compact["send_mail"],
            after_compact["smtp_called"],
            after_compact["live_outreach_allowed"],
            execution.get("send_mail"),
            execution.get("smtp_called"),
            execution.get("live_outreach_allowed"),
        ]
    )
    if unexpected_send_flags:
        decision = "FAIL_SEND_FLAG_REGRESSION"
    elif not execute_safe_auto:
        decision = "DRY_RUN_READY"
    elif score_delta > 0 or blocker_delta > 0:
        decision = "NO_SEND_PROGRESS_RECORDED"
    else:
        decision = "NO_SEND_REVIEW_REQUIRED"
    event_id = None
    if execute_safe_auto or unexpected_send_flags:
        event = execute(
            """
            INSERT INTO system_events(type, severity, message, payload_json)
            VALUES ('launch_repair.cycle', %s, 'Launch repair cycle evaluated no-send progress', %s)
            RETURNING id
            """,
            (
                "critical" if unexpected_send_flags else "info",
                Jsonb(
                    {
                        "decision": decision,
                        "execute_safe_auto": execute_safe_auto,
                        "before": before_compact,
                        "after": after_compact,
                        "score_delta": score_delta,
                        "blocker_delta": blocker_delta,
                        "execution_status": execution.get("status"),
                        "executed_count": execution.get("executed_count", 0),
                        "review_task_count": execution.get("review_task_count", 0),
                        "send_mail": False,
                        "smtp_called": False,
                        "live_outreach_allowed": False,
                        "raw_recipient_addresses_included": False,
                        "secrets_included": False,
                    }
                ),
            ),
        )
        event_id = str(event["id"]) if event else None
    return json_safe(
        {
            "decision": decision,
            "execute_safe_auto": execute_safe_auto,
            "before": before_compact,
            "plan": {
                "status": plan.get("status"),
                "safe_auto_count": plan.get("safe_auto_count", 0),
                "review_required_count": plan.get("review_required_count", 0),
                "actions": plan.get("actions", []),
            },
            "execution": {
                "status": execution.get("status"),
                "executed_count": execution.get("executed_count", 0),
                "review_task_count": execution.get("review_task_count", 0),
            },
            "after": after_compact,
            "score_delta": score_delta,
            "blocker_delta": blocker_delta,
            "system_event_id": event_id,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
