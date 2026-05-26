from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.campaign_economics import run_campaign_economics_check
from app.db import execute, fetch_one
from app.mail_recovery import check_mail_clean_window, create_mailer_draft
from app.main import app
from app.revenue_simulation import run_synthetic_lead_simulation


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_synthetic_lead_simulation_creates_pipeline_records():
    result = run_synthetic_lead_simulation(12, "P7", "p7_dentists")
    assert result["status"] == "completed"
    assert result["accepted_count"] == 12
    assert result["scanner_jobs_count"] == 12
    assert result["audits_count"] == 12
    assert result["campaign_id"]


def test_campaign_economics_passes_for_simulated_campaign():
    sim = run_synthetic_lead_simulation(25, "P7", "p7_dentists")
    check = run_campaign_economics_check(str(sim["campaign_id"]), "contact_form_repair", 0.02)
    assert check["decision"] == "pass"
    assert check["expected_margin_percent"] >= 70


def test_campaign_economics_blocks_empty_campaign():
    campaign = execute("INSERT INTO campaigns(name, dry_run) VALUES (%s, true) RETURNING id", ("empty-economics-test",))
    check = run_campaign_economics_check(str(campaign["id"]), "contact_form_repair", 0.02)
    assert check["decision"] == "blocked"


def test_campaign_economics_blocks_low_conversion_risk():
    sim = run_synthetic_lead_simulation(25, "P7", "p7_low_conversion")
    check = run_campaign_economics_check(str(sim["campaign_id"]), "contact_form_repair", 0.001)
    assert check["decision"] == "blocked"
    assert check["risk_score"] >= 20


def test_mail_clean_window_blocks_on_existing_runtime_signals():
    check = check_mail_clean_window(24)
    assert check["status"] in {"blocked", "ready_for_mail_qa_recheck"}
    if check["bounce_or_dsn_count"] or check["rate_limit_count"]:
        assert check["status"] == "blocked"


def test_mailer_draft_qa_persists_without_sending():
    draft = create_mailer_draft("reply_ask_price", "ask_price", "audit@voiddorescue.com", "lead@example.test")
    assert draft["status"] == "draft_ready"
    assert draft["recipient_hash"] != "lead@example.test"
    assert "Pricing" in draft["subject"] or "pricing" in draft["subject"].lower()


def test_mailer_draft_endpoint_does_not_expose_raw_recipient():
    response = client.post("/admin/mailer/drafts", json={"template_key": "reply_ask_details", "recipient_email": "private@example.test"}, headers=admin_headers())
    assert response.status_code == 200
    payload = response.json()["draft"]
    assert payload["recipient_hash"] != "private@example.test"
    assert "private@example.test" not in str(payload)


def test_p7_agents_execute_without_live_send():
    sim = run_agent("revenue_simulation_agent", {"count": 5})
    clean = run_agent("mail_clean_window_agent")
    assert sim["status"] == "completed"
    assert clean["status"] == "completed"


def test_p7_admin_endpoints_require_auth_and_work():
    assert client.post("/admin/revenue/simulate", json={"count": 1}).status_code == 401
    response = client.post("/admin/revenue/simulate", json={"count": 3}, headers=admin_headers())
    assert response.status_code == 200
    campaign_id = response.json()["simulation"]["campaign_id"]
    econ = client.post(f"/admin/campaigns/{campaign_id}/economics", json={}, headers=admin_headers())
    assert econ.status_code == 200
    clean = client.post("/admin/mail/clean-window", json={}, headers=admin_headers())
    assert clean.status_code == 200
    draft = client.post("/admin/mailer/drafts", json={"template_key": "reply_ask_price"}, headers=admin_headers())
    assert draft.status_code == 200


def test_p7_tables_exist():
    for table in ["revenue_simulation_runs", "campaign_economics_checks", "mail_clean_window_checks", "mailer_drafts"]:
        row = fetch_one("SELECT to_regclass(%s) AS name", (table,))
        assert row["name"] == table
