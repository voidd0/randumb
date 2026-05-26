from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .self_operating import record_learning


def run_scout_self_check(scout_run_id: str) -> dict[str, Any]:
    rows = fetch_all("SELECT status, rejection_reason FROM scout_leads WHERE scout_run_id = %s", (scout_run_id,))
    accepted = sum(1 for row in rows if row["status"] == "accepted")
    rejected = sum(1 for row in rows if row["status"] == "rejected")
    dedupe = sum(1 for row in rows if row["rejection_reason"] == "duplicate_domain")
    excluded = sum(1 for row in rows if row["rejection_reason"] == "excluded_niche")
    issues = []
    if not rows:
        issues.append({"code": "empty_scout_run", "severity": "high"})
    if accepted == 0 and rows:
        issues.append({"code": "no_accepted_leads", "severity": "high"})
    if rejected > accepted:
        issues.append({"code": "rejection_rate_high", "severity": "medium"})
    status = "pass" if not issues else "needs_review"
    row = execute(
        """
        INSERT INTO scout_self_checks(scout_run_id, status, accepted_count, rejected_count, dedupe_count, excluded_count, issues_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (scout_run_id, status, accepted, rejected, dedupe, excluded, Jsonb(issues)),
    )
    for issue in issues:
        record_learning(issue["code"], "scout_self_check", f"Scout self-check found {issue['code']}.", "Tune source/adapters before campaign use.", issue["severity"], issue)
    return dict(row)


def score_scout_provenance(scout_run_id: str) -> dict[str, Any]:
    leads = fetch_all("SELECT source_url, confidence, status, rejection_reason FROM scout_leads WHERE scout_run_id = %s", (scout_run_id,))
    total = len(leads)
    with_source = len([lead for lead in leads if lead.get("source_url")])
    rejected = len([lead for lead in leads if lead.get("status") == "rejected" or lead.get("rejection_reason")])
    confidence_values = []
    for lead in leads:
        raw = float(lead.get("confidence") or 0)
        confidence_values.append(raw / 100 if raw > 1 else raw)
    source_coverage = round(with_source / total, 4) if total else 0
    confidence_average = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0
    score = int(source_coverage * 45) + int(confidence_average * 35) + (20 if rejected == 0 else max(0, 20 - min(rejected * 5, 20)))
    issues: list[dict[str, Any]] = []
    if not total:
        issues.append({"code": "no_scout_leads", "severity": "high"})
    if source_coverage < 0.8:
        issues.append({"code": "weak_source_url_coverage", "severity": "medium", "coverage": source_coverage})
    if confidence_average < 0.65:
        issues.append({"code": "low_average_confidence", "severity": "medium", "confidence": confidence_average})
    status = "pass" if score >= 75 and not any(issue["severity"] == "high" for issue in issues) else "needs_review"
    row = execute(
        """
        INSERT INTO scout_provenance_scores(
          scout_run_id, status, score, source_url_coverage, confidence_average,
          duplicate_or_rejected_count, issues_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (scout_run_id, status, score, source_coverage, confidence_average, rejected, Jsonb(issues)),
    )
    return dict(row)
