from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .audit_strength import score_audit_strength
from .campaign_economics import run_campaign_economics_check
from .campaign_preview_reviews import campaign_preview_review_summary
from .db import execute, fetch_all, fetch_one
from .p0 import latest_decision, mail_signal_summary
from .scout_quality import lead_scout_quality_gate
from .scouts import scout_source_readiness_gate


def _lead_scout_source_readiness_gate(lead_id: str) -> dict[str, Any]:
    lead = fetch_one("SELECT source FROM leads WHERE id = %s", (lead_id,))
    if not lead:
        return {"allowed": False, "decision": "FAIL_REVIEW_REQUIRED", "blockers": [{"code": "lead_not_found", "severity": "high"}], "send_mail": False, "live_outreach_allowed": False}
    if lead["source"] != "scout_agent":
        return {"allowed": True, "decision": "NOT_SCOUT_AGENT", "blockers": [], "send_mail": False, "live_outreach_allowed": False}
    row = fetch_one(
        """
        SELECT sr.id AS scout_run_id, sr.source_id
        FROM scanner_jobs sj
        JOIN scout_leads sl ON sl.id::text = sj.result_json->>'scout_lead_id'
        JOIN scout_runs sr ON sr.id = sl.scout_run_id
        WHERE sj.result_json->>'lead_id' = %s
        ORDER BY sj.queued_at DESC
        LIMIT 1
        """,
        (lead_id,),
    )
    if not row:
        return {
            "allowed": False,
            "decision": "FAIL_REVIEW_REQUIRED",
            "blockers": [{"code": "missing_scout_source_readiness_link", "severity": "high"}],
            "send_mail": False,
            "live_outreach_allowed": False,
        }
    gate = scout_source_readiness_gate(str(row["source_id"]))
    gate["scout_run_id"] = str(row["scout_run_id"])
    gate["source_id"] = str(row["source_id"])
    return gate


def campaign_readiness_snapshot(campaign_id: str) -> dict[str, Any]:
    campaign = fetch_one("SELECT * FROM campaigns WHERE id = %s", (campaign_id,))
    if not campaign:
        raise ValueError("campaign_not_found")
    leads = fetch_all("SELECT lead_id, audit_id, score FROM campaign_leads WHERE campaign_id = %s", (campaign_id,))
    strengths = [int(score_audit_strength(str(lead["audit_id"]))["final_score"]) for lead in leads if lead.get("audit_id")]
    quality_gates = [lead_scout_quality_gate(str(lead["lead_id"])) for lead in leads if lead.get("lead_id")]
    source_readiness_gates = [_lead_scout_source_readiness_gate(str(lead["lead_id"])) for lead in leads if lead.get("lead_id")]
    scout_quality_failed = [gate for gate in quality_gates if not gate.get("allowed_for_campaign_preview")]
    scout_quality_passed = [gate for gate in quality_gates if gate.get("allowed_for_campaign_preview")]
    source_readiness_failed = [gate for gate in source_readiness_gates if not gate.get("allowed")]
    source_readiness_passed = [gate for gate in source_readiness_gates if gate.get("allowed")]
    min_strength = min(strengths) if strengths else 0
    qualified = len([lead for lead in leads if int(lead.get("score") or 0) >= 70])
    economics = run_campaign_economics_check(campaign_id, campaign.get("offer_key") or "contact_form_repair", 0.02)
    review_summary = campaign_preview_review_summary(campaign_id)
    signals = mail_signal_summary(24)
    mail_qa = latest_decision("mail_qa_runs")
    visual = latest_decision("visual_qa_runs")
    blockers: list[dict[str, Any]] = []
    if not leads:
        blockers.append({"code": "no_campaign_leads", "severity": "high"})
    if scout_quality_failed:
        blockers.append(
            {
                "code": "scout_quality_not_pass",
                "severity": "high",
                "failed_count": len(scout_quality_failed),
                "decisions": sorted({gate.get("decision", "unknown") for gate in scout_quality_failed}),
            }
        )
    if source_readiness_failed:
        blockers.append(
            {
                "code": "scout_source_readiness_not_pass",
                "severity": "high",
                "failed_count": len(source_readiness_failed),
                "decisions": sorted({gate.get("readiness", {}).get("status", gate.get("decision", "unknown")) for gate in source_readiness_failed}),
            }
        )
    if min_strength < 70:
        blockers.append({"code": "audit_strength_below_threshold", "severity": "medium", "min_audit_strength": min_strength})
    if economics["decision"] != "pass":
        blockers.append({"code": "campaign_economics_blocked", "severity": "high", "decision": economics["decision"]})
    if int(review_summary.get("rejected_count") or 0) >= len(leads) and leads:
        blockers.append({"code": "all_preview_rows_rejected", "severity": "high", "review_summary": review_summary})
    elif int(review_summary.get("held_count") or 0) > 0:
        blockers.append({"code": "preview_rows_held_for_review", "severity": "medium", "review_summary": review_summary})
    if mail_qa != "PASS":
        blockers.append({"code": "mail_qa_not_pass", "severity": "high", "decision": mail_qa})
    if signals["bounce_or_dsn_count"] or signals["rate_limit_count"] or signals["spam_signal_count"]:
        blockers.append({"code": "recent_mail_signal", "severity": "high", "signals": signals})
    if visual != "PASS":
        blockers.append({"code": "visual_qa_not_pass", "severity": "medium", "decision": visual})
    status = "ready_for_preview_only" if not blockers else "blocked"
    mail_decision = "PASS" if mail_qa == "PASS" and not signals["bounce_or_dsn_count"] and not signals["rate_limit_count"] else "blocked"
    row = execute(
        """
        INSERT INTO campaign_readiness_snapshots(
          campaign_id, status, lead_count, qualified_count, min_audit_strength,
          economics_decision, mail_safety_decision, visual_safety_decision, blockers_json, summary_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            campaign_id,
            status,
            len(leads),
            qualified,
            min_strength,
            economics["decision"],
            mail_decision,
            visual,
            Jsonb(blockers),
            Jsonb(
                {
                    "dry_run": campaign.get("dry_run"),
                    "economics_risk": economics["risk_score"],
                    "mail_signals": signals,
                    "scout_quality": {
                        "checked_count": len(quality_gates),
                        "passed_count": len(scout_quality_passed),
                        "failed_count": len(scout_quality_failed),
                        "send_mail": False,
                        "live_outreach_allowed": False,
                        "raw_recipient_addresses_included": False,
                        "secrets_included": False,
                    },
                    "scout_source_readiness": {
                        "checked_count": len(source_readiness_gates),
                        "passed_count": len(source_readiness_passed),
                        "failed_count": len(source_readiness_failed),
                        "send_mail": False,
                        "live_outreach_allowed": False,
                        "raw_recipient_addresses_included": False,
                        "secrets_included": False,
                    },
                    "preview_reviews": review_summary,
                }
            ),
        ),
    )
    return dict(row)
