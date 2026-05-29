from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from .canary_operator_packet import build_canary_operator_packet
from .canary_send_window_plan import build_canary_send_window_plan
from .db import execute, fetch_all, fetch_one
from .lead_supply_buildout import lead_supply_buildout
from .p0 import mail_signal_summary, runtime_state_snapshot


def _safe_json(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _count_unrecovered_agent_failures() -> int:
    row = fetch_one(
        """
        SELECT count(*) AS count
        FROM agent_runs failed
        WHERE failed.status = 'failed'
          AND failed.created_at > now() - interval '24 hours'
          AND NOT EXISTS (
            SELECT 1 FROM agent_runs recovered
            WHERE recovered.agent = failed.agent
              AND recovered.status = 'completed'
              AND recovered.created_at > failed.created_at
          )
        """
    )
    return int(row["count"] or 0) if row else 0


def _dedupe_open_items() -> dict[str, Any]:
    build_rows = fetch_all(
        """
        WITH ranked AS (
          SELECT id, row_number() OVER (
            PARTITION BY module, title, status
            ORDER BY created_at ASC, id ASC
          ) AS rn
          FROM self_build_queue
          WHERE status = 'queued'
        )
        UPDATE self_build_queue q
        SET status = 'superseded_duplicate',
            updated_at = now()
        FROM ranked
        WHERE q.id = ranked.id AND ranked.rn > 1
        RETURNING q.id
        """
    )
    fix_rows = fetch_all(
        """
        WITH ranked AS (
          SELECT id, row_number() OVER (
            PARTITION BY type, title, status
            ORDER BY created_at ASC, id ASC
          ) AS rn
          FROM self_fix_tasks
          WHERE status = 'open'
        )
        UPDATE self_fix_tasks f
        SET status = 'superseded_duplicate',
            updated_at = now()
        FROM ranked
        WHERE f.id = ranked.id AND ranked.rn > 1
        RETURNING f.id
        """
    )
    return {"build_duplicates_closed": len(build_rows), "fix_duplicates_closed": len(fix_rows)}


def _close_resolved_items() -> dict[str, Any]:
    resolved = {"agent_failure_tasks_closed": 0}
    if _count_unrecovered_agent_failures() == 0:
        rows = fetch_all(
            """
            UPDATE self_fix_tasks
            SET status = 'resolved_current_state',
                evidence_json = jsonb_set(
                  evidence_json,
                  '{self_development_resolution}',
                  %s::jsonb,
                  true
                ),
                updated_at = now()
            WHERE status = 'open'
              AND (
                type = 'self_audit_finding'
                OR type = 'closed_loop_finding'
              )
              AND (
                lower(title) LIKE '%%agent failure%%'
                OR lower(title) LIKE '%%unrecovered agent failure%%'
              )
            RETURNING id
            """,
            (Jsonb({"reason": "no_unrecovered_agent_failures_24h", "closed_by": "self_development_executor"}),),
        )
        resolved["agent_failure_tasks_closed"] = len(rows)
    return resolved


def _safe_to_execute() -> tuple[bool, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    state = runtime_state_snapshot()
    signals = mail_signal_summary(24)
    if int(state.get("live_outreach_sent_count", 0) or 0) > 0:
        issues.append({"code": "live_outreach_already_sent", "severity": "high"})
    if signals.get("bounce_or_dsn_count") or signals.get("rate_limit_count") or signals.get("spam_signal_count"):
        issues.append({"code": "recent_mail_signal", "severity": "high", "signals": signals})
    if state.get("latest_mail_qa_decision") != "PASS":
        issues.append({"code": "mail_qa_not_pass", "severity": "high", "decision": state.get("latest_mail_qa_decision")})
    return not issues, issues


def _execute_safe_build_items(limit: int) -> dict[str, Any]:
    allowed, blockers = _safe_to_execute()
    if not allowed:
        return {"executed": 0, "blocked": len(blockers), "blockers": blockers}
    rows = fetch_all(
        """
        SELECT id, module, priority, title, acceptance_json, created_at
        FROM self_build_queue
        WHERE status = 'queued'
          AND module IN ('lead_supply', 'conversion_pipeline', 'scout_sources')
        ORDER BY
          CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
          created_at ASC
        LIMIT %s
        """,
        (limit,),
    )
    actions: list[dict[str, Any]] = []
    for row in rows:
        module = str(row["module"])
        try:
            if module == "lead_supply":
                result = lead_supply_buildout(
                    target_preview_count=110,
                    canary_count=20,
                    limit=120,
                    max_cycles=1,
                    max_seconds=75,
                    enrichment_limit=2,
                    apply=True,
                )
            elif module == "conversion_pipeline":
                result = {
                    "operator_packet": build_canary_operator_packet(20, store=True, run_checkout_simulation=False),
                    "send_window": build_canary_send_window_plan(20, store=True),
                    "send_mail": False,
                    "live_outreach_allowed": False,
                }
            else:
                result = lead_supply_buildout(
                    target_preview_count=110,
                    canary_count=20,
                    limit=80,
                    max_cycles=1,
                    max_seconds=60,
                    enrichment_limit=0,
                    apply=True,
                )
            safe_result = _safe_json(result)
            execute(
                """
                UPDATE self_build_queue
                SET status = 'executed_safe_auto',
                    acceptance_json = jsonb_build_object(
                      'original_acceptance', acceptance_json,
                      'self_development_execution', %s::jsonb
                    ),
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    Jsonb(
                        {
                            "agent": "self_development_executor",
                            "module": module,
                            "send_mail": False,
                            "live_outreach_allowed": False,
                            "result": safe_result,
                        }
                    ),
                    row["id"],
                ),
            )
            actions.append({"id": str(row["id"]), "module": module, "status": "executed_safe_auto"})
        except Exception as exc:
            execute(
                """
                UPDATE self_build_queue
                SET status = 'blocked_executor_error',
                    acceptance_json = jsonb_build_object(
                      'original_acceptance', acceptance_json,
                      'self_development_error', %s::jsonb
                    ),
                    updated_at = now()
                WHERE id = %s
                """,
                (Jsonb({"error": type(exc).__name__, "send_mail": False, "live_outreach_allowed": False}), row["id"]),
            )
            actions.append({"id": str(row["id"]), "module": module, "status": "blocked_executor_error", "error": type(exc).__name__})
    return {"executed": len([item for item in actions if item["status"] == "executed_safe_auto"]), "blocked": 0, "blockers": [], "actions": actions}


def run_self_development_cycle(limit: int = 10, execute_safe_auto: bool = True) -> dict[str, Any]:
    dedupe = _dedupe_open_items()
    resolved = _close_resolved_items()
    execution = _execute_safe_build_items(max(1, limit)) if execute_safe_auto else {"executed": 0, "blocked": 0, "blockers": [], "actions": []}
    open_counts = fetch_one(
        """
        SELECT
          (SELECT count(*) FROM self_build_queue WHERE status = 'queued') AS queued_build_items,
          (SELECT count(*) FROM self_fix_tasks WHERE status = 'open') AS open_fix_tasks,
          (SELECT count(*) FROM self_learning_events) AS learning_events
        """
    )
    result = {
        "status": "completed",
        "dedupe": dedupe,
        "resolved": resolved,
        "execution": execution,
        "open_counts": dict(open_counts or {}),
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
    row = execute(
        """
        INSERT INTO self_operating_cycles(
          scope, status, findings_count, fix_tasks_created,
          build_items_created, learning_events_created, result_json
        )
        VALUES ('self_development_executor', %s, %s, 0, %s, 0, %s)
        RETURNING id
        """,
        (
            "executed" if execution.get("executed") else "maintenance",
            int(dedupe["build_duplicates_closed"]) + int(dedupe["fix_duplicates_closed"]) + int(resolved["agent_failure_tasks_closed"]),
            int(execution.get("executed", 0) or 0),
            Jsonb(result),
        ),
    )
    result["cycle_id"] = str(row["id"])
    return result
