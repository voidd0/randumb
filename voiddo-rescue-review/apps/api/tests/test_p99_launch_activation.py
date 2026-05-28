from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.db import execute, fetch_one
from app.launch_activation import apply_launch_activation, launch_activation_readiness, prepare_launch_activation
from app.main import app
from app.outreach_live_queue import live_outreach_queue_candidates, stage_live_outreach_batch
from app.p0 import transport_gate_status


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM launch_activation_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
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
