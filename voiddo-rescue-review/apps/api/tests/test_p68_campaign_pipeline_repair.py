from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.campaign_pipeline_repair import campaign_pipeline_gap_snapshot, repair_campaign_pipeline
from app.db import execute, fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM campaign_readiness_snapshots WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s) OR preview_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM audit_strength_scores WHERE audit_id IN (SELECT id FROM audits WHERE domain LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE domain LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE domain LIKE %s", (f"%{token}%",))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s", (f"%{token}%",))


def _orphan_pipeline_case(token: str) -> tuple[str, str, str]:
    domain = f"p68-{token}.clinic"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, 'EE', 'Tallinn', 'en', 'dentists', 'p68_test', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P68 Clinic {token}", f"https://{domain}", domain, f"owner-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p68_test', 'scouted', 80, 'en', 'EE', 'Tallinn', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}"),
    )
    audit = execute(
        """
        INSERT INTO audits(domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, 'completed', 48, 'Contact path may be weak.', %s, now())
        RETURNING id
        """,
        (domain, f"https://{domain}", f"p68-{token}"),
    )
    for severity in ["critical", "high", "high"]:
        execute(
            """
            INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
            VALUES (%s, 'contact_path', %s, 'Public contact path may be weak', 'Visible from a public browser session.', 'Review the public enquiry path.')
            """,
            (audit["id"], severity),
        )
    return str(business["id"]), str(lead["id"]), str(audit["id"])


def test_campaign_pipeline_repair_links_orphan_audit_and_scores_lead_without_sending():
    token = uuid.uuid4().hex[:8]
    try:
        _business_id, lead_id, audit_id = _orphan_pipeline_case(token)
        before = campaign_pipeline_gap_snapshot(50)
        assert before["send_mail"] is False
        result = repair_campaign_pipeline(50, dry_run=False)
        audit = fetch_one("SELECT business_id, lead_id FROM audits WHERE id = %s", (audit_id,))
        score = fetch_one("SELECT final_score FROM lead_scores WHERE lead_id = %s AND audit_id = %s", (lead_id, audit_id))
        assert str(audit["lead_id"]) == lead_id
        assert score and int(score["final_score"]) >= 70
        assert result["linked_audits"] >= 1
        assert result["scored_leads"] >= 1
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_campaign_pipeline_repair_dry_run_and_endpoints_are_safe():
    assert client.get("/admin/campaign-pipeline/gaps").status_code == 401
    assert client.post("/admin/campaign-pipeline/repair", json={"dry_run": True}).status_code == 401
    gaps = client.get("/admin/campaign-pipeline/gaps", headers=admin_headers())
    assert gaps.status_code == 200
    assert gaps.json()["pipeline"]["send_mail"] is False
    repair = client.post("/admin/campaign-pipeline/repair", json={"dry_run": True, "limit": 10}, headers=admin_headers())
    assert repair.status_code == 200
    assert repair.json()["pipeline"]["status"] == "dry_run"
    assert repair.json()["pipeline"]["send_mail"] is False


def test_campaign_pipeline_repair_agents_are_dry_run_no_send():
    gap = run_agent("campaign_pipeline_gap_agent", {"limit": 10})
    repair = run_agent("campaign_pipeline_repair_agent", {"limit": 10})
    assert gap["status"] == "completed"
    assert repair["status"] == "completed"
    assert gap["result_json"]["send_mail"] is False
    assert repair["result_json"]["status"] == "dry_run"
    assert repair["result_json"]["send_mail"] is False
