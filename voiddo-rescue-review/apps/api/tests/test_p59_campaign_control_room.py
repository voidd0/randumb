from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.campaign_control_room import campaign_control_room_snapshot, campaign_preview_rows, prepare_campaign_control_room, qualified_campaign_lead_candidates
from app.campaign_preview_reviews import auto_review_campaign_previews, latest_campaign_preview_reviews, review_campaign_preview
from app.db import execute, fetch_one
from app.lead_scoring import score_lead
from app.main import app
from app.scouts import create_campaign, prepare_campaign_gated


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM agent_runs WHERE agent IN ('campaign_control_room_agent', 'campaign_control_room_prepare_agent') AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_preview_reviews WHERE campaign_lead_id IN (SELECT id FROM campaign_leads WHERE preview_json::text LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaign_readiness_snapshots WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s) OR preview_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaigns WHERE name LIKE %s OR country = %s", (f"%{token}%", f"P59{token[:3].upper()}"))
    execute("DELETE FROM audit_strength_scores WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))


def _qualified_lead(token: str) -> tuple[str, str]:
    country = f"P59{token[:3].upper()}"
    domain = f"p59-{token}.clinic"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, %s, 'Control City', 'en', 'dentists', 'p59_test', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P59 Clinic {token}", country, f"https://{domain}", domain, f"owner-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p59_test', 'scouted', 90, 'en', %s, 'Control City', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}", country),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 68, 'Contact path and mobile CTA may be weak.', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"p59-{token}"),
    )
    for issue_type, severity, title in [
        ("contact_path", "high", "Contact path may be weak"),
        ("mobile_cta", "high", "Mobile CTA may be hard to use"),
        ("metadata", "medium", "Homepage metadata may be incomplete"),
    ]:
        execute(
            """
            INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
            VALUES (%s, %s, %s, %s, 'Visible from a public browser session.', 'Review and improve this public website path.')
            """,
            (audit["id"], issue_type, severity, title),
        )
    execute(
        """
        INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport)
        VALUES (%s, 'desktop', %s, %s, 'desktop')
        """,
        (audit["id"], f"/app/storage/screenshots/p59-{token}.png", f"/media/screenshots/p59-{token}.png"),
    )
    score_lead(str(lead["id"]), str(audit["id"]))
    execute("UPDATE leads SET score = 91 WHERE id = %s", (lead["id"],))
    execute("UPDATE lead_scores SET final_score = 91 WHERE lead_id = %s AND audit_id = %s", (lead["id"], audit["id"]))
    return str(lead["id"]), str(audit["id"])


def test_campaign_control_room_finds_candidates_without_raw_email():
    token = uuid.uuid4().hex[:8]
    try:
        _qualified_lead(token)
        result = qualified_campaign_lead_candidates(50, 70)
        text = str(result)
        assert f"owner-{token}@" not in text
        assert result["raw_recipient_addresses_included"] is False
        assert any(item["domain"] == f"p59-{token}.clinic" for item in result["candidates"])
    finally:
        _cleanup(token)


def test_campaign_control_room_prepare_scores_audit_and_creates_preview_only_campaign():
    token = uuid.uuid4().hex[:8]
    try:
        _qualified_lead(token)
        result = prepare_campaign_control_room(100, 70, dry_run=False, max_segments=5)
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert result["audit_strengths_scored"] >= 1
        assert result["campaigns_created_or_confirmed"] >= 1
        assert f"owner-{token}@" not in str(result)
        snapshot = campaign_control_room_snapshot(100, 70)
        assert snapshot["candidate_count"] >= 1
        assert snapshot["raw_recipient_addresses_included"] is False
    finally:
        _cleanup(token)


def test_campaign_control_room_preview_rows_are_redacted_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _qualified_lead(token)
        campaign = create_campaign(
            {
                "name": f"P59 preview rows {token}",
                "country": f"P59{token[:3].upper()}",
                "language": "en",
                "niche": "dentists",
                "offer_key": "contact_form_repair",
            }
        )
        prepare_campaign_gated(str(campaign["id"]), 70, 20)
        result = campaign_preview_rows(100)
        text = str(result)
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert result["raw_recipient_addresses_included"] is False
        assert f"owner-{token}@" not in text
        rows = [row for row in result["rows"] if row["domain"] == f"p59-{token}.clinic"]
        assert rows
        assert rows[0]["send_mail"] is False
        assert rows[0]["smtp_called"] is False
        assert rows[0]["audit_slug"] == f"p59-{token}"
        review = review_campaign_preview(rows[0]["campaign_lead_id"], "approved", "proof looks specific")
        assert review["send_mail"] is False
        assert review["raw_recipient_addresses_included"] is False
        assert f"owner-{token}@" not in str(review)
        reviewed = campaign_preview_rows(100)
        reviewed_row = [row for row in reviewed["rows"] if row["domain"] == f"p59-{token}.clinic"][0]
        assert reviewed_row["latest_review_action"] == "approved"
        latest_reviews = latest_campaign_preview_reviews(20)
        assert latest_reviews["send_mail"] is False
        assert any(item["campaign_lead_id"] == rows[0]["campaign_lead_id"] for item in latest_reviews["reviews"])
    finally:
        _cleanup(token)


def test_campaign_preview_self_review_agent_approves_strong_rows_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        _qualified_lead(token)
        campaign = create_campaign(
            {
                "name": f"P59 self review {token}",
                "country": f"P59{token[:3].upper()}",
                "language": "en",
                "niche": "dentists",
                "offer_key": "contact_form_repair",
            }
        )
        prepare_campaign_gated(str(campaign["id"]), 70, 20)
        dry = auto_review_campaign_previews(100, apply=False, campaign_id=str(campaign["id"]))
        assert dry["send_mail"] is False
        assert f"owner-{token}@" not in str(dry)
        result = auto_review_campaign_previews(100, apply=True, campaign_id=str(campaign["id"]))
        rows = campaign_preview_rows(100)["rows"]
        row = [item for item in rows if item["domain"] == f"p59-{token}.clinic"][0]
        assert row["latest_review_action"] == "approved"
        assert result["smtp_called"] is False
        agent = run_agent("campaign_preview_self_review_agent", {"limit": 5, "apply": True, "campaign_id": str(campaign["id"])})
        assert agent["status"] == "completed"
        assert agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_campaign_control_room_admin_endpoints_require_auth():
    assert client.get("/admin/campaign-control-room").status_code == 401
    assert client.get("/admin/campaign-control-room/preview-rows").status_code == 401
    assert client.get("/admin/campaign-control-room/reviews").status_code == 401
    assert client.post("/admin/campaign-control-room/review", json={"campaign_lead_id": str(uuid.uuid4()), "action": "held"}).status_code == 401
    assert client.post("/admin/campaign-control-room/auto-review", json={"limit": 1}).status_code == 401
    assert client.post("/admin/campaign-control-room/prepare", json={"dry_run": True}).status_code == 401
    assert client.get("/admin/campaign-control-room", headers=admin_headers()).status_code == 200
    assert client.get("/admin/campaign-control-room/preview-rows", headers=admin_headers()).status_code == 200
    assert client.get("/admin/campaign-control-room/reviews", headers=admin_headers()).status_code == 200
    assert client.post("/admin/campaign-control-room/auto-review", json={"limit": 1, "apply": False}, headers=admin_headers()).status_code == 200
    response = client.post("/admin/campaign-control-room/prepare", json={"dry_run": True, "limit": 5}, headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["control_room"]["status"] == "preview_only"


def test_campaign_control_room_agents_are_no_send():
    snapshot = run_agent("campaign_control_room_agent", {"limit": 5})
    prepare = run_agent("campaign_control_room_prepare_agent", {"limit": 5})
    assert snapshot["status"] == "completed"
    assert prepare["status"] == "completed"
    assert snapshot["result_json"]["send_mail"] is False
    assert prepare["result_json"]["send_mail"] is False
