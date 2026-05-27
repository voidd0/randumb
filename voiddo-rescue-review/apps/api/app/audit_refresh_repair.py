from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _mismatched_refresh_jobs(limit: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT sj.id AS job_id,
               sj.audit_id AS duplicate_audit_id,
               sj.result_json->'job_meta'->>'audit_id' AS original_audit_id
        FROM scanner_jobs sj
        WHERE COALESCE(sj.result_json->>'reason', sj.result_json->'job_meta'->>'reason') = 'audit_evidence_remediation'
          AND sj.status = 'completed'
          AND sj.audit_id IS NOT NULL
          AND sj.result_json->'job_meta'->>'audit_id' IS NOT NULL
          AND sj.audit_id::text <> sj.result_json->'job_meta'->>'audit_id'
        ORDER BY sj.completed_at DESC NULLS LAST, sj.updated_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 25), 100)),),
    )
    return [
        {
            "job_id": str(row["job_id"]),
            "duplicate_audit_id": str(row["duplicate_audit_id"]),
            "original_audit_id": str(row["original_audit_id"]),
        }
        for row in rows
    ]


def audit_refresh_attachment_repair_snapshot(limit: int = 25) -> dict[str, Any]:
    jobs = _mismatched_refresh_jobs(limit)
    return json_safe(
        {
            "status": "ready",
            "mismatch_count": len(jobs),
            "jobs": jobs,
            **SAFE_FLAGS,
        }
    )


def repair_audit_refresh_attachments(limit: int = 25, dry_run: bool = True) -> dict[str, Any]:
    jobs = _mismatched_refresh_jobs(limit)
    repaired: list[dict[str, Any]] = []
    if not dry_run:
        for job in jobs:
            duplicate_id = job["duplicate_audit_id"]
            original_id = job["original_audit_id"]
            updated = execute(
                """
                UPDATE audits original
                SET business_id = COALESCE(original.business_id, duplicate.business_id),
                    lead_id = COALESCE(original.lead_id, duplicate.lead_id),
                    domain = duplicate.domain,
                    url = duplicate.url,
                    status = 'completed',
                    score = duplicate.score,
                    summary = duplicate.summary,
                    checked_at = duplicate.checked_at
                FROM audits duplicate
                WHERE original.id = %s
                  AND duplicate.id = %s
                RETURNING original.id
                """,
                (original_id, duplicate_id),
            )
            if not updated:
                continue
            execute("DELETE FROM audit_issues WHERE audit_id = %s", (original_id,))
            execute("UPDATE audit_issues SET audit_id = %s WHERE audit_id = %s", (original_id, duplicate_id))
            execute("DELETE FROM screenshots WHERE audit_id = %s", (original_id,))
            execute("UPDATE screenshots SET audit_id = %s WHERE audit_id = %s", (original_id, duplicate_id))
            execute(
                """
                UPDATE scanner_jobs
                SET audit_id = %s,
                    result_json = result_json || %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    original_id,
                    Jsonb(
                        {
                            "audit_refresh_attachment_repaired": True,
                            "duplicate_audit_id": duplicate_id,
                            **SAFE_FLAGS,
                        }
                    ),
                    job["job_id"],
                ),
            )
            execute(
                """
                UPDATE audits
                SET status = 'superseded',
                    summary = 'Superseded by original audit after audit-refresh attachment repair.',
                    checked_at = now()
                WHERE id = %s
                """,
                (duplicate_id,),
            )
            execute(
                """
                INSERT INTO system_events(type, severity, message, payload_json)
                VALUES ('audit_refresh_attachment_repair', 'info', 'Audit-refresh scanner result reattached to original audit.', %s)
                """,
                (
                    Jsonb(
                        {
                            "job_id": job["job_id"],
                            "original_audit_id": original_id,
                            "duplicate_audit_id": duplicate_id,
                            **SAFE_FLAGS,
                        }
                    ),
                ),
            )
            repaired.append(job)
    return json_safe(
        {
            "status": "dry_run" if dry_run else ("repaired" if repaired else "idle_no_mismatches"),
            "dry_run": dry_run,
            "mismatch_count": len(jobs),
            "repaired_count": 0 if dry_run else len(repaired),
            "repaired": repaired,
            **SAFE_FLAGS,
        }
    )
