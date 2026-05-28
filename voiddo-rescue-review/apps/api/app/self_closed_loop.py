from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import mail_signal_summary, runtime_state_snapshot
from .self_operating import create_self_fix_task, queue_self_build, record_learning, run_self_audit


def _recent_existing(table: str, where: str, params: tuple) -> bool:
    row = fetch_one(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", params)
    return bool(row)


def _create_fix_once(task_type: str, title: str, priority: str, evidence: dict[str, Any], safety_level: str = "safe") -> dict[str, Any] | None:
    if _recent_existing(
        "self_fix_tasks",
        "type = %s AND title = %s AND status = 'open' AND created_at > now() - interval '7 days'",
        (task_type, title),
    ):
        return None
    safe_evidence = json.loads(json.dumps(evidence, default=str))
    return create_self_fix_task(task_type, title, priority, safe_evidence, safety_level)


def _queue_build_once(module: str, title: str, priority: str, acceptance: list[str]) -> dict[str, Any] | None:
    if _recent_existing(
        "self_build_queue",
        "module = %s AND title = %s AND status = 'queued' AND created_at > now() - interval '14 days'",
        (module, title),
    ):
        return None
    return queue_self_build(module, title, priority, acceptance)


def _learn_once(signal_type: str, source: str, lesson: str, prevention_rule: str, severity: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if _recent_existing(
        "self_learning_events",
        "signal_type = %s AND source = %s AND lesson = %s AND created_at > now() - interval '7 days'",
        (signal_type, source, lesson),
    ):
        return None
    return record_learning(signal_type, source, lesson, prevention_rule, severity, payload)


def _latest_campaign_blockers(limit: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT DISTINCT ON (campaign_id) campaign_id, status, blockers_json, summary_json, created_at
        FROM campaign_readiness_snapshots
        ORDER BY campaign_id, created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    blockers: list[dict[str, Any]] = []
    for row in rows:
        if row["status"] != "blocked":
            continue
        for blocker in row["blockers_json"] or []:
            blockers.append(
                {
                    "source": "campaign_readiness",
                    "campaign_id": str(row["campaign_id"]),
                    "code": blocker.get("code", "campaign_blocker"),
                    "severity": blocker.get("severity", "medium"),
                    "evidence": blocker,
                }
            )
    return blockers


def _latest_agent_failures(limit: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT failed.agent, failed.error, failed.created_at
        FROM agent_runs failed
        WHERE failed.status = 'failed'
          AND failed.created_at > now() - interval '24 hours'
          AND NOT EXISTS (
            SELECT 1 FROM agent_runs recovered
            WHERE recovered.agent = failed.agent
              AND recovered.status = 'completed'
              AND recovered.created_at > failed.created_at
          )
        ORDER BY failed.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [
        {
            "source": "agent_runs",
            "code": "unrecovered_agent_failure",
            "severity": "high",
            "agent": row["agent"],
            "error": row["error"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _quality_plugin_blockers(limit: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT tool, target, status, score, issues_json, created_at
        FROM quality_plugin_runs
        WHERE status NOT IN ('PASS', 'PASS_WITH_WARNINGS')
          AND created_at > now() - interval '24 hours'
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [
        {
            "source": "quality_plugins",
            "code": "quality_plugin_failure",
            "severity": "high",
            "tool": row["tool"],
            "target": row["target"],
            "status": row["status"],
            "score": row["score"],
            "issues": row["issues_json"] or [],
        }
        for row in rows
    ]


def run_self_operating_closed_loop(scope: str = "closed_loop", limit: int = 25) -> dict[str, Any]:
    self_audit = run_self_audit(scope)
    state = runtime_state_snapshot()
    signals = mail_signal_summary(24)
    findings: list[dict[str, Any]] = []
    findings.extend(dict(item, source="self_audit") for item in self_audit.get("findings", []))
    findings.extend(_latest_campaign_blockers(limit))
    findings.extend(_latest_agent_failures(limit))
    findings.extend(_quality_plugin_blockers(limit))

    if signals["bounce_or_dsn_count"] or signals["rate_limit_count"] or signals["spam_signal_count"]:
        findings.append(
            {
                "source": "mail_signals",
                "code": "recent_mail_signal",
                "severity": "high",
                "evidence": signals,
            }
        )
    if state.get("launch_readiness_state") == "LIVE_OUTREACH_READY" and int(state.get("warmup_sent_count", 0) or 0) < 5:
        findings.append(
            {
                "source": "runtime_state",
                "code": "launch_readiness_overstated",
                "severity": "critical",
                "evidence": {
                    "launch_readiness_state": state.get("launch_readiness_state"),
                    "warmup_sent_count": state.get("warmup_sent_count"),
                },
            }
        )

    fix_created = 0
    build_created = 0
    learning_created = 0
    actions: list[dict[str, Any]] = []
    for finding in findings:
        code = str(finding.get("code") or "unknown_finding")
        severity = str(finding.get("severity") or "medium")
        priority = "P0" if severity == "critical" else "P1" if severity == "high" else "P2"
        detail = str(finding.get("agent") or finding.get("campaign_id") or finding.get("target") or finding.get("source") or "")
        suffix = f": {detail[:80]}" if detail else ""
        title = f"Resolve {code.replace('_', ' ')}{suffix}"
        evidence = json.loads(json.dumps({
            "finding": finding,
            "send_mail": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }, default=str))
        fix = _create_fix_once("closed_loop_finding", title, priority, evidence)
        if fix:
            fix_created += 1
            actions.append({"action": "self_fix_task_created", "code": code, "id": str(fix["id"])})
        build = _queue_build_once(
            str(finding.get("source") or "self_operating"),
            f"Prevent recurring {code.replace('_', ' ')}{suffix}",
            priority,
            [
                "Add or tighten an automated check for this failure mode.",
                "Keep live outreach disabled unless all launch gates pass.",
                "Store only redacted evidence in reports and review packages.",
            ],
        )
        if build:
            build_created += 1
            actions.append({"action": "self_build_item_created", "code": code, "id": str(build["id"])})
        lesson = _learn_once(
            code,
            f"{str(finding.get('source') or scope)}{suffix}",
            f"{code.replace('_', ' ')} must be detected before revenue actions run.",
            f"Run closed-loop self-audit before campaign/warmup/outbound state changes for {code}.",
            severity,
            evidence,
        )
        if lesson:
            learning_created += 1
            actions.append({"action": "learning_recorded", "code": code, "id": str(lesson["id"])})

    status = "pass" if not findings else "actions_created" if (fix_created or build_created or learning_created) else "known_findings_tracked"
    result = {
        "scope": scope,
        "status": status,
        "findings_count": len(findings),
        "fix_tasks_created": fix_created,
        "build_items_created": build_created,
        "learning_events_created": learning_created,
        "actions": actions,
        "send_mail": False,
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
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (scope, status, len(findings), fix_created, build_created, learning_created, Jsonb(result)),
    )
    result["cycle_id"] = str(row["id"])
    return result


def latest_self_operating_cycles(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, scope, status, findings_count, fix_tasks_created, build_items_created,
               learning_events_created, result_json, created_at
        FROM self_operating_cycles
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {"count": len(rows), "cycles": [dict(row) for row in rows], "send_mail": False, "live_outreach_allowed": False}
