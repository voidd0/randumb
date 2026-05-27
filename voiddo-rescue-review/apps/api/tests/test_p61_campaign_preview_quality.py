from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.campaign_preview_quality import campaign_preview_quality_pack
from app.db import execute, fetch_one
from app.lead_scoring import score_lead
from app.main import app
from app.scouts import create_campaign, prepare_campaign


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM outbound_mailer_decisions WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM public_language_gate_runs WHERE scope = 'campaign_preview_quality' AND issues_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
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
    domain = f"p61-{token}.example.test"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, 'QA', 'Quality City', 'en', 'dentists', 'p61_test', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P61 Clinic {token}", f"https://{domain}", domain, f"owner-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p61_test', 'scouted', 91, 'en', 'QA', 'Quality City', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}"),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 67, 'Contact path and mobile CTA may be weak.', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"p61-{token}"),
    )
    issue_count = 1 if weak else 3
    for i in range(issue_count):
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
            (audit["id"], f"/app/storage/screenshots/p61-{token}.png", f"/media/screenshots/p61-{token}.png"),
        )
    score_lead(str(lead["id"]), str(audit["id"]))
    execute("UPDATE leads SET score = 91 WHERE id = %s", (lead["id"],))
    execute("UPDATE lead_scores SET final_score = 91 WHERE lead_id = %s AND audit_id = %s", (lead["id"], audit["id"]))
    campaign = create_campaign({"name": f"p61-campaign-{token}", "country": "QA", "language": "en", "niche": "dentists", "offer_key": "contact_form_repair"})
    preview = prepare_campaign(str(campaign["id"]), 70, 5)
    assert preview["preview_count"] == 1
    return str(campaign["id"])


def test_campaign_preview_quality_passes_strong_preview_without_raw_email():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        result = campaign_preview_quality_pack(campaign_id, 5)
        text = str(result)
        assert result["status"] == "PASS_PREVIEW_QUALITY"
        assert result["ready_count"] == 1
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert result["raw_recipient_addresses_included"] is False
        assert f"owner-{token}@" not in text
        assert result["items"][0]["unsubscribe_ready"] is True
        assert result["items"][0]["legal_note_ready"] is True
    finally:
        _cleanup(token)


def test_campaign_preview_quality_blocks_weak_audit_evidence():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token, weak=True)
        result = campaign_preview_quality_pack(campaign_id, 5)
        assert result["status"] == "REVIEW_REQUIRED"
        assert "audit_strength_below_70" in result["blockers_by_code"]
        assert result["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preview_quality_admin_and_agent():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        assert client.post(f"/admin/campaigns/{campaign_id}/preview-quality", json={"limit": 5}).status_code == 401
        response = client.post(f"/admin/campaigns/{campaign_id}/preview-quality", json={"limit": 5}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["quality"]["send_mail"] is False
        agent = run_agent("campaign_preview_quality_agent", {"campaign_id": campaign_id, "limit": 5})
        assert agent["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
    finally:
        _cleanup(token)
