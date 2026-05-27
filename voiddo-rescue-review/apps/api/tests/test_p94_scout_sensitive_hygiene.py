from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.campaign_control_room import qualified_campaign_lead_candidates
from app.db import execute, fetch_one
from app.main import app
from app.scout_sensitive_hygiene import archive_sensitive_scout_targets, scout_sensitive_target_snapshot
from app.scouts import create_scout_run, create_scout_source, process_scout_run


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM campaign_leads WHERE preview_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_readiness_snapshots WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM suppression_list WHERE source = %s OR domain LIKE %s OR email LIKE %s", (f"p94-{token}", f"%{token}%", f"%{token}%"))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR url LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_leads WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_runs WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM scout_source_readiness_checks WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM scout_sources WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s", (f"%{token}%",))


def test_scout_run_rejects_hospital_and_large_enterprise_targets_without_send():
    token = uuid.uuid4().hex[:8]
    csv_text = (
        "business_name,website_url,email,country,city,language,niche,source_url,confidence\n"
        f"Renown Medical Center {token},https://renown-{token}.org,hello@renown-{token}.org,US,Reno,en,clinics,https://source.test/{token},90\n"
        f"Social Profile {token},https://facebook.com/local-{token},hello@local-{token}.com,US,Reno,en,law firms,https://source.test/{token}/social,90\n"
        f"Local Dental {token},https://local-{token}.clinic,hello@local-{token}.clinic,US,Reno,en,dentists,https://source.test/{token}/2,90\n"
    )
    try:
        source = create_scout_source({"name": f"p94-sensitive-{token}", "source_type": "manual_csv_scout", "country": "US", "language": "en", "niche": "clinics", "config_json": {"csv": csv_text}})
        run = create_scout_run(str(source["id"]))
        result = process_scout_run(str(run["id"]))
        assert result["accepted"] == 1
        assert result["rejected"] == 2
        sensitive = fetch_one("SELECT status, rejection_reason FROM scout_leads WHERE domain = %s", (f"renown-{token}.org",))
        assert sensitive["status"] == "rejected"
        assert sensitive["rejection_reason"] == "excluded_sensitive_target"
        social = fetch_one("SELECT status, rejection_reason FROM scout_leads WHERE domain = 'facebook.com' AND email = %s", (f"hello@local-{token}.com",))
        assert social["status"] == "rejected"
        assert social["rejection_reason"] == "excluded_sensitive_target"
        assert result.get("send_mail") is None or result.get("send_mail") is False
    finally:
        _cleanup(token)


def test_sensitive_hygiene_archives_existing_preview_and_keeps_campaign_candidates_clean():
    token = uuid.uuid4().hex[:8]
    domain = f"hopkinsmedicine-{token}.org"
    try:
        source = execute(
            """
            INSERT INTO scout_sources(name, source_type, country, language, niche, status, config_json)
            VALUES (%s, 'manual_csv_scout', 'US', 'en', 'clinics', 'active', '{}'::jsonb)
            RETURNING id
            """,
            (f"p94-source-{token}",),
        )
        run = execute("INSERT INTO scout_runs(source_id, status, country, niche, language) VALUES (%s, 'completed', 'US', 'clinics', 'en') RETURNING id", (source["id"],))
        scout_lead = execute(
            """
            INSERT INTO scout_leads(scout_run_id, business_name, domain, website_url, email, country, language, niche, source_url, confidence, status)
            VALUES (%s, %s, %s, %s, %s, 'US', 'en', 'clinics', %s, 90, 'accepted')
            RETURNING id
            """,
            (run["id"], f"Hopkins Medical Center {token}", domain, f"https://{domain}", f"hello@{domain}", f"https://source.test/{token}"),
        )
        business = execute(
            """
            INSERT INTO businesses(name, country, language, niche, source, website_url, domain, email, status)
            VALUES (%s, 'US', 'en', 'clinics', 'scout_agent', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"Hopkins Medical Center {token}", f"https://{domain}", domain, f"hello@{domain}"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, niche)
            VALUES (%s, %s, 'scout_agent', 'scouted', 91, 'en', 'US', 'clinics')
            RETURNING id
            """,
            (business["id"], f"hello@{domain}"),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 40, %s, %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], domain, f"https://{domain}", f"Sensitive target {token}", f"p94-{token}"),
        )
        execute("INSERT INTO lead_scores(lead_id, audit_id, final_score, technical_score, sales_score, urgency_score, value_score, deliverability_score) VALUES (%s, %s, 91, 90, 90, 90, 90, 90)", (lead["id"], audit["id"]))
        campaign = execute("INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run) VALUES (%s, 'preview_ready', 'US', 'en', 'clinics', 'contact_form_repair', true) RETURNING id", (f"p94-campaign-{token}",))
        preview = execute(
            "INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json) VALUES (%s, %s, %s, 'preview', 91, %s) RETURNING id",
            (campaign["id"], lead["id"], audit["id"], Jsonb({"token": token, "scout_lead_id": str(scout_lead["id"])})),
        )
        scanner_job = execute(
            "INSERT INTO scanner_jobs(url, business_name, dry_run, status, result_json) VALUES (%s, %s, false, 'queued', %s) RETURNING id",
            (f"https://{domain}", f"Hopkins Medical Center {token}", Jsonb({"token": token, "lead_id": str(lead["id"]), "scout_lead_id": str(scout_lead["id"])})),
        )

        snapshot = scout_sensitive_target_snapshot(50)
        assert snapshot["candidate_count"] >= 1
        result = archive_sensitive_scout_targets(50, apply=True)
        assert result["archived_count"] >= 1
        assert result["send_mail"] is False
        assert result["raw_recipient_addresses_included"] is False
        assert fetch_one("SELECT status FROM campaign_leads WHERE id = %s", (preview["id"],))["status"] == "archived_sensitive_target"
        assert fetch_one("SELECT status FROM leads WHERE id = %s", (lead["id"],))["status"] == "excluded_sensitive_target"
        assert fetch_one("SELECT status FROM scanner_jobs WHERE id = %s", (scanner_job["id"],))["status"] == "archived_sensitive_target"
        candidates = qualified_campaign_lead_candidates(100, 70)
        assert all(item["lead_id"] != str(lead["id"]) for item in candidates["candidates"])
    finally:
        _cleanup(token)


def test_sensitive_hygiene_endpoint_and_agents_are_admin_gated_no_send():
    assert client.get("/admin/scouts/sensitive-targets").status_code == 401
    ok = client.get("/admin/scouts/sensitive-targets", headers=admin_headers())
    assert ok.status_code == 200
    assert ok.json()["hygiene"]["send_mail"] is False
    run = client.post("/admin/scouts/archive-sensitive-targets", json={"limit": 5, "apply": False}, headers=admin_headers())
    assert run.status_code == 200
    assert run.json()["hygiene"]["live_outreach_allowed"] is False
    agent = run_agent("scout_sensitive_hygiene_snapshot_agent", {"limit": 5})
    assert agent["status"] == "completed"
    assert agent["result_json"]["raw_recipient_addresses_included"] is False


def test_sensitive_hygiene_archives_queued_scanner_jobs_for_already_excluded_leads():
    token = uuid.uuid4().hex[:8]
    domain = f"facebook-{token}.com"
    try:
        business = execute(
            "INSERT INTO businesses(name, domain, source, status) VALUES (%s, %s, 'scout_agent', 'excluded_sensitive_target') RETURNING id",
            (f"Excluded {token}", domain),
        )
        lead = execute(
            "INSERT INTO leads(business_id, email, source, status, score, language, country, niche) VALUES (%s, %s, 'scout_agent', 'excluded_sensitive_target', 0, 'en', 'US', 'law firms') RETURNING id",
            (business["id"], f"hello@{domain}"),
        )
        job = execute(
            "INSERT INTO scanner_jobs(url, business_name, dry_run, status, result_json) VALUES (%s, %s, false, 'queued', %s) RETURNING id",
            (f"https://{domain}", f"Excluded {token}", Jsonb({"token": token, "lead_id": str(lead["id"])})),
        )
        result = archive_sensitive_scout_targets(50, apply=True)
        assert result["archived_scanner_jobs_count"] >= 1
        assert fetch_one("SELECT status FROM scanner_jobs WHERE id = %s", (job["id"],))["status"] == "archived_sensitive_target"
    finally:
        _cleanup(token)
