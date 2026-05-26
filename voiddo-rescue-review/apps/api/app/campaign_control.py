from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .audit_strength import score_audit_strength
from .campaign_economics import run_campaign_economics_check
from .db import execute, fetch_all, fetch_one
from .p0 import latest_decision, mail_signal_summary


def campaign_readiness_snapshot(campaign_id: str) -> dict[str, Any]:
    campaign = fetch_one("SELECT * FROM campaigns WHERE id = %s", (campaign_id,))
    if not campaign:
        raise ValueError("campaign_not_found")
    leads = fetch_all("SELECT lead_id, audit_id, score FROM campaign_leads WHERE campaign_id = %s", (campaign_id,))
    strengths = [int(score_audit_strength(str(lead["audit_id"]))["final_score"]) for lead in leads if lead.get("audit_id")]
    min_strength = min(strengths) if strengths else 0
    qualified = len([lead for lead in leads if int(lead.get("score") or 0) >= 70])
    economics = run_campaign_economics_check(campaign_id, campaign.get("offer_key") or "contact_form_repair", 0.02)
    signals = mail_signal_summary(24)
    mail_qa = latest_decision("mail_qa_runs")
    visual = latest_decision("visual_qa_runs")
    blockers: list[dict[str, Any]] = []
    if not leads:
        blockers.append({"code": "no_campaign_leads", "severity": "high"})
    if min_strength < 70:
        blockers.append({"code": "audit_strength_below_threshold", "severity": "medium", "min_audit_strength": min_strength})
    if economics["decision"] != "pass":
        blockers.append({"code": "campaign_economics_blocked", "severity": "high", "decision": economics["decision"]})
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
            Jsonb({"dry_run": campaign.get("dry_run"), "economics_risk": economics["risk_score"], "mail_signals": signals}),
        ),
    )
    return dict(row)
