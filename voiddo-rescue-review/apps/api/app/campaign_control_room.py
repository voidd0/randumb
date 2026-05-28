from __future__ import annotations

from collections import defaultdict
from typing import Any

from .audit_strength import score_audit_strength
from .campaign_control import campaign_readiness_snapshot
from .db import execute, fetch_all, fetch_one
from .p0 import json_safe, latest_mail_qa_decision, mail_signal_summary
from .scouts import create_campaign, prepare_campaign_gated

TEST_COUNTRY_PATTERN = r"^(P7|P8|P9|P10|P11|P12|P59|P60|P61|P62|P63|P68|P72|P73|P74)"


def _latest_audit_strength(audit_id: str) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT final_score, completeness_score, proof_score, commercial_score, issues_json, created_at
        FROM audit_strength_scores
        WHERE audit_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (audit_id,),
    )
    return dict(row) if row else None


def qualified_campaign_lead_candidates(limit: int = 100, threshold: int = 70) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 250))
    safe_threshold = max(0, min(int(threshold or 70), 100))
    rows = fetch_all(
        """
        SELECT l.id AS lead_id, l.country, l.language, l.niche, l.source,
               b.name AS business_name, b.domain,
               a.id AS audit_id, a.public_slug, a.score AS audit_score, a.status AS audit_status,
               COALESCE(ls.final_score, l.score, 0) AS final_score,
               latest_strength.final_score AS audit_strength_score
        FROM leads l
        JOIN businesses b ON b.id = l.business_id
        JOIN audits a ON a.lead_id = l.id OR a.business_id = b.id
        LEFT JOIN LATERAL (
          SELECT final_score FROM lead_scores WHERE lead_id = l.id ORDER BY created_at DESC LIMIT 1
        ) ls ON true
        LEFT JOIN LATERAL (
          SELECT final_score FROM audit_strength_scores WHERE audit_id = a.id ORDER BY created_at DESC LIMIT 1
        ) latest_strength ON true
        WHERE COALESCE(ls.final_score, l.score, 0) >= %s
          AND a.status = 'completed'
          AND l.email IS NOT NULL
          AND COALESCE(l.country, '') <> ''
          AND COALESCE(l.niche, '') <> ''
          AND upper(COALESCE(l.country, '')) !~ %s
          AND lower(COALESCE(l.source, '')) NOT LIKE 'p%%\\_test' ESCAPE '\\'
          AND lower(COALESCE(l.email, '')) NOT LIKE '%%.example.test'
          AND lower(COALESCE(b.domain, '')) NOT LIKE '%%.example.test'
          AND lower(COALESCE(a.domain, '')) NOT LIKE '%%.example.test'
          AND lower(COALESCE(b.domain, '')) NOT IN ('example.com', 'localhost')
          AND lower(COALESCE(a.domain, '')) NOT IN ('example.com', 'localhost')
          AND COALESCE(l.status, '') NOT IN ('excluded_sensitive_target', 'suppressed', 'unsubscribed')
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(s.email) = lower(l.email))
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(COALESCE(s.domain, '')) = lower(COALESCE(b.domain, '')))
        ORDER BY COALESCE(ls.final_score, l.score, 0) DESC, a.created_at DESC
        LIMIT %s
        """,
        (safe_threshold, TEST_COUNTRY_PATTERN, safe_limit),
    )
    candidates = []
    for row in rows:
        strength = int(row["audit_strength_score"] or 0)
        blockers = []
        if strength and strength < 70:
            blockers.append("audit_strength_below_70")
        elif not strength:
            blockers.append("audit_strength_missing")
        candidates.append(
            {
                "lead_id": str(row["lead_id"]),
                "audit_id": str(row["audit_id"]),
                "business_name": row["business_name"],
                "domain": row["domain"],
                "country": row["country"],
                "language": row["language"],
                "niche": row["niche"],
                "lead_source": row["source"],
                "audit_slug": row["public_slug"],
                "lead_score": int(row["final_score"] or 0),
                "audit_strength_score": strength,
                "campaign_ready": not blockers,
                "blockers": blockers,
            }
        )
    return {
        "candidate_count": len(candidates),
        "threshold": safe_threshold,
        "candidates": candidates,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def campaign_segment_candidates(limit: int = 100, threshold: int = 70) -> dict[str, Any]:
    candidates = qualified_campaign_lead_candidates(limit, threshold)["candidates"]
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        key = (str(item.get("country") or ""), str(item.get("language") or "en"), str(item.get("niche") or ""))
        grouped[key].append(item)
    segments = []
    for (country, language, niche), items in grouped.items():
        ready = [item for item in items if item["campaign_ready"]]
        avg_score = round(sum(item["lead_score"] for item in items) / len(items), 2) if items else 0
        avg_strength = round(sum(item["audit_strength_score"] for item in items) / len(items), 2) if items else 0
        segments.append(
            {
                "country": country,
                "language": language,
                "niche": niche,
                "lead_count": len(items),
                "ready_count": len(ready),
                "average_lead_score": avg_score,
                "average_audit_strength": avg_strength,
                "decision": "READY_FOR_PREVIEW" if ready else "NEEDS_AUDIT_STRENGTH",
            }
        )
    segments.sort(key=lambda row: (row["ready_count"], row["average_lead_score"], row["average_audit_strength"]), reverse=True)
    return {
        "segment_count": len(segments),
        "segments": segments,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def _score_missing_strengths(candidates: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    scored = []
    for item in candidates[:limit]:
        if int(item.get("audit_strength_score") or 0) > 0:
            continue
        strength = score_audit_strength(str(item["audit_id"]))
        scored.append({"audit_id": item["audit_id"], "final_score": int(strength["final_score"])})
    return {"scored_count": len(scored), "audits": scored}


def _campaign_for_segment(segment: dict[str, Any], offer_key: str) -> dict[str, Any]:
    existing = fetch_one(
        """
        SELECT *
        FROM campaigns
        WHERE COALESCE(country, '') = COALESCE(%s, '')
          AND COALESCE(language, '') = COALESCE(%s, '')
          AND COALESCE(niche, '') = COALESCE(%s, '')
          AND COALESCE(offer_key, '') = COALESCE(%s, '')
          AND status IN ('draft', 'preview_ready')
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (segment["country"], segment["language"], segment["niche"], offer_key),
    )
    if existing:
        payload = dict(existing)
        payload["created_new"] = False
        return payload
    created = create_campaign(
        {
            "name": f"Rescue {segment['country']} {segment['niche']} preview",
            "country": segment["country"],
            "language": segment["language"],
            "niche": segment["niche"],
            "offer_key": offer_key,
            "dry_run": True,
        }
    )
    created["created_new"] = True
    return created


def campaign_control_room_snapshot(limit: int = 100, threshold: int = 70) -> dict[str, Any]:
    candidates = qualified_campaign_lead_candidates(limit, threshold)
    segments = campaign_segment_candidates(limit, threshold)
    signals = mail_signal_summary(24)
    preview_rows = campaign_preview_rows(min(limit, 25))
    return json_safe(
        {
            "status": "snapshot",
            "candidate_count": candidates["candidate_count"],
            "ready_candidate_count": len([item for item in candidates["candidates"] if item["campaign_ready"]]),
            "segment_count": segments["segment_count"],
            "top_segments": segments["segments"][:10],
            "first_batch_preview_rows": preview_rows["rows"],
            "first_batch_preview_count": preview_rows["count"],
            "mail_qa_decision": latest_mail_qa_decision(),
            "mail_signal_blockers": signals,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def campaign_preview_rows(limit: int = 25) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    rows = fetch_all(
        """
        SELECT cl.id AS campaign_lead_id, cl.status, cl.score, cl.preview_json, cl.created_at, cl.updated_at,
               c.id AS campaign_id, c.name AS campaign_name, c.status AS campaign_status,
               c.country, c.language, c.niche, c.offer_key, c.dry_run,
               b.name AS business_name, b.domain,
               a.public_slug, a.score AS audit_score,
               latest_strength.final_score AS audit_strength_score,
               latest_preflight.status AS latest_preflight_status,
               latest_review.action AS latest_review_action,
               latest_review.reason AS latest_review_reason,
               latest_review.created_at AS latest_review_at
        FROM campaign_leads cl
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN leads l ON l.id = cl.lead_id
        JOIN businesses b ON b.id = l.business_id
        LEFT JOIN audits a ON a.id = cl.audit_id
        LEFT JOIN LATERAL (
          SELECT final_score FROM audit_strength_scores WHERE audit_id = cl.audit_id ORDER BY created_at DESC LIMIT 1
        ) latest_strength ON true
        LEFT JOIN LATERAL (
          SELECT status FROM campaign_readiness_snapshots WHERE campaign_id = c.id ORDER BY created_at DESC LIMIT 1
        ) latest_preflight ON true
        LEFT JOIN LATERAL (
          SELECT action, reason, created_at
          FROM campaign_preview_reviews
          WHERE campaign_lead_id = cl.id
          ORDER BY created_at DESC
          LIMIT 1
        ) latest_review ON true
        WHERE cl.status = 'preview'
          AND COALESCE(l.status, '') NOT IN ('excluded_sensitive_target', 'suppressed', 'unsubscribed')
          AND upper(COALESCE(c.country, '')) !~ %s
          AND lower(COALESCE(l.source, '')) NOT LIKE 'p%%\\_test' ESCAPE '\\'
          AND lower(COALESCE(b.domain, '')) NOT LIKE '%%.example.test'
        ORDER BY cl.score DESC NULLS LAST, cl.updated_at DESC NULLS LAST, cl.created_at DESC
        LIMIT %s
        """,
        (TEST_COUNTRY_PATTERN, safe_limit),
    )
    payload = [
        {
            "campaign_lead_id": str(row["campaign_lead_id"]),
            "campaign_id": str(row["campaign_id"]),
            "campaign_name": row["campaign_name"],
            "campaign_status": row["campaign_status"],
            "country": row["country"],
            "language": row["language"],
            "niche": row["niche"],
            "offer_key": row["offer_key"],
            "dry_run": bool(row["dry_run"]),
            "business_name": row["business_name"],
            "domain": row["domain"],
            "audit_slug": row["public_slug"],
            "audit_score": int(row["audit_score"] or 0),
            "lead_score": int(row["score"] or 0),
            "audit_strength_score": int(row["audit_strength_score"] or 0),
            "latest_preflight_status": row["latest_preflight_status"] or "missing",
            "latest_review_action": row["latest_review_action"] or "unreviewed",
            "latest_review_reason": row["latest_review_reason"] or "",
            "latest_review_at": row["latest_review_at"],
            "preview_status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        }
        for row in rows
    ]
    return json_safe(
        {
            "status": "ready" if payload else "empty",
            "count": len(payload),
            "rows": payload,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def prepare_campaign_control_room(
    limit: int = 100,
    threshold: int = 70,
    dry_run: bool = True,
    offer_key: str = "contact_form_repair",
    max_segments: int = 3,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 250))
    safe_segments = max(1, min(int(max_segments or 3), 10))
    candidates_payload = qualified_campaign_lead_candidates(safe_limit, threshold)
    candidates = candidates_payload["candidates"]
    segments = campaign_segment_candidates(safe_limit, threshold)["segments"][:safe_segments]
    if dry_run:
        return {
            "status": "preview_only",
            "candidate_count": candidates_payload["candidate_count"],
            "segment_count": len(segments),
            "segments": segments,
            "audit_strengths_scored": 0,
            "campaigns_created_or_confirmed": 0,
            "campaign_previews_prepared": 0,
            "readiness_snapshots": 0,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }

    strength = _score_missing_strengths(candidates, safe_limit)
    refreshed_segments = campaign_segment_candidates(safe_limit, threshold)["segments"][:safe_segments]
    prepared = []
    readiness = []
    for segment in refreshed_segments:
        if segment["ready_count"] <= 0:
            continue
        campaign = _campaign_for_segment(segment, offer_key)
        preview = prepare_campaign_gated(str(campaign["id"]), threshold, min(20, safe_limit))
        ready = campaign_readiness_snapshot(str(campaign["id"]))
        prepared.append(
            {
                "campaign_id": str(campaign["id"]),
                "created_new": bool(campaign.get("created_new")),
                "segment": {key: segment[key] for key in ["country", "language", "niche"]},
                "preview_count": int(preview.get("preview_count") or 0),
                "preview_status": preview.get("status", "unknown"),
            }
        )
        readiness.append({"campaign_id": str(ready["campaign_id"]), "status": ready["status"], "lead_count": int(ready["lead_count"] or 0)})
    return json_safe(
        {
            "status": "prepared",
            "candidate_count": candidates_payload["candidate_count"],
            "segment_count": len(refreshed_segments),
            "audit_strengths_scored": strength["scored_count"],
            "campaigns_created_or_confirmed": len(prepared),
            "campaign_previews_prepared": sum(item["preview_count"] for item in prepared),
            "readiness_snapshots": len(readiness),
            "campaigns": prepared,
            "readiness": readiness,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
