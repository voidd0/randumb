from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.audit_evidence_remediation import audit_evidence_candidates, audit_evidence_remediation, latest_audit_evidence_remediation_runs
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.scouts import create_campaign


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM audit_evidence_remediation_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent IN ('audit_evidence_candidates_agent', 'audit_evidence_remediation_agent') AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM codex_tasks WHERE input_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR business_name LIKE %s OR url LIKE %s", (f"%{token}%", f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM audit_strength_scores WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s", (f"%{token}%",))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s", (f"%{token}%",))


def _weak_campaign(token: str) -> tuple[str, str]:
    domain = f"p84-{token}.example.test"
    business = execute(
        "INSERT INTO businesses(name, domain, website_url, source, niche, country, status) VALUES (%s, %s, %s, 'p84', 'dentists', 'QA', 'scouted') RETURNING id",
        (f"P84 {token}", domain, f"https://{domain}"),
    )
    lead = execute(
        "INSERT INTO leads(business_id, email, source, status, score, niche, country, language) VALUES (%s, %s, 'p84', 'scouted', 90, 'dentists', 'QA', 'en') RETURNING id",
        (business["id"], f"owner-{token}@{domain}"),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 60, %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"p84-{token}"),
    )
    campaign = create_campaign({"name": f"p84-{token}", "country": "QA", "language": "en", "niche": "dentists", "offer_key": "contact_form_repair"})
    execute(
        """
        INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json)
        VALUES (%s, %s, %s, 'preview', 88, '{}')
        """,
        (campaign["id"], lead["id"], audit["id"]),
    )
    return str(campaign["id"]), str(audit["id"])


def test_audit_evidence_remediation_queues_scanner_and_task_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        _, audit_id = _weak_campaign(token)
        candidates = audit_evidence_candidates(25)
        assert any(item["audit_id"] == audit_id for item in candidates["candidates"])
        dry = audit_evidence_remediation(25, dry_run=True)
        assert dry["queued_scanner_jobs"] == 0
        result = audit_evidence_remediation(25, dry_run=False)
        item = next(candidate for candidate in result["candidates"] if candidate["audit_id"] == audit_id)
        assert "missing_screenshots" in item["issues"]
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert fetch_one("SELECT count(*) AS count FROM scanner_jobs WHERE audit_id = %s AND result_json->>'reason' = 'audit_evidence_remediation'", (audit_id,))["count"] == 1
        assert fetch_one("SELECT count(*) AS count FROM codex_tasks WHERE input_json->>'source' = 'audit_evidence_remediation' AND input_json->>'audit_id' = %s", (audit_id,))["count"] == 1
        second = audit_evidence_remediation(25, dry_run=False)
        assert second["send_mail"] is False
    finally:
        _cleanup(token)


def test_audit_evidence_remediation_endpoints_and_agents_are_admin_gated():
    token = uuid.uuid4().hex[:8]
    try:
        _weak_campaign(token)
        assert client.get("/admin/audit-evidence/remediation-candidates").status_code == 401
        assert client.post("/admin/audit-evidence/remediate", json={"dry_run": True}).status_code == 401
        response = client.post("/admin/audit-evidence/remediate", json={"limit": 25, "dry_run": True}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["remediation"]["send_mail"] is False
        history = client.get("/admin/audit-evidence/remediation-runs", headers=admin_headers())
        assert history.status_code == 200
        assert latest_audit_evidence_remediation_runs(5)["send_mail"] is False
        candidates_agent = run_agent("audit_evidence_candidates_agent", {"limit": 25})
        remediation_agent = run_agent("audit_evidence_remediation_agent", {"limit": 25, "dry_run": True})
        assert candidates_agent["status"] == "completed"
        assert remediation_agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
