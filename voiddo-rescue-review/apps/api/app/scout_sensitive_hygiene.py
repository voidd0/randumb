from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import json_safe
from .scouts import is_excluded_sensitive_target


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
    return "excluded_sensitive_target"


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
            if business_id:
                execute("UPDATE businesses SET status = 'excluded_sensitive_target', updated_at = now() WHERE id = %s", (business_id,))
            archived.append(item)
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
            "archived": archived,
            **SAFE_FLAGS,
        }
    )
