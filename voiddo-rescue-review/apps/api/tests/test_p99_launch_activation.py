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
from app.campaign_preflight_status import PREFLIGHT_POLICY_VERSION
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
    import app.launch_activation as activation_module

    class Settings:
        allow_live_outreach_activation = False
        outreach_dry_run = True
        outreach_paused = True
        first_live_send_flag = False
        daily_send_limit = 20
        hourly_domain_send_limit = 5

    activation_module.get_settings.cache_clear()
    original_get_settings = activation_module.get_settings
    activation_module.get_settings = lambda: Settings()
    try:
        result = apply_launch_activation("START LIVE OUTREACH", requested_by="test_p99", dry_run=False)
    finally:
        activation_module.get_settings = original_get_settings
        activation_module.get_settings.cache_clear()
    activation = result["activation"]
    assert activation["decision"] == "BLOCKED"
    assert "allow_live_outreach_activation_env_false" in activation["blockers"]
    assert activation["runtime_change_performed"] is False
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False


def test_launch_activation_apply_clears_outreach_runtime_pause(monkeypatch):
    import app.launch_activation as activation_module

    token = f"p99-{uuid.uuid4()}"
    previous = fetch_one("SELECT value, source, reason FROM runtime_controls WHERE key = 'pause_outreach'")
    execute(
        """
        INSERT INTO runtime_controls(key, value, source, reason)
        VALUES ('pause_outreach', true, %s, 'test setup')
        ON CONFLICT (key) DO UPDATE SET value = excluded.value, source = excluded.source, reason = excluded.reason, updated_at = now()
        """,
        (token,),
    )

    class Settings:
        allow_live_outreach_activation = True
        daily_send_limit = 20
        hourly_domain_send_limit = 5

    readiness = {
        "decision": "READY_FOR_OPERATOR_ENV_ACTIVATION",
        "blockers": [],
        "scoreboard": {"state": "PREVIEW_PIPELINE_READY_NO_OUTREACH", "score": 100, "blocker_count": 0},
        "preview_message_count": 20,
        "approved_preview_count": 20,
        "live_outreach_sent_count": 0,
        "warmup_sent_count": 0,
    }
    monkeypatch.setattr(activation_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(activation_module, "launch_activation_readiness", lambda _limit: readiness)
    try:
        result = apply_launch_activation("START LIVE OUTREACH", requested_by=token, limit=20, dry_run=False)
        control = fetch_one("SELECT value, source FROM runtime_controls WHERE key = 'pause_outreach'")
    finally:
        execute("DELETE FROM launch_activation_runs WHERE requested_by = %s", (token,))
        if previous:
            execute(
                """
                INSERT INTO runtime_controls(key, value, source, reason)
                VALUES ('pause_outreach', %s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET value = excluded.value, source = excluded.source, reason = excluded.reason, updated_at = now()
                """,
                (previous["value"], previous["source"], previous["reason"]),
            )
        else:
            execute("DELETE FROM runtime_controls WHERE key = 'pause_outreach'")
    activation = result["activation"]
    assert activation["decision"] == "READY_RECORDED_NO_ENV_CHANGE"
    assert activation["runtime_change_performed"] is True
    assert control["value"] is False
    assert control["source"] == "launch_activation"
    assert result["send_mail"] is False


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


def test_live_outreach_stage_assigns_24_minute_due_spacing(monkeypatch):
    import app.outreach_live_queue as queue_module

    class Settings:
        daily_send_limit = 20
        outreach_dry_run = False
        outreach_paused = False
        first_live_send_flag = True
        allow_live_outreach_activation = True

    updates: list[tuple[int, str]] = []
    monkeypatch.setattr(queue_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(queue_module, "launch_activation_readiness", lambda _limit: {"decision": "READY_FOR_OPERATOR_ENV_ACTIVATION"})
    monkeypatch.setattr(queue_module, "launch_readiness_scoreboard", lambda _limit: {"state": "LIVE_OUTREACH_READY", "score": 100, "blocker_count": 0})
    monkeypatch.setattr(queue_module, "live_outreach_quota_status", lambda: {"allowed": True, "blockers": []})
    monkeypatch.setattr(
        queue_module,
        "_candidate_rows",
        lambda _limit: [
            {"outreach_message_id": "00000000-0000-0000-0000-000000000001", "campaign_id": "c1", "domain": "one.example", "public_slug": "one", "recipient_domain": "one.example"},
            {"outreach_message_id": "00000000-0000-0000-0000-000000000002", "campaign_id": "c1", "domain": "two.example", "public_slug": "two", "recipient_domain": "two.example"},
            {"outreach_message_id": "00000000-0000-0000-0000-000000000003", "campaign_id": "c1", "domain": "three.example", "public_slug": "three", "recipient_domain": "three.example"},
        ],
    )

    def fake_execute(sql, params=()):
        if "send_after = now()" in sql:
            updates.append((params[0], params[1]))
            return None
        return {"id": "run-id", "status": "queued", "decision": "STAGED_FOR_WORKER", "requested_by": "test", "dry_run": False, "requested_limit": 3, "candidate_count": 3, "staged_count": 3, "sent_count": 0, "blocked_count": 0, "created_at": "now"}

    monkeypatch.setattr(queue_module, "execute", fake_execute)
    result = queue_module.stage_live_outreach_batch(3, dry_run=False, requested_by="test")
    assert result["result"]["decision"] == "STAGED_FOR_WORKER"
    assert result["result"]["send_spacing_minutes"] == 24
    assert [minute for minute, _message_id in updates] == [0, 24, 48]


def test_live_outreach_stage_allows_runtime_live_ready_state(monkeypatch):
    import app.outreach_live_queue as queue_module

    class Settings:
        daily_send_limit = 20
        outreach_dry_run = False
        outreach_paused = False
        first_live_send_flag = True
        allow_live_outreach_activation = True

    updates: list[tuple[int, str]] = []
    monkeypatch.setattr(queue_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(queue_module, "launch_activation_readiness", lambda _limit: {"decision": "BLOCKED", "blockers": ["runtime_live_flags_not_locked_before_activation"]})
    monkeypatch.setattr(queue_module, "launch_readiness_scoreboard", lambda _limit: {"state": "LIVE_OUTREACH_READY", "score": 100, "blocker_count": 0})
    monkeypatch.setattr(queue_module, "live_outreach_quota_status", lambda: {"allowed": True, "blockers": []})
    monkeypatch.setattr(
        queue_module,
        "_candidate_rows",
        lambda _limit: [
            {"outreach_message_id": "00000000-0000-0000-0000-000000000011", "campaign_id": "c1", "domain": "one.example", "public_slug": "one", "recipient_domain": "one.example"},
        ],
    )

    def fake_execute(sql, params=()):
        if "send_after = now()" in sql:
            updates.append((params[0], params[1]))
            return None
        return {"id": "run-id", "status": "queued", "decision": "STAGED_FOR_WORKER", "requested_by": "test", "dry_run": False, "requested_limit": 1, "candidate_count": 1, "staged_count": 1, "sent_count": 0, "blocked_count": 0, "created_at": "now"}

    monkeypatch.setattr(queue_module, "execute", fake_execute)
    result = queue_module.stage_live_outreach_batch(1, dry_run=False, requested_by="test")
    assert result["result"]["decision"] == "STAGED_FOR_WORKER"
    assert result["result"]["runtime_activation_ready"] is True
    assert result["result"]["runtime_launch_state"] == "LIVE_OUTREACH_READY"
    assert updates == [(0, "00000000-0000-0000-0000-000000000011")]


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
            (campaign["id"], Jsonb({"token": token, "decision": "PASS_NO_SEND_PREFLIGHT", "policy_version": PREFLIGHT_POLICY_VERSION})),
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
            (campaign["id"], Jsonb({"token": token, "decision": "PASS_NO_SEND_PREFLIGHT", "policy_version": PREFLIGHT_POLICY_VERSION})),
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
            (campaign["id"], Jsonb({"token": token, "decision": "PASS_NO_SEND_PREFLIGHT", "policy_version": PREFLIGHT_POLICY_VERSION})),
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


def test_live_queue_and_canary_quality_block_stale_preflight_policy():
    token = uuid.uuid4().hex[:8]
    try:
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
            VALUES (%s, 'US', 'Control', 'en', 'dentists', 'p99', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"P99 Stale Policy {token}", f"https://p99-stale-policy-{token}.com", f"p99-stale-policy-{token}.com", f"owner@p99-stale-policy-{token}.com"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
            VALUES (%s, %s, 'p99', 'qualified', 88, 'en', 'US', 'Control', 'dentists')
            RETURNING id
            """,
            (business["id"], f"owner@p99-stale-policy-{token}.com"),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 90, 'P99 stale policy audit', %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], f"p99-stale-policy-{token}.com", f"https://p99-stale-policy-{token}.com", f"p99-stale-policy-{token}"),
        )
        campaign = execute(
            """
            INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
            VALUES (%s, 'preview_ready', 'US', 'en', 'dentists', 'contact_form_repair', true)
            RETURNING id
            """,
            (f"p99-stale-policy-{token}",),
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
            "INSERT INTO audit_strength_scores(audit_id, final_score, proof_score, commercial_score, completeness_score, issues_json) VALUES (%s, 82, 84, 82, 80, '[]'::jsonb)",
            (audit["id"],),
        )
        execute("INSERT INTO campaign_preview_reviews(campaign_lead_id, action, reason, actor) VALUES (%s, 'approved', 'stale policy fixture', 'test')", (preview["id"],))
        execute(
            """
            INSERT INTO campaign_preflight_runs(campaign_id, status, decision, checked_count, ready_count, blocker_count, result_json)
            VALUES (%s, 'completed', 'PASS_NO_SEND_PREFLIGHT', 1, 1, 0, %s)
            """,
            (campaign["id"], Jsonb({"token": token, "decision": "PASS_NO_SEND_PREFLIGHT", "policy_version": "legacy_before_mx_bounce_gate"})),
        )
        execute(
            """
            INSERT INTO outreach_messages(lead_id, audit_id, mailbox, subject, body, html_body, status)
            VALUES (%s, %s, 'audit@voiddorescue.com', %s, %s, %s, 'preview')
            """,
            (
                lead["id"],
                audit["id"],
                f"p99 stale policy {token}",
                f"Public non-invasive website check.\nUnsubscribe: https://go.rescue.voiddo.com/unsubscribe/u_00000000-0000-0000-0000-000000000000.{token}",
                "<!doctype html><html><body>Vøiddo Rescue</body></html>",
            ),
        )
        queue = live_outreach_queue_candidates(100)
        assert f"p99-stale-policy-{token}.com" not in str(queue)
        quality = canary_batch_quality(100, store=False)
        row = [item for item in quality["items"] if item["domain"] == f"p99-stale-policy-{token}.com"][0]
        assert "campaign_preflight_policy_stale" in row["blockers"]
        assert quality["send_mail"] is False
    finally:
        _cleanup(token)


def test_canary_and_live_queue_skip_large_or_sensitive_first_batch_targets():
    token = uuid.uuid4().hex[:8]
    try:
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
            VALUES (%s, 'US', 'Control', 'en', 'local tourism', 'p99', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"Red Roof Control {token}", "https://www.redroof.com", "www.redroof.com", f"owner@redroof-{token}.example.com"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
            VALUES (%s, %s, 'p99', 'qualified', 92, 'en', 'US', 'Control', 'local tourism')
            RETURNING id
            """,
            (business["id"], f"owner@redroof-{token}.example.com"),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, 'www.redroof.com', 'https://www.redroof.com', 'completed', 90, 'P99 redroof audit', %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], f"p99-redroof-{token}"),
        )
        campaign = execute(
            """
            INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
            VALUES (%s, 'preview_ready', 'US', 'en', 'local tourism', 'contact_form_repair', true)
            RETURNING id
            """,
            (f"p99-redroof-{token}",),
        )
        preview = execute(
            """
            INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json)
            VALUES (%s, %s, %s, 'preview', 92, %s)
            RETURNING id
            """,
            (campaign["id"], lead["id"], audit["id"], Jsonb({"token": token})),
        )
        execute(
            "INSERT INTO audit_strength_scores(audit_id, final_score, proof_score, commercial_score, completeness_score, issues_json) VALUES (%s, 88, 90, 88, 84, '[]'::jsonb)",
            (audit["id"],),
        )
        execute("INSERT INTO campaign_preview_reviews(campaign_lead_id, action, reason, actor) VALUES (%s, 'approved', 'p99 redroof proof', 'test')", (preview["id"],))
        execute(
            """
            INSERT INTO campaign_preflight_runs(campaign_id, status, decision, checked_count, ready_count, blocker_count, result_json)
            VALUES (%s, 'completed', 'PASS_NO_SEND_PREFLIGHT', 1, 1, 0, %s)
            """,
            (campaign["id"], Jsonb({"token": token, "decision": "PASS_NO_SEND_PREFLIGHT", "policy_version": PREFLIGHT_POLICY_VERSION})),
        )
        execute(
            """
            INSERT INTO outreach_messages(lead_id, audit_id, mailbox, subject, body, html_body, status)
            VALUES (%s, %s, 'audit@voiddorescue.com', %s, %s, %s, 'preview')
            """,
            (
                lead["id"],
                audit["id"],
                f"p99 redroof {token}",
                f"Public non-invasive website check.\nUnsubscribe: https://go.rescue.voiddo.com/unsubscribe/u_00000000-0000-0000-0000-000000000000.{token}",
                "<!doctype html><html><body>Vøiddo Rescue</body></html>",
            ),
        )
        assert "redroof.com" not in str(live_outreach_queue_candidates(100))
        result = canary_batch_quality(100, store=False)
        assert "redroof.com" not in str(result)
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
