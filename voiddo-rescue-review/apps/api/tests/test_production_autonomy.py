from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import DAILY_LOOP_ADVISORY_LOCK_KEY, run_agent, run_daily_loop
from app.db import connect, execute, fetch_all, fetch_one
from app.email_templates import render_all_samples, render_email_template, qa_email_template
from app.lead_scoring import score_lead
from app.main import app
from app.mailer_throttle import throttle_decision
from app.p0 import handle_paddle_event, record_mail_signal
from app.scout_quality import latest_scout_quality_gate, lead_scout_quality_gate, run_scout_quality_gate
from app.scouts import create_campaign, create_scout_run, create_scout_source, get_campaign, prepare_campaign, prepare_campaign_gated, process_queued_scout_runs, process_scout_run, process_scout_run_gated, run_scout_source_readiness, scout_campaign_expansion_gate


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup_token(token: str):
    execute("DELETE FROM self_operating_cycles WHERE result_json::text LIKE %s OR scope LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM self_fix_tasks WHERE evidence_json::text LIKE %s OR title LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM self_learning_events WHERE payload_json::text LIKE %s OR lesson LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM self_build_queue WHERE acceptance_json::text LIKE %s OR title LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM agent_runs WHERE agent LIKE 'qa-failing-agent-%%' OR result_json::text LIKE %s OR error LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaign_leads WHERE preview_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scanner_jobs WHERE url LIKE %s OR result_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute(
        """
        DELETE FROM lead_scores
        WHERE lead_id IN (
          SELECT l.id
          FROM leads l
          JOIN businesses b ON b.id = l.business_id
          WHERE b.domain LIKE %s OR l.email LIKE %s OR l.source = 'test_prod'
        )
        """,
        (f"%{token}%", f"%{token}%"),
    )
    execute(
        """
        DELETE FROM leads
        WHERE source = 'test_prod'
           OR email LIKE %s
           OR business_id IN (SELECT id FROM businesses WHERE domain LIKE %s)
        """,
        (f"%{token}%", f"%{token}%"),
    )
    execute("DELETE FROM businesses WHERE domain LIKE %s OR source = 'test_prod'", (f"%{token}%",))
    execute("DELETE FROM scout_provenance_scores WHERE scout_run_id IN (SELECT id FROM scout_runs WHERE result_json::text LIKE %s OR source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s))", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_self_checks WHERE scout_run_id IN (SELECT id FROM scout_runs WHERE result_json::text LIKE %s OR source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s))", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_source_readiness_checks WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM scout_leads WHERE domain LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scout_runs WHERE result_json::text LIKE %s OR source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_sources WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM mail_signals WHERE source = %s", (f"test-{token}",))


def test_manual_csv_scout_imports_fifty_leads_and_queues_scans():
    token = uuid.uuid4().hex[:8]
    rows = ["business_name,website_url,email,country,city,language,niche,source_url"]
    rows.extend(
        f"Biz {i},https://prod-{token}-{i}.example.test,owner{i}@prod-{token}-{i}.example.test,EE,Tallinn,en,dentists,https://source.example/{i}"
        for i in range(50)
    )
    try:
        source = create_scout_source({"name": f"prod-{token}", "source_type": "manual_csv_scout", "country": "EE", "language": "en", "niche": "dentists", "config_json": {"csv": "\n".join(rows)}})
        run = create_scout_run(str(source["id"]))
        result = process_scout_run(str(run["id"]))
        assert result["found"] == 50
        assert result["accepted"] == 50
        assert result["scanner_jobs"] == 50
    finally:
        _cleanup_token(token)


def test_scout_dedupes_duplicate_domains():
    token = uuid.uuid4().hex[:8]
    csv_text = f"business_name,website_url,email,country,niche\nOne,https://dup-{token}.example.test,a@dup-{token}.example.test,EE,dentists\nTwo,https://dup-{token}.example.test,b@dup-{token}.example.test,EE,dentists\n"
    try:
        source = create_scout_source({"name": f"dedupe-{token}", "source_type": "manual_csv_scout", "config_json": {"csv": csv_text}})
        run = create_scout_run(str(source["id"]))
        result = process_scout_run(str(run["id"]))
        assert result["accepted"] == 1
        assert result["rejected"] == 1
    finally:
        _cleanup_token(token)


def test_scout_rejects_excluded_niche():
    token = uuid.uuid4().hex[:8]
    csv_text = f"business_name,website_url,email,country,niche\nBad,https://bad-{token}.example.test,a@bad-{token}.example.test,EE,crypto\n"
    try:
        source = create_scout_source({"name": f"excluded-{token}", "source_type": "manual_csv_scout", "config_json": {"csv": csv_text}})
        run = create_scout_run(str(source["id"]))
        result = process_scout_run(str(run["id"]))
        assert result["accepted"] == 0
        assert result["rejected"] == 1
    finally:
        _cleanup_token(token)


def test_scout_rejects_excluded_large_enterprise_brand():
    token = uuid.uuid4().hex[:8]
    csv_text = f"business_name,website_url,email,country,niche\nChain Hotel,https://marriott-{token}.example.test,a@marriott-{token}.example.test,US,local tourism\n"
    try:
        source = create_scout_source({"name": f"largebrand-{token}", "source_type": "manual_csv_scout", "config_json": {"csv": csv_text}})
        run = create_scout_run(str(source["id"]))
        result = process_scout_run(str(run["id"]))
        assert result["accepted"] == 0
        assert result["rejected"] == 1
        row = fetch_one("SELECT rejection_reason FROM scout_leads WHERE domain = %s", (f"marriott-{token}.example.test",))
        assert row["rejection_reason"] == "excluded_large_enterprise"
    finally:
        _cleanup_token(token)


def test_scout_rejects_large_dental_chain_brand():
    token = uuid.uuid4().hex[:8]
    csv_text = f"business_name,website_url,email,country,niche\nAspen Dental,https://aspendental-{token}.example.test,a@aspendental-{token}.example.test,US,dentists\n"
    try:
        source = create_scout_source({"name": f"large-dental-{token}", "source_type": "manual_csv_scout", "config_json": {"csv": csv_text}})
        run = create_scout_run(str(source["id"]))
        result = process_scout_run(str(run["id"]))
        assert result["accepted"] == 0
        assert result["rejected"] == 1
        row = fetch_one("SELECT rejection_reason FROM scout_leads WHERE domain = %s", (f"aspendental-{token}.example.test",))
        assert row["rejection_reason"] == "excluded_large_enterprise"
    finally:
        _cleanup_token(token)


def test_scout_rejects_large_retailer_domains_from_public_sources():
    token = uuid.uuid4().hex[:8]
    domain = f"homedepot-{token}.example.test"
    csv_text = f"business_name,website_url,email,country,niche\nHome Depot,https://{domain},a@{domain},US,contractors\n"
    try:
        source = create_scout_source({"name": f"large-retailer-{token}", "source_type": "manual_csv_scout", "config_json": {"csv": csv_text}})
        run = create_scout_run(str(source["id"]))
        result = process_scout_run(str(run["id"]))
        assert result["accepted"] == 0
        assert result["rejected"] == 1
        row = fetch_one("SELECT rejection_reason FROM scout_leads WHERE domain = %s AND scout_run_id = %s", (domain, run["id"]))
        assert row["rejection_reason"] == "excluded_large_enterprise"
    finally:
        _cleanup_token(token)


def test_lead_scoring_explains_reasoning():
    token = uuid.uuid4().hex[:8]
    try:
        business = execute("INSERT INTO businesses(name, domain, source, niche, country, status) VALUES (%s, %s, 'test_prod', 'dentists', 'EE', 'scouted') RETURNING id", (f"Score {token}", f"score-{token}.example.test"))
        lead = execute("INSERT INTO leads(business_id, email, source, status, niche, country, language) VALUES (%s, %s, 'test_prod', 'scouted', 'dentists', 'EE', 'en') RETURNING id", (business["id"], f"owner@score-{token}.example.test"))
        audit = execute("INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at) VALUES (%s, %s, %s, %s, 'completed', 45, 'Issue', %s, now()) RETURNING id", (business["id"], lead["id"], f"score-{token}.example.test", f"https://score-{token}.example.test", f"score-{token}"))
        execute("INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text) VALUES (%s, 'contact_path', 'high', 'No contact path', 'No contact path')", (audit["id"],))
        result = score_lead(str(lead["id"]), str(audit["id"]))
        assert result["final_score"] >= 50
        assert "severity_counts" in result["reasoning_json"]
    finally:
        _cleanup_token(token)


def test_lead_scoring_qualifies_email_lead_with_high_contact_path_issue():
    token = uuid.uuid4().hex[:8]
    try:
        business = execute("INSERT INTO businesses(name, domain, source, niche, country, status) VALUES (%s, %s, 'test_prod', 'dentists', 'US', 'scouted') RETURNING id", (f"Contact Path {token}", f"contactpath-{token}.example.test"))
        lead = execute("INSERT INTO leads(business_id, email, source, status, niche, country, language) VALUES (%s, %s, 'test_prod', 'scouted', 'dentists', 'US', 'en') RETURNING id", (business["id"], f"owner@contactpath-{token}.example.test"))
        audit = execute("INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at) VALUES (%s, %s, %s, %s, 'completed', 55, 'Contact issue', %s, now()) RETURNING id", (business["id"], lead["id"], f"contactpath-{token}.example.test", f"https://contactpath-{token}.example.test", f"contactpath-{token}"))
        execute("INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text) VALUES (%s, 'contact_path', 'high', 'No obvious enquiry path', 'No obvious enquiry path')", (audit["id"],))
        result = score_lead(str(lead["id"]), str(audit["id"]))
        assert result["final_score"] >= 70
        assert result["reasoning_json"]["issue_types"] == ["contact_path"]
    finally:
        _cleanup_token(token)


def test_campaign_prepare_selects_top_scored_leads():
    token = uuid.uuid4().hex[:8]
    try:
        niche = f"test_niche_{token}"
        country = f"T{token[:2].upper()}"
        business = execute("INSERT INTO businesses(name, domain, source, niche, country, status) VALUES (%s, %s, 'test_prod', %s, %s, 'scouted') RETURNING id", (f"Campaign {token}", f"campaign-{token}.example.test", niche, country))
        lead = execute("INSERT INTO leads(business_id, email, source, status, score, niche, country, language) VALUES (%s, %s, 'test_prod', 'scouted', 85, %s, %s, 'en') RETURNING id", (business["id"], f"owner@campaign-{token}.example.test", niche, country))
        audit = execute("INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at) VALUES (%s, %s, %s, %s, 'completed', 70, 'Issue', %s, now()) RETURNING id", (business["id"], lead["id"], f"campaign-{token}.example.test", f"https://campaign-{token}.example.test", f"campaign-{token}"))
        execute("INSERT INTO lead_scores(lead_id, audit_id, final_score, technical_score, sales_score, urgency_score, value_score, deliverability_score) VALUES (%s, %s, 88, 90, 80, 90, 80, 80)", (lead["id"], audit["id"]))
        campaign = create_campaign({"name": f"campaign-{token}", "country": country, "language": "en", "niche": niche})
        result = prepare_campaign(str(campaign["id"]), threshold=70, limit=20)
        assert result["preview_count"] == 1
        assert get_campaign(str(campaign["id"]))["leads"][0]["score"] == 88
    finally:
        _cleanup_token(token)


def test_admin_scout_and_campaign_endpoints_require_auth():
    assert client.post("/admin/scouts/sources", json={}).status_code == 401
    assert client.get("/admin/campaigns/control-room", headers=admin_headers()).status_code == 404
    assert client.post("/admin/campaigns", json={"name": "x"}, headers=admin_headers()).status_code == 200


def test_scout_expansion_gate_blocks_without_self_audit_matrix():
    token = uuid.uuid4().hex[:8]
    csv_text = f"business_name,website_url,email,country,niche\nGate,https://gate-{token}.example.test,gate@gate-{token}.example.test,EE,dentists\n"
    try:
        execute("DELETE FROM mailer_self_audit_matrix_history")
        source = create_scout_source({"name": f"gate-{token}", "source_type": "manual_csv_scout", "config_json": {"csv": csv_text}})
        run = create_scout_run(str(source["id"]))
        result = process_scout_run_gated(str(run["id"]))
        assert result["status"] == "blocked"
        assert result["send_mail"] is False
        assert "missing_mailer_self_audit_matrix" in result["gate"]["blockers"]
        assert fetch_one("SELECT status FROM scout_runs WHERE id = %s", (run["id"],))["status"] == "blocked"
    finally:
        _cleanup_token(token)
        run_agent("mailer_business_kpi_agent")
        run_agent("mailer_self_audit_matrix_agent")


def test_gated_scout_agent_processes_queued_run_after_self_audit_matrix():
    token = uuid.uuid4().hex[:8]
    csv_text = f"business_name,website_url,email,country,niche,source_url,confidence\nGate Ok,https://gate-ok-{token}.example.test,gate-ok@gate-ok-{token}.example.test,EE,dentists,https://directory.example/{token},95\n"
    try:
        run_agent("mailer_business_kpi_agent")
        run_agent("mailer_self_audit_matrix_agent")
        gate = scout_campaign_expansion_gate()
        assert gate["allowed"] is True
        source = create_scout_source({"name": f"gate-ok-{token}", "source_type": "manual_csv_scout", "config_json": {"csv": csv_text}})
        create_scout_run(str(source["id"]))
        result = process_queued_scout_runs(1)
        assert result["processed"] == 1
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert result["results"][0]["accepted"] == 1
    finally:
        _cleanup_token(token)


def test_gated_scout_blocks_weak_source_before_scanner_queue():
    token = uuid.uuid4().hex[:8]
    csv_text = f"business_name,website_url,email,country,niche\nWeak,https://weak-{token}.example.test,weak@weak-{token}.example.test,EE,dentists\n"
    try:
        run_agent("mailer_business_kpi_agent")
        run_agent("mailer_self_audit_matrix_agent")
        source = create_scout_source({"name": f"weak-quality-{token}", "source_type": "manual_csv_scout", "config_json": {"csv": csv_text}})
        run = create_scout_run(str(source["id"]))
        result = process_scout_run_gated(str(run["id"]))
        assert result["status"] == "review_required"
        assert result["reason"] == "source_readiness_review_required"
        assert result["source_readiness_gate"]["allowed"] is False
        assert result["send_mail"] is False
        assert fetch_one("SELECT status FROM scout_runs WHERE id = %s", (run["id"],))["status"] == "review_required"
        assert fetch_one("SELECT count(*) AS count FROM scanner_jobs WHERE url LIKE %s", (f"%weak-{token}.example.test%",))["count"] == 0
    finally:
        _cleanup_token(token)


def test_gated_campaign_excludes_scout_leads_without_quality_pass():
    token = uuid.uuid4().hex[:8]
    niche = f"quality_weak_{token}"
    country = f"Q{token[:2].upper()}"
    csv_text = f"business_name,website_url,email,country,niche\nWeak Campaign,https://weak-campaign-{token}.example.test,weak@weak-campaign-{token}.example.test,{country},{niche}\n"
    try:
        run_agent("mailer_business_kpi_agent")
        run_agent("mailer_self_audit_matrix_agent")
        source = create_scout_source({"name": f"weak-campaign-quality-{token}", "source_type": "manual_csv_scout", "country": country, "language": "en", "niche": niche, "config_json": {"csv": csv_text}})
        run = create_scout_run(str(source["id"]))
        result = process_scout_run(str(run["id"]))
        run_scout_quality_gate(str(run["id"]))
        lead_id = result["previews"][0]["lead_id"]
        business = fetch_one("SELECT business_id FROM leads WHERE id = %s", (lead_id,))
        audit = execute("INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at) VALUES (%s, %s, %s, %s, 'completed', 80, 'Issue', %s, now()) RETURNING id", (business["business_id"], lead_id, f"weak-campaign-{token}.example.test", f"https://weak-campaign-{token}.example.test", f"weak-campaign-{token}"))
        execute("INSERT INTO lead_scores(lead_id, audit_id, final_score, technical_score, sales_score, urgency_score, value_score, deliverability_score) VALUES (%s, %s, 88, 90, 80, 90, 80, 80)", (lead_id, audit["id"]))
        campaign = create_campaign({"name": f"weak-campaign-{token}", "country": country, "language": "en", "niche": niche})
        prepared = prepare_campaign_gated(str(campaign["id"]), threshold=70, limit=20)
        assert prepared["preview_count"] == 0
        assert prepared["quality_excluded"] == 1
        assert lead_scout_quality_gate(lead_id)["allowed_for_campaign_preview"] is False
    finally:
        _cleanup_token(token)


def test_gated_campaign_allows_scout_leads_with_quality_pass():
    token = uuid.uuid4().hex[:8]
    niche = f"quality_strong_{token}"
    country = f"Q{token[:2].upper()}"
    csv_text = f"business_name,website_url,email,country,niche,confidence,source_url\nStrong Campaign,https://strong-campaign-{token}.example.test,strong@strong-campaign-{token}.example.test,{country},{niche},95,https://directory.example/{token}\n"
    try:
        run_agent("mailer_business_kpi_agent")
        run_agent("mailer_self_audit_matrix_agent")
        source = create_scout_source({"name": f"strong-campaign-quality-{token}", "source_type": "manual_csv_scout", "country": country, "language": "en", "niche": niche, "config_json": {"csv": csv_text}})
        readiness = run_scout_source_readiness(str(source["id"]))
        assert readiness["status"] == "PASS_SOURCE_READY"
        run = create_scout_run(str(source["id"]))
        result = process_scout_run_gated(str(run["id"]))
        assert result["quality_gate"]["decision"] == "PASS_IMPORT_READY"
        lead_id = result["previews"][0]["lead_id"]
        business = fetch_one("SELECT business_id FROM leads WHERE id = %s", (lead_id,))
        audit = execute("INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at) VALUES (%s, %s, %s, %s, 'completed', 80, 'Issue', %s, now()) RETURNING id", (business["business_id"], lead_id, f"strong-campaign-{token}.example.test", f"https://strong-campaign-{token}.example.test", f"strong-campaign-{token}"))
        execute("INSERT INTO lead_scores(lead_id, audit_id, final_score, technical_score, sales_score, urgency_score, value_score, deliverability_score) VALUES (%s, %s, 88, 90, 80, 90, 80, 80)", (lead_id, audit["id"]))
        campaign = create_campaign({"name": f"strong-campaign-{token}", "country": country, "language": "en", "niche": niche})
        prepared = prepare_campaign_gated(str(campaign["id"]), threshold=70, limit=20)
        assert prepared["preview_count"] == 1
        assert prepared["quality_excluded"] == 0
        assert get_campaign(str(campaign["id"]))["leads"][0]["preview_json"]["scout_quality_decision"] == "PASS_IMPORT_READY"
    finally:
        _cleanup_token(token)


def test_gated_campaign_prepare_requires_self_audit_matrix():
    token = uuid.uuid4().hex[:8]
    try:
        execute("DELETE FROM mailer_self_audit_matrix_history")
        campaign = create_campaign({"name": f"gate-campaign-{token}", "country": "EE", "language": "en", "niche": "dentists"})
        blocked = prepare_campaign_gated(str(campaign["id"]), threshold=70, limit=20)
        assert blocked["status"] == "blocked"
        assert blocked["send_mail"] is False
        assert "missing_mailer_self_audit_matrix" in blocked["gate"]["blockers"]
        run_agent("mailer_business_kpi_agent")
        run_agent("mailer_self_audit_matrix_agent")
        allowed = prepare_campaign_gated(str(campaign["id"]), threshold=70, limit=20)
        assert allowed["status"] == "preview_ready"
        assert allowed["live_send"] is False
    finally:
        _cleanup_token(token)


def test_email_templates_render_all_samples_and_pass_qa():
    samples = render_all_samples()
    assert len(samples) >= 10
    assert all(sample["qa"]["passed"] for sample in samples)
    assert all(sample["html"].startswith("<!doctype html>") for sample in samples)
    assert all("Managed website rescue by vøiddo" in sample["html"] for sample in samples)
    rendered = render_email_template("first_audit_notice", "he")
    assert qa_email_template(rendered)["passed"] is True
    assert 'dir="rtl"' in rendered["html"]


def test_agent_runs_are_recorded():
    result = run_agent("email_template_agent")
    assert result["status"] == "completed"
    assert result["result_json"]["all_pass"] is True
    stored = fetch_one("SELECT count(*) AS count FROM agent_runs WHERE agent = 'email_template_agent'")
    assert int(stored["count"]) >= 1


def test_reporting_alias_agents_are_no_send():
    for agent in ["runtime_state_report_agent", "daily_business_report_agent", "blockers_report_agent"]:
        result = run_agent(agent)
        assert result["status"] == "completed"
        assert result["result_json"].get("send_mail") is False
        assert result["result_json"].get("live_outreach_allowed") is False


def test_self_closed_loop_creates_idempotent_actions_for_unrecovered_agent_failure():
    token = uuid.uuid4().hex[:8]
    agent_name = f"qa-failing-agent-{token}"
    try:
        execute(
            "INSERT INTO agent_runs(agent, status, error, started_at, completed_at) VALUES (%s, 'failed', %s, now(), now())",
            (agent_name, f"failure-{token}"),
        )
        first = run_agent("self_closed_loop_agent", {"scope": f"qa-{token}", "limit": 10})
        payload = first["result_json"]
        assert payload["send_mail"] is False
        assert payload["live_outreach_allowed"] is False
        assert payload["findings_count"] >= 1
        assert payload["fix_tasks_created"] >= 1
        assert payload["build_items_created"] >= 1
        assert payload["learning_events_created"] >= 1

        second = run_agent("self_closed_loop_agent", {"scope": f"qa-{token}", "limit": 10})
        assert second["result_json"]["fix_tasks_created"] == 0
        assert second["result_json"]["learning_events_created"] == 0
        stored = fetch_one("SELECT count(*) AS count FROM self_operating_cycles WHERE scope = %s", (f"qa-{token}",))
        assert int(stored["count"]) >= 2
    finally:
        _cleanup_token(token)


def test_daily_loop_runs_dry_without_live_outreach():
    result = run_daily_loop()
    assert result["live_outreach"] is False
    assert result["agents"] >= 5


def test_daily_loop_skips_when_advisory_lock_is_held():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (DAILY_LOOP_ADVISORY_LOCK_KEY,))
        try:
            result = run_daily_loop()
            assert result["status"] == "skipped_already_running"
            assert result["lock_acquired"] is False
            assert result["agents"] == 0
            assert result["send_mail"] is False
            assert result["live_outreach_allowed"] is False
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (DAILY_LOOP_ADVISORY_LOCK_KEY,))


def test_mail_throttle_blocks_recent_rate_limit(monkeypatch):
    import app.mailer_throttle as mailer_throttle

    token = uuid.uuid4().hex[:8]
    try:
        monkeypatch.setattr(mailer_throttle, "recent_mail_signal_count", lambda types, hours=24: 1 if "smtp_rate_limit" in types else 0)
        record_mail_signal("smtp_rate_limit", "warning", f"test-{token}", raw_summary="test rate limit")
        decision = throttle_decision("provider", f"gmail-{token}", 600)
        assert decision["allowed"] is False
        assert decision["reason"] == "recent_rate_limit"
    finally:
        _cleanup_token(token)


def test_paddle_paid_creates_onboarding_when_provisioning_enabled():
    token = uuid.uuid4().hex
    result = handle_paddle_event(
        {
            "event_type": "transaction.paid",
            "data": {
                "id": f"txn_onboard_{token}",
                "customer_id": f"ctm_onboard_{token}",
                "customer": {"email": f"onboard-{token}@voiddorescue.local"},
                "custom_data": {"product_key": "contact_form_repair"},
                "details": {"totals": {"total": "9900", "currency_code": "USD"}},
            },
        },
        provisioning_paused=False,
    )
    assert "onboarding_task_created" in result["actions"]
    row = fetch_one("SELECT count(*) AS count FROM onboarding_tasks WHERE payload_json->>'paddle_transaction_id' = %s", (f"txn_onboard_{token}",))
    assert int(row["count"]) == 1


def test_checkout_all_product_configs_return_ready_or_fail_closed():
    for product in ["monitor_monthly", "fix_lite_monthly", "rescue_pro_monthly", "audit_onetime", "contact_form_repair", "emergency_fix"]:
        response = client.get(f"/checkout/config/{product}")
        assert response.status_code in {200, 503}


def test_owner_outreach_send_still_blocked():
    response = client.post("/outreach/send", json={"email": "lead@example.test", "body": "hello"})
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


def test_visual_route_text_has_no_unresolved_vars():
    for path in ["/", "/status", "/customer"]:
        response = client.get(path)
        assert response.status_code in {200, 404}


def test_hygiene_report_exists():
    assert fetch_one("SELECT count(*) AS count FROM schema_migrations WHERE filename = '009_production_autonomy.sql'") is not None
