from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.audit_refresh_completion import audit_refresh_completion_watch, latest_audit_refresh_completion_watches
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.lead_scoring import score_lead
from app.main import app
from app.scouts import create_campaign, prepare_campaign


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM audit_refresh_completion_watches WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_preflight_runs WHERE result_json::text LIKE %s OR campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM public_language_gate_runs WHERE issues_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent = 'audit_refresh_completion_watch_agent' AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s) OR preview_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR url LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM audit_strength_scores WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))


def _baseline(token: str) -> None:
    row = fetch_one(
        """
        SELECT count(*) AS count
        FROM scanner_jobs
        WHERE COALESCE(result_json->>'reason', result_json->'job_meta'->>'reason') = 'audit_evidence_remediation'
          AND status = 'completed'
        """
    )
    execute(
        """
        INSERT INTO audit_refresh_completion_watches(
          status, dry_run, completed_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES ('refreshed_no_send', false, %s, %s, false, false, false, false, false)
        """,
        (int(row["count"] or 0), Jsonb({"token": token, "baseline": True, "send_mail": False})),
    )


def _campaign_with_completed_refresh_job(token: str) -> tuple[str, str]:
    domain = f"p86-{token}.clinic"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, 'QA', 'Refresh City', 'en', 'dentists', 'p86_test', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P86 Clinic {token}", f"https://{domain}", domain, f"owner-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p86_test', 'scouted', 91, 'en', 'QA', 'Refresh City', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}"),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 72, 'Public enquiry path may be weak.', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"p86-{token}"),
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
        (audit["id"], f"/app/storage/screenshots/p86-{token}.png", f"/media/screenshots/p86-{token}.png"),
    )
    score_lead(str(lead["id"]), str(audit["id"]))
    execute("UPDATE leads SET score = 91 WHERE id = %s", (lead["id"],))
    execute("UPDATE lead_scores SET final_score = 91 WHERE lead_id = %s AND audit_id = %s", (lead["id"], audit["id"]))
    campaign = create_campaign({"name": f"p86-campaign-{token}", "country": "QA", "language": "en", "niche": "dentists", "offer_key": "contact_form_repair"})
    preview = prepare_campaign(str(campaign["id"]), 70, 5)
    assert preview["preview_count"] == 1
    execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, audit_id, result_json, completed_at)
        VALUES (%s, %s, false, 'completed', 220, %s, %s, now())
        """,
        (
            f"https://{domain}",
            f"P86 Clinic {token}",
            audit["id"],
            Jsonb({"reason": "audit_evidence_remediation", "token": token, "send_mail": False}),
        ),
    )
    return str(campaign["id"]), str(audit["id"])


def _policy_pass() -> dict:
    return {"score": 100, "decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "send_mail": False, "smtp_called": False, "live_outreach_allowed": False}


def test_audit_refresh_completion_watch_rescores_and_reruns_preflight_without_send(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        _baseline(token)
        campaign_id, audit_id = _campaign_with_completed_refresh_job(token)
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        dry = audit_refresh_completion_watch(25, 1, dry_run=True)
        assert dry["status"] == "dry_run_ready"
        assert dry["new_completed_count"] >= 1
        assert f"owner-{token}@" not in str(dry)
        result = audit_refresh_completion_watch(25, 1, dry_run=False)
        assert result["status"] == "refreshed_no_send"
        assert any(item["audit_id"] == audit_id for item in result["rescored_audits"])
        assert any(item["campaign_id"] == campaign_id for item in result["preflight_runs"])
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_audit_refresh_completion_watch_endpoints_and_agent_are_admin_gated_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _baseline(token)
        _campaign_with_completed_refresh_job(token)
        assert client.get("/admin/audit-refresh/completion-watches").status_code == 401
        assert client.post("/admin/audit-refresh/completion-watch", json={"dry_run": True}).status_code == 401
        response = client.post(
            "/admin/audit-refresh/completion-watch",
            json={"limit": 25, "min_new_completed": 1, "dry_run": True},
            headers=admin_headers(),
        )
        assert response.status_code == 200
        assert response.json()["watch"]["send_mail"] is False
        history = client.get("/admin/audit-refresh/completion-watches", headers=admin_headers())
        assert history.status_code == 200
        assert latest_audit_refresh_completion_watches(5)["send_mail"] is False
        agent = run_agent("audit_refresh_completion_watch_agent", {"limit": 25, "dry_run": True})
        assert agent["status"] == "completed"
        assert agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_audit_refresh_completion_watch_tracks_completed_job_meta_reason():
    token = uuid.uuid4().hex[:8]
    try:
        _baseline(token)
        domain = f"p86-meta-{token}.clinic"
        audit = execute(
            """
            INSERT INTO audits(domain, url, status, score, public_slug, checked_at)
            VALUES (%s, %s, 'completed', 75, %s, now())
            RETURNING id
            """,
            (domain, f"https://{domain}", f"p86-meta-{token}"),
        )
        execute(
            """
            INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, audit_id, result_json, completed_at)
            VALUES (%s, %s, false, 'completed', 220, %s, %s, now())
            """,
            (
                f"https://{domain}",
                f"P86 Meta {token}",
                audit["id"],
                Jsonb({"job_meta": {"reason": "audit_evidence_remediation", "token": token}, "send_mail": False}),
            ),
        )
        result = audit_refresh_completion_watch(25, 1, dry_run=True)
        assert result["completed_count"] >= 1
        assert any(item["audit_id"] == str(audit["id"]) for item in result["jobs"])
        assert result["send_mail"] is False
    finally:
        _cleanup(token)


def test_audit_refresh_completion_watch_force_rescores_without_new_count(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        _baseline(token)
        campaign_id, audit_id = _campaign_with_completed_refresh_job(token)
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        first = audit_refresh_completion_watch(25, 1, dry_run=False, force=True)
        second = audit_refresh_completion_watch(25, 1, dry_run=False, force=True)
        assert first["status"] == "force_refreshed_no_send"
        assert second["status"] == "force_refreshed_no_send"
        assert any(item["audit_id"] == audit_id for item in second["rescored_audits"])
        assert any(item["campaign_id"] == campaign_id for item in second["preflight_runs"])
        assert second["send_mail"] is False
        assert second["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
