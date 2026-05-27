from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one


def score_audit_strength(audit_id: str) -> dict[str, Any]:
    audit = fetch_one("SELECT * FROM audits WHERE id = %s", (audit_id,))
    if not audit:
        raise ValueError("audit_not_found")
    issues = fetch_all("SELECT * FROM audit_issues WHERE audit_id = %s", (audit_id,))
    screenshots = fetch_all("SELECT * FROM screenshots WHERE audit_id = %s", (audit_id,))
    findings: list[dict[str, Any]] = []
    completeness = 40
    proof = 20
    commercial = 30
    if audit.get("summary"):
        completeness += 15
    else:
        findings.append({"code": "missing_summary"})
    if audit.get("public_slug"):
        completeness += 15
    else:
        findings.append({"code": "missing_public_slug"})
    issue_count = len(issues)
    has_strong_issue = any(row.get("severity") in {"critical", "high"} for row in issues)
    has_screenshot = bool(screenshots)
    has_public_summary = bool(audit.get("summary"))
    strong_two_issue_audit = issue_count >= 2 and has_strong_issue and has_screenshot and has_public_summary
    if issue_count >= 3:
        completeness += 20
        commercial += 20
    elif issue_count >= 2:
        if strong_two_issue_audit:
            completeness += 15
            commercial += 25
        else:
            completeness += 10
            commercial += 10
            findings.append({"code": "fewer_than_three_issues"})
    elif issue_count == 1:
        completeness += 10
        commercial += 10
        findings.append({"code": "fewer_than_three_issues"})
    else:
        findings.append({"code": "missing_issues"})
    if has_screenshot:
        proof += 50
    else:
        findings.append({"code": "missing_screenshots"})
    if has_strong_issue:
        commercial += 20
    final = max(0, min(100, round((completeness + proof + commercial) / 3)))
    row = execute(
        """
        INSERT INTO audit_strength_scores(audit_id, completeness_score, proof_score, commercial_score, final_score, issues_json)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (audit_id, min(100, completeness), min(100, proof), min(100, commercial), final, Jsonb(findings)),
    )
    return dict(row)
