from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
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
            SELECT DISTINCT ON (r.campaign_id)
                   r.id, r.campaign_id, r.decision, r.checked_count, r.ready_count,
                   r.blocker_count, r.result_json, r.created_at,
                   c.name, c.status AS campaign_status, c.country, c.language, c.niche, c.offer_key
            FROM campaign_preflight_runs r
            LEFT JOIN campaigns c ON c.id = r.campaign_id
            WHERE r.campaign_id IS NOT NULL
            ORDER BY r.campaign_id, r.created_at DESC
            LIMIT %s
            """,
            (max(1, min(int(limit or 25), 100)),),
        )
        if row["decision"] != "PASS_NO_SEND_PREFLIGHT"
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
