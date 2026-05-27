from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.lead_scoring import backfill_post_scan_lead_scores
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM agent_runs WHERE agent = 'post_scan_lead_scoring_agent' AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s", (f"%{token}%",))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))


def _completed_audit_without_score(token: str) -> tuple[str, str]:
    domain = f"p72-{token}.example.test"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, 'US', 'Score City', 'en', 'dentists', 'p72_test', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P72 Clinic {token}", f"https://{domain}", domain, f"hello-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p72_test', 'scouted', 0, 'en', 'US', 'Score City', 'dentists')
        RETURNING id
        """,
        (business["id"], f"hello-{token}@{domain}"),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 62, 'Public contact path may be weak.', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"p72-{token}"),
    )
    for issue_type in ["contact_path", "mobile_cta", "metadata"]:
        execute(
            """
            INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
            VALUES (%s, %s, 'high', 'Public enquiry path may be weak', 'Visible from a public browser session.', 'Review the public enquiry path.')
            """,
            (audit["id"], issue_type),
        )
    return str(lead["id"]), str(audit["id"])


def test_post_scan_lead_score_backfill_scores_completed_audit_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        lead_id, audit_id = _completed_audit_without_score(token)
        dry = backfill_post_scan_lead_scores(20, dry_run=True)
        assert dry["candidate_count"] >= 1
        assert dry["scored_count"] == 0
        assert dry["send_mail"] is False

        result = backfill_post_scan_lead_scores(20, dry_run=False)
        assert result["status"] == "scored"
        assert result["scored_count"] >= 1
        assert result["qualified_count"] >= 1
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        row = fetch_one("SELECT score FROM leads WHERE id = %s", (lead_id,))
        score = fetch_one("SELECT final_score FROM lead_scores WHERE lead_id = %s AND audit_id = %s", (lead_id, audit_id))
        assert int(row["score"]) >= 70
        assert int(score["final_score"]) >= 70
    finally:
        _cleanup(token)


def test_post_scan_lead_score_backfill_endpoint_and_agent_are_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _completed_audit_without_score(token)
        assert client.post("/admin/leads/backfill-post-scan-scores", json={"dry_run": True}).status_code == 401
        response = client.post(
            "/admin/leads/backfill-post-scan-scores",
            json={"limit": 20, "dry_run": True},
            headers=admin_headers(),
        )
        assert response.status_code == 200
        assert response.json()["backfill"]["status"] == "dry_run"
        agent = run_agent("post_scan_lead_scoring_agent", {"limit": 20, "dry_run": False})
        assert agent["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
        assert agent["result_json"]["smtp_called"] is False
        assert agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
