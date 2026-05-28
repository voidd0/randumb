from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import json_safe
from .scouts import _is_excluded_large_brand, is_excluded_sensitive_target


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _reason_for(row: dict[str, Any]) -> str:
    niche = str(row.get("niche") or "").strip().lower()
    if niche in {"government", "banks", "bank", "hospitals", "hospital", "gambling", "adult", "crypto", "political"}:
        return "excluded_niche"
    if _is_excluded_large_brand(
        str(row.get("business_name") or ""),
        str(row.get("domain") or ""),
        str(row.get("website_url") or ""),
    ):
        return "excluded_large_enterprise"
    return "excluded_sensitive_target"


def _archive_scanner_jobs_for_sensitive_refs(reason: str, lead_id: str | None = None, scout_lead_id: str | None = None) -> int:
    row = execute(
        """
        WITH candidates AS (
          SELECT id
          FROM scanner_jobs
          WHERE status IN ('queued', 'running', 'completed', 'failed')
            AND (
              (%s::text IS NOT NULL AND result_json->>'lead_id' = %s::text)
              OR (%s::text IS NOT NULL AND result_json->>'scout_lead_id' = %s::text)
            )
        ),
        updated_jobs AS (
          UPDATE scanner_jobs sj
          SET status = 'archived_sensitive_target',
              result_json = COALESCE(result_json, '{}'::jsonb) || %s::jsonb,
              updated_at = now()
          FROM candidates
          WHERE sj.id = candidates.id
          RETURNING sj.id, sj.audit_id
        ),
        updated_audits AS (
          UPDATE audits a
          SET status = 'archived_sensitive_target'
          FROM updated_jobs uj
          WHERE uj.audit_id IS NOT NULL
            AND a.id = uj.audit_id
          RETURNING a.id
        )
        SELECT count(*) AS count FROM updated_jobs
        """,
        (
            lead_id,
            lead_id,
            scout_lead_id,
            scout_lead_id,
            Jsonb({"scout_sensitive_hygiene": {**SAFE_FLAGS, "reason": reason}}),
        ),
    )
    return int(row["count"] or 0) if row else 0


def scout_sensitive_target_snapshot(limit: int = 200) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 200), 500))
    rows = fetch_all(
        """
        SELECT sl.id AS scout_lead_id, sl.business_name, sl.domain, sl.website_url, sl.niche,
               l.id AS lead_id, b.id AS business_id
        FROM scout_leads sl
        LEFT JOIN businesses b ON lower(b.domain) = lower(sl.domain)
        LEFT JOIN leads l ON l.business_id = b.id
        WHERE sl.status = 'accepted'
          AND COALESCE(sl.domain, '') <> ''
        ORDER BY sl.created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    candidates = []
    for row in rows:
        payload = dict(row)
        if not is_excluded_sensitive_target(
            str(payload.get("business_name") or ""),
            str(payload.get("domain") or ""),
            str(payload.get("website_url") or ""),
            str(payload.get("niche") or ""),
        ):
            continue
        candidates.append(
            {
                "scout_lead_id": str(payload["scout_lead_id"]),
                "lead_id": str(payload["lead_id"]) if payload.get("lead_id") else None,
                "business_id": str(payload["business_id"]) if payload.get("business_id") else None,
                "domain_hash": hashlib.sha256(str(payload.get("domain") or "").lower().encode("utf-8")).hexdigest()[:12],
                "reason": _reason_for(payload),
            }
        )
    return json_safe(
        {
            "status": "candidates_found" if candidates else "clean",
            "candidate_count": len(candidates),
            "candidates": candidates,
            **SAFE_FLAGS,
        }
    )


def archive_sensitive_scout_targets(limit: int = 200, apply: bool = False) -> dict[str, Any]:
    snapshot = scout_sensitive_target_snapshot(limit)
    archived = []
    archived_scanner_jobs = 0
    if apply:
        for item in snapshot["candidates"]:
            reason = item["reason"]
            scout_lead_id = item["scout_lead_id"]
            lead_id = item.get("lead_id")
            business_id = item.get("business_id")
            execute(
                """
                UPDATE scout_leads
                SET status = 'rejected',
                    rejection_reason = %s
                WHERE id = %s
                """,
                (reason, scout_lead_id),
            )
            if lead_id:
                execute("UPDATE leads SET status = 'excluded_sensitive_target', score = 0, updated_at = now() WHERE id = %s", (lead_id,))
                archived_scanner_jobs += _archive_scanner_jobs_for_sensitive_refs(reason, lead_id=lead_id, scout_lead_id=scout_lead_id)
                execute(
                    """
                    UPDATE campaign_leads
                    SET status = 'archived_sensitive_target',
                        preview_json = COALESCE(preview_json, '{}'::jsonb) || %s::jsonb,
                        updated_at = now()
                    WHERE lead_id = %s
                      AND status = 'preview'
                    """,
                    (Jsonb({"scout_sensitive_hygiene": {**SAFE_FLAGS, "reason": reason}}), lead_id),
                )
            if not lead_id:
                archived_scanner_jobs += _archive_scanner_jobs_for_sensitive_refs(reason, scout_lead_id=scout_lead_id)
            if business_id:
                execute("UPDATE businesses SET status = 'excluded_sensitive_target', updated_at = now() WHERE id = %s", (business_id,))
            archived.append(item)
        scanner_row = execute(
            """
            WITH candidates AS (
              SELECT sj.id
              FROM scanner_jobs sj
              LEFT JOIN leads l ON l.id::text = sj.result_json->>'lead_id'
              LEFT JOIN scout_leads sl ON sl.id::text = sj.result_json->>'scout_lead_id'
              WHERE sj.status IN ('queued', 'running', 'completed', 'failed')
                AND (
                  l.status = 'excluded_sensitive_target'
                  OR sl.rejection_reason = 'excluded_sensitive_target'
                  OR sl.rejection_reason = 'excluded_large_enterprise'
                )
            ),
            updated AS (
              UPDATE scanner_jobs sj
              SET status = 'archived_sensitive_target',
                  result_json = COALESCE(result_json, '{}'::jsonb) || %s::jsonb,
                  updated_at = now()
              FROM candidates
              WHERE sj.id = candidates.id
              RETURNING sj.id, sj.audit_id
            ),
            updated_audits AS (
              UPDATE audits a
              SET status = 'archived_sensitive_target'
              FROM updated
              WHERE updated.audit_id IS NOT NULL
                AND a.id = updated.audit_id
              RETURNING a.id
            )
            SELECT count(*) AS count FROM updated
            """,
            (Jsonb({"scout_sensitive_hygiene": {**SAFE_FLAGS, "reason": "existing_excluded_sensitive_target"}}),),
        )
        archived_scanner_jobs += int(scanner_row["count"] or 0) if scanner_row else 0
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('scout_sensitive_hygiene', %s, 'Scout sensitive-target hygiene evaluated', %s)
        """,
        ("warning" if snapshot["candidate_count"] else "info", Jsonb({"apply": apply, "candidate_count": snapshot["candidate_count"], **SAFE_FLAGS})),
    )
    return json_safe(
        {
            "status": "archived" if archived else ("dry_run_candidates" if snapshot["candidate_count"] else "clean"),
            "apply": apply,
            "candidate_count": snapshot["candidate_count"],
            "archived_count": len(archived),
            "archived_scanner_jobs_count": archived_scanner_jobs,
            "archived": archived,
            **SAFE_FLAGS,
        }
    )
