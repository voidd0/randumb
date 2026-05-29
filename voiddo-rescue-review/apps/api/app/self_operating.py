from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .economics import run_economics_audit
from .mail_send_compliance import mail_send_compliance_snapshot
from .p0 import mail_signal_summary, runtime_state_snapshot


MODULES = [
    "lead_scouting",
    "scanner",
    "audit_pages",
    "checkout",
    "mailer",
    "warmup",
    "inbox",
    "owner_commands",
    "customer_onboarding",
    "visual_qa",
    "mail_qa",
    "daily_loop",
    "export_hygiene",
]


def create_self_fix_task(
    task_type: str,
    title: str,
    priority: str = "P2",
    evidence: dict[str, Any] | None = None,
    safety_level: str = "safe",
    source_audit_id: str | None = None,
) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO self_fix_tasks(source_audit_id, type, priority, title, evidence_json, safety_level)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (source_audit_id, task_type, priority, title, Jsonb(evidence or {}), safety_level),
    )
    return dict(row)


def record_learning(signal_type: str, source: str, lesson: str, prevention_rule: str, severity: str = "info", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO self_learning_events(signal_type, source, lesson, prevention_rule, severity, payload_json)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (signal_type, source, lesson, prevention_rule, severity, Jsonb(payload or {})),
    )
    return dict(row)


def queue_self_build(module: str, title: str, priority: str = "P2", acceptance: list[str] | None = None) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO self_build_queue(module, priority, title, acceptance_json)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (module, priority, title, Jsonb(acceptance or [])),
    )
    return dict(row)


def run_self_audit(scope: str = "full") -> dict[str, Any]:
    state = runtime_state_snapshot()
    signals = mail_signal_summary(24)
    settings = get_settings()
    send_compliance = mail_send_compliance_snapshot(24)
    findings: list[dict[str, Any]] = []

    live_outreach_sent = int(state.get("live_outreach_sent_count", 0) or 0)
    live_runtime_armed = (
        settings.outreach_dry_run is False
        and settings.outreach_paused is False
        and settings.first_live_send_flag is True
    )
    live_mail_signals_clean = (
        int(state.get("bounce_count", 0) or 0) == 0
        and int(state.get("rate_limit_signal_count", 0) or 0) == 0
        and int(state.get("spam_signal_count", 0) or 0) == 0
        and int(state.get("mail_auth_failure_count", 0) or 0) == 0
        and state.get("latest_mail_qa_decision") == "PASS"
        and send_compliance.get("decision") == "PASS"
    )
    if live_outreach_sent > 0 and not (live_runtime_armed and live_mail_signals_clean):
        findings.append(
            {
                "severity": "critical",
                "code": "unauthorized_or_unsafe_live_outreach_sent",
                "message": "Live outreach exists without the required runtime flags and clean mail-safety evidence.",
            }
        )
    if int(state.get("bounce_count", 0)) > 0:
        findings.append({"severity": "high", "code": "recent_bounce_or_dsn", "message": "Recent bounce/DSN signals block warmup and outreach."})
    if int(state.get("rate_limit_signal_count", 0)) > 0:
        findings.append({"severity": "high", "code": "recent_rate_limit", "message": "Recent SMTP rate-limit signal blocks mail sending."})
    if state.get("latest_mail_qa_decision") != "PASS":
        findings.append({"severity": "high", "code": "mail_qa_not_pass", "message": "Latest mail QA is not PASS."})
    live_canary_evidence_ready = live_runtime_armed and live_mail_signals_clean and live_outreach_sent > 0
    if state.get("launch_readiness_state") == "LIVE_OUTREACH_READY" and not live_canary_evidence_ready:
        findings.append({"severity": "medium", "code": "readiness_overstated_check", "message": "Verify live readiness is backed by scenario evidence."})

    agent_failures = fetch_one(
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
    if agent_failures and int(agent_failures["count"]) > 0:
        findings.append({"severity": "high", "code": "recent_agent_failures", "message": f"{agent_failures['count']} agent failures in last 24h."})

    economics = run_economics_audit()
    if economics["status"] != "pass":
        findings.append({"severity": "medium", "code": "economics_review_required", "message": "One or more products do not meet margin rules."})

    score = max(0, 100 - len([f for f in findings if f["severity"] == "critical"]) * 50 - len([f for f in findings if f["severity"] == "high"]) * 20 - len([f for f in findings if f["severity"] == "medium"]) * 10)
    status = "pass" if score >= 90 and not findings else "needs_fix"
    row = execute(
        "INSERT INTO self_audit_runs(scope, status, score, findings_json) VALUES (%s, %s, %s, %s) RETURNING *",
        (scope, status, score, Jsonb(findings)),
    )

    for finding in findings:
        if finding["severity"] in {"critical", "high"}:
            create_self_fix_task("self_audit_finding", finding["message"], "P0" if finding["severity"] == "critical" else "P1", finding, "safe", str(row["id"]))
        record_learning(finding["code"], "self_audit", finding["message"], f"Prevent recurrence of {finding['code']} before enabling launch gates.", finding["severity"], finding)

    return {"audit": dict(row), "findings": findings, "signals": signals, "economics": economics}


def self_operating_summary() -> dict[str, Any]:
    counts = {row["name"]: row["count"] for row in fetch_all(
        """
        SELECT 'self_audit_runs' AS name, count(*) AS count FROM self_audit_runs
        UNION ALL SELECT 'self_fix_tasks_open', count(*) FROM self_fix_tasks WHERE status = 'open'
        UNION ALL SELECT 'self_learning_events', count(*) FROM self_learning_events
        UNION ALL SELECT 'self_build_queue_open', count(*) FROM self_build_queue WHERE status = 'queued'
        UNION ALL SELECT 'quality_plugin_runs', count(*) FROM quality_plugin_runs
        UNION ALL SELECT 'autonomous_mailer_decisions', count(*) FROM autonomous_mailer_decisions
        """
    )}
    latest = fetch_one("SELECT * FROM self_audit_runs ORDER BY created_at DESC LIMIT 1")
    return {"counts": counts, "latest_self_audit": latest}
