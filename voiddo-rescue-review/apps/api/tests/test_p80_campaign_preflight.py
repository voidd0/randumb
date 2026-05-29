from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
import pytest
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.campaign_preflight import campaign_preflight_batch, campaign_preflight_orphan_hygiene, latest_campaign_preflight_runs
from app.campaign_preflight_status import PREFLIGHT_POLICY_VERSION, latest_campaign_preflight_status
from app.campaign_preview_reviews import review_campaign_preview
from app.db import execute, fetch_one
from app.lead_scoring import score_lead
from app.main import app
from app.scouts import create_campaign, prepare_campaign


client = TestClient(app)


@pytest.fixture(autouse=True)
def _mx_gate_pass(monkeypatch):
    import app.campaign_preview_quality as quality_module

    monkeypatch.setattr(
        quality_module,
        "_email_domain_delivery_status",
        lambda _email: {"status": "pass", "reason": "mx_found", "domain_hash": "hash", "mx_count": 1},
    )


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM campaign_preflight_runs WHERE result_json::text LIKE %s OR campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM outbound_mailer_decisions WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM public_language_gate_runs WHERE scope = 'campaign_preview_quality' AND issues_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent = 'campaign_preflight_agent' AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_preview_reviews WHERE campaign_lead_id IN (SELECT id FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s) OR preview_json::text LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s) OR preview_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM audit_strength_scores WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))


def _campaign(token: str, weak: bool = False) -> str:
    domain = f"p80-{token}.clinic"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, 'QA', 'Preflight City', 'en', 'dentists', 'p80_test', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P80 Clinic {token}", f"https://{domain}", domain, f"owner-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p80_test', 'scouted', 91, 'en', 'QA', 'Preflight City', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}"),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 68, 'Contact path and mobile CTA may be weak.', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"p80-{token}"),
    )
    issue_count = 1 if weak else 3
    for _ in range(issue_count):
        execute(
            """
            INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
            VALUES (%s, 'contact_path', 'high', 'Contact path may be weak', 'Visible from a public browser session.', 'Review the public enquiry path.')
            """,
            (audit["id"],),
        )
    if not weak:
        execute(
            """
            INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport)
            VALUES (%s, 'desktop', %s, %s, 'desktop')
            """,
            (audit["id"], f"/app/storage/screenshots/p80-{token}.png", f"/media/screenshots/p80-{token}.png"),
        )
    score_lead(str(lead["id"]), str(audit["id"]))
    execute("UPDATE leads SET score = 91 WHERE id = %s", (lead["id"],))
    execute("UPDATE lead_scores SET final_score = 91 WHERE lead_id = %s AND audit_id = %s", (lead["id"], audit["id"]))
    campaign = create_campaign({"name": f"p80-campaign-{token}", "country": "QA", "language": "en", "niche": "dentists", "offer_key": "contact_form_repair"})
    preview = prepare_campaign(str(campaign["id"]), 70, 5)
    assert preview["preview_count"] == 1
    preview_row = fetch_one("SELECT id FROM campaign_leads WHERE campaign_id = %s LIMIT 1", (campaign["id"],))
    review_campaign_preview(str(preview_row["id"]), "approved", "QA80 approved preview")
    return str(campaign["id"])


def _policy_pass() -> dict:
    return {"score": 100, "decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "send_mail": False, "smtp_called": False, "live_outreach_allowed": False}


def _transport_preview_ready() -> dict:
    return {
        "allowed": False,
        "reason": "outreach_dry_run_enabled",
        "source": "test_campaign_preview_outreach_message",
        "checks": {"unsubscribe_one_click_ready": True, "html_body_ready": True, "has_unsubscribe": True},
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
    }


def test_campaign_preflight_passes_quality_and_policy_without_send(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        monkeypatch.setattr(preflight, "campaign_preview_transport_gate_status", lambda campaign_id: _transport_preview_ready())
        result = campaign_preflight_batch(5, campaign_id)
        assert result["campaign_count"] == 1
        assert result["passed_count"] == 1
        run = result["runs"][0]
        assert run["decision"] == "PASS_NO_SEND_PREFLIGHT"
        assert run["policy_version"] == PREFLIGHT_POLICY_VERSION
        assert run["send_mail"] is False
        assert run["smtp_called"] is False
        assert run["live_outreach_allowed"] is False
        assert f"owner-{token}@" not in str(result)
        assert latest_campaign_preflight_runs(5)["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_status_blocks_stale_policy_even_when_time_fresh():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        row = execute(
            """
            INSERT INTO campaign_preflight_runs(
              campaign_id, status, decision, checked_count, ready_count, blocker_count, result_json,
              send_mail, smtp_called, live_outreach_allowed, raw_recipient_addresses_included, secrets_included
            )
            VALUES (%s, 'completed', 'PASS_NO_SEND_PREFLIGHT', 1, 1, 0, %s, false, false, false, false, false)
            RETURNING id
            """,
            (
                campaign_id,
                Jsonb({"token": token, "policy_version": "legacy_before_mx_bounce_gate"}),
            ),
        )
        status = latest_campaign_preflight_status(campaign_id)
        assert status["id"] == str(row["id"])
        assert status["fresh"] is True
        assert status["policy_current"] is False
        assert status["allowed"] is False
        assert status["reason"] == "campaign_preflight_policy_stale"
        assert status["required_policy_version"] == PREFLIGHT_POLICY_VERSION
    finally:
        _cleanup(token)


def test_campaign_preflight_repairs_safe_mailer_queue_before_policy_block(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    calls = {"policy": 0, "process": 0, "trend": 0}

    def _policy_then_pass() -> dict:
        calls["policy"] += 1
        if calls["policy"] == 1:
            return {
                "score": 45,
                "decision": "NO_SEND_BLOCKED_REPAIR",
                "blockers": ["current_mailer_action_queue_not_empty"],
                "queue_hygiene": {"mailer_action_queue_rows": 2},
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
            }
        return _policy_pass()

    try:
        campaign_id = _campaign(token)
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_then_pass)
        monkeypatch.setattr(preflight, "campaign_preview_transport_gate_status", lambda campaign_id: _transport_preview_ready())
        monkeypatch.setattr(preflight, "process_mailer_action_queue", lambda limit=10: calls.update(process=calls["process"] + 1) or {"processed_count": limit, "send_mail": False, "live_outreach_allowed": False})
        monkeypatch.setattr(preflight, "mailer_digest_trend_guard", lambda: calls.update(trend=calls["trend"] + 1) or {"decision": "PASS_NO_SEND", "send_mail": False, "live_outreach_allowed": False})
        monkeypatch.setattr(preflight, "_record_inline_trend_guard", lambda trend: None)
        result = campaign_preflight_batch(5, campaign_id)
        run = result["runs"][0]
        assert result["passed_count"] == 1
        assert run["decision"] == "PASS_NO_SEND_PREFLIGHT"
        assert run["mailer_policy_repair"]["processed_count"] == 2
        assert calls == {"policy": 2, "process": 1, "trend": 1}
        assert run["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_refreshes_stale_trend_guard_without_queue(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    calls = {"policy": 0, "trend": 0}

    def _stale_trend_then_pass() -> dict:
        calls["policy"] += 1
        if calls["policy"] == 1:
            return {
                "score": 65,
                "decision": "NO_SEND_BLOCKED_REPAIR",
                "blockers": ["trend_guard_not_pass"],
                "queue_hygiene": {"mailer_action_queue_rows": 0},
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
            }
        return _policy_pass()

    try:
        campaign_id = _campaign(token)
        monkeypatch.setattr(preflight, "mailer_policy_score", _stale_trend_then_pass)
        monkeypatch.setattr(preflight, "campaign_preview_transport_gate_status", lambda campaign_id: _transport_preview_ready())
        monkeypatch.setattr(preflight, "mailer_digest_trend_guard", lambda: calls.update(trend=calls["trend"] + 1) or {"decision": "PASS_NO_SEND", "send_mail": False, "live_outreach_allowed": False})
        monkeypatch.setattr(preflight, "_record_inline_trend_guard", lambda trend: None)
        result = campaign_preflight_batch(5, campaign_id)
        run = result["runs"][0]
        assert result["passed_count"] == 1
        assert run["mailer_policy_repair"]["processed_count"] == 0
        assert calls == {"policy": 2, "trend": 1}
    finally:
        _cleanup(token)


def test_campaign_preflight_blocks_weak_preview(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token, weak=True)
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        monkeypatch.setattr(preflight, "campaign_preview_transport_gate_status", lambda campaign_id: _transport_preview_ready())
        result = campaign_preflight_batch(5, campaign_id)
        assert result["failed_count"] == 1
        assert "preview_quality_not_pass" in result["runs"][0]["blockers"]
        assert result["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_blocks_missing_real_outreach_preview(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        result = campaign_preflight_batch(5, campaign_id)
        run = result["runs"][0]
        assert result["failed_count"] == 1
        assert run["transport_reason"] == "outreach_preview_message_missing"
        assert "transport_unsubscribe_not_ready" in run["blockers"]
        assert "transport_html_not_ready" in run["blockers"]
        assert run["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_blocks_held_preview_review(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        preview = fetch_one("SELECT id FROM campaign_leads WHERE campaign_id = %s LIMIT 1", (campaign_id,))
        review_campaign_preview(str(preview["id"]), "held", "needs stronger proof")
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        monkeypatch.setattr(preflight, "campaign_preview_transport_gate_status", lambda campaign_id: _transport_preview_ready())
        result = campaign_preflight_batch(5, campaign_id)
        assert result["failed_count"] == 1
        assert "preview_rows_held_for_review" in result["runs"][0]["blockers"]
        assert result["runs"][0]["preview_review_summary"]["held_count"] == 1
        assert result["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_batch_skips_held_only_campaigns(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        preview = fetch_one("SELECT id FROM campaign_leads WHERE campaign_id = %s LIMIT 1", (campaign_id,))
        review_campaign_preview(str(preview["id"]), "held", "not enough public proof")
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        monkeypatch.setattr(preflight, "campaign_preview_transport_gate_status", lambda campaign_id: _transport_preview_ready())
        batch = campaign_preflight_batch(50)
        assert all(run["campaign_id"] != campaign_id for run in batch["runs"])
        explicit = campaign_preflight_batch(5, campaign_id)
        assert explicit["failed_count"] == 1
        assert explicit["runs"][0]["preview_review_summary"]["held_count"] == 1
        assert explicit["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_excludes_held_rows_when_usable_rows_exist(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        weak_domain = f"p80-held-{token}.clinic"
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
            VALUES (%s, 'QA', 'Preflight City', 'en', 'dentists', 'p80_test', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"P80 Held Clinic {token}", f"https://{weak_domain}", weak_domain, f"held-{token}@{weak_domain}"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
            VALUES (%s, %s, 'p80_test', 'scouted', 91, 'en', 'QA', 'Preflight City', 'dentists')
            RETURNING id
            """,
            (business["id"], f"held-{token}@{weak_domain}"),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 50, 'Weak single issue audit.', %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], weak_domain, f"https://{weak_domain}", f"p80-held-{token}"),
        )
        execute("INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text) VALUES (%s, 'metadata', 'medium', 'Metadata issue', 'Visible from a public browser session.')", (audit["id"],))
        preview = execute(
            """
            INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json)
            VALUES (%s, %s, %s, 'preview', 91, %s)
            RETURNING id
            """,
            (campaign_id, lead["id"], audit["id"], Jsonb({"token": token, "kind": "held_weak_row"})),
        )
        review_campaign_preview(str(preview["id"]), "held", "single weak issue stays excluded")
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        monkeypatch.setattr(preflight, "campaign_preview_transport_gate_status", lambda campaign_id: _transport_preview_ready())
        result = campaign_preflight_batch(5, campaign_id)
        run = result["runs"][0]
        assert result["passed_count"] == 1
        assert run["preview_review_summary"]["held_count"] == 1
        assert "preview_rows_held_for_review" not in run["blockers"]
        assert run["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_endpoint_and_agent_are_admin_gated(monkeypatch):
    import app.campaign_preflight as preflight

    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        monkeypatch.setattr(preflight, "mailer_policy_score", _policy_pass)
        monkeypatch.setattr(preflight, "campaign_preview_transport_gate_status", lambda campaign_id: _transport_preview_ready())
        assert client.get("/admin/campaign-preflight/runs").status_code == 401
        assert client.post("/admin/campaign-preflight/run", json={"campaign_id": campaign_id}).status_code == 401
        response = client.post("/admin/campaign-preflight/run", json={"campaign_id": campaign_id}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["preflight"]["send_mail"] is False
        agent = run_agent("campaign_preflight_agent", {"campaign_id": campaign_id})
        assert agent["status"] == "completed"
        assert agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_campaign_preflight_orphan_hygiene_cleans_deleted_campaign_telemetry():
    token = uuid.uuid4().hex[:8]
    try:
        row = execute(
            """
            INSERT INTO campaign_preflight_runs(campaign_id, status, decision, checked_count, ready_count, blocker_count, result_json)
            VALUES (NULL, 'completed', 'FAIL_BLOCK_LAUNCH', 1, 0, 1, %s)
            RETURNING id
            """,
            (Jsonb({"token": token, "reason": "deleted_synthetic_campaign"}),),
        )
        preview = campaign_preflight_orphan_hygiene(50, apply=False)
        assert preview["orphan_count"] >= 1
        assert preview["deleted_count"] == 0
        result = run_agent("campaign_preflight_orphan_hygiene_agent", {"limit": 50, "apply": True})
        assert result["status"] == "completed"
        assert result["result_json"]["deleted_count"] >= 1
        assert result["result_json"]["send_mail"] is False
        assert fetch_one("SELECT id FROM campaign_preflight_runs WHERE id = %s", (row["id"],)) is None
    finally:
        execute("DELETE FROM campaign_preflight_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
