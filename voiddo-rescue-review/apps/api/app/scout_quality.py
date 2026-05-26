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
