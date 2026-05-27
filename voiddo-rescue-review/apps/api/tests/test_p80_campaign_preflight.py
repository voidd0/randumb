from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.campaign_preflight import campaign_preflight_batch, latest_campaign_preflight_runs
from app.campaign_preview_reviews import review_campaign_preview
from app.db import execute, fetch_one
from app.lead_scoring import score_lead
from app.main import app
from app.scouts import create_campaign, prepare_campaign


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM campaign_preflight_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM outbound_mailer_decisions WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM public_language_gate_runs WHERE scope = 'campaign_preview_quality' AND issues_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent = 'campaign_preflight_agent' AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_preview_reviews WHERE campaign_lead_id IN (SELECT id FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s) OR preview_json::text LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s) OR preview_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM audit_strength_scores WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))


def _campaign(token: str, weak: bool = False) -> str:
    domain = f"p80-{token}.clinic"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, 'QA', 'Preflight City', 'en', 'dentists', 'p80_test', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P80 Clinic {token}", f"https://{domain}", domain, f"owner-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p80_test', 'scouted', 91, 'en', 'QA', 'Preflight City', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}"),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 68, 'Contact path and mobile CTA may be weak.', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"p80-{token}"),
    )
    issue_count = 1 if weak else 3
    for _ in range(issue_count):
        execute(
            """
            INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
            VALUES (%s, 'contact_path', 'high', 'Contact path may be weak', 'Visible from a public browser session.', 'Review the public enquiry path.')
            """,
            (audit["id"],),
        )
    if not weak:
        execute(
            """
            INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport)
            VALUES (%s, 'desktop', %s, %s, 'desktop')
            """,
            (audit["id"], f"/app/storage/screenshots/p80-{token}.png", f"/media/screenshots/p80-{token}.png"),
        )
    score_lead(str(lead["id"]), str(audit["id"]))
    execute("UPDATE leads SET score = 91 WHERE id = %s", (lead["id"],))
    execute("UPDATE lead_scores SET final_score = 91 WHERE lead_id = %s AND audit_id = %s", (lead["id"], audit["id"]))
    campaign = create_campaign({"name": f"p80-campaign-{token}", "country": "QA", "language": "en", "niche": "dentists", "offer_key": "contact_form_repair"})
    preview = prepare_campaign(str(campaign["id"]), 70, 5)
    assert preview["preview_count"] == 1
    return str(campaign["id"])


def _policy_pass() -> dict:
    return {"score": 100, "decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "send_mail": False, "smtp_called": False, "live_outreach_allowed": False}


def test_campaign_preflight_passes_quality_and_policy_without_send(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        result = campaign_preflight_batch(5, campaign_id)
        assert result["campaign_count"] == 1
        assert result["passed_count"] == 1
        run = result["runs"][0]
        assert run["decision"] == "PASS_NO_SEND_PREFLIGHT"
        assert run["send_mail"] is False
        assert run["smtp_called"] is False
        assert run["live_outreach_allowed"] is False
        assert f"owner-{token}@" not in str(result)
        assert latest_campaign_preflight_runs(5)["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_blocks_weak_preview(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token, weak=True)
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        result = campaign_preflight_batch(5, campaign_id)
        assert result["failed_count"] == 1
        assert "preview_quality_not_pass" in result["runs"][0]["blockers"]
        assert result["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_blocks_held_preview_review(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        preview = fetch_one("SELECT id FROM campaign_leads WHERE campaign_id = %s LIMIT 1", (campaign_id,))
        review_campaign_preview(str(preview["id"]), "held", "needs stronger proof")
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        result = campaign_preflight_batch(5, campaign_id)
        assert result["failed_count"] == 1
        assert "preview_rows_held_for_review" in result["runs"][0]["blockers"]
        assert result["runs"][0]["preview_review_summary"]["held_count"] == 1
        assert result["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_endpoint_and_agent_are_admin_gated(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        assert client.get("/admin/campaign-preflight/runs").status_code == 401
        assert client.post("/admin/campaign-preflight/run", json={"campaign_id": campaign_id}).status_code == 401
        response = client.post("/admin/campaign-preflight/run", json={"campaign_id": campaign_id}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["preflight"]["send_mail"] is False
        agent = run_agent("campaign_preflight_agent", {"campaign_id": campaign_id})
        assert agent["status"] == "completed"
        assert agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
