from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _pct(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _avg(values: list[int]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _top(counter: Counter[str], limit: int = 8) -> list[dict[str, Any]]:
    return [{"code": code, "count": count} for code, count in counter.most_common(limit)]


def _lead_rows(limit: int) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    return [dict(row) for row in fetch_all(
        """
        SELECT
          l.id AS lead_id,
          l.source AS lead_source,
          l.status AS lead_status,
          l.country,
          l.city,
          l.niche,
          l.language,
          (l.email IS NOT NULL AND l.email <> '') AS has_email,
          b.domain,
          a.id AS audit_id,
          a.status AS audit_status,
          COALESCE(a.score, 0) AS audit_score,
          COALESCE(ls.final_score, l.score, 0) AS final_score,
          COALESCE(ls.deliverability_score, 0) AS deliverability_score,
          COALESCE(issue_stats.issue_count, 0) AS issue_count,
          COALESCE(issue_stats.critical_high_count, 0) AS critical_high_count,
          COALESCE(issue_stats.contact_signal_count, 0) AS contact_signal_count,
          COALESCE(bounce_stats.bounced_count, 0) AS bounced_count,
          source_link.source_id,
          source_link.source_name,
          source_link.source_type,
          source_link.scout_run_id
        FROM leads l
        JOIN businesses b ON b.id = l.business_id
        LEFT JOIN LATERAL (
          SELECT count(*) AS bounced_count
          FROM outreach_messages om
          WHERE om.lead_id = l.id
            AND (om.status = 'bounced' OR om.bounced_at IS NOT NULL)
        ) bounce_stats ON true
        LEFT JOIN LATERAL (
          SELECT *
          FROM audits a
          WHERE a.lead_id = l.id OR a.business_id = b.id
          ORDER BY a.checked_at DESC NULLS LAST, a.created_at DESC
          LIMIT 1
        ) a ON true
        LEFT JOIN LATERAL (
          SELECT *
          FROM lead_scores ls
          WHERE ls.lead_id = l.id
          ORDER BY ls.created_at DESC
          LIMIT 1
        ) ls ON true
        LEFT JOIN LATERAL (
          SELECT
            count(*) AS issue_count,
            count(*) FILTER (WHERE severity IN ('critical', 'high')) AS critical_high_count,
            count(*) FILTER (WHERE issue_type IN ('contact', 'contact_path', 'mobile_cta', 'booking', 'broken_link')) AS contact_signal_count
          FROM audit_issues ai
          WHERE ai.audit_id = a.id
        ) issue_stats ON true
        LEFT JOIN LATERAL (
          SELECT ss.id AS source_id, ss.name AS source_name, ss.source_type, sr.id AS scout_run_id
          FROM scanner_jobs sj
          JOIN scout_leads sl ON sl.id::text = sj.result_json->>'scout_lead_id'
          JOIN scout_runs sr ON sr.id = sl.scout_run_id
          JOIN scout_sources ss ON ss.id = sr.source_id
          WHERE sj.result_json->>'lead_id' = l.id::text
          ORDER BY sj.queued_at DESC
          LIMIT 1
        ) source_link ON true
        WHERE COALESCE(l.source, '') NOT IN (
          'lead_batch_dry_run', 'p8_test', 'p9_test', 'p59_test', 'p61_test', 'p72_test'
        )
          AND COALESCE(b.domain, '') NOT LIKE '%%.example.test'
          AND COALESCE(b.domain, '') NOT IN ('example.com', 'localhost')
        ORDER BY l.created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )]


def _low_score_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    domain = str(row.get("domain") or "").lower()
    if not row.get("has_email"):
        reasons.append("missing_email")
    if not row.get("country") or not row.get("niche"):
        reasons.append("missing_country_or_niche")
    if not row.get("audit_id") or row.get("audit_status") != "completed":
        reasons.append("missing_completed_audit")
    if int(row.get("issue_count") or 0) == 0 and row.get("audit_status") == "completed":
        reasons.append("no_public_issue_evidence")
    if int(row.get("critical_high_count") or 0) == 0 and row.get("audit_status") == "completed":
        reasons.append("no_critical_or_high_issue")
    if int(row.get("contact_signal_count") or 0) == 0 and row.get("audit_status") == "completed":
        reasons.append("no_contact_or_cta_signal")
    if int(row.get("deliverability_score") or 0) < 60:
        reasons.append("weak_deliverability_signal")
    if row.get("lead_status") == "bounced" or int(row.get("bounced_count") or 0) > 0:
        reasons.append("bounced_or_dsn_observed")
    if domain.endswith(".example.test") or domain == "example.com" or domain == "localhost":
        reasons.append("test_or_placeholder_domain")
    if not row.get("source_id") and row.get("lead_source") == "scout_agent":
        reasons.append("missing_scout_source_link")
    return reasons


def lead_quality_diagnostics(limit: int = 500, store: bool = True) -> dict[str, Any]:
    rows = _lead_rows(limit)
    scores = [int(row.get("final_score") or 0) for row in rows]
    qualified = [row for row in rows if int(row.get("final_score") or 0) >= 70]
    completed = [row for row in rows if row.get("audit_status") == "completed"]
    issue_rows = [row for row in completed if int(row.get("issue_count") or 0) > 0]
    high_signal_rows = [row for row in completed if int(row.get("critical_high_count") or 0) > 0]
    email_rows = [row for row in rows if row.get("has_email")]

    reason_counts: Counter[str] = Counter()
    source_buckets: dict[str, dict[str, Any]] = {}
    segment_buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        low_reasons = _low_score_reasons(row)
        if int(row.get("final_score") or 0) < 70 or "bounced_or_dsn_observed" in low_reasons:
            reason_counts.update(low_reasons)
        source_key = str(row.get("source_id") or row.get("lead_source") or "unknown")
        bucket = source_buckets.setdefault(
            source_key,
            {
                "source_id": str(row["source_id"]) if row.get("source_id") else None,
                "source_name": row.get("source_name") or row.get("lead_source") or "unknown",
                "source_type": row.get("source_type") or "unknown",
                "sampled_count": 0,
                "qualified_count": 0,
                "scores": [],
                "low_score_reasons": Counter(),
            },
        )
        bucket["sampled_count"] += 1
        bucket["qualified_count"] += 1 if int(row.get("final_score") or 0) >= 70 else 0
        bucket["scores"].append(int(row.get("final_score") or 0))
        if int(row.get("final_score") or 0) < 70 or "bounced_or_dsn_observed" in low_reasons:
            bucket["low_score_reasons"].update(low_reasons)

        segment_key = f"{row.get('country') or 'missing'}:{row.get('niche') or 'missing'}"
        segment = segment_buckets.setdefault(segment_key, {"country": row.get("country") or "missing", "niche": row.get("niche") or "missing", "sampled_count": 0, "qualified_count": 0, "scores": []})
        segment["sampled_count"] += 1
        segment["qualified_count"] += 1 if int(row.get("final_score") or 0) >= 70 else 0
        segment["scores"].append(int(row.get("final_score") or 0))

    source_quality = []
    for bucket in source_buckets.values():
        sampled = int(bucket["sampled_count"])
        source_quality.append(
            {
                "source_id": bucket["source_id"],
                "source_name": bucket["source_name"],
                "source_type": bucket["source_type"],
                "sampled_count": sampled,
                "qualified_count": int(bucket["qualified_count"]),
                "qualified_rate": _pct(int(bucket["qualified_count"]), sampled),
                "average_final_score": _avg(bucket["scores"]),
                "top_low_score_reasons": _top(bucket["low_score_reasons"], 5),
            }
        )
    source_quality.sort(key=lambda item: (item["qualified_rate"], item["average_final_score"], item["sampled_count"]), reverse=True)

    segment_quality = []
    for segment in segment_buckets.values():
        sampled = int(segment["sampled_count"])
        segment_quality.append(
            {
                "country": segment["country"],
                "niche": segment["niche"],
                "sampled_count": sampled,
                "qualified_count": int(segment["qualified_count"]),
                "qualified_rate": _pct(int(segment["qualified_count"]), sampled),
                "average_final_score": _avg(segment["scores"]),
            }
        )
    segment_quality.sort(key=lambda item: (item["qualified_rate"], item["average_final_score"], item["sampled_count"]), reverse=True)

    recommendations: list[dict[str, Any]] = []
    if rows and _pct(len(qualified), len(rows)) < 0.15:
        recommendations.append({"code": "increase_issue_signal_sources", "priority": "high", "reason": "qualified_rate_below_15_percent"})
    if rows and _pct(len(email_rows), len(rows)) < 0.5:
        recommendations.append({"code": "prefer_email_rich_sources", "priority": "high", "reason": "email_coverage_below_50_percent"})
    if completed and _pct(len(high_signal_rows), len(completed)) < 0.25:
        recommendations.append({"code": "improve_contact_cta_scanner_evidence", "priority": "medium", "reason": "critical_high_signal_rate_below_25_percent"})
    for item in source_quality[-5:]:
        if item["sampled_count"] >= 5 and item["qualified_rate"] == 0:
            recommendations.append({"code": "pause_low_yield_source", "priority": "medium", "source_id": item["source_id"], "source_name": item["source_name"]})

    status = "PASS_LEAD_QUALITY_NO_SEND" if rows and _pct(len(qualified), len(rows)) >= 0.15 else "NEEDS_SOURCE_TUNING_NO_SEND"
    summary = {
        "sampled_count": len(rows),
        "completed_audit_count": len(completed),
        "email_coverage": _pct(len(email_rows), len(rows)),
        "issue_evidence_rate": _pct(len(issue_rows), len(completed)),
        "critical_high_signal_rate": _pct(len(high_signal_rows), len(completed)),
        "qualified_count": len(qualified),
        "qualified_rate": _pct(len(qualified), len(rows)),
        "average_final_score": _avg(scores),
        "top_low_score_reasons": _top(reason_counts),
        "top_sources": source_quality[:12],
        "top_segments": segment_quality[:12],
        "weak_sources": [item for item in source_quality if item["sampled_count"] >= 5 and item["qualified_rate"] == 0][:12],
    }
    result = {
        "status": status,
        "blocker_count": len([item for item in recommendations if item.get("priority") == "high"]),
        "summary": summary,
        "recommendations": recommendations,
        **SAFE_FLAGS,
    }
    if store:
        row = execute(
            """
            INSERT INTO lead_quality_diagnostic_runs(
              status, sampled_count, qualified_count, qualified_rate, average_final_score,
              blocker_count, summary_json, recommendations_json,
              send_mail, smtp_called, live_outreach_allowed,
              raw_recipient_addresses_included, secrets_included
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
            RETURNING id, created_at
            """,
            (
                status,
                len(rows),
                len(qualified),
                _pct(len(qualified), len(rows)),
                _avg(scores),
                result["blocker_count"],
                Jsonb(summary),
                Jsonb(recommendations),
            ),
        )
        result["diagnostic_run_id"] = str(row["id"])
        result["created_at"] = row["created_at"].isoformat()
    return result


def latest_lead_quality_diagnostics() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT *
        FROM lead_quality_diagnostic_runs
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    if not row:
        return {"status": "missing", "summary": {}, "recommendations": [], **SAFE_FLAGS}
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "sampled_count": int(row["sampled_count"] or 0),
        "qualified_count": int(row["qualified_count"] or 0),
        "qualified_rate": float(row["qualified_rate"] or 0),
        "average_final_score": float(row["average_final_score"] or 0),
        "blocker_count": int(row["blocker_count"] or 0),
        "summary": row["summary_json"],
        "recommendations": row["recommendations_json"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        **SAFE_FLAGS,
    }


def lead_quality_diagnostics_snapshot(limit: int = 500) -> dict[str, Any]:
    return lead_quality_diagnostics(limit, store=False)


def record_lead_quality_diagnostics(limit: int = 500) -> dict[str, Any]:
    return lead_quality_diagnostics(limit, store=True)


def latest_lead_quality_diagnostics_history(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT *
        FROM lead_quality_diagnostic_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 100)),),
    )
    return {
        "count": len(rows),
        "latest": latest_lead_quality_diagnostics(),
        "history": [
            {
                "id": str(row["id"]),
                "status": row["status"],
                "sampled_count": int(row["sampled_count"] or 0),
                "qualified_count": int(row["qualified_count"] or 0),
                "qualified_rate": float(row["qualified_rate"] or 0),
                "average_final_score": float(row["average_final_score"] or 0),
                "blocker_count": int(row["blocker_count"] or 0),
                "summary": row["summary_json"],
                "recommendations": row["recommendations_json"],
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ],
        **SAFE_FLAGS,
    }


def scout_source_performance(limit: int = 100, store: bool = True) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
          ss.id AS source_id,
          ss.name AS source_name,
          ss.source_type,
          ss.country,
          ss.niche,
          count(DISTINCT l.id) AS lead_count,
          count(DISTINCT l.id) FILTER (WHERE l.email IS NOT NULL) AS email_count,
          count(DISTINCT a.id) FILTER (WHERE a.status = 'completed') AS scanned_count,
          count(DISTINCT l.id) FILTER (WHERE ls.final_score IS NOT NULL) AS scored_count,
          count(DISTINCT l.id) FILTER (WHERE COALESCE(ls.final_score, l.score, 0) >= 70) AS qualified_count,
          count(DISTINCT l.id) FILTER (
            WHERE l.status = 'bounced'
               OR EXISTS (
                 SELECT 1 FROM outreach_messages om
                 WHERE om.lead_id = l.id
                   AND (om.status = 'bounced' OR om.bounced_at IS NOT NULL)
               )
          ) AS bounced_count,
          COALESCE(avg(COALESCE(ls.final_score, l.score, 0)), 0) AS average_final_score,
          count(DISTINCT a.id) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM audit_issues ai
              WHERE ai.audit_id = a.id
                AND ai.severity IN ('critical', 'high')
            )
          ) AS high_signal_audit_count
        FROM scout_sources ss
        JOIN scout_runs sr ON sr.source_id = ss.id
        JOIN scout_leads sl ON sl.scout_run_id = sr.id
        LEFT JOIN scanner_jobs sj ON sj.result_json->>'scout_lead_id' = sl.id::text
        LEFT JOIN leads l ON l.id::text = sj.result_json->>'lead_id'
        LEFT JOIN LATERAL (
          SELECT *
          FROM audits a
          WHERE a.lead_id = l.id
          ORDER BY a.checked_at DESC NULLS LAST, a.created_at DESC
          LIMIT 1
        ) a ON true
        LEFT JOIN LATERAL (
          SELECT *
          FROM lead_scores ls
          WHERE ls.lead_id = l.id
          ORDER BY ls.created_at DESC
          LIMIT 1
        ) ls ON true
        WHERE COALESCE(ss.status, '') NOT IN ('archived_test_artifact', 'excluded_sensitive_target')
        GROUP BY ss.id, ss.name, ss.source_type, ss.country, ss.niche
        ORDER BY ss.created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 100), 500)),),
    )
    performances: list[dict[str, Any]] = []
    for row in rows:
        lead_count = int(row["lead_count"] or 0)
        scanned_count = int(row["scanned_count"] or 0)
        scored_count = int(row["scored_count"] or 0)
        qualified_count = int(row["qualified_count"] or 0)
        bounced_count = int(row["bounced_count"] or 0)
        avg_score = round(float(row["average_final_score"] or 0), 2)
        email_coverage = _pct(int(row["email_count"] or 0), lead_count)
        issue_signal_rate = _pct(int(row["high_signal_audit_count"] or 0), scanned_count)
        qualified_rate = _pct(qualified_count, scored_count or lead_count)
        bounce_rate = _pct(bounced_count, lead_count)
        if scanned_count < 3:
            status = "NEEDS_MORE_DATA_NO_SEND"
            recommendation = "KEEP_TESTING"
        elif bounced_count >= 1 and bounce_rate >= 0.2:
            status = "BOUNCE_RISK_REVIEW_NO_SEND"
            recommendation = "PAUSE_SOURCE_UNTIL_REVIEW"
        elif qualified_rate >= 0.2 and avg_score >= 55 and email_coverage >= 0.4:
            status = "PASS_SOURCE_PERFORMANCE_NO_SEND"
            recommendation = "PROMOTE_SOURCE_FOR_MORE_SCOUTING"
        elif scanned_count >= 5 and qualified_count == 0:
            status = "LOW_YIELD_REVIEW_NO_SEND"
            recommendation = "PAUSE_SOURCE_UNTIL_REVIEW"
        else:
            status = "WATCH_SOURCE_NO_SEND"
            recommendation = "KEEP_TESTING_WITH_SMALL_BATCHES"
        reasoning = {
            "source_name": row["source_name"],
            "source_type": row["source_type"],
            "country": row["country"],
            "niche": row["niche"],
            "lead_count": lead_count,
            "scanned_count": scanned_count,
            "scored_count": scored_count,
            "qualified_count": qualified_count,
            "bounced_count": bounced_count,
            "bounce_rate": bounce_rate,
            "qualified_rate": qualified_rate,
            "average_final_score": avg_score,
            "email_coverage": email_coverage,
            "issue_signal_rate": issue_signal_rate,
            "recommendation_reason": recommendation.lower(),
            **SAFE_FLAGS,
        }
        item = {
            "source_id": str(row["source_id"]),
            "source_name": row["source_name"],
            "status": status,
            "scanned_count": scanned_count,
            "scored_count": scored_count,
            "qualified_count": qualified_count,
            "bounced_count": bounced_count,
            "bounce_rate": bounce_rate,
            "qualified_rate": qualified_rate,
            "average_final_score": avg_score,
            "email_coverage": email_coverage,
            "issue_signal_rate": issue_signal_rate,
            "recommendation": recommendation,
            "reasoning": reasoning,
            **SAFE_FLAGS,
        }
        if store:
            stored = execute(
                """
                INSERT INTO scout_source_performance_scores(
                  source_id, status, scanned_count, scored_count, qualified_count,
                  qualified_rate, average_final_score, email_coverage, issue_signal_rate,
                  recommendation, reasoning_json, send_mail, smtp_called, live_outreach_allowed,
                  raw_recipient_addresses_included, secrets_included
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, false, false, false, false)
                RETURNING id, created_at
                """,
                (
                    row["source_id"],
                    status,
                    scanned_count,
                    scored_count,
                    qualified_count,
                    qualified_rate,
                    avg_score,
                    email_coverage,
                    issue_signal_rate,
                    recommendation,
                    Jsonb(reasoning),
                ),
            )
            item["performance_score_id"] = str(stored["id"])
            item["created_at"] = stored["created_at"].isoformat()
        performances.append(item)

    promote = [item for item in performances if item["recommendation"] == "PROMOTE_SOURCE_FOR_MORE_SCOUTING"]
    pause = [item for item in performances if item["recommendation"] == "PAUSE_SOURCE_UNTIL_REVIEW"]
    status = "PASS_SOURCE_FEEDBACK_NO_SEND" if performances and not pause else "SOURCE_FEEDBACK_REVIEW_NO_SEND"
    return {
        "status": status,
        "source_count": len(performances),
        "promote_count": len(promote),
        "pause_review_count": len(pause),
        "performances": performances,
        "next_actions": {
            "promote_source_ids": [item["source_id"] for item in promote[:20]],
            "pause_review_source_ids": [item["source_id"] for item in pause[:20]],
            "no_live_send": True,
        },
        **SAFE_FLAGS,
    }


def latest_scout_source_performance(limit: int = 20) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT ssp.*, ss.name AS source_name, ss.source_type
        FROM scout_source_performance_scores ssp
        LEFT JOIN scout_sources ss ON ss.id = ssp.source_id
        ORDER BY ssp.created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 20), 100)),),
    )
    return {
        "count": len(rows),
        "performances": [
            {
                "id": str(row["id"]),
                "source_id": str(row["source_id"]) if row.get("source_id") else None,
                "source_name": row.get("source_name"),
                "source_type": row.get("source_type"),
                "status": row["status"],
                "scanned_count": int(row["scanned_count"] or 0),
                "scored_count": int(row["scored_count"] or 0),
                "qualified_count": int(row["qualified_count"] or 0),
                "qualified_rate": float(row["qualified_rate"] or 0),
                "average_final_score": float(row["average_final_score"] or 0),
                "email_coverage": float(row["email_coverage"] or 0),
                "issue_signal_rate": float(row["issue_signal_rate"] or 0),
                "recommendation": row["recommendation"],
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ],
        **SAFE_FLAGS,
    }


def apply_scout_source_feedback(limit: int = 100, dry_run: bool = True) -> dict[str, Any]:
    result = scout_source_performance(limit, store=not dry_run)
    result["dry_run"] = dry_run
    applied: list[dict[str, Any]] = []
    for item in result.get("performances", []):
        action = "none"
        if item["recommendation"] == "PAUSE_SOURCE_UNTIL_REVIEW":
            action = "would_deprioritize" if dry_run else "deprioritized"
            if not dry_run:
                execute(
                    """
                    UPDATE scout_sources
                    SET status = 'quality_deprioritized',
                        config_json = config_json || %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                      AND status IN ('active', 'preflight_ready')
                    """,
                    (
                        Jsonb(
                            {
                                "post_scan_feedback": {
                                    "recommendation": item["recommendation"],
                                    "status": item["status"],
                                    "qualified_rate": item["qualified_rate"],
                                    "bounce_rate": item.get("bounce_rate", 0),
                                    "average_final_score": item["average_final_score"],
                                }
                            }
                        ),
                        item["source_id"],
                    ),
                )
        elif item["recommendation"] == "PROMOTE_SOURCE_FOR_MORE_SCOUTING":
            action = "would_promote" if dry_run else "promoted"
            if not dry_run:
                execute(
                    """
                    UPDATE scout_sources
                    SET config_json = config_json || %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        Jsonb(
                            {
                                "post_scan_feedback": {
                                    "recommendation": item["recommendation"],
                                    "status": item["status"],
                                    "qualified_rate": item["qualified_rate"],
                                    "average_final_score": item["average_final_score"],
                                }
                            }
                        ),
                        item["source_id"],
                    ),
                )
        elif item["recommendation"] == "KEEP_TESTING":
            action = "would_keep_testing" if dry_run else "kept_testing"
        elif item["recommendation"] == "KEEP_TESTING_WITH_SMALL_BATCHES":
            action = "would_keep_small_batch" if dry_run else "kept_small_batch"
        if action != "none":
            applied.append(
                {
                    "source_id": item["source_id"],
                    "source_name": item["source_name"],
                    "recommendation": item["recommendation"],
                    "applied_action": action,
                    "qualified_count": item["qualified_count"],
                    "qualified_rate": item["qualified_rate"],
                    "bounce_rate": item.get("bounce_rate", 0),
                    "average_final_score": item["average_final_score"],
                }
            )
    result["applied"] = applied
    result["applied_status_changes"] = len([item for item in applied if item["applied_action"] in {"deprioritized", "promoted"}])
    result["reason"] = "post_scan_source_feedback_preview" if dry_run else "post_scan_source_feedback_applied"
    return result
