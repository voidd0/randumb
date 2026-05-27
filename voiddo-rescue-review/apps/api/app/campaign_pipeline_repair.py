from __future__ import annotations

from typing import Any

from .campaign_control_room import campaign_control_room_snapshot, prepare_campaign_control_room
from .db import execute, fetch_all, fetch_one
from .lead_scoring import score_lead
from .p0 import json_safe


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def campaign_pipeline_gap_snapshot(limit: int = 100) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 500))
    linkable = _count(
        """
        SELECT count(*)
        FROM audits a
        JOIN businesses b ON lower(b.domain) = lower(a.domain)
        WHERE a.status = 'completed'
          AND a.business_id IS NULL
          AND a.lead_id IS NULL
        """
    )
    linked_candidates = _count(
        """
        SELECT count(*)
        FROM leads l
        JOIN audits a ON a.lead_id = l.id OR a.business_id = l.business_id
        WHERE a.status = 'completed'
          AND l.email IS NOT NULL
          AND COALESCE(l.score, 0) >= 70
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(s.email) = lower(l.email))
        """
    )
    unscored = _count(
        """
        SELECT count(*)
        FROM leads l
        JOIN audits a ON a.lead_id = l.id OR a.business_id = l.business_id
        WHERE a.status = 'completed'
          AND l.email IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM lead_scores ls WHERE ls.lead_id = l.id AND (ls.audit_id = a.id OR ls.audit_id IS NULL)
          )
        """
    )
    preview_rows = _count("SELECT count(*) FROM campaign_leads WHERE status = 'preview'")
    control_room = campaign_control_room_snapshot(min(safe_limit, 100), 70)
    return json_safe(
        {
            "status": "gap_detected" if linkable or unscored or control_room.get("ready_candidate_count", 0) <= 0 else "ready",
            "orphan_audits_linkable_by_domain": linkable,
            "linked_candidate_count": linked_candidates,
            "unscored_linked_leads": unscored,
            "campaign_preview_rows": preview_rows,
            "control_room": {
                "candidate_count": control_room.get("candidate_count", 0),
                "ready_candidate_count": control_room.get("ready_candidate_count", 0),
                "segment_count": control_room.get("segment_count", 0),
            },
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def _link_orphan_audits(limit: int) -> list[str]:
    rows = fetch_all(
        """
        WITH matches AS (
          SELECT a.id AS audit_id,
                 b.id AS business_id,
                 (
                   SELECT l.id
                   FROM leads l
                   WHERE l.business_id = b.id
                   ORDER BY l.created_at DESC
                   LIMIT 1
                 ) AS lead_id
          FROM audits a
          JOIN businesses b ON lower(b.domain) = lower(a.domain)
          WHERE a.status = 'completed'
            AND a.business_id IS NULL
            AND a.lead_id IS NULL
          ORDER BY a.created_at DESC
          LIMIT %s
        ),
        updated AS (
          UPDATE audits a
          SET business_id = matches.business_id,
              lead_id = matches.lead_id
          FROM matches
          WHERE a.id = matches.audit_id
            AND matches.lead_id IS NOT NULL
          RETURNING a.id
        )
        SELECT id FROM updated
        """,
        (limit,),
    )
    return [str(row["id"]) for row in rows]


def _score_linked_leads(limit: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT DISTINCT ON (l.id) l.id AS lead_id, a.id AS audit_id
        FROM leads l
        JOIN audits a ON a.lead_id = l.id OR a.business_id = l.business_id
        WHERE a.status = 'completed'
          AND l.email IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM lead_scores ls WHERE ls.lead_id = l.id AND (ls.audit_id = a.id OR ls.audit_id IS NULL)
          )
        ORDER BY l.id, a.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    scored = []
    for row in rows:
        score = score_lead(str(row["lead_id"]), str(row["audit_id"]))
        scored.append({"lead_id": str(row["lead_id"]), "audit_id": str(row["audit_id"]), "final_score": int(score["final_score"])})
    return scored


def repair_campaign_pipeline(limit: int = 100, dry_run: bool = True) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 500))
    before = campaign_pipeline_gap_snapshot(safe_limit)
    if dry_run:
        return {
            "status": "dry_run",
            "before": before,
            "linked_audits": 0,
            "scored_leads": 0,
            "campaign_previews_prepared": 0,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    linked = _link_orphan_audits(safe_limit)
    scored = _score_linked_leads(safe_limit)
    prepared = prepare_campaign_control_room(safe_limit, 70, dry_run=False, offer_key="contact_form_repair", max_segments=5)
    after = campaign_pipeline_gap_snapshot(safe_limit)
    return json_safe(
        {
            "status": "repaired",
            "before": before,
            "linked_audits": len(linked),
            "scored_leads": len(scored),
            "campaign_previews_prepared": int(prepared.get("campaign_previews_prepared", 0) or 0),
            "campaigns_created_or_confirmed": int(prepared.get("campaigns_created_or_confirmed", 0) or 0),
            "after": after,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
