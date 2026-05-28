from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db import execute, fetch_one
from app.launch_activation import apply_launch_activation, launch_activation_readiness, prepare_launch_activation
from app.main import app
from app.outreach_live_queue import live_outreach_queue_candidates, stage_live_outreach_batch
from app.canary_batch_quality import canary_batch_quality
from app.canary_checkout_simulation import run_canary_checkout_simulation
from app.p0 import transport_gate_status


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM launch_activation_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent = 'canary_batch_quality_agent' AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent = 'canary_checkout_simulation_agent' AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM outreach_messages WHERE subject LIKE %s OR body LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaign_preflight_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_preview_reviews WHERE campaign_lead_id IN (SELECT id FROM campaign_leads WHERE preview_json::text LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaign_leads WHERE preview_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s", (f"%{token}%",))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s", (f"%{token}%",))


def test_launch_activation_endpoint_requires_admin_and_stays_no_send():
    assert client.get("/admin/launch-activation").status_code == 401
    response = client.get("/admin/launch-activation", headers=admin_headers())
    assert response.status_code == 200
    payload = response.json()["activation"]
    assert payload["send_mail"] is False
    assert payload["live_outreach_allowed"] is False
    assert "activation_env_required" in payload


def test_launch_activation_prepare_records_no_send_run():
    result = prepare_launch_activation(5, requested_by="test_p99")
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    run_id = result["run"]["id"]
    row = fetch_one("SELECT send_mail, smtp_called, live_outreach_allowed FROM launch_activation_runs WHERE id = %s", (run_id,))
    assert row["send_mail"] is False
    assert row["smtp_called"] is False
    assert row["live_outreach_allowed"] is False


def test_launch_activation_apply_is_blocked_without_runtime_activation_flag():
    result = apply_launch_activation("START LIVE OUTREACH", requested_by="test_p99", dry_run=False)
    activation = result["activation"]
    assert activation["decision"] == "BLOCKED"
    assert "allow_live_outreach_activation_env_false" in activation["blockers"]
    assert activation["runtime_change_performed"] is False
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False


def test_live_outreach_queue_stage_dry_run_never_changes_preview_status():
    before_preview = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'preview'")
    result = stage_live_outreach_batch(5, dry_run=True, requested_by="test_p99")
    after_preview = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'preview'")
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert result["result"]["decision"] == "BLOCKED"
    assert "dry_run_no_messages_staged" in result["result"]["blockers"]
    assert result["result"]["staged_count"] == 0
    assert after_preview["count"] == before_preview["count"]


def test_live_outreach_queue_candidates_are_redacted():
    result = live_outreach_queue_candidates(5)
    assert result["send_mail"] is False
    assert result["raw_recipient_addresses_included"] is False
    assert "@" not in str(result)
    for item in result["candidates"]:
        assert item["recipient_domain_hash"]


def test_canary_batch_quality_passes_redacted_single_candidate():
    token = uuid.uuid4().hex[:8]
    try:
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
            VALUES (%s, 'US', 'Control', 'en', 'dentists', 'p99', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"P99 Canary {token}", f"https://p99-canary-{token}.com", f"p99-canary-{token}.com", f"owner@p99-canary-{token}.com"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
            VALUES (%s, %s, 'p99', 'qualified', 88, 'en', 'US', 'Control', 'dentists')
            RETURNING id
            """,
            (business["id"], f"owner@p99-canary-{token}.com"),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 90, 'P99 canary audit', %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], f"p99-canary-{token}.com", f"https://p99-canary-{token}.com", f"p99-canary-{token}"),
        )
        campaign = execute(
            """
            INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
            VALUES (%s, 'preview_ready', 'US', 'en', 'dentists', 'contact_form_repair', true)
            RETURNING id
            """,
            (f"p99-canary-{token}",),
        )
        preview = execute(
            """
            INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json)
            VALUES (%s, %s, %s, 'preview', 88, %s)
            RETURNING id
            """,
            (campaign["id"], lead["id"], audit["id"], Jsonb({"token": token})),
        )
        execute(
            "INSERT INTO audit_strength_scores(audit_id, final_score, proof_score, commercial_score, completeness_score, issues_json) VALUES (%s, 78, 80, 80, 74, '[]'::jsonb)",
            (audit["id"],),
        )
        execute(
            "INSERT INTO campaign_preview_reviews(campaign_lead_id, action, reason, actor) VALUES (%s, 'approved', 'p99 canary proof', 'test')",
            (preview["id"],),
        )
        execute(
            """
            INSERT INTO campaign_preflight_runs(campaign_id, status, decision, checked_count, ready_count, blocker_count, result_json)
            VALUES (%s, 'completed', 'PASS_NO_SEND_PREFLIGHT', 1, 1, 0, %s)
            """,
            (campaign["id"], Jsonb({"token": token, "decision": "PASS_NO_SEND_PREFLIGHT"})),
        )
        execute(
            """
            INSERT INTO outreach_messages(lead_id, audit_id, mailbox, subject, body, html_body, status)
            VALUES (%s, %s, 'audit@voiddorescue.com', %s, %s, %s, 'preview')
            """,
            (
                lead["id"],
                audit["id"],
                f"p99 canary {token}",
                f"Public non-invasive website check.\nUnsubscribe: https://go.rescue.voiddo.com/unsubscribe/u_00000000-0000-0000-0000-000000000000.{token}",
                "<!doctype html><html><body>Vøiddo Rescue</body></html>",
            ),
        )
        result = canary_batch_quality(1, store=True)
        assert result["decision"] == "PASS_CANARY_BATCH_QUALITY"
        assert result["candidate_count"] == 1
        assert result["economics"]["decision"] == "pass"
        assert result["economics"]["average_gross_margin_percent"] >= 70
        assert result["economics"]["offer_mix"][0]["offer_key"] == "contact_form_repair"
        assert result["items"][0]["domain"] == f"p99-canary-{token}.com"
        assert result["send_mail"] is False
        assert result["raw_recipient_addresses_included"] is False
        assert f"owner@p99-canary-{token}.com" not in str(result)
        row = fetch_one("SELECT status FROM agent_runs WHERE agent = 'canary_batch_quality_agent' AND result_json::text LIKE %s ORDER BY created_at DESC LIMIT 1", (f"%{token}%",))
        assert row["status"] == "completed"
    finally:
        _cleanup(token)


def test_canary_batch_quality_blocks_domain_country_mismatch():
    token = uuid.uuid4().hex[:8]
    try:
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
            VALUES (%s, 'US', 'Control', 'en', 'dentists', 'p99', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"P99 Mismatch {token}", f"https://p99-mismatch-{token}.ca", f"p99-mismatch-{token}.ca", f"owner@p99-mismatch-{token}.ca"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
            VALUES (%s, %s, 'p99', 'qualified', 88, 'en', 'US', 'Control', 'dentists')
            RETURNING id
            """,
            (business["id"], f"owner@p99-mismatch-{token}.ca"),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 90, 'P99 mismatch audit', %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], f"p99-mismatch-{token}.ca", f"https://p99-mismatch-{token}.ca", f"p99-mismatch-{token}"),
        )
        campaign = execute(
            """
            INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
            VALUES (%s, 'preview_ready', 'US', 'en', 'dentists', 'contact_form_repair', true)
            RETURNING id
            """,
            (f"p99-mismatch-{token}",),
        )
        preview = execute(
            """
            INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json)
            VALUES (%s, %s, %s, 'preview', 88, %s)
            RETURNING id
            """,
            (campaign["id"], lead["id"], audit["id"], Jsonb({"token": token})),
        )
        execute(
            "INSERT INTO audit_strength_scores(audit_id, final_score, proof_score, commercial_score, completeness_score, issues_json) VALUES (%s, 78, 80, 80, 74, '[]'::jsonb)",
            (audit["id"],),
        )
        execute("INSERT INTO campaign_preview_reviews(campaign_lead_id, action, reason, actor) VALUES (%s, 'approved', 'p99 mismatch proof', 'test')", (preview["id"],))
        execute(
            """
            INSERT INTO campaign_preflight_runs(campaign_id, status, decision, checked_count, ready_count, blocker_count, result_json)
            VALUES (%s, 'completed', 'PASS_NO_SEND_PREFLIGHT', 1, 1, 0, %s)
            """,
            (campaign["id"], Jsonb({"token": token, "decision": "PASS_NO_SEND_PREFLIGHT"})),
        )
        execute(
            """
            INSERT INTO outreach_messages(lead_id, audit_id, mailbox, subject, body, html_body, status)
            VALUES (%s, %s, 'audit@voiddorescue.com', %s, %s, %s, 'preview')
            """,
            (
                lead["id"],
                audit["id"],
                f"p99 mismatch {token}",
                f"Public non-invasive website check.\nUnsubscribe: https://go.rescue.voiddo.com/unsubscribe/u_00000000-0000-0000-0000-000000000000.{token}",
                "<!doctype html><html><body>Vøiddo Rescue</body></html>",
            ),
        )
        result = canary_batch_quality(1, store=False)
        assert result["decision"] == "FAIL_CANARY_BATCH_QUALITY"
        assert "domain_country_mismatch" in result["blockers"]
        assert result["items"][0]["inferred_country"] == "CA"
        assert result["send_mail"] is False
    finally:
        _cleanup(token)


def test_live_outreach_queue_uses_latest_preview_review_only():
    token = uuid.uuid4().hex[:8]
    try:
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
            VALUES (%s, 'US', 'Control', 'en', 'dentists', 'p99', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"P99 Held {token}", f"https://p99-held-{token}.com", f"p99-held-{token}.com", f"owner@p99-held-{token}.com"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
            VALUES (%s, %s, 'p99', 'qualified', 88, 'en', 'US', 'Control', 'dentists')
            RETURNING id
            """,
            (business["id"], f"owner@p99-held-{token}.com"),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 90, 'P99 held audit', %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], f"p99-held-{token}.com", f"https://p99-held-{token}.com", f"p99-held-{token}"),
        )
        campaign = execute(
            """
            INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
            VALUES (%s, 'preview_ready', 'US', 'en', 'dentists', 'contact_form_repair', true)
            RETURNING id
            """,
            (f"p99-held-{token}",),
        )
        preview = execute(
            """
            INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json)
            VALUES (%s, %s, %s, 'preview', 88, %s)
            RETURNING id
            """,
            (campaign["id"], lead["id"], audit["id"], Jsonb({"token": token})),
        )
        execute("INSERT INTO campaign_preview_reviews(campaign_lead_id, action, reason, actor) VALUES (%s, 'approved', 'first pass', 'test')", (preview["id"],))
        execute("INSERT INTO campaign_preview_reviews(campaign_lead_id, action, reason, actor) VALUES (%s, 'held', 'latest hold', 'test')", (preview["id"],))
        execute(
            """
            INSERT INTO campaign_preflight_runs(campaign_id, status, decision, checked_count, ready_count, blocker_count, result_json)
            VALUES (%s, 'completed', 'PASS_NO_SEND_PREFLIGHT', 1, 1, 0, %s)
            """,
            (campaign["id"], Jsonb({"token": token, "decision": "PASS_NO_SEND_PREFLIGHT"})),
        )
        execute(
            """
            INSERT INTO outreach_messages(lead_id, audit_id, mailbox, subject, body, html_body, status)
            VALUES (%s, %s, 'audit@voiddorescue.com', %s, %s, %s, 'preview')
            """,
            (
                lead["id"],
                audit["id"],
                f"p99 held {token}",
                f"Public non-invasive website check.\nUnsubscribe: https://go.rescue.voiddo.com/unsubscribe/u_00000000-0000-0000-0000-000000000000.{token}",
                "<!doctype html><html><body>Vøiddo Rescue</body></html>",
            ),
        )
        result = live_outreach_queue_candidates(100)
        assert f"p99-held-{token}.com" not in str(result)
        assert result["send_mail"] is False
    finally:
        _cleanup(token)


def test_transport_gate_exposes_live_quota_and_blocks_daily_cap():
    token = uuid.uuid4().hex[:8]
    try:
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
            VALUES (%s, 'US', 'Control', 'en', 'dentists', 'p99', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"P99 {token}", f"https://p99-{token}.com", f"p99-{token}.com", f"owner@p99-{token}.com"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
            VALUES (%s, %s, 'p99', 'qualified', 90, 'en', 'US', 'Control', 'dentists')
            RETURNING id
            """,
            (business["id"], f"owner@p99-{token}.com"),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 90, 'P99 quota audit', %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], f"p99-{token}.com", f"https://p99-{token}.com", f"p99-{token}"),
        )
        for index in range(20):
            execute(
                """
                INSERT INTO outreach_messages(lead_id, audit_id, mailbox, subject, body, html_body, status, sent_at)
                VALUES (%s, %s, 'audit@voiddorescue.com', %s, 'sent', '<!doctype html><html></html>', 'sent', now())
                """,
                (lead["id"], audit["id"], f"p99 sent {token} {index}"),
            )
        gate = transport_gate_status(
            {
                "email": f"next@p99-{token}.com",
                "body": "Public non-invasive website check.\nUnsubscribe: https://go.rescue.voiddo.com/unsubscribe/u_00000000-0000-0000-0000-000000000000.sample",
                "html_body": "<!doctype html><html></html>",
            }
        )
        assert gate["checks"]["live_quota"]["daily_sent"] >= 1
        assert "daily_send_limit_reached" in gate["checks"]["live_quota"]["blockers"]
        assert gate["checks"]["live_quota"]["raw_recipient_addresses_included"] is False
    finally:
        _cleanup(token)


def test_canary_checkout_simulation_blocks_when_no_candidate(monkeypatch):
    import app.canary_checkout_simulation as simulation

    monkeypatch.setattr(simulation, "canary_batch_quality", lambda limit, store=False: {"items": [], "send_mail": False, "live_outreach_allowed": False})
    result = run_canary_checkout_simulation(cleanup_after=True)
    assert result["decision"] == "NO_CANARY_CANDIDATE"
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
