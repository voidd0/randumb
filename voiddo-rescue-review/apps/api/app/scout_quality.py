from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
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


def run_scout_quality_gate(scout_run_id: str) -> dict[str, Any]:
    self_check = run_scout_self_check(scout_run_id)
    provenance = score_scout_provenance(scout_run_id)
    blockers: list[dict[str, Any]] = []
    if self_check["status"] != "pass":
        blockers.append({"code": "scout_self_check_not_pass", "severity": "high", "status": self_check["status"]})
    if provenance["status"] != "pass":
        blockers.append({"code": "scout_provenance_not_pass", "severity": "high", "status": provenance["status"], "score": int(provenance["score"])})
    decision = "PASS_IMPORT_READY" if not blockers else "FAIL_REVIEW_REQUIRED"
    return {
        "decision": decision,
        "allowed_for_campaign_preview": not blockers,
        "blockers": blockers,
        "self_check_id": str(self_check["id"]),
        "self_check_status": self_check["status"],
        "provenance_score_id": str(provenance["id"]),
        "provenance_status": provenance["status"],
        "provenance_score": int(provenance["score"]),
        "source_url_coverage": float(provenance["source_url_coverage"] or 0),
        "confidence_average": float(provenance["confidence_average"] or 0),
        "send_mail": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def latest_scout_quality_gate(scout_run_id: str) -> dict[str, Any]:
    self_check = fetch_one(
        "SELECT * FROM scout_self_checks WHERE scout_run_id = %s ORDER BY created_at DESC LIMIT 1",
        (scout_run_id,),
    )
    provenance = fetch_one(
        "SELECT * FROM scout_provenance_scores WHERE scout_run_id = %s ORDER BY created_at DESC LIMIT 1",
        (scout_run_id,),
    )
    blockers: list[dict[str, Any]] = []
    if not self_check:
        blockers.append({"code": "missing_scout_self_check", "severity": "high"})
    elif self_check["status"] != "pass":
        blockers.append({"code": "scout_self_check_not_pass", "severity": "high", "status": self_check["status"]})
    if not provenance:
        blockers.append({"code": "missing_scout_provenance_score", "severity": "high"})
    elif provenance["status"] != "pass":
        blockers.append({"code": "scout_provenance_not_pass", "severity": "high", "status": provenance["status"], "score": int(provenance["score"])})
    return {
        "decision": "PASS_IMPORT_READY" if not blockers else "FAIL_REVIEW_REQUIRED",
        "allowed_for_campaign_preview": not blockers,
        "blockers": blockers,
        "self_check_status": self_check["status"] if self_check else "missing",
        "provenance_status": provenance["status"] if provenance else "missing",
        "provenance_score": int(provenance["score"]) if provenance else 0,
        "source_url_coverage": float(provenance["source_url_coverage"] or 0) if provenance else 0,
        "confidence_average": float(provenance["confidence_average"] or 0) if provenance else 0,
        "send_mail": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def lead_scout_quality_gate(lead_id: str) -> dict[str, Any]:
    lead = fetch_one("SELECT source FROM leads WHERE id = %s", (lead_id,))
    if not lead:
        return {"allowed_for_campaign_preview": False, "decision": "FAIL_REVIEW_REQUIRED", "blockers": [{"code": "lead_not_found", "severity": "high"}]}
    if lead["source"] != "scout_agent":
        return {"allowed_for_campaign_preview": True, "decision": "NOT_SCOUT_AGENT", "blockers": []}
    row = fetch_one(
        """
        SELECT sl.scout_run_id
        FROM scanner_jobs sj
        JOIN scout_leads sl ON sl.id::text = sj.result_json->>'scout_lead_id'
        WHERE sj.result_json->>'lead_id' = %s
        ORDER BY sj.queued_at DESC
        LIMIT 1
        """,
        (lead_id,),
    )
    if not row:
        return {
            "allowed_for_campaign_preview": False,
            "decision": "FAIL_REVIEW_REQUIRED",
            "blockers": [{"code": "missing_scout_quality_link", "severity": "high"}],
            "send_mail": False,
            "live_outreach_allowed": False,
        }
    gate = latest_scout_quality_gate(str(row["scout_run_id"]))
    missing_evidence = {blocker["code"] for blocker in gate.get("blockers", [])} & {"missing_scout_self_check", "missing_scout_provenance_score"}
    if missing_evidence:
        gate = run_scout_quality_gate(str(row["scout_run_id"]))
    gate["scout_run_id"] = str(row["scout_run_id"])
    return gate


def scout_campaign_quality_summary() -> dict[str, Any]:
    run_counts = fetch_all(
        """
        SELECT status, count(*) AS count
        FROM scout_runs
        GROUP BY status
        ORDER BY status
        """
    )
    latest_provenance = fetch_one(
        """
        SELECT status, score, source_url_coverage, confidence_average, duplicate_or_rejected_count, created_at
        FROM scout_provenance_scores
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    latest_self_check = fetch_one(
        """
        SELECT status, accepted_count, rejected_count, dedupe_count, excluded_count, created_at
        FROM scout_self_checks
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    readiness = fetch_one(
        """
        SELECT status, lead_count, qualified_count, summary_json, blockers_json, created_at
        FROM campaign_readiness_snapshots
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    campaign_leads = fetch_one("SELECT count(*) AS count FROM campaign_leads")
    scout_campaign_leads = fetch_one(
        """
        SELECT count(*) AS count
        FROM campaign_leads cl
        JOIN leads l ON l.id = cl.lead_id
        WHERE l.source = 'scout_agent'
        """
    )
    latest_quality = (readiness or {}).get("summary_json", {}).get("scout_quality", {}) if readiness else {}
    blockers = []
    if latest_provenance and latest_provenance["status"] != "pass":
        blockers.append({"code": "latest_scout_provenance_not_pass", "severity": "medium"})
    if latest_self_check and latest_self_check["status"] != "pass":
        blockers.append({"code": "latest_scout_self_check_not_pass", "severity": "medium"})
    if int(latest_quality.get("failed_count") or 0) > 0:
        blockers.append({"code": "latest_campaign_scout_quality_failed", "severity": "high", "failed_count": int(latest_quality.get("failed_count") or 0)})
    return {
        "status": "PASS_NO_SEND" if not blockers else "REVIEW_REQUIRED_NO_SEND",
        "blockers": blockers,
        "scout_runs_by_status": {row["status"]: int(row["count"]) for row in run_counts},
        "latest_self_check": {
            "status": latest_self_check["status"] if latest_self_check else "missing",
            "accepted_count": int(latest_self_check["accepted_count"]) if latest_self_check else 0,
            "rejected_count": int(latest_self_check["rejected_count"]) if latest_self_check else 0,
            "dedupe_count": int(latest_self_check["dedupe_count"]) if latest_self_check else 0,
            "excluded_count": int(latest_self_check["excluded_count"]) if latest_self_check else 0,
        },
        "latest_provenance": {
            "status": latest_provenance["status"] if latest_provenance else "missing",
            "score": int(latest_provenance["score"]) if latest_provenance else 0,
            "source_url_coverage": float(latest_provenance["source_url_coverage"] or 0) if latest_provenance else 0,
            "confidence_average": float(latest_provenance["confidence_average"] or 0) if latest_provenance else 0,
            "duplicate_or_rejected_count": int(latest_provenance["duplicate_or_rejected_count"]) if latest_provenance else 0,
        },
        "campaign_quality": {
            "campaign_leads": int(campaign_leads["count"]) if campaign_leads else 0,
            "scout_campaign_leads": int(scout_campaign_leads["count"]) if scout_campaign_leads else 0,
            "latest_checked_count": int(latest_quality.get("checked_count") or 0),
            "latest_passed_count": int(latest_quality.get("passed_count") or 0),
            "latest_failed_count": int(latest_quality.get("failed_count") or 0),
        },
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
