from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .launch_activation import launch_activation_readiness
from .p0 import json_safe, live_outreach_quota_status, recipient_hash


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _candidate_rows(limit: int = 20) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in fetch_all(
            """
            SELECT DISTINCT ON (om.id)
                   om.id AS outreach_message_id,
                   cl.campaign_id,
                   a.domain,
                   a.public_slug,
                   om.created_at,
                   lower(split_part(l.email, '@', 2)) AS recipient_domain
            FROM outreach_messages om
            JOIN leads l ON l.id = om.lead_id
            JOIN businesses b ON b.id = l.business_id
            JOIN audits a ON a.id = om.audit_id
            JOIN campaign_leads cl ON cl.lead_id = om.lead_id AND cl.audit_id = om.audit_id AND cl.status = 'preview'
            JOIN LATERAL (
              SELECT action
              FROM campaign_preview_reviews
              WHERE campaign_lead_id = cl.id
              ORDER BY created_at DESC
              LIMIT 1
            ) latest_review ON true
            WHERE om.status = 'preview'
              AND latest_review.action = 'approved'
              AND om.html_body IS NOT NULL
              AND om.html_body <> ''
              AND om.body LIKE '%%/unsubscribe/u_%%'
              AND COALESCE(l.status, '') NOT IN ('excluded_sensitive_target', 'suppressed', 'unsubscribed')
              AND COALESCE(b.status, '') NOT IN ('excluded_sensitive_target', 'suppressed', 'unsubscribed')
              AND NOT EXISTS (
                    SELECT 1 FROM suppression_list s
                    WHERE lower(s.email) = lower(l.email)
                       OR lower(s.domain) = lower(split_part(l.email, '@', 2))
              )
              AND EXISTS (
                    SELECT 1
                    FROM campaign_preflight_runs p
                    WHERE p.campaign_id = cl.campaign_id
                      AND p.decision = 'PASS_NO_SEND_PREFLIGHT'
                      AND p.created_at >= now() - interval '120 minutes'
              )
            ORDER BY om.id, om.created_at DESC
            LIMIT %s
            """,
            (max(1, min(int(limit or 20), 100)),),
        )
    ]


def live_outreach_queue_candidates(limit: int = 20) -> dict[str, Any]:
    rows = _candidate_rows(limit)
    return json_safe(
        {
            "status": "ready" if rows else "empty",
            "candidate_count": len(rows),
            "candidates": [
                {
                    "outreach_message_id": str(row["outreach_message_id"]),
                    "campaign_id": str(row["campaign_id"]),
                    "domain": row["domain"],
                    "audit_slug": row["public_slug"],
                    "recipient_domain_hash": recipient_hash(row["recipient_domain"] or ""),
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
            **SAFE_FLAGS,
        }
    )


def _record_send_run(result: dict[str, Any], requested_by: str, dry_run: bool, requested_limit: int) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO outreach_send_runs(
          status, decision, requested_by, dry_run, requested_limit,
          candidate_count, staged_count, sent_count, blocked_count,
          result_json, send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, status, decision, requested_by, dry_run, requested_limit,
                  candidate_count, staged_count, sent_count, blocked_count, created_at
        """,
        (
            result["status"],
            result["decision"],
            requested_by,
            dry_run,
            requested_limit,
            int(result.get("candidate_count") or 0),
            int(result.get("staged_count") or 0),
            int(result.get("sent_count") or 0),
            int(result.get("blocked_count") or 0),
            Jsonb(result),
        ),
    )
    recorded = dict(row)
    recorded.update(SAFE_FLAGS)
    return json_safe(recorded)


def stage_live_outreach_batch(limit: int = 20, dry_run: bool = True, requested_by: str = "operator") -> dict[str, Any]:
    settings = get_settings()
    safe_limit = max(1, min(int(limit or 20), settings.daily_send_limit, 100))
    readiness = launch_activation_readiness(safe_limit)
    candidates = _candidate_rows(safe_limit)
    quota = live_outreach_quota_status()
    blockers: list[str] = []
    if readiness.get("decision") != "READY_FOR_OPERATOR_ENV_ACTIVATION":
        blockers.append("launch_activation_not_ready")
    if not quota["allowed"]:
        blockers.extend(quota["blockers"])
    if not candidates:
        blockers.append("no_approved_preview_candidates")
    if settings.outreach_dry_run or settings.outreach_paused or not settings.first_live_send_flag:
        blockers.append("live_runtime_flags_locked")
    if not settings.allow_live_outreach_activation:
        blockers.append("allow_live_outreach_activation_env_false")
    if dry_run:
        blockers.append("dry_run_no_messages_staged")

    staged_ids: list[str] = []
    decision = "STAGED_FOR_WORKER" if not blockers else "BLOCKED"
    if decision == "STAGED_FOR_WORKER":
        ids = [str(row["outreach_message_id"]) for row in candidates]
        execute("UPDATE outreach_messages SET status = 'queued' WHERE id = ANY(%s::uuid[])", (ids,))
        staged_ids = ids

    result = json_safe(
        {
            "status": "queued" if staged_ids else "blocked",
            "decision": decision,
            "blockers": sorted(set(blockers)),
            "candidate_count": len(candidates),
            "staged_count": len(staged_ids),
            "sent_count": 0,
            "blocked_count": 0 if staged_ids else len(candidates),
            "quota": quota,
            "readiness_decision": readiness.get("decision"),
            "candidate_ids": staged_ids if staged_ids else [],
            "candidate_preview": [
                {
                    "outreach_message_id": str(row["outreach_message_id"]),
                    "campaign_id": str(row["campaign_id"]),
                    "domain": row["domain"],
                    "audit_slug": row["public_slug"],
                    "recipient_domain_hash": recipient_hash(row["recipient_domain"] or ""),
                }
                for row in candidates[:safe_limit]
            ],
            **SAFE_FLAGS,
        }
    )
    run = _record_send_run(result, requested_by, dry_run, safe_limit)
    return json_safe({"run": run, "result": result, **SAFE_FLAGS})


def latest_outreach_send_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, decision, requested_by, dry_run, requested_limit,
               candidate_count, staged_count, sent_count, blocked_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM outreach_send_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 50)),),
    )
    queued = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    sent = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'sent'")
    return json_safe(
        {
            "count": len(rows),
            "runs": [dict(row) for row in rows],
            "queued_message_count": int((queued or {}).get("count", 0) or 0),
            "sent_message_count": int((sent or {}).get("count", 0) or 0),
            **SAFE_FLAGS,
        }
    )
