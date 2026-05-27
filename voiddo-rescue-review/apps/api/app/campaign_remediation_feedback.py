from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import json_safe
from .self_operating import create_self_fix_task, queue_self_build, record_learning


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _recent_executions(limit: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in fetch_all(
            """
            SELECT id, campaign_id, status, executed_count, skipped_count, result_json, created_at
            FROM campaign_remediation_executions
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (max(1, min(int(limit or 25), 100)),),
        )
    ]


def _blocker_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        result = row.get("result_json") or {}
        for blocker in (result.get("preflight") or {}).get("blockers", []):
            counts[blocker] = counts.get(blocker, 0) + 1
        for action in result.get("actions", []):
            if action.get("status", "").startswith("skipped"):
                code = f"skipped:{action.get('action')}"
                counts[code] = counts.get(code, 0) + 1
    return counts


def _sample_tokens(rows: list[dict[str, Any]]) -> list[str]:
    tokens = []
    for row in rows:
        token = (row.get("result_json") or {}).get("token")
        if token and token not in tokens:
            tokens.append(str(token))
    return tokens[:5]


def _dedup_learning(signal_type: str, source: str, lesson: str, prevention_rule: str, severity: str, payload: dict[str, Any]) -> dict[str, Any]:
    existing = fetch_one(
        """
        SELECT id
        FROM self_learning_events
        WHERE signal_type = %s
          AND source = %s
          AND payload_json->>'dedupe_key' = %s
          AND created_at > now() - interval '24 hours'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (signal_type, source, payload["dedupe_key"]),
    )
    if existing:
        return {"status": "existing", "id": str(existing["id"]), "signal_type": signal_type}
    row = record_learning(signal_type, source, lesson, prevention_rule, severity, payload)
    return {"status": "created", "id": str(row["id"]), "signal_type": signal_type}


def _dedup_self_build(title: str, module: str, priority: str, acceptance: list[str]) -> dict[str, Any]:
    existing = fetch_one(
        """
        SELECT id
        FROM self_build_queue
        WHERE status = 'queued'
          AND module = %s
          AND title = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (module, title),
    )
    if existing:
        return {"status": "existing", "id": str(existing["id"]), "title": title}
    row = queue_self_build(module, title, priority, acceptance)
    return {"status": "created", "id": str(row["id"]), "title": title}


def _dedup_self_fix(title: str, task_type: str, priority: str, evidence: dict[str, Any]) -> dict[str, Any]:
    existing = fetch_one(
        """
        SELECT id
        FROM self_fix_tasks
        WHERE status = 'open'
          AND type = %s
          AND title = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (task_type, title),
    )
    if existing:
        return {"status": "existing", "id": str(existing["id"]), "title": title}
    row = create_self_fix_task(task_type, title, priority, evidence, "safe")
    return {"status": "created", "id": str(row["id"]), "title": title}


def campaign_remediation_feedback(limit: int = 25, repeated_threshold: int = 3) -> dict[str, Any]:
    rows = _recent_executions(limit)
    counts = _blocker_counts(rows)
    sample_tokens = _sample_tokens(rows)
    learning: list[dict[str, Any]] = []
    self_build: list[dict[str, Any]] = []
    self_fix: list[dict[str, Any]] = []
    threshold = max(2, min(int(repeated_threshold or 3), 10))

    for blocker, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        severity = "high" if count >= threshold else "info"
        token_scope = ",".join(sample_tokens) if sample_tokens else "global"
        dedupe_key = f"{blocker}:{count >= threshold}:{token_scope}"
        learning.append(
            _dedup_learning(
                "campaign_remediation_blocker",
                "campaign_remediation_feedback",
                f"Campaign remediation repeatedly observed {blocker}.",
                f"Prioritize a safe fix path for {blocker} before campaign can approach live outreach.",
                severity,
                {"dedupe_key": dedupe_key, "blocker": blocker, "count": count, "threshold": threshold, "sample_tokens": sample_tokens, **SAFE_FLAGS},
            )
        )
        if count >= threshold:
            if blocker == "audit_strength_below_70" or blocker.startswith("skipped:improve_audit_evidence"):
                self_build.append(
                    _dedup_self_build(
                        "Strengthen audit evidence automation for blocked campaigns",
                        "audit_pages",
                        "P1",
                        ["raise audit_strength_scores above 70", "keep public non-invasive wording", "rerun Huanshu if UI changes"],
                    )
                )
            elif blocker == "mailer_policy_not_ready":
                self_fix.append(
                    _dedup_self_fix(
                        "Repair mailer policy blockers before campaign launch",
                        "campaign_remediation_feedback",
                        "P1",
                        {"blocker": blocker, "count": count, **SAFE_FLAGS},
                    )
                )
            else:
                self_build.append(
                    _dedup_self_build(
                        f"Reduce repeated campaign blocker: {blocker}",
                        "campaign_pipeline",
                        "P2",
                        ["create a focused safe repair", "add regression test", "rerun campaign preflight"],
                    )
                )

    result = json_safe(
        {
            "status": "feedback_recorded" if rows else "idle_no_executions",
            "execution_count": len(rows),
            "blocker_counts": counts,
            "learning": learning,
            "self_build": self_build,
            "self_fix": self_fix,
            "learning_count": len(learning),
            "self_build_count": len(self_build),
            "self_fix_count": len(self_fix),
            **SAFE_FLAGS,
        }
    )
    saved = execute(
        """
        INSERT INTO campaign_remediation_feedback_runs(
          status, execution_count, learning_count, self_fix_count, self_build_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (
            result["status"],
            result["execution_count"],
            result["learning_count"],
            result["self_fix_count"],
            result["self_build_count"],
            Jsonb(result),
        ),
    )
    result["run_id"] = str(saved["id"])
    result["created_at"] = saved["created_at"].isoformat()
    return result


def latest_campaign_remediation_feedback(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, execution_count, learning_count, self_fix_count, self_build_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM campaign_remediation_feedback_runs
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
                    "status": row["status"],
                    "execution_count": int(row["execution_count"] or 0),
                    "learning_count": int(row["learning_count"] or 0),
                    "self_fix_count": int(row["self_fix_count"] or 0),
                    "self_build_count": int(row["self_build_count"] or 0),
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
