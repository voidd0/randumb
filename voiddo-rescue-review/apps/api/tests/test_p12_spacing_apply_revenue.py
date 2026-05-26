from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.campaign_control import campaign_readiness_snapshot
from app.db import execute, fetch_one
from app.main import app
from app.p0 import handle_paddle_event
from app.lead_scoring import score_lead
from app.reply_actions import plan_reply_action
from app.scouts import create_campaign, create_scout_run, create_scout_source, prepare_campaign, process_scout_run
from app.warmup_planner import apply_provider_spacing_when_safe, rollback_latest_spacing_repair


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _seed_spacing_rows(token: str) -> list[str]:
    recipients = [
        f"p12-a-{token}@gmail.com",
        f"p12-b-{token}@gmail.com",
        f"p12-c-{token}@outlook.com",
        f"p12-d-{token}@proton.me",
    ]
    ids: list[str] = []
    for index, recipient in enumerate(recipients):
        row = execute(
            """
            INSERT INTO warmup_schedule(recipient_email, sender_mailbox, day_number, scheduled_for, status, result_json)
            VALUES (%s, 'audit@voiddorescue.com', 1, now() + (%s || ' minutes')::interval, 'scheduled', %s)
            RETURNING id
            """,
            (recipient, index + 60, Jsonb({"pytest": token})),
        )
        ids.append(str(row["id"]))
    return ids


def _cleanup_token(token: str) -> None:
    execute("DELETE FROM warmup_schedule WHERE recipient_email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scout_leads WHERE domain LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scanner_jobs WHERE url LIKE %s OR result_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaign_leads WHERE preview_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s", (f"%{token}%",))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s", (f"%{token}%",))
    execute("DELETE FROM onboarding_tasks WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM fix_requests WHERE evidence_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM payments WHERE paddle_transaction_id LIKE %s", (f"%{token}%",))
    execute("DELETE FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_runs WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM scout_sources WHERE name LIKE %s", (f"%{token}%",))


def test_spacing_apply_blocks_on_recent_signals(monkeypatch):
    import app.warmup_planner as planner

    monkeypatch.setattr(planner, "mail_signal_summary", lambda hours=24: {"bounce_or_dsn_count": 1, "rate_limit_count": 0, "spam_signal_count": 0, "items": []})
    repair = apply_provider_spacing_when_safe(4)
    assert repair["status"] == "blocked_safety_gate"
    assert repair["applied"] is False
    assert any(issue["code"] == "recent_mail_signals" for issue in repair["issues_json"])


def test_spacing_apply_and_rollback_restore_schedule(monkeypatch):
    import app.warmup_planner as planner

    token = uuid.uuid4().hex[:8]
    try:
        ids = _seed_spacing_rows(token)
        before = fetch_one("SELECT scheduled_for FROM warmup_schedule WHERE id = %s", (ids[0],))["scheduled_for"]
        monkeypatch.setattr(planner, "mail_signal_summary", lambda hours=24: {"bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0, "items": []})
        monkeypatch.setattr(planner, "latest_mail_qa_decision", lambda: "PASS")
        repair = apply_provider_spacing_when_safe(4)
        assert repair["status"] == "applied_safe_gate"
        assert repair["applied"] is True
        marked = fetch_one("SELECT result_json ? 'p12_spacing_repair' AS marked FROM warmup_schedule WHERE id = %s", (ids[0],))
        assert marked["marked"] is True
        rollback = rollback_latest_spacing_repair()
        after = fetch_one("SELECT scheduled_for, result_json ? 'p12_spacing_repair' AS marked FROM warmup_schedule WHERE id = %s", (ids[0],))
        assert rollback["status"] == "rolled_back"
        assert after["scheduled_for"] == before
        assert after["marked"] is False
    finally:
        _cleanup_token(token)


def test_scout_to_campaign_to_checkout_revenue_scenario():
    token = uuid.uuid4().hex[:8]
    try:
        csv_text = (
            "business_name,website_url,email,country,niche,source_url,confidence\n"
            f"Revenue,https://rev-{token}.example.test,owner@rev-{token}.example.test,P12,dentists,https://source.example/rev,90\n"
        )
        source = create_scout_source({"name": f"rev-{token}", "source_type": "manual_csv_scout", "country": "P12", "language": "en", "niche": "dentists", "config_json": {"csv": csv_text}})
        run = create_scout_run(str(source["id"]))
        processed = process_scout_run(str(run["id"]))
        assert processed["accepted"] == 1
        lead = fetch_one("SELECT id, business_id FROM leads WHERE email = %s", (f"owner@rev-{token}.example.test",))
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 85, 'Contact issue', %s, now())
            RETURNING id
            """,
            (lead["business_id"], lead["id"], f"rev-{token}.example.test", f"https://rev-{token}.example.test", f"rev-{token}"),
        )
        for _ in range(3):
            execute("INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text) VALUES (%s, 'contact', 'high', 'Issue', 'Issue text')", (audit["id"],))
        execute("INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport) VALUES (%s, 'desktop', '/tmp/rev.png', '/media/rev.png', 'desktop')", (audit["id"],))
        score_lead(str(lead["id"]), str(audit["id"]))
        campaign = create_campaign({"name": f"rev-{token}", "country": "P12", "language": "en", "niche": "dentists", "offer_key": "contact_form_repair"})
        preview = prepare_campaign(str(campaign["id"]), 70, 20)
        readiness = campaign_readiness_snapshot(str(campaign["id"]))
        assert preview["preview_count"] == 1
        assert readiness["lead_count"] == 1
        paid = handle_paddle_event(
            {
                "event_type": "transaction.paid",
                "data": {
                    "id": f"txn_rev_{token}",
                    "customer_id": f"ctm_rev_{token}",
                    "customer": {"email": f"buyer-rev-{token}@voiddorescue.local"},
                    "custom_data": {"product_key": "contact_form_repair"},
                    "details": {"totals": {"total": "9900", "currency_code": "USD"}},
                },
            },
            provisioning_paused=False,
        )
        assert "payment_recorded" in paid["actions"]
        assert "fix_request_created" in paid["actions"]
        assert "onboarding_task_created" in paid["actions"]
        customer = fetch_one("SELECT id FROM customers WHERE paddle_customer_id = %s", (f"ctm_rev_{token}",))
        assert customer is not None
    finally:
        _cleanup_token(token)


def test_unsafe_reply_creates_review_plan_and_no_auto_reply():
    plan = plan_reply_action("Security", "This was an unauthorized security scan", "support@voiddorescue.com")
    assert plan["classification"] == "security_accusation"
    assert plan["auto_reply_allowed"] is False
    assert plan["human_review_required"] is True
    assert plan["safe_action"] == "stop_thread_create_review_item"


def test_p12_admin_endpoints_require_auth_and_work():
    assert client.post("/admin/warmup/provider-spacing-apply", json={"limit": 4}).status_code == 401
    assert client.post("/admin/warmup/provider-spacing-apply", json={"limit": 4}, headers=admin_headers()).status_code == 200
    assert client.post("/admin/warmup/provider-spacing-rollback", headers=admin_headers()).status_code == 200


def test_p12_rollback_table_exists():
    row = fetch_one("SELECT to_regclass(%s) AS name", ("warmup_schedule_rollbacks",))
    assert row["name"] == "warmup_schedule_rollbacks"
