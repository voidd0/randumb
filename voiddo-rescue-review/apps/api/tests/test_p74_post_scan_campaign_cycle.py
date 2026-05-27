from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.post_scan_campaign_cycle import latest_post_scan_campaign_cycles, post_scan_campaign_cycle


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM post_scan_campaign_cycles WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_action_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_readiness_snapshots WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaign_leads WHERE preview_json::text LIKE %s OR campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaigns WHERE name LIKE %s OR country = %s", (f"%{token}%", f"P74{token[:3].upper()}"))
    execute("DELETE FROM audit_strength_scores WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scanner_jobs WHERE business_name LIKE %s OR result_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_leads WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_runs WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM scout_sources WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent = 'post_scan_campaign_cycle_agent' AND result_json::text LIKE %s", (f"%{token}%",))


def _seed_completed_scan_candidate(token: str) -> tuple[str, str]:
    country = f"P74{token[:3].upper()}"
    domain = f"p74-{token}.clinic"
    source = execute(
        """
        INSERT INTO scout_sources(name, source_type, country, language, niche, status, config_json)
        VALUES (%s, 'manual_csv_scout', %s, 'en', 'dentists', 'active', '{}'::jsonb)
        RETURNING id
        """,
        (f"p74-source-{token}", country),
    )
    run = execute(
        """
        INSERT INTO scout_runs(source_id, status, country, niche, language, found_count, accepted_count, completed_at)
        VALUES (%s, 'completed', %s, 'dentists', 'en', 1, 1, now())
        RETURNING id
        """,
        (source["id"], country),
    )
    scout_lead = execute(
        """
        INSERT INTO scout_leads(scout_run_id, business_name, domain, website_url, email, country, city, language, niche, source_url, confidence, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'Cycle City', 'en', 'dentists', %s, 90, 'accepted')
        RETURNING id
        """,
        (run["id"], f"P74 Clinic {token}", domain, f"https://{domain}", f"owner-{token}@{domain}", country, f"https://source.test/{token}"),
    )
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, %s, 'Cycle City', 'en', 'dentists', 'p74_test', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P74 Clinic {token}", country, f"https://{domain}", domain, f"owner-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p74_test', 'scouted', 0, 'en', %s, 'Cycle City', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}", country),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 58, %s, %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"Public contact path issue {token}", f"p74-{token}"),
    )
    for issue_type, severity in [("contact_path", "high"), ("mobile_cta", "high"), ("metadata", "medium")]:
        execute(
            """
            INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
            VALUES (%s, %s, %s, 'Public enquiry path may be weak', 'Visible from a public browser session.', 'Review the public enquiry path.')
            """,
            (audit["id"], issue_type, severity),
        )
    execute(
        """
        INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport)
        VALUES (%s, 'desktop', %s, %s, 'desktop')
        """,
        (audit["id"], f"/app/storage/screenshots/p74-{token}.png", f"/media/screenshots/p74-{token}.png"),
    )
    execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, audit_id, result_json, completed_at)
        VALUES (%s, %s, false, 'completed', %s, %s, now())
        """,
        (
            f"https://{domain}",
            f"P74 Clinic {token}",
            audit["id"],
            Jsonb({"lead_id": str(lead["id"]), "scout_lead_id": str(scout_lead["id"]), "token": token}),
        ),
    )
    return str(lead["id"]), str(audit["id"])


def test_post_scan_campaign_cycle_scores_and_prepares_preview_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        lead_id, audit_id = _seed_completed_scan_candidate(token)
        dry = post_scan_campaign_cycle(100, dry_run=True)
        assert dry["status"] == "dry_run_no_send"
        assert dry["send_mail"] is False
        assert fetch_one("SELECT 1 FROM lead_scores WHERE lead_id = %s AND audit_id = %s", (lead_id, audit_id)) is None

        result = post_scan_campaign_cycle(100, dry_run=False)
        assert result["status"] == "completed_no_send"
        assert result["steps"]["backfill"]["scored_count"] >= 1
        assert result["after"]["campaign"]["ready_candidate_count"] >= 1
        assert result["after"]["campaign_preview_count"] >= 1
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
        assert f"owner-{token}@" not in str(result)
        score = fetch_one("SELECT final_score FROM lead_scores WHERE lead_id = %s AND audit_id = %s", (lead_id, audit_id))
        assert int(score["final_score"]) >= 70
    finally:
        _cleanup(token)


def test_post_scan_campaign_cycle_endpoints_and_agent_are_admin_gated_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _seed_completed_scan_candidate(token)
        assert client.get("/admin/post-scan-campaign-cycles").status_code == 401
        assert client.post("/admin/post-scan-campaign-cycle", json={"dry_run": True}).status_code == 401
        response = client.post("/admin/post-scan-campaign-cycle", json={"limit": 100, "dry_run": True}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["cycle"]["send_mail"] is False
        history = client.get("/admin/post-scan-campaign-cycles", headers=admin_headers())
        assert history.status_code == 200
        assert history.json()["cycles"]["count"] >= 1
        agent = run_agent("post_scan_campaign_cycle_agent", {"limit": 100, "dry_run": True})
        assert agent["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
        assert latest_post_scan_campaign_cycles(5)["send_mail"] is False
    finally:
        _cleanup(token)
