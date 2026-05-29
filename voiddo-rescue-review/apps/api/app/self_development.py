from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from .canary_batch_quality import canary_batch_quality
from .canary_checkout_simulation import run_canary_checkout_simulation
from .canary_operator_packet import build_canary_operator_packet
from .canary_send_window_plan import build_canary_send_window_plan
from .db import execute, fetch_all, fetch_one
from .economics import latest_economics_summary, run_economics_audit
from .launch_activation import launch_activation_readiness
from .lead_supply_buildout import lead_supply_buildout
from .mailer_control_room import mailer_policy_score
from .p0 import mail_signal_summary, runtime_state_snapshot
from .quality_plugins import latest_quality_summary, quality_plugin_manifest
from .revenue_loop import prepare_revenue_loop


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
    resolved = {
        "agent_failure_tasks_closed": 0,
        "agent_failure_build_items_closed": 0,
        "campaign_readiness_build_items_closed": 0,
        "campaign_readiness_fix_tasks_closed": 0,
    }
    if _count_unrecovered_agent_failures() == 0:
        build_rows = fetch_all(
            """
            UPDATE self_build_queue
            SET status = 'resolved_current_state',
                acceptance_json = jsonb_build_object(
                  'original_acceptance', acceptance_json,
                  'self_development_resolution', %s::jsonb
                ),
                updated_at = now()
            WHERE status = 'queued'
              AND module IN ('agent_runs', 'self_audit')
              AND (
                lower(title) LIKE '%%agent failure%%'
                OR lower(title) LIKE '%%unrecovered agent failure%%'
                OR lower(title) LIKE '%%recent agent failures%%'
              )
            RETURNING id
            """,
            (Jsonb({"reason": "no_unrecovered_agent_failures_24h", "closed_by": "self_development_executor", "send_mail": False, "live_outreach_allowed": False}),),
        )
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
        resolved["agent_failure_build_items_closed"] = len(build_rows)
        resolved["agent_failure_tasks_closed"] = len(rows)
    campaign_evidence = _campaign_launch_evidence()
    if campaign_evidence["resolved"]:
        build_rows = fetch_all(
            """
            UPDATE self_build_queue
            SET status = 'resolved_current_state',
                acceptance_json = jsonb_build_object(
                  'original_acceptance', acceptance_json,
                  'self_development_resolution', %s::jsonb
                ),
                updated_at = now()
            WHERE status = 'queued'
              AND module IN ('campaign_readiness', 'campaign_pipeline', 'audit_pages')
              AND (
                lower(title) LIKE '%%campaign%%'
                OR lower(title) LIKE '%%audit strength%%'
                OR lower(title) LIKE '%%preview%%'
                OR lower(title) LIKE '%%transport%%'
                OR lower(title) LIKE '%%scout quality%%'
                OR lower(title) LIKE '%%scout source readiness%%'
                OR lower(title) LIKE '%%mail qa%%'
                OR lower(title) LIKE '%%visual qa%%'
              )
            RETURNING id
            """,
            (Jsonb(campaign_evidence),),
        )
        self_audit_rows = fetch_all(
            """
            UPDATE self_build_queue
            SET status = 'resolved_current_state',
                acceptance_json = jsonb_build_object(
                  'original_acceptance', acceptance_json,
                  'self_development_resolution', %s::jsonb
                ),
                updated_at = now()
            WHERE status = 'queued'
              AND module IN ('self_audit', 'pytest_module')
              AND (
                lower(title) LIKE '%%mail qa%%'
                OR lower(title) LIKE '%%visual qa%%'
                OR lower(title) LIKE '%%regression harness%%'
              )
            RETURNING id
            """,
            (Jsonb(campaign_evidence),),
        )
        fix_rows = fetch_all(
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
                lower(title) LIKE '%%campaign%%'
                OR lower(title) LIKE '%%scout quality%%'
                OR lower(title) LIKE '%%scout source readiness%%'
                OR lower(title) LIKE '%%audit strength%%'
                OR lower(title) LIKE '%%preview%%'
                OR lower(title) LIKE '%%transport%%'
                OR lower(title) LIKE '%%mail qa%%'
                OR lower(title) LIKE '%%visual qa%%'
              )
            RETURNING id
            """,
            (Jsonb(campaign_evidence),),
        )
        resolved["campaign_readiness_build_items_closed"] = len(build_rows) + len(self_audit_rows)
        resolved["campaign_readiness_fix_tasks_closed"] = len(fix_rows)
    return resolved


def _campaign_launch_evidence() -> dict[str, Any]:
    try:
        activation = launch_activation_readiness(20)
        quality = canary_batch_quality(20)
    except Exception as exc:
        return {"resolved": False, "error": type(exc).__name__}
    activation_decision = activation.get("decision")
    quality_decision = quality.get("decision")
    quality_blockers = quality.get("blockers") or []
    resolved = (
        activation_decision == "READY_FOR_OPERATOR_ENV_ACTIVATION"
        and quality_decision == "PASS_CANARY_BATCH_QUALITY"
        and not quality_blockers
    )
    return {
        "resolved": resolved,
        "reason": "current_canary_launch_gates_pass" if resolved else "campaign_launch_gates_not_pass",
        "activation_decision": activation_decision,
        "canary_quality_decision": quality_decision,
        "canary_quality_blocker_count": len(quality_blockers),
        "closed_by": "self_development_executor",
        "send_mail": False,
        "live_outreach_allowed": False,
    }


def _safe_to_execute(allow_mail_blocked_no_send: bool = False) -> tuple[bool, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    state = runtime_state_snapshot()
    signals = mail_signal_summary(24)
    live_outreach_sent = int(state.get("live_outreach_sent_count", 0) or 0)
    clean_active_canary = (
        state.get("launch_readiness_state") == "LIVE_OUTREACH_READY"
        and state.get("latest_mail_qa_decision") == "PASS"
        and int(signals.get("bounce_or_dsn_count", 0) or 0) == 0
        and int(signals.get("rate_limit_count", 0) or 0) == 0
        and int(signals.get("spam_signal_count", 0) or 0) == 0
        and int(signals.get("mail_auth_failure_count", 0) or 0) == 0
    )
    if live_outreach_sent > 0 and not clean_active_canary and not allow_mail_blocked_no_send:
        issues.append({"code": "unsafe_live_outreach_state", "severity": "high"})
    if (
        signals.get("bounce_or_dsn_count")
        or signals.get("rate_limit_count")
        or signals.get("spam_signal_count")
        or signals.get("mail_auth_failure_count")
    ) and not allow_mail_blocked_no_send:
        issues.append({"code": "recent_mail_signal", "severity": "high", "signals": signals})
    if state.get("latest_mail_qa_decision") != "PASS" and not allow_mail_blocked_no_send:
        issues.append({"code": "mail_qa_not_pass", "severity": "high", "decision": state.get("latest_mail_qa_decision")})
    return not issues, issues


def _visual_revenue_gate_snapshot() -> dict[str, Any]:
    latest_visual = fetch_one(
        """
        SELECT decision, huanshu_status, target_url, score, created_at
        FROM visual_qa_runs
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    latest_huanshu = fetch_one(
        """
        SELECT status, target, score, created_at
        FROM quality_plugin_runs
        WHERE tool = 'huanshu'
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    quality = latest_quality_summary()
    blockers: list[str] = []
    if not latest_visual:
        blockers.append("missing_visual_qa_run")
    elif latest_visual["decision"] not in {"PASS", "PASS_WITH_WARNINGS"}:
        blockers.append("latest_visual_qa_not_pass")
    if not latest_huanshu or latest_huanshu["status"] != "PASS":
        blockers.append("latest_huanshu_not_pass")
    if not quality.get("all_pass"):
        blockers.append("secondary_design_plugins_not_all_pass")
    return _safe_json(
        {
            "decision": "PASS_NO_SEND" if not blockers else "BLOCKED_REVIEW",
            "blockers": blockers,
            "canonical": "huanshu",
            "manifest": quality_plugin_manifest(),
            "latest_visual": dict(latest_visual or {}),
            "latest_huanshu": dict(latest_huanshu or {}),
            "quality_summary": quality,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def _execute_no_send_module(module: str) -> dict[str, Any]:
    if module == "lead_supply":
        return lead_supply_buildout(
            target_preview_count=110,
            canary_count=20,
            limit=120,
            max_cycles=1,
            max_seconds=45,
            enrichment_limit=0,
            apply=True,
        )
    if module == "scout_sources":
        return lead_supply_buildout(
            target_preview_count=110,
            canary_count=20,
            limit=80,
            max_cycles=1,
            max_seconds=45,
            enrichment_limit=0,
            apply=True,
        )
    if module == "conversion_pipeline":
        return {
            "operator_packet": build_canary_operator_packet(20, store=True, run_checkout_simulation=False),
            "send_window": build_canary_send_window_plan(20, store=True),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        }
    if module == "checkout_conversion":
        return {
            "checkout_simulation": run_canary_checkout_simulation(cleanup_after=True),
            "revenue_loop": prepare_revenue_loop(20, dry_run=True, prepare_campaigns=False, prepare_customers=True),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        }
    if module == "offer_economics":
        return {
            "economics_audit": run_economics_audit(),
            "summary": latest_economics_summary(),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        }
    if module == "visual_conversion_quality":
        return _visual_revenue_gate_snapshot()
    if module == "mailer_policy":
        return {
            "policy": mailer_policy_score(),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        }
    if module == "daily_loop_readiness":
        return {
            "runtime": runtime_state_snapshot(),
            "operator_packet": build_canary_operator_packet(20, store=True, run_checkout_simulation=False),
            "send_window": build_canary_send_window_plan(20, store=True),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        }
    raise ValueError("unsupported_self_development_module")


def _execute_safe_build_items(limit: int) -> dict[str, Any]:
    allowed, blockers = _safe_to_execute(allow_mail_blocked_no_send=True)
    if not allowed:
        return {"executed": 0, "blocked": len(blockers), "blockers": blockers}
    rows = fetch_all(
        """
        SELECT id, module, priority, title, acceptance_json, created_at
        FROM self_build_queue
        WHERE status = 'queued'
          AND module IN (
            'lead_supply',
            'conversion_pipeline',
            'scout_sources',
            'checkout_conversion',
            'offer_economics',
            'visual_conversion_quality',
            'mailer_policy',
            'daily_loop_readiness'
          )
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
            result = _execute_no_send_module(module)
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
            int(dedupe["build_duplicates_closed"])
            + int(dedupe["fix_duplicates_closed"])
            + int(resolved["agent_failure_tasks_closed"])
            + int(resolved["agent_failure_build_items_closed"])
            + int(resolved["campaign_readiness_build_items_closed"])
            + int(resolved["campaign_readiness_fix_tasks_closed"]),
            int(execution.get("executed", 0) or 0),
            Jsonb(result),
        ),
    )
    result["cycle_id"] = str(row["id"])
    return result
