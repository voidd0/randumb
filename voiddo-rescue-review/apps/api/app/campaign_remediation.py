from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .campaign_actions import run_campaign_action
from .campaign_preflight import campaign_preflight
from .campaign_preview_quality import campaign_preview_quality_pack
from .db import execute, fetch_all, fetch_one
from .mailer_control_room import mailer_policy_score
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _latest_failed_preflights(limit: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in fetch_all(
            """
            SELECT *
            FROM (
              SELECT DISTINCT ON (r.campaign_id)
                     r.id, r.campaign_id, r.decision, r.checked_count, r.ready_count,
                     r.blocker_count, r.result_json, r.created_at,
                     c.name, c.status AS campaign_status, c.country, c.language, c.niche, c.offer_key
              FROM campaign_preflight_runs r
              LEFT JOIN campaigns c ON c.id = r.campaign_id
              WHERE r.campaign_id IS NOT NULL
              ORDER BY r.campaign_id, r.created_at DESC
            ) latest
            WHERE decision <> 'PASS_NO_SEND_PREFLIGHT'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (max(1, min(int(limit or 25), 100)),),
        )
    ]


def _action_for_blocker(blocker: str) -> dict[str, Any]:
    mapping = {
        "preview_quality_not_pass": ("refresh_campaign_preview_quality", "SAFE_AUTO", "Regenerate preview evidence and rerun campaign preview quality."),
        "no_ready_preview_rows": ("refresh_campaign_previews", "SAFE_AUTO", "Rebuild preview rows from qualified leads without sending mail."),
        "audit_strength_below_70": ("improve_audit_evidence", "MEDIUM_RISK", "Create scanner/audit task to improve public evidence quality."),
        "mailer_policy_not_ready": ("repair_mailer_policy_blockers", "SAFE_AUTO", "Run mailer policy blocker repair without sending outreach."),
        "transport_unexpectedly_allows_live_send": ("safety_lock_campaign", "HIGH_RISK", "Safety review required because transport unexpectedly allowed live send."),
        "transport_unexpected_block_reason": ("review_transport_gate_reason", "MEDIUM_RISK", "Review transport gate reason and align allowed safe blockers."),
    }
    action, risk, note = mapping.get(blocker, ("review_campaign_blocker", "MEDIUM_RISK", "Review campaign blocker and create a focused fix."))
    return {"blocker": blocker, "action": action, "risk": risk, "note": note, "send_mail": False, "live_outreach_allowed": False}


def _task_type_for_action(action: str) -> str:
    if action in {"improve_audit_evidence", "refresh_campaign_preview_quality", "refresh_campaign_previews"}:
        return "scanner_failed_case"
    if action == "repair_mailer_policy_blockers":
        return "deployment_issue"
    if action.startswith("review_transport") or action == "safety_lock_campaign":
        return "deployment_issue"
    return "campaign_blocker"


def _create_task(campaign_id: str, action: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any]:
    title = f"Rescue campaign remediation: {action['action']}"
    existing = fetch_one(
        """
        SELECT id
        FROM codex_tasks
        WHERE status IN ('open', 'review_required')
          AND input_json->>'source' = 'campaign_remediation_planner'
          AND input_json->>'campaign_id' = %s
          AND input_json->>'action' = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (campaign_id, action["action"]),
    )
    if existing:
        return {"status": "existing", "task_id": str(existing["id"]), "action": action["action"]}
    row = execute(
        """
        INSERT INTO codex_tasks(type, priority, status, title, description, input_json)
        VALUES (%s, %s, 'open', %s, %s, %s)
        RETURNING id
        """,
        (
            _task_type_for_action(action["action"]),
            "high" if action["risk"] == "HIGH_RISK" else "medium" if action["risk"] == "MEDIUM_RISK" else "normal",
            title,
            action["note"],
            Jsonb(
                {
                    "source": "campaign_remediation_planner",
                    "campaign_id": campaign_id,
                    "action": action["action"],
                    "risk": action["risk"],
                    "blocker": action["blocker"],
                    "preflight_run_id": str(preflight["id"]),
                    "preflight_decision": preflight["decision"],
                    "source_token": (preflight.get("result_json") or {}).get("token", ""),
                    "checked_count": int(preflight["checked_count"] or 0),
                    "ready_count": int(preflight["ready_count"] or 0),
                    "constraints": ["no_live_outreach", "no_smtp", "no_secret_exposure", "no_non_rescue_changes"],
                    "expected_output": "Safe repair or evidence improvement, followed by focused tests and preflight rerun.",
                }
            ),
        ),
    )
    return {"status": "created", "task_id": str(row["id"]), "action": action["action"]}


def campaign_remediation_plan(limit: int = 25, create_tasks: bool = True) -> dict[str, Any]:
    rows = _latest_failed_preflights(limit)
    plans: list[dict[str, Any]] = []
    task_results: list[dict[str, Any]] = []
    for row in rows:
        result = row.get("result_json") or {}
        blockers = list(result.get("blockers") or [])
        quality_codes = sorted((result.get("quality_blockers_by_code") or {}).keys())
        for code in quality_codes:
            if code not in blockers:
                blockers.append(code)
        actions = [_action_for_blocker(blocker) for blocker in blockers]
        campaign_id = str(row["campaign_id"])
        tasks = [_create_task(campaign_id, action, row) for action in actions] if create_tasks else []
        task_results.extend(tasks)
        plan = {
            "campaign_id": campaign_id,
            "campaign_status": row.get("campaign_status"),
            "decision": row["decision"],
            "blockers": blockers,
            "actions": actions,
            "tasks": tasks,
            "checked_count": int(row["checked_count"] or 0),
            "ready_count": int(row["ready_count"] or 0),
            **SAFE_FLAGS,
        }
        saved = execute(
            """
            INSERT INTO campaign_remediation_plans(
              campaign_id, status, blocker_count, task_count, plan_json,
              send_mail, smtp_called, live_outreach_allowed,
              raw_recipient_addresses_included, secrets_included
            )
            VALUES (%s, %s, %s, %s, %s, false, false, false, false, false)
            RETURNING id, created_at
            """,
            (campaign_id, "planned", len(blockers), len(tasks), Jsonb(json_safe(plan))),
        )
        plan["plan_id"] = str(saved["id"])
        plan["created_at"] = saved["created_at"].isoformat()
        plans.append(plan)
    return json_safe(
        {
            "status": "planned" if plans else "idle_no_failed_preflights",
            "campaign_count": len(plans),
            "task_count": len(task_results),
            "created_task_count": len([item for item in task_results if item["status"] == "created"]),
            "plans": plans,
            **SAFE_FLAGS,
        }
    )


def latest_campaign_remediation_plans(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, campaign_id, status, blocker_count, task_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM campaign_remediation_plans
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 100)),),
    )
    return json_safe(
        {
            "count": len(rows),
            "history": [
                {
                    "id": str(row["id"]),
                    "campaign_id": str(row["campaign_id"]) if row.get("campaign_id") else None,
                    "status": row["status"],
                    "blocker_count": int(row["blocker_count"] or 0),
                    "task_count": int(row["task_count"] or 0),
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
    )


def _latest_plan_rows(limit: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in fetch_all(
            """
            SELECT *
            FROM (
              SELECT DISTINCT ON (campaign_id)
                     id, campaign_id, status, blocker_count, task_count, plan_json, created_at
              FROM campaign_remediation_plans
              WHERE campaign_id IS NOT NULL
              ORDER BY campaign_id, created_at DESC
            ) latest
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (max(1, min(int(limit or 10), 100)),),
        )
    ]


def _execute_safe_action(campaign_id: str, action: dict[str, Any]) -> dict[str, Any]:
    action_name = action["action"]
    if action.get("risk") != "SAFE_AUTO":
        return {"status": "skipped_review_required", "action": action_name, "risk": action.get("risk"), **SAFE_FLAGS}
    if action_name == "refresh_campaign_previews":
        result = run_campaign_action("refresh_previews", campaign_id, limit=100, dry_run=False)
    elif action_name == "refresh_campaign_preview_quality":
        result = campaign_preview_quality_pack(campaign_id, 20)
    elif action_name == "repair_mailer_policy_blockers":
        result = mailer_policy_score()
    else:
        return {"status": "skipped_no_safe_executor", "action": action_name, "risk": action.get("risk"), **SAFE_FLAGS}
    return {
        "status": "executed",
        "action": action_name,
        "risk": action.get("risk"),
        "result_status": result.get("status") or result.get("decision"),
        "send_mail": bool(result.get("send_mail", False)),
        "smtp_called": bool(result.get("smtp_called", False)),
        "live_outreach_allowed": bool(result.get("live_outreach_allowed", False)),
        "raw_recipient_addresses_included": bool(result.get("raw_recipient_addresses_included", False)),
        "secrets_included": bool(result.get("secrets_included", False)),
    }


def execute_campaign_remediation(limit: int = 10, rerun_preflight: bool = True) -> dict[str, Any]:
    rows = _latest_plan_rows(limit)
    executions: list[dict[str, Any]] = []
    for row in rows:
        campaign_id = str(row["campaign_id"])
        plan = row.get("plan_json") or {}
        action_results = [_execute_safe_action(campaign_id, action) for action in plan.get("actions", [])]
        preflight_result = campaign_preflight(campaign_id, 20) if rerun_preflight else {"status": "skipped"}
        executed = len([item for item in action_results if item["status"] == "executed"])
        skipped = len(action_results) - executed
        result = json_safe(
            {
                "campaign_id": campaign_id,
                "plan_id": str(row["id"]),
                "status": "executed" if executed else "skipped_no_safe_actions",
                "actions": action_results,
                "preflight": {
                    "decision": preflight_result.get("decision"),
                    "status": preflight_result.get("status"),
                    "blockers": preflight_result.get("blockers", []),
                },
                "executed_count": executed,
                "skipped_count": skipped,
                **SAFE_FLAGS,
            }
        )
        saved = execute(
            """
            INSERT INTO campaign_remediation_executions(
              campaign_id, status, executed_count, skipped_count, result_json,
              send_mail, smtp_called, live_outreach_allowed,
              raw_recipient_addresses_included, secrets_included
            )
            VALUES (%s, %s, %s, %s, %s, false, false, false, false, false)
            RETURNING id, created_at
            """,
            (campaign_id, result["status"], executed, skipped, Jsonb(result)),
        )
        result["execution_id"] = str(saved["id"])
        result["created_at"] = saved["created_at"].isoformat()
        executions.append(result)
    return json_safe(
        {
            "status": "executed" if executions else "idle_no_remediation_plans",
            "campaign_count": len(executions),
            "executed_count": sum(item["executed_count"] for item in executions),
            "skipped_count": sum(item["skipped_count"] for item in executions),
            "executions": executions,
            **SAFE_FLAGS,
        }
    )


def latest_campaign_remediation_executions(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, campaign_id, status, executed_count, skipped_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM campaign_remediation_executions
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 100)),),
    )
    return json_safe(
        {
            "count": len(rows),
            "history": [
                {
                    "id": str(row["id"]),
                    "campaign_id": str(row["campaign_id"]) if row.get("campaign_id") else None,
                    "status": row["status"],
                    "executed_count": int(row["executed_count"] or 0),
                    "skipped_count": int(row["skipped_count"] or 0),
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
    )
