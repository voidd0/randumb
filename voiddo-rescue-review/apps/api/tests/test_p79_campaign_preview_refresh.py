from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.campaign_preview_refresh import campaign_preview_refresh_snapshot, latest_campaign_preview_refresh_runs, refresh_campaign_previews_if_needed
from app.db import execute, fetch_one
from app.lead_scoring import score_lead
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM campaign_preview_refresh_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent IN ('campaign_preview_refresh_snapshot_agent', 'campaign_preview_refresh_agent') AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_readiness_snapshots WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s) OR preview_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaigns WHERE name LIKE %s OR country = %s", (f"%{token}%", f"P79{token[:3].upper()}"))
    execute("DELETE FROM audit_strength_scores WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))


def _seed_preview_candidate(token: str) -> tuple[str, str, str]:
    country = f"P79{token[:3].upper()}"
    domain = f"p79-{token}.clinic"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, %s, 'Refresh City', 'en', 'dentists', 'p79_test', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P79 Clinic {token}", country, f"https://{domain}", domain, f"owner-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p79_test', 'scouted', 91, 'en', %s, 'Refresh City', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}", country),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 70, 'Public contact path may be weak.', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"p79-{token}"),
    )
    for issue_type in ["contact_path", "mobile_cta", "metadata"]:
        execute(
            """
            INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
            VALUES (%s, %s, 'high', 'Public enquiry path may be weak', 'Visible from a public browser session.', 'Review the public enquiry path.')
            """,
            (audit["id"], issue_type),
        )
    execute(
        """
        INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport)
        VALUES (%s, 'desktop', %s, %s, 'desktop')
        """,
        (audit["id"], f"/app/storage/screenshots/p79-{token}.png", f"/media/screenshots/p79-{token}.png"),
    )
    score_lead(str(lead["id"]), str(audit["id"]))
    execute("UPDATE lead_scores SET final_score = 91 WHERE lead_id = %s AND audit_id = %s", (lead["id"], audit["id"]))
    campaign = execute(
        """
        INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
        VALUES (%s, 'preview_ready', %s, 'en', 'dentists', 'contact_form_repair', true)
        RETURNING id
        """,
        (f"p79-campaign-{token}", country),
    )
    execute(
        """
        INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json, updated_at)
        VALUES (%s, %s, %s, 'preview', 70, %s, now() - interval '2 hours')
        """,
        (campaign["id"], lead["id"], audit["id"], Jsonb({"token": token, "stale": True})),
    )
    return str(campaign["id"]), str(lead["id"]), str(audit["id"])


def test_campaign_preview_refresh_detects_stale_and_refreshes_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id, lead_id, audit_id = _seed_preview_candidate(token)
        snapshot = campaign_preview_refresh_snapshot(100, stale_hours=1)
        assert snapshot["should_refresh"] is True
        assert snapshot["stale_preview_count"] >= 1
        dry = refresh_campaign_previews_if_needed(100, stale_hours=1, dry_run=True)
        assert dry["status"] == "dry_run_refresh_recommended"
        result = refresh_campaign_previews_if_needed(100, stale_hours=1, dry_run=False)
        assert result["status"] == "refreshed_no_send"
        assert result["refreshed_preview_count"] >= 1
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
        assert f"owner-{token}@" not in str(result)
        row = fetch_one("SELECT updated_at > now() - interval '5 minutes' AS refreshed FROM campaign_leads WHERE campaign_id = %s AND lead_id = %s AND audit_id = %s", (campaign_id, lead_id, audit_id))
        assert row["refreshed"] is True
        assert latest_campaign_preview_refresh_runs(5)["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preview_refresh_endpoint_and_agent_are_admin_gated():
    token = uuid.uuid4().hex[:8]
    try:
        _seed_preview_candidate(token)
        assert client.get("/admin/campaign-preview/refresh-snapshot").status_code == 401
        assert client.post("/admin/campaign-preview/refresh", json={"dry_run": True}).status_code == 401
        response = client.post("/admin/campaign-preview/refresh", json={"stale_hours": 1, "dry_run": True}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["refresh"]["send_mail"] is False
        history = client.get("/admin/campaign-preview/refresh-runs", headers=admin_headers())
        assert history.status_code == 200
        snapshot_agent = run_agent("campaign_preview_refresh_snapshot_agent", {"stale_hours": 1})
        refresh_agent = run_agent("campaign_preview_refresh_agent", {"stale_hours": 1, "dry_run": True})
        assert snapshot_agent["status"] == "completed"
        assert refresh_agent["status"] == "completed"
        assert snapshot_agent["result_json"]["send_mail"] is False
        assert refresh_agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
