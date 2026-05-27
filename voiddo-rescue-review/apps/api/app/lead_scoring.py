from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one


HIGH_VALUE_NICHES = {
    "dentists": 18,
    "clinics": 16,
    "law firms": 16,
    "contractors": 14,
    "beauty salons": 10,
    "local tourism": 10,
    "private courses": 9,
}
HIGH_VALUE_COUNTRIES = {"US": 16, "UK": 14, "AU": 14, "NZ": 13, "CA": 14, "IE": 13, "IL": 12, "EE": 9, "DE": 13, "NL": 13}
ROLE_INBOX_PENALTY = {"info": -5, "hello": -3, "support": -8, "admin": -10, "noreply": -30}
FREE_EMAIL_DOMAINS = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "proton.me"}


@dataclass
class ScoreResult:
    technical_score: int
    sales_score: int
    urgency_score: int
    value_score: int
    deliverability_score: int
    final_score: int
    reasoning_json: dict[str, Any]


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def score_from_audit(audit: dict[str, Any] | None, lead: dict[str, Any]) -> ScoreResult:
    issues = []
    if audit:
        issues = fetch_all("SELECT severity, issue_type, title FROM audit_issues WHERE audit_id = %s", (audit["id"],))
    severity_counts = {key: 0 for key in ["critical", "high", "medium", "low"]}
    issue_types: set[str] = set()
    for issue in issues:
        severity_counts[str(issue["severity"])] = severity_counts.get(str(issue["severity"]), 0) + 1
        issue_types.add(str(issue["issue_type"]))

    technical = 20
    technical += severity_counts.get("critical", 0) * 35
    technical += severity_counts.get("high", 0) * 24
    technical += severity_counts.get("medium", 0) * 12
    technical += severity_counts.get("low", 0) * 4
    if audit:
        technical += max(0, 100 - int(audit.get("score") or 0)) // 3
    if {"contact_path", "availability", "https"} & issue_types:
        technical += 10

    niche = (lead.get("niche") or "").lower()
    country = (lead.get("country") or "").upper()
    sales = 35 + HIGH_VALUE_NICHES.get(niche, 6) + HIGH_VALUE_COUNTRIES.get(country, 6)
    if lead.get("email"):
        sales += 10
    if lead.get("contact_name"):
        sales += 5

    urgency = 10
    urgency += severity_counts.get("critical", 0) * 30
    urgency += severity_counts.get("high", 0) * 20
    if {"contact_path", "availability", "https"} & issue_types:
        urgency += 32

    value = 30 + HIGH_VALUE_NICHES.get(niche, 6) + HIGH_VALUE_COUNTRIES.get(country, 6)
    if niche in {"dentists", "clinics", "law firms", "contractors"}:
        value += 10

    email = (lead.get("email") or "").lower()
    local = email.split("@", 1)[0] if "@" in email else ""
    domain = email.split("@", 1)[1] if "@" in email else ""
    deliverability = 70 if email else 20
    deliverability += ROLE_INBOX_PENALTY.get(local, 0)
    if domain in FREE_EMAIL_DOMAINS:
        deliverability -= 8
    suppressed = fetch_one("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s) OR lower(domain) = lower(%s)", (email, domain))
    if suppressed:
        deliverability = 0

    technical = clamp(technical)
    sales = clamp(sales)
    urgency = clamp(urgency)
    value = clamp(value)
    deliverability = clamp(deliverability)
    final = clamp(round((technical * 0.35) + (sales * 0.18) + (urgency * 0.25) + (value * 0.14) + (deliverability * 0.08)))
    reasoning = {
        "severity_counts": severity_counts,
        "issue_types": sorted(issue_types),
        "niche": niche,
        "country": country,
        "email_domain": domain,
        "suppressed": bool(suppressed),
        "weights": {"technical": 0.35, "sales": 0.18, "urgency": 0.25, "value": 0.14, "deliverability": 0.08},
    }
    return ScoreResult(technical, sales, urgency, value, deliverability, final, reasoning)


def score_lead(lead_id: str, audit_id: str | None = None) -> dict[str, Any]:
    lead = fetch_one("SELECT * FROM leads WHERE id = %s", (lead_id,))
    if not lead:
        raise ValueError("lead_not_found")
    audit = None
    if audit_id:
        audit = fetch_one("SELECT * FROM audits WHERE id = %s", (audit_id,))
    if not audit:
        audit = fetch_one("SELECT * FROM audits WHERE lead_id = %s ORDER BY created_at DESC LIMIT 1", (lead_id,))
    result = score_from_audit(dict(audit) if audit else None, dict(lead))
    row = execute(
        """
        INSERT INTO lead_scores(lead_id, audit_id, technical_score, sales_score, urgency_score, value_score,
                                deliverability_score, final_score, reasoning_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, lead_id, audit_id, technical_score, sales_score, urgency_score, value_score,
                  deliverability_score, final_score, reasoning_json, created_at
        """,
        (
            lead_id,
            audit["id"] if audit else None,
            result.technical_score,
            result.sales_score,
            result.urgency_score,
            result.value_score,
            result.deliverability_score,
            result.final_score,
            Jsonb(result.reasoning_json),
        ),
    )
    execute("UPDATE leads SET score = %s, updated_at = now() WHERE id = %s", (result.final_score, lead_id))
    return dict(row)


def backfill_post_scan_lead_scores(limit: int = 50, dry_run: bool = True) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 50), 250))
    rows = fetch_all(
        """
        SELECT a.id AS audit_id, a.lead_id, a.domain, l.email, l.score AS current_score
        FROM audits a
        JOIN leads l ON l.id = a.lead_id
        WHERE a.status = 'completed'
          AND a.lead_id IS NOT NULL
          AND l.email IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM lead_scores ls
            WHERE ls.lead_id = a.lead_id
              AND ls.audit_id = a.id
          )
        ORDER BY a.checked_at DESC NULLS LAST, a.created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    if dry_run:
        return {
            "status": "dry_run",
            "candidate_count": len(rows),
            "scored_count": 0,
            "qualified_count": 0,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    scored = []
    for row in rows:
        result = score_lead(str(row["lead_id"]), str(row["audit_id"]))
        scored.append(
            {
                "lead_id": str(row["lead_id"]),
                "audit_id": str(row["audit_id"]),
                "domain": row["domain"],
                "final_score": int(result["final_score"] or 0),
                "qualified": int(result["final_score"] or 0) >= 70,
            }
        )
    return {
        "status": "scored" if scored else "idle",
        "candidate_count": len(rows),
        "scored_count": len(scored),
        "qualified_count": len([item for item in scored if item["qualified"]]),
        "scores": scored[:25],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
