from __future__ import annotations

from typing import Any, Callable

from psycopg.types.json import Jsonb

from .buyer_journey_scenarios import run_buyer_journey_scenario
from .campaign_control_room import prepare_campaign_control_room
from .db import execute, fetch_one
from .launch_readiness_scoreboard import launch_readiness_scoreboard
from .mailer_control_room import mailer_policy_score
from .p0 import build_warmup_calendar, json_safe, run_mail_qa


ACTION_CATALOG: dict[str, dict[str, Any]] = {
    "checkout_not_ready": {
        "action": "create_checkout_configuration_review_task",
        "risk": "HIGH_RISK",
        "reason": "checkout credentials/configuration changes must stay explicit and secret-safe",
    },
    "mail_qa_not_pass": {
        "action": "run_mail_qa_without_deliverability_send",
        "risk": "SAFE_AUTO",
        "handler": "mail_qa_no_send",
    },
    "recent_bounce_or_dsn": {
        "action": "record_mail_policy_score_and_wait_clean_window",
        "risk": "SAFE_AUTO",
        "handler": "mailer_policy_score",
    },
    "recent_rate_limit": {
        "action": "record_mail_policy_score_and_wait_clean_window",
        "risk": "SAFE_AUTO",
        "handler": "mailer_policy_score",
    },
    "recent_spam_signal": {
        "action": "create_mail_signal_review_task",
        "risk": "HIGH_RISK",
    },
    "visual_qa_not_pass": {
        "action": "create_visual_qa_review_task",
        "risk": "MEDIUM_RISK",
    },
    "huanshu_not_pass": {
        "action": "create_huanshu_review_task",
        "risk": "MEDIUM_RISK",
    },
    "secondary_design_plugins_not_pass": {
        "action": "create_secondary_design_plugin_review_task",
        "risk": "MEDIUM_RISK",
    },
    "warmup_schedule_missing": {
        "action": "prepare_warmup_calendar_without_sending",
        "risk": "MEDIUM_RISK",
        "handler": "warmup_calendar_no_send",
    },
    "buyer_journey_campaign_preview_missing": {
        "action": "run_no_send_buyer_journey_scenario",
        "risk": "SAFE_AUTO",
        "handler": "buyer_journey_scenario_no_send",
    },
    "campaign_preview_pipeline_empty": {
        "action": "refresh_campaign_control_room_preview_only",
        "risk": "SAFE_AUTO",
        "handler": "campaign_preview_refresh",
    },
    "mailer_policy_score_not_ready": {
        "action": "recompute_mailer_policy_score",
        "risk": "SAFE_AUTO",
        "handler": "mailer_policy_score",
    },
    "transport_gate_unexpectedly_allows_live_send": {
        "action": "create_transport_gate_review_task",
        "risk": "HIGH_RISK",
    },
    "live_outreach_flags_not_blocked": {
        "action": "create_live_flag_review_task",
        "risk": "HIGH_RISK",
    },
    "global_kill_switch_enabled": {
        "action": "create_runtime_control_review_task",
        "risk": "HIGH_RISK",
    },
}


def _review_task_for_action(action: dict[str, Any], blocker: dict[str, Any]) -> dict[str, Any]:
    title = f"Review launch blocker: {blocker['code']}"
    existing = fetch_one(
        """
        SELECT id, status
        FROM codex_tasks
        WHERE type = 'deployment_issue'
          AND status IN ('open', 'review_required')
          AND title = %s
          AND input_json->>'source' = 'launch_repair_planner'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (title,),
    )
    if existing:
        return {"status": "existing_review_task", "task_id": str(existing["id"])}
    row = execute(
        """
        INSERT INTO codex_tasks(type, priority, status, title, description, input_json)
        VALUES ('deployment_issue', %s, 'open', %s, %s, %s)
        RETURNING id
        """,
        (
            "high" if action["risk"] == "HIGH_RISK" else "medium",
            title,
            "Launch readiness blocker requires a safe review or configuration fix.",
            Jsonb(
                {
                    "source": "launch_repair_planner",
                    "blocker": blocker,
                    "action": action,
                    "constraints": [
                        "no_live_outreach",
                        "no_warmup_forcing",
                        "no_secret_exposure",
                        "no_non_rescue_changes",
                    ],
                    "send_mail": False,
                    "smtp_called": False,
                    "live_outreach_allowed": False,
                    "raw_recipient_addresses_included": False,
                    "secrets_included": False,
                }
            ),
        ),
    )
    return {"status": "created_review_task", "task_id": str(row["id"]) if row else None}


def launch_repair_plan(limit: int = 25) -> dict[str, Any]:
    scoreboard = launch_readiness_scoreboard(limit)
    blockers = scoreboard.get("blockers") or []
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for blocker in blockers:
        code = str(blocker.get("code") or "unknown")
        if code in seen:
            continue
        seen.add(code)
        spec = ACTION_CATALOG.get(
            code,
            {"action": "create_unknown_launch_blocker_review_task", "risk": "HIGH_RISK"},
        )
        actions.append(
            {
                "blocker_code": code,
                "severity": blocker.get("severity", "high"),
                "action": spec["action"],
                "risk": spec["risk"],
                "handler": spec.get("handler"),
                "auto_executable": spec["risk"] == "SAFE_AUTO" and bool(spec.get("handler")),
                "detail_included": bool(blocker.get("detail") is not None),
            }
        )
    return json_safe(
        {
            "status": "planned" if actions else "no_blockers",
            "scoreboard_state": scoreboard["state"],
            "score": scoreboard["score"],
            "blocker_count": len(blockers),
            "actions": actions,
            "safe_auto_count": len([item for item in actions if item["auto_executable"]]),
            "review_required_count": len([item for item in actions if not item["auto_executable"]]),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def _handlers() -> dict[str, Callable[[], dict[str, Any]]]:
    return {
        "mail_qa_no_send": lambda: run_mail_qa(allow_deliverability_send=False),
        "mailer_policy_score": mailer_policy_score,
        "buyer_journey_scenario_no_send": lambda: run_buyer_journey_scenario(cleanup=True),
        "campaign_preview_refresh": lambda: prepare_campaign_control_room(100, 70, dry_run=True),
        "warmup_calendar_no_send": lambda: build_warmup_calendar(),
    }


def execute_launch_repair_plan(limit: int = 25, dry_run: bool = True) -> dict[str, Any]:
    plan = launch_repair_plan(limit)
    handlers = _handlers()
    results: list[dict[str, Any]] = []
    if dry_run:
        return {
            **plan,
            "status": "dry_run",
            "executed_count": 0,
            "review_task_count": 0,
            "results": [],
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        }
    for action in plan["actions"]:
        risk = action["risk"]
        handler_key = action.get("handler")
        blocker = {"code": action["blocker_code"], "severity": action.get("severity", "high")}
        if risk != "SAFE_AUTO" or not handler_key:
            task = _review_task_for_action(action, blocker)
            results.append({**action, **task, "executed": False})
            continue
        result = handlers[handler_key]()
        results.append(
            {
                **action,
                "executed": True,
                "result": json_safe(result),
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
            }
        )
    event = execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('launch_repair.plan_executed', 'info', 'Launch repair planner executed safe actions and review tasks', %s)
        RETURNING id
        """,
        (
            Jsonb(
                {
                    "scoreboard_state": plan["scoreboard_state"],
                    "executed_count": len([item for item in results if item.get("executed")]),
                    "review_task_count": len([item for item in results if str(item.get("status", "")).endswith("review_task")]),
                    "send_mail": False,
                    "smtp_called": False,
                    "live_outreach_allowed": False,
                }
            ),
        ),
    )
    return json_safe(
        {
            **plan,
            "status": "executed",
            "executed_count": len([item for item in results if item.get("executed")]),
            "review_task_count": len([item for item in results if str(item.get("status", "")).endswith("review_task")]),
            "system_event_id": str(event["id"]) if event else None,
            "results": results,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
