from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .audit_strength import score_audit_strength
from .db import execute, fetch_all, fetch_one
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}

REMEDIABLE_ISSUES = {"missing_screenshots", "missing_issues", "fewer_than_three_issues", "missing_summary"}


def _latest_strength(audit_id: str) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT final_score, issues_json, created_at
        FROM audit_strength_scores
        WHERE audit_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (audit_id,),
    )
    return dict(row) if row else score_audit_strength(audit_id)


def audit_evidence_candidates(limit: int = 25) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT *
        FROM (
          SELECT DISTINCT ON (a.id)
                 a.id AS audit_id, a.url, a.domain, a.summary, a.public_slug,
                 b.name AS business_name, cl.campaign_id, a.checked_at, a.created_at
          FROM campaign_leads cl
          JOIN audits a ON a.id = cl.audit_id
          LEFT JOIN businesses b ON b.id = a.business_id
          LEFT JOIN LATERAL (
            SELECT final_score FROM audit_strength_scores WHERE audit_id = a.id ORDER BY created_at DESC LIMIT 1
          ) latest_strength ON true
          WHERE cl.status = 'preview'
            AND COALESCE(latest_strength.final_score, 0) < 70
          ORDER BY a.id, a.checked_at DESC NULLS LAST, a.created_at DESC
        ) latest
        ORDER BY checked_at DESC NULLS LAST, created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 25), 100)),),
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        strength = _latest_strength(str(row["audit_id"]))
        issues = [item.get("code") for item in (strength.get("issues_json") or []) if isinstance(item, dict)]
        remediable = [issue for issue in issues if issue in REMEDIABLE_ISSUES]
        candidates.append(
            {
                "audit_id": str(row["audit_id"]),
                "campaign_id": str(row["campaign_id"]) if row.get("campaign_id") else None,
                "domain": row["domain"],
                "url": row["url"],
                "business_name": row["business_name"],
                "strength_score": int(strength["final_score"] or 0),
                "issues": issues,
                "remediable_issues": remediable,
                "needs_scanner_refresh": bool({"missing_screenshots", "missing_issues", "fewer_than_three_issues"} & set(issues)),
                "needs_summary": "missing_summary" in issues,
            }
        )
    return json_safe({"candidate_count": len(candidates), "candidates": candidates, **SAFE_FLAGS})


def _queue_scanner_refresh(candidate: dict[str, Any]) -> dict[str, Any]:
    existing = fetch_one(
        """
        SELECT id, status
        FROM scanner_jobs
        WHERE audit_id = %s
          AND status IN ('queued', 'running')
          AND result_json->>'reason' = 'audit_evidence_remediation'
        ORDER BY queued_at DESC
        LIMIT 1
        """,
        (candidate["audit_id"],),
    )
    if existing:
        return {"status": "existing", "scanner_job_id": str(existing["id"]), "audit_id": candidate["audit_id"]}
    row = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, audit_id, result_json)
        VALUES (%s, %s, false, 'queued', 190, %s, %s)
        RETURNING id, status, priority
        """,
        (
            candidate["url"],
            candidate.get("business_name") or candidate.get("domain"),
            candidate["audit_id"],
            Jsonb(
                {
                    "reason": "audit_evidence_remediation",
                    "audit_id": candidate["audit_id"],
                    "campaign_id": candidate.get("campaign_id"),
                    "issues": candidate.get("remediable_issues", []),
                    **SAFE_FLAGS,
                }
            ),
        ),
    )
    return {"status": "queued", "scanner_job_id": str(row["id"]), "audit_id": candidate["audit_id"], "priority": int(row["priority"])}


def _create_audit_task(candidate: dict[str, Any]) -> dict[str, Any]:
    title = "Improve Rescue audit evidence after strength gate"
    existing = fetch_one(
        """
        SELECT id
        FROM codex_tasks
        WHERE status IN ('open', 'review_required')
          AND input_json->>'source' = 'audit_evidence_remediation'
          AND input_json->>'audit_id' = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (candidate["audit_id"],),
    )
    if existing:
        return {"status": "existing", "task_id": str(existing["id"]), "audit_id": candidate["audit_id"]}
    row = execute(
        """
        INSERT INTO codex_tasks(type, priority, status, title, description, input_json)
        VALUES ('scanner_failed_case', 'medium', 'open', %s, %s, %s)
        RETURNING id
        """,
        (
            title,
            "Audit evidence is too weak for campaign preview; refresh scanner evidence without invasive checks.",
            Jsonb(
                {
                    "source": "audit_evidence_remediation",
                    "audit_id": candidate["audit_id"],
                    "campaign_id": candidate.get("campaign_id"),
                    "domain": candidate.get("domain"),
                    "issues": candidate.get("remediable_issues", []),
                    "constraints": ["public_safe_scan_only", "no_live_outreach", "no_secret_exposure"],
                    **SAFE_FLAGS,
                }
            ),
        ),
    )
    return {"status": "created", "task_id": str(row["id"]), "audit_id": candidate["audit_id"]}


def audit_evidence_remediation(limit: int = 25, dry_run: bool = True) -> dict[str, Any]:
    snapshot = audit_evidence_candidates(limit)
    queued: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    touched: list[dict[str, Any]] = []
    for candidate in snapshot["candidates"]:
        if candidate["needs_summary"] and not dry_run:
            execute(
                """
                UPDATE audits
                SET summary = COALESCE(NULLIF(summary, ''), 'Public website check needs refreshed evidence before outreach.'),
                    checked_at = COALESCE(checked_at, now())
                WHERE id = %s
                """,
                (candidate["audit_id"],),
            )
            touched.append({"audit_id": candidate["audit_id"], "updated_summary_if_missing": True})
        if candidate["needs_scanner_refresh"] and not dry_run:
            queued.append(_queue_scanner_refresh(candidate))
        if candidate["remediable_issues"] and not dry_run:
            tasks.append(_create_audit_task(candidate))
        if not dry_run:
            score_audit_strength(candidate["audit_id"])
    result = json_safe(
        {
            "status": "dry_run" if dry_run else "remediation_queued",
            "candidate_count": snapshot["candidate_count"],
            "queued_scanner_jobs": len([item for item in queued if item["status"] == "queued"]),
            "existing_scanner_jobs": len([item for item in queued if item["status"] == "existing"]),
            "codex_task_count": len([item for item in tasks if item["status"] == "created"]),
            "existing_task_count": len([item for item in tasks if item["status"] == "existing"]),
            "summary_updates": len(touched),
            "candidates": snapshot["candidates"],
            "scanner_jobs": queued,
            "tasks": tasks,
            "summary_touches": touched,
            **SAFE_FLAGS,
        }
    )
    saved = execute(
        """
        INSERT INTO audit_evidence_remediation_runs(
          status, candidate_count, queued_scanner_jobs, codex_task_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (result["status"], result["candidate_count"], result["queued_scanner_jobs"], result["codex_task_count"], Jsonb(result)),
    )
    result["run_id"] = str(saved["id"])
    result["created_at"] = saved["created_at"].isoformat()
    return result


def latest_audit_evidence_remediation_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, candidate_count, queued_scanner_jobs, codex_task_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM audit_evidence_remediation_runs
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
                    "candidate_count": int(row["candidate_count"] or 0),
                    "queued_scanner_jobs": int(row["queued_scanner_jobs"] or 0),
                    "codex_task_count": int(row["codex_task_count"] or 0),
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
