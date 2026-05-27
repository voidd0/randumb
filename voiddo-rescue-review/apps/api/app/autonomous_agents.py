from __future__ import annotations

import json
from typing import Any, Callable

from psycopg.types.json import Jsonb

from .clean_window_recheck import clean_window_recheck, post_window_recheck_scheduler
from .db import execute, fetch_one
from .email_templates import render_all_samples
from .economics import run_economics_audit
from .autonomous_mailer import run_autonomous_mailer_cycle
from .mailer_control import evaluate_outbound_message
from .mailer_control_room import cleanup_mailer_digest_history, mailer_digest_trend_guard, mailer_policy_score, write_mailer_digest_agent_report, write_owner_status_report
from .mailer_readiness import run_clean_window_transition, sender_rotation_ready
from .mailer_autonomy import mailer_status_snapshot, record_mail_signal_lessons, run_clean_window_recovery
from .mailer_closed_loop import run_mailer_closed_loop
from .mailer_ops_actions import cleanup_mailer_ops_synthetic_history, write_mailer_ops_retention_agent_report
from .mail_recovery import check_mail_clean_window
from .mailer_throttle import throttle_decision
from .reply_actions import plan_reply_action
from .customer_journey import customer_journey_snapshot
from .customer_mail_simulation import run_customer_mail_simulation
from .monitoring import process_due_monitoring_targets, run_monitoring_check
from .p0 import (
    build_warmup_calendar,
    mail_signal_summary,
    prepare_outreach_preview,
    run_mail_qa,
    run_warmup_calendar_due,
    runtime_state_snapshot,
)
from .quality_plugins import latest_quality_summary
from .revenue_simulation import run_synthetic_lead_simulation
from .language_gate import check_no_ai_public_language
from .scouts import process_scout_run
from .self_operating import run_self_audit, self_operating_summary
from .warmup_planner import apply_provider_spacing_when_safe, plan_provider_spaced_warmup


def _record_agent(agent: str, func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    row = execute(
        "INSERT INTO agent_runs(agent, status, started_at) VALUES (%s, 'running', now()) RETURNING id",
        (agent,),
    )
    try:
        result = json.loads(json.dumps(func(), default=str))
        if agent == "mailer_digest_agent":
            digest_report = write_mailer_digest_agent_report(str(row["id"]), result)
            result["digest_agent_report"] = digest_report
        if agent == "mailer_ops_retention_agent":
            retention_report = write_mailer_ops_retention_agent_report(str(row["id"]), result)
            result["ops_retention_agent_report"] = retention_report
        done = execute(
            "UPDATE agent_runs SET status = 'completed', completed_at = now(), result_json = %s WHERE id = %s RETURNING *",
            (Jsonb(result), row["id"]),
        )
        return dict(done)
    except Exception as exc:
        failed = execute(
            "UPDATE agent_runs SET status = 'failed', completed_at = now(), error = %s WHERE id = %s RETURNING *",
            (type(exc).__name__, row["id"]),
        )
        return dict(failed)


def run_agent(agent: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}

    def scout_agent():
        run_id = payload.get("scout_run_id")
        if not run_id:
            return {"dry_run": True, "status": "no_scout_run_selected"}
        return process_scout_run(run_id)

    agents: dict[str, Callable[[], dict[str, Any]]] = {
        "scout_agent": scout_agent,
        "scanner_agent": lambda: {"dry_run": True, "status": "scanner_worker_processes_existing_queue"},
        "audit_page_agent": lambda: {"dry_run": True, "status": "audit_pages_api_backed"},
        "visual_qa_agent": lambda: {"dry_run": True, "status": "huanshu_required", "routes": ["/", "/r/demo", "/admin", "/customer", "/status"]},
        "mail_qa_agent": lambda: {"mail_qa": run_mail_qa()},
        "deliverability_agent": lambda: {"dry_run": True, "signals": mail_signal_summary()},
        "warmup_agent": lambda: run_warmup_calendar_due(limit=2),
        "campaign_agent": lambda: prepare_outreach_preview(int(payload.get("limit", 20))),
        "inbox_agent": lambda: {"dry_run": True, "status": "worker_polls_when_enabled"},
        "owner_command_agent": lambda: {"dry_run": True, "status": "owner_commands_are_gated"},
        "checkout_agent": lambda: {"dry_run": True, "status": "paddle_webhook_handlers_ready"},
        "reporting_agent": lambda: runtime_state_snapshot(),
        "fix_task_agent": lambda: {"dry_run": True, "status": "codex_tasks_endpoint_ready"},
        "mail_throttle_agent": lambda: throttle_decision("global", "diagnostic", 600),
        "email_template_agent": lambda: {"rendered": len(render_all_samples()), "all_pass": all(item["qa"]["passed"] for item in render_all_samples())},
        "warmup_calendar_agent": lambda: build_warmup_calendar(),
        "economics_agent": lambda: run_economics_audit(),
        "self_audit_agent": lambda: run_self_audit("agent_cycle"),
        "self_fix_agent": lambda: self_operating_summary(),
        "self_learning_agent": lambda: self_operating_summary(),
        "self_building_agent": lambda: self_operating_summary(),
        "autonomous_mailer_agent": lambda: run_autonomous_mailer_cycle(),
        "autonomous_mailer_executor_agent": lambda: run_mailer_closed_loop(int(payload.get("limit", 10))),
        "customer_mail_simulation_agent": lambda: run_customer_mail_simulation(True),
        "mailer_digest_agent": lambda: write_owner_status_report(send_if_safe=False),
        "mailer_digest_retention_agent": lambda: cleanup_mailer_digest_history(90),
        "mailer_digest_trend_guard_agent": lambda: mailer_digest_trend_guard(),
        "mailer_policy_score_agent": lambda: mailer_policy_score(),
        "mailer_ops_retention_agent": lambda: cleanup_mailer_ops_synthetic_history(),
        "outbound_mailer_gate_agent": lambda: evaluate_outbound_message({"email": "sample@example.test", "template_key": "first_audit_notice"}),
        "reply_action_agent": lambda: plan_reply_action("Price", "How much does it cost?", "audit@voiddorescue.com"),
        "quality_plugin_agent": lambda: latest_quality_summary(),
        "revenue_simulation_agent": lambda: run_synthetic_lead_simulation(int(payload.get("count", 25))),
        "mail_clean_window_agent": lambda: check_mail_clean_window(24),
        "mail_clean_window_transition_agent": lambda: run_clean_window_transition(24),
        "mailer_status_agent": lambda: mailer_status_snapshot(),
        "mail_signal_learning_agent": lambda: record_mail_signal_lessons(24),
        "clean_window_recovery_agent": lambda: run_clean_window_recovery(24),
        "clean_window_recheck_agent": lambda: clean_window_recheck(24, False),
        "post_window_recheck_agent": lambda: post_window_recheck_scheduler(24, run_recovery_if_due=False),
        "customer_journey_agent": lambda: {"dry_run": True, "status": "customer_journeys_snapshot_on_payment_or_admin_request"},
        "monitoring_agent": lambda: {"dry_run": True, "status": "monitoring_targets_checked_by_protected_endpoint_or_scheduler"},
        "monitoring_scheduler_agent": lambda: process_due_monitoring_targets(5, True),
        "sender_rotation_readiness_agent": lambda: sender_rotation_ready(),
        "warmup_spacing_planner_agent": lambda: plan_provider_spaced_warmup(50, False),
        "warmup_spacing_apply_gate_agent": lambda: apply_provider_spacing_when_safe(50),
        "public_language_gate_agent": lambda: check_no_ai_public_language(),
    }
    if agent not in agents:
        raise ValueError("unknown_agent")
    return _record_agent(agent, agents[agent])


def run_daily_loop() -> dict[str, Any]:
    selected = [
        "mail_throttle_agent",
        "email_template_agent",
        "visual_qa_agent",
        "deliverability_agent",
        "campaign_agent",
        "reporting_agent",
        "fix_task_agent",
        "monitoring_scheduler_agent",
        "economics_agent",
        "autonomous_mailer_agent",
        "autonomous_mailer_executor_agent",
        "customer_mail_simulation_agent",
        "mailer_ops_retention_agent",
        "mailer_digest_agent",
        "mailer_digest_retention_agent",
        "mailer_digest_trend_guard_agent",
        "mailer_policy_score_agent",
        "outbound_mailer_gate_agent",
        "reply_action_agent",
        "mail_clean_window_transition_agent",
        "mailer_status_agent",
        "mail_signal_learning_agent",
        "clean_window_recovery_agent",
        "clean_window_recheck_agent",
        "post_window_recheck_agent",
        "sender_rotation_readiness_agent",
        "warmup_spacing_planner_agent",
        "warmup_spacing_apply_gate_agent",
        "self_audit_agent",
    ]
    runs = [run_agent(agent) for agent in selected]
    return {"agents": len(runs), "runs": runs, "live_outreach": False}
