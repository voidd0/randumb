from __future__ import annotations

import json
from typing import Any, Callable

from psycopg.types.json import Jsonb

from .db import execute, fetch_one
from .email_templates import render_all_samples
from .economics import run_economics_audit
from .autonomous_mailer import run_autonomous_mailer_cycle
from .mailer_control import evaluate_outbound_message
from .mailer_readiness import run_clean_window_transition, sender_rotation_ready
from .mail_recovery import check_mail_clean_window
from .mailer_throttle import throttle_decision
from .reply_actions import plan_reply_action
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


def _record_agent(agent: str, func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    row = execute(
        "INSERT INTO agent_runs(agent, status, started_at) VALUES (%s, 'running', now()) RETURNING id",
        (agent,),
    )
    try:
        result = json.loads(json.dumps(func(), default=str))
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
        "outbound_mailer_gate_agent": lambda: evaluate_outbound_message({"email": "sample@example.test", "template_key": "first_audit_notice"}),
        "reply_action_agent": lambda: plan_reply_action("Price", "How much does it cost?", "audit@voiddorescue.com"),
        "quality_plugin_agent": lambda: latest_quality_summary(),
        "revenue_simulation_agent": lambda: run_synthetic_lead_simulation(int(payload.get("count", 25))),
        "mail_clean_window_agent": lambda: check_mail_clean_window(24),
        "mail_clean_window_transition_agent": lambda: run_clean_window_transition(24),
        "sender_rotation_readiness_agent": lambda: sender_rotation_ready(),
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
        "economics_agent",
        "autonomous_mailer_agent",
        "outbound_mailer_gate_agent",
        "reply_action_agent",
        "mail_clean_window_transition_agent",
        "sender_rotation_readiness_agent",
        "self_audit_agent",
    ]
    runs = [run_agent(agent) for agent in selected]
    return {"agents": len(runs), "runs": runs, "live_outreach": False}
