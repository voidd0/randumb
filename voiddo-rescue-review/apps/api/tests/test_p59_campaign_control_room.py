from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.campaign_control_room import campaign_control_room_snapshot, prepare_campaign_control_room, qualified_campaign_lead_candidates
from app.db import execute, fetch_one
from app.lead_scoring import score_lead
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM agent_runs WHERE agent IN ('campaign_control_room_agent', 'campaign_control_room_prepare_agent') AND result_json::text LIKE %s", (f"%{token}%",))
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


def test_campaign_control_room_admin_endpoints_require_auth():
    assert client.get("/admin/campaign-control-room").status_code == 401
    assert client.post("/admin/campaign-control-room/prepare", json={"dry_run": True}).status_code == 401
    assert client.get("/admin/campaign-control-room", headers=admin_headers()).status_code == 200
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
