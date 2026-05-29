from __future__ import annotations

from collections import Counter
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .economics import calculate_unit_economics
from .p0 import json_safe, recipient_hash
from .scouts import infer_country_from_domain, is_excluded_sensitive_target


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}
TEST_COUNTRY_PATTERN = r"^(P7|P8|P9|P10|P11|P12|P59|P60|P61|P62|P63|P68|P72|P73|P74)"
CANARY_BLOCKED_DOMAIN_EXACT = ("redroof.com", "chcb.org", "oscc.ca", "theisens.com")
CANARY_BLOCKED_TEXT_PATTERNS = (
    "%redroof%",
    "%red roof%",
    "%theisens%",
    "%communityhealth%",
    "%community health%",
    "%healthsystem%",
    "%health system%",
    "%urgentcare%",
    "%urgent care%",
    "%hospital%",
    "%medicalcenter%",
    "%medical center%",
    "%medicalcentre%",
    "%medical centre%",
    "%seniorcitizens%",
    "%senior citizens%",
    "%seniorcenter%",
    "%senior center%",
    "%seniorcentre%",
    "%senior centre%",
    "%dui%",
    "%criminaldefense%",
    "%criminal defense%",
)


def canary_batch_quality(limit: int = 20, store: bool = True) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 100))
    rows = fetch_all(
        """
        SELECT om.id AS outreach_message_id,
               cl.id AS campaign_lead_id,
               cl.campaign_id,
               c.country, c.language, c.niche, c.offer_key,
               b.name AS business_name,
               b.domain,
               b.website_url,
               b.status AS business_status,
               a.public_slug,
               lower(split_part(l.email, '@', 2)) AS recipient_domain,
               latest_review.action AS review_action,
               latest_preflight.decision AS preflight_decision,
               om.body, om.html_body, om.status AS message_status,
               COALESCE(ls.final_score, cl.score, l.score, 0) AS lead_score,
               latest_strength.final_score AS audit_strength_score
        FROM outreach_messages om
        JOIN leads l ON l.id = om.lead_id
        JOIN businesses b ON b.id = l.business_id
        JOIN audits a ON a.id = om.audit_id
        JOIN campaign_leads cl ON cl.lead_id = om.lead_id AND cl.audit_id = om.audit_id AND cl.status = 'preview'
        JOIN campaigns c ON c.id = cl.campaign_id
        LEFT JOIN LATERAL (
          SELECT action
          FROM campaign_preview_reviews
          WHERE campaign_lead_id = cl.id
          ORDER BY created_at DESC
          LIMIT 1
        ) latest_review ON true
        LEFT JOIN LATERAL (
          SELECT decision
          FROM campaign_preflight_runs
          WHERE campaign_id = c.id
          ORDER BY created_at DESC
          LIMIT 1
        ) latest_preflight ON true
        LEFT JOIN LATERAL (
          SELECT final_score FROM lead_scores WHERE lead_id = l.id ORDER BY created_at DESC LIMIT 1
        ) ls ON true
        LEFT JOIN LATERAL (
          SELECT final_score FROM audit_strength_scores WHERE audit_id = a.id ORDER BY created_at DESC LIMIT 1
        ) latest_strength ON true
        WHERE om.status = 'preview'
          AND upper(COALESCE(c.country, '')) !~ %s
          AND lower(COALESCE(c.niche, '')) NOT IN ('government', 'banks', 'bank', 'hospital', 'hospitals', 'gambling', 'adult', 'crypto', 'political')
          AND regexp_replace(lower(COALESCE(b.domain, a.domain, '')), '^www\\.', '') <> ALL(%s)
          AND NOT (
                lower(COALESCE(b.name, '') || ' ' || COALESCE(b.domain, '') || ' ' || COALESCE(b.website_url, '') || ' ' || COALESCE(c.niche, ''))
                LIKE ANY(%s)
          )
          AND lower(COALESCE(b.domain, '')) NOT LIKE '%%.example.test'
          AND lower(COALESCE(l.email, '')) NOT LIKE '%%.example.test'
          AND lower(COALESCE(b.domain, '')) NOT IN ('example.com', 'localhost')
          AND COALESCE(l.status, '') NOT IN ('excluded_sensitive_target', 'suppressed', 'unsubscribed')
          AND NOT EXISTS (
                SELECT 1 FROM suppression_list s
                WHERE lower(s.email) = lower(l.email)
                   OR lower(COALESCE(s.domain, '')) = lower(COALESCE(b.domain, ''))
                   OR lower(COALESCE(s.domain, '')) = lower(split_part(l.email, '@', 2))
          )
        ORDER BY om.created_at DESC, om.id DESC
        LIMIT %s
        """,
        (TEST_COUNTRY_PATTERN, list(CANARY_BLOCKED_DOMAIN_EXACT), list(CANARY_BLOCKED_TEXT_PATTERNS), safe_limit),
    )
    items: list[dict[str, Any]] = []
    domain_counts: Counter[str] = Counter()
    recipient_domain_counts: Counter[str] = Counter()
    campaign_counts: Counter[str] = Counter()
    segment_counts: Counter[str] = Counter()
    offer_counts: Counter[str] = Counter()
    offer_economics: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    warnings: list[str] = []

    for row in rows:
        domain = str(row["domain"] or "").lower()
        recipient_domain = str(row["recipient_domain"] or "").lower()
        segment = f"{row['country']}:{row['niche']}"
        domain_counts[domain] += 1
        recipient_domain_counts[recipient_domain] += 1
        campaign_counts[str(row["campaign_id"])] += 1
        segment_counts[segment] += 1
        offer_key = str(row["offer_key"] or "")
        offer_counts[offer_key] += 1
        if offer_key and offer_key not in offer_economics:
            try:
                offer_economics[offer_key] = calculate_unit_economics(offer_key)
            except ValueError:
                offer_economics[offer_key] = {"product_key": offer_key, "decision": "review", "gross_margin_percent": 0, "price_cents": 0, "gross_margin_cents": 0}
                blockers.append("unknown_offer_key")
        item_blockers = []
        inferred_country = infer_country_from_domain(domain)
        body = row["body"] or ""
        html_body = row["html_body"] or ""
        if inferred_country and str(row["country"] or "").upper() != inferred_country:
            item_blockers.append("domain_country_mismatch")
        if row["business_status"] in {"excluded_sensitive_target", "suppressed", "unsubscribed"}:
            item_blockers.append("business_status_excluded")
        if is_excluded_sensitive_target(
            str(row["business_name"] or ""),
            domain,
            str(row["website_url"] or ""),
            str(row["niche"] or ""),
        ):
            item_blockers.append("sensitive_or_large_target")
        if row["review_action"] != "approved":
            item_blockers.append("preview_not_approved")
        if row["preflight_decision"] != "PASS_NO_SEND_PREFLIGHT":
            item_blockers.append("campaign_preflight_not_passed")
        if "unsubscribe/u_" not in body:
            item_blockers.append("missing_signed_unsubscribe")
        if not html_body or "<html" not in html_body.lower():
            item_blockers.append("html_body_not_ready")
        if not row["public_slug"]:
            item_blockers.append("missing_audit_slug")
        if int(row["lead_score"] or 0) < 70:
            item_blockers.append("lead_score_below_70")
        if int(row["audit_strength_score"] or 0) < 70:
            item_blockers.append("audit_strength_below_70")
        if offer_economics.get(offer_key, {}).get("decision") != "pass":
            item_blockers.append("offer_economics_not_pass")
        blockers.extend(item_blockers)
        items.append(
            {
                "outreach_message_id": str(row["outreach_message_id"]),
                "campaign_lead_id": str(row["campaign_lead_id"]),
                "campaign_id": str(row["campaign_id"]),
                "country": row["country"],
                "language": row["language"],
                "niche": row["niche"],
                "offer_key": row["offer_key"],
                "domain": domain,
                "inferred_country": inferred_country,
                "audit_slug": row["public_slug"],
                "recipient_domain_hash": recipient_hash(recipient_domain),
                "lead_score": int(row["lead_score"] or 0),
                "audit_strength_score": int(row["audit_strength_score"] or 0),
                "blockers": sorted(set(item_blockers)),
            }
        )

    if len(items) < min(safe_limit, 20):
        blockers.append("canary_candidate_count_below_requested_limit")
    if any(count > 1 for count in domain_counts.values()):
        blockers.append("duplicate_business_domain_in_canary")
    if any(count > 5 for count in recipient_domain_counts.values()):
        blockers.append("recipient_domain_concentration_above_5")
    if any(count > 5 for count in campaign_counts.values()):
        warnings.append("campaign_concentration_above_5")
    if len(segment_counts) < 3 and len(items) >= 10:
        warnings.append("low_segment_diversity")
    failing_offers = [key for key, value in offer_economics.items() if value.get("decision") != "pass"]
    if failing_offers:
        blockers.append("offer_economics_not_pass")

    weighted_price_cents = sum(int(offer_economics.get(key, {}).get("price_cents") or 0) * count for key, count in offer_counts.items())
    weighted_margin_cents = sum(int(offer_economics.get(key, {}).get("gross_margin_cents") or 0) * count for key, count in offer_counts.items())
    average_margin_percent = round((weighted_margin_cents / weighted_price_cents) * 100, 2) if weighted_price_cents else 0
    conservative_conversion_rate = 0.01
    economics = {
        "offer_mix": [
            {
                "offer_key": key,
                "count": count,
                "price_cents": int(offer_economics.get(key, {}).get("price_cents") or 0),
                "gross_margin_percent": float(offer_economics.get(key, {}).get("gross_margin_percent") or 0),
                "decision": offer_economics.get(key, {}).get("decision"),
            }
            for key, count in sorted(offer_counts.items())
        ],
        "weighted_price_cents": weighted_price_cents,
        "weighted_gross_margin_cents": weighted_margin_cents,
        "average_gross_margin_percent": average_margin_percent,
        "conservative_conversion_rate": conservative_conversion_rate,
        "modeled_expected_revenue_cents": round(weighted_price_cents * conservative_conversion_rate),
        "modeled_expected_gross_margin_cents": round(weighted_margin_cents * conservative_conversion_rate),
        "decision": "pass" if not failing_offers and average_margin_percent >= 70 else "review",
    }
    if economics["decision"] != "pass":
        blockers.append("canary_economics_not_pass")

    decision = "PASS_CANARY_BATCH_QUALITY" if not blockers else "FAIL_CANARY_BATCH_QUALITY"
    result = json_safe(
        {
            "status": "completed",
            "decision": decision,
            "requested_limit": safe_limit,
            "candidate_count": len(items),
            "segment_count": len(segment_counts),
            "campaign_count": len(campaign_counts),
            "recipient_domain_count": len([key for key in recipient_domain_counts if key]),
            "economics": economics,
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "segments": [{"segment": key, "count": value} for key, value in sorted(segment_counts.items())],
            "items": items,
            **SAFE_FLAGS,
        }
    )
    if store:
        execute(
            """
            INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at)
            VALUES ('canary_batch_quality_agent', %s, %s, now(), now())
            """,
            ("completed" if decision.startswith("PASS") else "blocked", Jsonb(result)),
        )
    return result
