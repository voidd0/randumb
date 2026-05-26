from __future__ import annotations

import os
import uuid
import base64
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db import execute, fetch_one
from app.main import app
from app.p0 import prepare_warmup, run_mail_qa, store_owner_command, transport_gate_status


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def owner_email() -> str:
    return os.environ["OWNER_COMMAND_EMAIL"]


def test_admin_metrics_requires_token_and_health_public():
    assert client.get("/health").status_code == 200
    assert client.get("/admin/metrics").status_code == 401
    assert client.get("/admin/metrics", headers=admin_headers()).status_code == 200
    assert client.get("/admin/metrics", headers={"Authorization": f"Bearer {os.environ['ADMIN_AUTH_TOKEN']}"}).status_code == 200
    basic = base64.b64encode(f"admin:{os.environ['ADMIN_AUTH_TOKEN']}".encode()).decode()
    assert client.get("/admin/metrics", headers={"Authorization": f"Basic {basic}"}).status_code == 200


def test_public_audit_endpoint_remains_public():
    slug = f"public-audit-{uuid.uuid4().hex[:8]}"
    execute(
        """
        INSERT INTO audits(domain, url, status, score, summary, public_slug, checked_at)
        VALUES ('example.com', 'https://example.com', 'completed', 90, 'public audit test', %s, now())
        RETURNING id
        """,
        (slug,),
    )
    response = client.get(f"/audits/{slug}")
    assert response.status_code == 200
    assert response.json()["audit"]["public_slug"] == slug


def test_owner_status_executes_metrics_result():
    result = store_owner_command(
        {
            "mailbox": "owner",
            "uid": uuid.uuid4().hex,
            "message_id": uuid.uuid4().hex,
            "sender": owner_email(),
            "reply_to": owner_email(),
            "subject": "STATUS",
            "body": "STATUS",
            "authentication_results": "dkim=pass spf=pass",
        }
    )
    assert result["status"] == "executed"
    assert result["result_json"]["action"] == "metrics"
    assert "metrics" in result["result_json"]


def test_owner_pause_all_records_safe_pause_result():
    result = store_owner_command(
        {
            "mailbox": "owner",
            "uid": uuid.uuid4().hex,
            "message_id": uuid.uuid4().hex,
            "sender": owner_email(),
            "reply_to": owner_email(),
            "subject": "PAUSE ALL",
            "body": "PAUSE ALL",
            "authentication_results": "dkim=pass",
        }
    )
    assert result["status"] == "executed"
    assert result["result_json"]["action"] == "pause_recorded"
    control = fetch_one("SELECT value FROM runtime_controls WHERE key = 'pause_outreach'")
    assert control and control["value"] is True


def test_owner_report_today_creates_report_file():
    result = store_owner_command(
        {
            "mailbox": "owner",
            "uid": uuid.uuid4().hex,
            "message_id": uuid.uuid4().hex,
            "sender": owner_email(),
            "reply_to": owner_email(),
            "subject": "REPORT TODAY",
            "body": "REPORT TODAY",
            "authentication_results": "dkim=pass",
        }
    )
    assert result["status"] == "executed"
    assert result["result_json"]["action"] == "report_today"
    assert result["result_json"]["report"]["path"]


def test_owner_run_mail_and_visual_qa_create_runs():
    mail = store_owner_command(
        {
            "mailbox": "owner",
            "uid": uuid.uuid4().hex,
            "message_id": uuid.uuid4().hex,
            "sender": owner_email(),
            "reply_to": owner_email(),
            "subject": "RUN MAIL QA",
            "body": "RUN MAIL QA",
            "authentication_results": "dkim=pass",
        }
    )
    visual = store_owner_command(
        {
            "mailbox": "owner",
            "uid": uuid.uuid4().hex,
            "message_id": uuid.uuid4().hex,
            "sender": owner_email(),
            "reply_to": owner_email(),
            "subject": "RUN VISUAL QA",
            "body": "RUN VISUAL QA",
            "authentication_results": "dkim=pass",
        }
    )
    assert mail["status"] == "prepared"
    assert mail["result_json"]["action"] == "mail_qa"
    assert visual["status"] == "prepared"
    assert visual["result_json"]["action"] == "visual_qa"


def test_owner_run_shell_remains_review_required():
    result = store_owner_command(
        {
            "mailbox": "owner",
            "uid": uuid.uuid4().hex,
            "message_id": uuid.uuid4().hex,
            "sender": owner_email(),
            "reply_to": owner_email(),
            "subject": "RUN SHELL",
            "body": "RUN SHELL rm -rf /",
            "authentication_results": "dkim=pass",
        }
    )
    assert result["status"] == "review_required"
    assert result["result_json"]["reason"] == "high_risk_command_blocked"


def test_sensitive_mutation_endpoints_require_admin_token():
    assert client.post("/qa/mail/run").status_code == 401
    assert client.post("/qa/mail/run", headers=admin_headers()).status_code == 200


def test_paddle_checkout_endpoint_configured_and_unconfigured(monkeypatch):
    unconfigured = client.get("/checkout/contact_form_repair", follow_redirects=False)
    assert unconfigured.status_code in {302, 503}
    if unconfigured.status_code == 503:
        assert unconfigured.text == "checkout_not_configured"

    import app.main as main

    monkeypatch.setattr(main, "hosted_checkout_url", lambda settings, product_key, audit_slug="", email="": "https://checkout.example.test/pay?price_id=test")
    configured = client.get("/checkout/contact_form_repair?audit=demo", follow_redirects=False)
    assert configured.status_code == 302
    assert configured.headers["location"].startswith("https://checkout.example.test/pay")


def test_deliverability_pool_missing_blocks(monkeypatch):
    import app.p0 as p0

    monkeypatch.setattr(p0, "approved_test_inbox_emails", lambda settings=None: [])
    result = run_mail_qa()
    assert result["decision"] == "FAIL_BLOCK_LAUNCH"
    assert "approved_test_inbox_pool_missing" in result["issues_json"]


def test_warmup_pool_missing_blocks(monkeypatch):
    import app.p0 as p0

    monkeypatch.setattr(p0, "approved_warmup_recipient_emails", lambda settings=None: [])
    result = prepare_warmup(recipient_pool_count=0, day_number=1)
    assert result["status"] == "blocked_no_recipient_pool"


def test_transport_refuses_without_flags_and_when_suppressed_or_missing_unsubscribe(monkeypatch):
    base = transport_gate_status({"email": "lead@example.com", "body": "Unsubscribe: https://go.example/u"})
    assert not base["allowed"]
    assert base["reason"] == "outreach_dry_run_enabled"

    import app.p0 as p0
    monkeypatch.setattr(
        p0,
        "get_settings",
        lambda: SimpleNamespace(outreach_dry_run=False, outreach_paused=False, first_live_send_flag=True),
    )
    monkeypatch.setattr(p0, "latest_decision", lambda table: "PASS")
    monkeypatch.setattr(p0, "effective_pause_state", lambda area, configured=False: configured)

    execute(
        "INSERT INTO suppression_list(email, reason, source) VALUES (%s, 'test', 'test')",
        ("blocked@example.com",),
    )
    suppressed = transport_gate_status({"email": "blocked@example.com", "body": "Unsubscribe: https://go.example/u"})
    assert not suppressed["allowed"]
    assert suppressed["reason"] == "recipient_suppressed"

    missing = transport_gate_status({"email": "lead2@example.com", "body": "hello"})
    assert not missing["allowed"]
    assert missing["reason"] == "missing_unsubscribe"
