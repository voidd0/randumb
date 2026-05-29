from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent, runtime_daily_loop_plan
from app.campaign_offer_optimizer import optimize_campaign_offers, recommend_campaign_offer
from app.db import execute, fetch_one


def _fixture_campaign(token: str, offer_key: str = "monitor_monthly", issue_type: str = "contact_form_missing", severity: str = "critical"):
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email)
        VALUES (%s, 'US', 'Austin', 'en', 'contractors', 'p146', %s, %s, %s)
        RETURNING id
        """,
        (f"P146 {token}", f"https://p146-{token}.example.net", f"p146-{token}.example.net", f"team-{token}@example.net"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, niche)
        VALUES (%s, %s, 'p146', 'qualified', 92, 'en', 'US', 'contractors')
        RETURNING id
        """,
        (business["id"], f"team-{token}@example.net"),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug)
        VALUES (%s, %s, %s, %s, 'completed', 88, 'QA audit', %s)
        RETURNING id
        """,
        (business["id"], lead["id"], f"p146-{token}.example.net", f"https://p146-{token}.example.net", f"p146-{token}"),
    )
    execute(
        """
        INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, evidence_json, recommendation)
        VALUES (%s, %s, %s, 'Contact form appears unavailable', 'Public browser check found a possible contact path issue.', %s, 'Repair the contact path.')
        """,
        (audit["id"], issue_type, severity, Jsonb({"token": token})),
    )
    campaign = execute(
        """
        INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
        VALUES (%s, 'preview_ready', 'US', 'en', 'contractors', %s, true)
        RETURNING id
        """,
        (f"p146 campaign {token}", offer_key),
    )
    execute(
        """
        INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json)
        VALUES (%s, %s, %s, 'preview', 91, %s)
        """,
        (campaign["id"], lead["id"], audit["id"], Jsonb({"token": token})),
    )
    return campaign


def _cleanup(token: str) -> None:
    execute("DELETE FROM system_events WHERE type = 'campaign.offer_optimizer' AND payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug = %s", (f"p146-{token}",))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE name LIKE %s", (f"%{token}%",))


def test_campaign_offer_optimizer_applies_contact_offer_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        campaign = _fixture_campaign(token)
        recommendation = recommend_campaign_offer(str(campaign["id"]))
        assert recommendation["recommended_offer_key"] == "contact_form_repair"
        assert recommendation["send_mail"] is False

        result = optimize_campaign_offers(limit=20, apply=True)

        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        campaign_row = fetch_one("SELECT offer_key FROM campaigns WHERE id = %s", (campaign["id"],))
        preview = fetch_one("SELECT preview_json FROM campaign_leads WHERE campaign_id = %s", (campaign["id"],))
        assert campaign_row["offer_key"] == "contact_form_repair"
        assert preview["preview_json"]["offer_optimizer"]["recommended_offer_key"] == "contact_form_repair"
    finally:
        _cleanup(token)


def test_campaign_offer_optimizer_agent_is_in_core_loop():
    run = run_agent("campaign_offer_optimizer_agent", {"limit": 1, "apply": False})
    assert run["status"] == "completed"
    assert run["result_json"]["send_mail"] is False
    assert "campaign_offer_optimizer_agent" in [agent for agent, _payload in runtime_daily_loop_plan()]
