from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .audit_strength import score_audit_strength
from .campaign_preview_reviews import preview_review_evidence
from .db import execute, fetch_all, fetch_one
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def held_preview_remediation_candidates(limit: int = 25) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    rows = fetch_all(
        """
        SELECT cl.id AS campaign_lead_id, cl.campaign_id, cl.audit_id, cl.score AS lead_score,
               c.name AS campaign_name, b.name AS business_name, b.domain,
               a.url, a.public_slug, a.summary,
               latest_review.reason AS review_reason,
               latest_strength.final_score AS audit_strength_score,
               latest_strength.issues_json AS strength_issues,
               issue_counts.issue_count,
               issue_counts.critical_high_count,
               shot_counts.screenshot_count
        FROM campaign_leads cl
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN leads l ON l.id = cl.lead_id
        JOIN businesses b ON b.id = l.business_id
        LEFT JOIN audits a ON a.id = cl.audit_id
        JOIN LATERAL (
          SELECT action, reason
          FROM campaign_preview_reviews
          WHERE campaign_lead_id = cl.id
          ORDER BY created_at DESC
          LIMIT 1
        ) latest_review ON true
        LEFT JOIN LATERAL (
          SELECT final_score, issues_json FROM audit_strength_scores WHERE audit_id = cl.audit_id ORDER BY created_at DESC LIMIT 1
        ) latest_strength ON true
        LEFT JOIN LATERAL (
          SELECT count(*) AS issue_count,
                 count(*) FILTER (WHERE severity IN ('critical', 'high')) AS critical_high_count
          FROM audit_issues
          WHERE audit_id = cl.audit_id
        ) issue_counts ON true
        LEFT JOIN LATERAL (
          SELECT count(*) AS screenshot_count FROM screenshots WHERE audit_id = cl.audit_id
        ) shot_counts ON true
        WHERE cl.status = 'preview'
          AND latest_review.action = 'held'
        ORDER BY cl.updated_at DESC NULLS LAST, cl.created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    candidates = []
    for row in rows:
        audit_strength = int(row["audit_strength_score"] or 0)
        if not audit_strength and row.get("audit_id"):
            audit_strength = int(score_audit_strength(str(row["audit_id"]))["final_score"])
        issue_count = int(row["issue_count"] or 0)
        critical_high_count = int(row["critical_high_count"] or 0)
        screenshot_count = int(row["screenshot_count"] or 0)
        evidence = preview_review_evidence(
            lead_score=int(row["lead_score"] or 0),
            audit_strength=audit_strength,
            issue_count=issue_count,
            critical_high_count=critical_high_count,
            screenshot_count=screenshot_count,
            public_slug=row.get("public_slug"),
        )
        gaps = list(evidence["evidence_gaps"])
        if not row.get("public_slug"):
            gaps.append("missing_public_audit_slug")
        if not row.get("summary"):
            gaps.append("missing_summary")
        if screenshot_count < 1:
            gaps.append("missing_screenshots")
        gaps = sorted(set(gaps))
        next_safe_actions = []
        if {"missing_screenshot_evidence", "single_screenshot_only", "audit_strength_below_minimum_auto_review_path", "no_public_issues_recorded", "no_critical_or_high_public_issue"} & set(gaps):
            next_safe_actions.append("refresh_public_scanner_evidence")
        if {"missing_summary", "missing_public_audit_slug", "missing_public_audit_page"} & set(gaps):
            next_safe_actions.append("repair_audit_page_metadata")
        if "lead_score_below_lowest_auto_review_path" in gaps:
            next_safe_actions.append("exclude_from_canary_until_stronger_public_signal")
        candidates.append(
            {
                "campaign_lead_id": str(row["campaign_lead_id"]),
                "campaign_id": str(row["campaign_id"]),
                "audit_id": str(row["audit_id"]) if row.get("audit_id") else None,
                "lead_score": int(row["lead_score"] or 0),
                "audit_strength_score": audit_strength,
                "issue_count": issue_count,
                "critical_high_count": critical_high_count,
                "screenshot_count": screenshot_count,
                "business_name": row["business_name"],
                "domain": row["domain"],
                "url": row["url"],
                "audit_slug": row["public_slug"],
                "review_reason": row["review_reason"] or "",
                "evidence_gaps": gaps,
                "approval_paths": evidence["approval_paths"],
                "decision_basis": evidence["decision_basis"],
                "next_safe_actions": next_safe_actions,
                "needs_scanner_refresh": "refresh_public_scanner_evidence" in next_safe_actions,
                "needs_copy_or_summary_repair": bool({"missing_summary", "missing_public_audit_slug"} & set(gaps)),
            }
        )
    return json_safe({"status": "ready" if candidates else "empty", "candidate_count": len(candidates), "candidates": candidates, **SAFE_FLAGS})


def _queue_review_scanner_refresh(candidate: dict[str, Any]) -> dict[str, Any]:
    if not candidate.get("audit_id") or not candidate.get("url"):
        return {"status": "skipped_missing_audit_or_url", "campaign_lead_id": candidate["campaign_lead_id"]}
    existing = fetch_one(
        """
        SELECT id, status
        FROM scanner_jobs
        WHERE audit_id = %s
          AND status IN ('queued', 'running')
          AND result_json->>'reason' = 'campaign_preview_review_remediation'
        ORDER BY queued_at DESC
        LIMIT 1
        """,
        (candidate["audit_id"],),
    )
    if existing:
        return {"status": "existing", "scanner_job_id": str(existing["id"]), "campaign_lead_id": candidate["campaign_lead_id"]}
    row = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, audit_id, result_json)
        VALUES (%s, %s, false, 'queued', 240, %s, %s)
        RETURNING id, priority
        """,
        (
            candidate["url"],
            candidate.get("business_name") or candidate.get("domain"),
            candidate["audit_id"],
            Jsonb({"reason": "campaign_preview_review_remediation", "campaign_lead_id": candidate["campaign_lead_id"], "campaign_id": candidate["campaign_id"], "evidence_gaps": candidate["evidence_gaps"], **SAFE_FLAGS}),
        ),
    )
    return {"status": "queued", "scanner_job_id": str(row["id"]), "priority": int(row["priority"] or 0), "campaign_lead_id": candidate["campaign_lead_id"]}


def _create_review_remediation_task(candidate: dict[str, Any]) -> dict[str, Any]:
    existing = fetch_one(
        """
        SELECT id FROM codex_tasks
        WHERE status IN ('open', 'review_required')
          AND input_json->>'source' = 'campaign_preview_review_remediation'
          AND input_json->>'campaign_lead_id' = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (candidate["campaign_lead_id"],),
    )
    if existing:
        return {"status": "existing", "task_id": str(existing["id"]), "campaign_lead_id": candidate["campaign_lead_id"]}
    row = execute(
        """
        INSERT INTO codex_tasks(type, priority, status, title, description, input_json)
        VALUES ('scanner_failed_case', 'medium', 'open', %s, %s, %s)
        RETURNING id
        """,
        (
            "Upgrade held Rescue preview evidence",
            "A preview candidate was held by autonomous review. Refresh public-safe evidence and copy before campaign use.",
            Jsonb({"source": "campaign_preview_review_remediation", "campaign_lead_id": candidate["campaign_lead_id"], "campaign_id": candidate["campaign_id"], "audit_id": candidate.get("audit_id"), "domain": candidate["domain"], "evidence_gaps": candidate["evidence_gaps"], "constraints": ["no_live_outreach", "public_safe_scan_only", "no_secret_exposure"], **SAFE_FLAGS}),
        ),
    )
    return {"status": "created", "task_id": str(row["id"]), "campaign_lead_id": candidate["campaign_lead_id"]}


def remediate_held_preview_reviews(limit: int = 25, dry_run: bool = True) -> dict[str, Any]:
    snapshot = held_preview_remediation_candidates(limit)
    queued = []
    tasks = []
    for candidate in snapshot["candidates"]:
        if candidate["needs_scanner_refresh"] and not dry_run:
            queued.append(_queue_review_scanner_refresh(candidate))
        if candidate["evidence_gaps"] and not dry_run:
            tasks.append(_create_review_remediation_task(candidate))
    result = json_safe(
        {
            "status": "dry_run" if dry_run else "remediation_queued",
            "candidate_count": snapshot["candidate_count"],
            "queued_scanner_jobs": len([item for item in queued if item["status"] == "queued"]),
            "existing_scanner_jobs": len([item for item in queued if item["status"] == "existing"]),
            "codex_task_count": len([item for item in tasks if item["status"] == "created"]),
            "existing_task_count": len([item for item in tasks if item["status"] == "existing"]),
            "candidates": snapshot["candidates"],
            "scanner_jobs": queued,
            "tasks": tasks,
            **SAFE_FLAGS,
        }
    )
    saved = execute(
        """
        INSERT INTO campaign_review_remediation_runs(status, candidate_count, queued_scanner_jobs, codex_task_count, result_json)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (result["status"], result["candidate_count"], result["queued_scanner_jobs"], result["codex_task_count"], Jsonb(result)),
    )
    result["run_id"] = str(saved["id"])
    result["created_at"] = saved["created_at"].isoformat()
    return result
