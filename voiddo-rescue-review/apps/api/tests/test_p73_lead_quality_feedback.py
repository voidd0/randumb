from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.lead_quality_diagnostics import (
    latest_lead_quality_diagnostics_history,
    latest_scout_source_performance,
    lead_quality_diagnostics,
    scout_source_performance,
)
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM scout_source_performance_scores WHERE reasoning_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM lead_quality_diagnostic_runs WHERE summary_json::text LIKE %s OR recommendations_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR business_name LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_leads WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_runs WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM scout_sources WHERE name LIKE %s", (f"%{token}%",))


def _seed_source(token: str, count: int = 3, final_score: int = 84, with_high_issue: bool = True) -> str:
    source = execute(
        """
        INSERT INTO scout_sources(name, source_type, country, language, niche, status, config_json)
        VALUES (%s, 'manual_csv_scout', 'US', 'en', 'dentists', 'active', '{}'::jsonb)
        RETURNING id
        """,
        (f"p73-source-{token}",),
    )
    run = execute(
        """
        INSERT INTO scout_runs(source_id, status, country, niche, language, found_count, accepted_count, rejected_count, completed_at)
        VALUES (%s, 'completed', 'US', 'dentists', 'en', %s, %s, 0, now())
        RETURNING id
        """,
        (source["id"], count, count),
    )
    for index in range(count):
        domain = f"p73-{token}-{index}.clinic"
        scout_lead = execute(
            """
            INSERT INTO scout_leads(scout_run_id, business_name, domain, website_url, email, country, city, language, niche, source_url, confidence, status)
            VALUES (%s, %s, %s, %s, %s, 'US', 'Quality City', 'en', 'dentists', %s, 90, 'accepted')
            RETURNING id
            """,
            (run["id"], f"P73 Clinic {token} {index}", domain, f"https://{domain}", f"hello-{token}-{index}@{domain}", f"https://source.test/{token}/{index}"),
        )
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
            VALUES (%s, 'US', 'Quality City', 'en', 'dentists', 'scout_agent', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"P73 Clinic {token} {index}", f"https://{domain}", domain, f"hello-{token}-{index}@{domain}"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
            VALUES (%s, %s, 'scout_agent', 'scouted', %s, 'en', 'US', 'Quality City', 'dentists')
            RETURNING id
            """,
            (business["id"], f"hello-{token}-{index}@{domain}", final_score),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 58, 'Public enquiry path issue visible.', %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], domain, f"https://{domain}", f"p73-{token}-{index}"),
        )
        execute(
            """
            INSERT INTO scanner_jobs(url, business_name, dry_run, status, audit_id, result_json, completed_at)
            VALUES (%s, %s, false, 'completed', %s, %s, now())
            """,
            (f"https://{domain}", f"P73 Clinic {token} {index}", audit["id"], Jsonb({"lead_id": str(lead["id"]), "scout_lead_id": str(scout_lead["id"])})),
        )
        if with_high_issue:
            execute(
                """
                INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
                VALUES (%s, 'contact_path', 'high', 'Public enquiry path may be weak', 'Visible from a public browser session.', 'Review the public enquiry path.')
                """,
                (audit["id"],),
            )
        execute(
            """
            INSERT INTO lead_scores(lead_id, audit_id, technical_score, sales_score, urgency_score, value_score, deliverability_score, final_score, reasoning_json)
            VALUES (%s, %s, 88, 75, 84, 76, 70, %s, %s)
            """,
            (lead["id"], audit["id"], final_score, Jsonb({"token": token})),
        )
    return str(source["id"])


def test_lead_quality_diagnostics_records_redacted_source_reasons():
    token = uuid.uuid4().hex[:8]
    try:
        _seed_source(token, count=3, final_score=86, with_high_issue=True)
        result = lead_quality_diagnostics(200, store=True)
        assert result["status"] in {"PASS_LEAD_QUALITY_NO_SEND", "NEEDS_SOURCE_TUNING_NO_SEND"}
        assert result["diagnostic_run_id"]
        assert result["summary"]["sampled_count"] >= 3
        assert any(item["source_name"] == f"p73-source-{token}" for item in result["summary"]["top_sources"])
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
        assert f"hello-{token}" not in str(result)
        history = latest_lead_quality_diagnostics_history(5)
        assert history["count"] >= 1
        assert history["latest"]["raw_recipient_addresses_included"] is False
    finally:
        _cleanup(token)


def test_scout_source_performance_promotes_good_source_without_mutating_status():
    token = uuid.uuid4().hex[:8]
    try:
        source_id = _seed_source(token, count=3, final_score=88, with_high_issue=True)
        before = fetch_one("SELECT status FROM scout_sources WHERE id = %s", (source_id,))
        result = scout_source_performance(100, store=True)
        performance = next(item for item in result["performances"] if item["source_id"] == source_id)
        assert performance["recommendation"] == "PROMOTE_SOURCE_FOR_MORE_SCOUTING"
        assert performance["qualified_rate"] >= 0.9
        assert performance["email_coverage"] >= 0.9
        assert performance["issue_signal_rate"] >= 0.9
        assert performance["send_mail"] is False
        assert performance["live_outreach_allowed"] is False
        after = fetch_one("SELECT status FROM scout_sources WHERE id = %s", (source_id,))
        assert before["status"] == after["status"]
        latest = latest_scout_source_performance(100)
        assert any(item["source_id"] == source_id for item in latest["performances"])
        assert f"hello-{token}" not in str(result)
    finally:
        _cleanup(token)


def test_apply_scout_source_feedback_deprioritizes_low_yield_source_only_when_executed():
    token = uuid.uuid4().hex[:8]
    try:
        source_id = _seed_source(token, count=5, final_score=34, with_high_issue=False)
        dry = run_agent("scout_source_feedback_agent", {"limit": 100, "dry_run": True})
        assert dry["status"] == "completed"
        assert dry["result_json"]["dry_run"] is True
        assert dry["result_json"]["applied_status_changes"] == 0
        assert fetch_one("SELECT status FROM scout_sources WHERE id = %s", (source_id,))["status"] == "active"

        live_apply = run_agent("scout_source_feedback_agent", {"limit": 100, "dry_run": False})
        assert live_apply["status"] == "completed"
        assert live_apply["result_json"]["send_mail"] is False
        assert live_apply["result_json"]["live_outreach_allowed"] is False
        assert any(item["source_id"] == source_id and item["applied_action"] == "deprioritized" for item in live_apply["result_json"]["applied"])
        assert fetch_one("SELECT status FROM scout_sources WHERE id = %s", (source_id,))["status"] == "quality_deprioritized"
    finally:
        _cleanup(token)


def test_lead_quality_feedback_endpoints_and_agents_are_admin_gated_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _seed_source(token, count=3, final_score=82, with_high_issue=True)
        assert client.get("/admin/leads/quality-diagnostics").status_code == 401
        response = client.post("/admin/leads/quality-diagnostics", json={"limit": 200}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["diagnostics"]["send_mail"] is False
        assert client.post("/admin/scouts/source-performance", json={"store": False}).status_code == 401
        source_response = client.post("/admin/scouts/source-performance", json={"limit": 100, "store": False}, headers=admin_headers())
        assert source_response.status_code == 200
        assert source_response.json()["performance"]["smtp_called"] is False
        agent = run_agent("lead_quality_diagnostics_agent", {"limit": 200})
        assert agent["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
        feedback_agent = run_agent("scout_source_feedback_agent", {"limit": 100, "dry_run": True})
        assert feedback_agent["status"] == "completed"
        assert feedback_agent["result_json"]["dry_run"] is True
        assert feedback_agent["result_json"]["applied_status_changes"] == 0
    finally:
        _cleanup(token)
