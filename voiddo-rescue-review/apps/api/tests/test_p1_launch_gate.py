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
    try:
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
    finally:
        execute("DELETE FROM runtime_controls WHERE source = 'owner_command' AND reason = 'PAUSE ALL'")


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


def test_paddle_client_checkout_config_route(monkeypatch):
    import app.main as main

    monkeypatch.setattr(
        main,
        "product_checkout_config",
        lambda settings, product_key, audit_slug="", email="": {
            "ready": True,
            "environment": "production",
            "client_token": "live_123456789012345678901234567",
            "product_key": product_key,
            "price_id": "pri_test",
            "product": {"name": "Contact Form Repair", "amount": 99, "currency": "USD", "mode": "one_time"},
            "audit_slug": audit_slug,
            "email": email,
            "custom_data": {"product_key": product_key, "audit_slug": audit_slug},
        },
    )
    response = client.get("/checkout/config/contact_form_repair?audit=demo")
    assert response.status_code == 200
    assert response.json()["price_id"] == "pri_test"


def test_deliverability_pool_missing_blocks(monkeypatch):
    import app.p0 as p0

    monkeypatch.setattr(p0, "approved_test_inbox_emails", lambda settings=None: [])
    result = run_mail_qa()
    assert result["decision"] == "FAIL_BLOCK_LAUNCH"
    assert "approved_test_inbox_pool_missing" in result["issues_json"]


def test_mail_qa_blocks_deliverability_errors(monkeypatch):
    import app.p0 as p0

    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def ehlo(self): pass
        def starttls(self, context=None): pass
        def login(self, user, password): pass

    class FakeIMAP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def login(self, user, password): pass
        def select(self, *args, **kwargs): pass
        def logout(self): pass

    def fake_dig(record_type: str, name: str) -> str:
        if name.startswith("dkim."):
            return "v=DKIM1; p=test"
        if name.startswith("_dmarc."):
            return "v=DMARC1; p=none"
        return "ok"

    monkeypatch.setattr(p0, "_dig", fake_dig)
    monkeypatch.setattr(p0.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(p0.imaplib, "IMAP4_SSL", FakeIMAP)
    monkeypatch.setattr(p0, "approved_test_inbox_emails", lambda settings=None: ["qa@example.test"])
    monkeypatch.setattr(p0, "run_deliverability_diagnostics", lambda settings, recipients, smtp_ready: {"sent": 0, "errors": ["SMTPDataError:451:rate limit"]})
    result = run_mail_qa()
    assert result["decision"] == "FAIL_BLOCK_LAUNCH"
    assert "deliverability_diagnostic_failed" in result["issues_json"]


def test_mail_qa_does_not_block_on_diagnostic_minute_cap(monkeypatch):
    import app.p0 as p0

    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def ehlo(self): pass
        def starttls(self, context=None): pass
        def login(self, user, password): pass

    class FakeIMAP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def login(self, user, password): pass
        def select(self, *args, **kwargs): pass
        def logout(self): pass

    def fake_dig(record_type: str, name: str) -> str:
        if name.startswith("dkim."):
            return "v=DKIM1; p=test"
        if name.startswith("_dmarc."):
            return "v=DMARC1; p=none"
        return "ok"

    monkeypatch.setattr(p0, "_dig", fake_dig)
    monkeypatch.setattr(p0.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(p0.imaplib, "IMAP4_SSL", FakeIMAP)
    monkeypatch.setattr(p0, "approved_test_inbox_emails", lambda settings=None: ["qa@example.test"])
    monkeypatch.setattr(p0, "provider_counts_for_test_inboxes", lambda: {"external": 1})
    monkeypatch.setattr(p0, "run_deliverability_diagnostics", lambda settings, recipients, smtp_ready: {"sent": 0, "errors": ["diagnostic_minute_cap_reached"]})
    result = run_mail_qa()
    assert result["decision"] == "PASS"
    assert "deliverability_diagnostic_failed" not in result["issues_json"]


def test_deliverability_diagnostic_sends_max_one(monkeypatch):
    import app.p0 as p0

    sent: list[str] = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def ehlo(self): pass
        def starttls(self, context=None): pass
        def login(self, user, password): pass
        def send_message(self, message): sent.append(message["To"])

    settings = SimpleNamespace(
        smtp_host="mail.example.test",
        smtp_port=587,
        smtp_username="audit@example.test",
        smtp_password="pw",
        smtp_from_default="audit@voiddorescue.com",
    )
    email = f"deliverability-{uuid.uuid4().hex[:8]}@example.test"
    monkeypatch.setattr(p0.smtplib, "SMTP", FakeSMTP)
    try:
        execute("DELETE FROM mail_signals WHERE source = 'deliverability_diagnostic_sent'")
        first = p0.run_deliverability_diagnostics(settings, [email], smtp_ready=True)
        second = p0.run_deliverability_diagnostics(settings, [email], smtp_ready=True)
        assert first["sent"] == 1
        assert first["results"][0]["message_id"].endswith("@voiddorescue.com>")
        assert first["results"][0]["smtp_result"] == "accepted"
        assert first["results"][0]["bounce_result"] == "pending_inbox_poll"
        assert second["sent"] == 0
        assert sent.count(email) == 1
    finally:
        execute("DELETE FROM test_inboxes WHERE lower(email) = lower(%s)", (email,))
        execute("DELETE FROM mail_signals WHERE source = 'deliverability_diagnostic_sent'")


def test_warmup_pool_missing_blocks(monkeypatch):
    import app.p0 as p0

    monkeypatch.setattr(p0, "approved_warmup_recipient_emails", lambda settings=None: [])
    result = prepare_warmup(recipient_pool_count=0, day_number=1)
    assert result["status"] == "blocked_no_recipient_pool"


def test_owner_start_warmup_blocked_without_pool_or_mail_pass(monkeypatch):
    import app.p0 as p0

    original_fetch_one = p0.fetch_one

    def fake_fetch_one(sql, params=()):
        if "FROM mail_qa_runs" in sql:
            return {"decision": "FAIL_BLOCK_LAUNCH", "issues_json": ["approved_test_inbox_pool_missing"]}
        return original_fetch_one(sql, params)

    monkeypatch.setattr(p0, "approved_warmup_recipient_emails", lambda settings=None: [])
    monkeypatch.setattr(p0, "fetch_one", fake_fetch_one)
    result = store_owner_command(
        {
            "mailbox": "owner",
            "uid": uuid.uuid4().hex,
            "message_id": uuid.uuid4().hex,
            "sender": owner_email(),
            "reply_to": owner_email(),
            "subject": "START WARMUP DAY=1",
            "body": "START WARMUP DAY=1",
            "authentication_results": "dkim=pass",
        }
    )
    assert result["status"] == "prepared"
    assert result["result_json"]["action"] == "warmup_start_gate"
    assert result["result_json"]["allowed"] is False


def test_owner_start_warmup_day1_sends_max_five_when_all_gates_pass(monkeypatch):
    import app.p0 as p0

    sent: list[str] = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def ehlo(self): pass
        def starttls(self, context=None): pass
        def login(self, user, password): pass
        def send_message(self, message): sent.append(message["To"])

    recipients = [f"warmup-{uuid.uuid4().hex[:6]}-{index}@example.test" for index in range(7)]
    monkeypatch.setattr(p0, "approved_warmup_recipient_emails", lambda settings=None: recipients)
    monkeypatch.setattr(p0, "effective_pause_state", lambda area, configured=False: False)
    monkeypatch.setattr(p0, "recent_mail_signal_count", lambda types, hours=24: 0)
    monkeypatch.setattr(p0.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(
        p0,
        "get_settings",
        lambda: SimpleNamespace(
            smtp_host="mail.example.test",
            smtp_port=587,
            smtp_username="audit@example.test",
            smtp_password="pw",
            smtp_from_default="audit@voiddorescue.com",
            owner_command_email=owner_email(),
        ),
    )
    mail_run = execute(
        """
        INSERT INTO mail_qa_runs(agent, status, decision, checks_json, issues_json)
        VALUES ('test', 'completed', 'PASS', '{}', '[]')
        RETURNING id
        """
    )
    result = store_owner_command(
        {
            "mailbox": "owner",
            "uid": uuid.uuid4().hex,
            "message_id": uuid.uuid4().hex,
            "sender": owner_email(),
            "reply_to": owner_email(),
            "subject": "START WARMUP DAY=1",
            "body": "START WARMUP DAY=1",
            "authentication_results": "dkim=pass",
        }
    )
    warmup_id = result["result_json"]["warmup"]["id"]
    try:
        assert result["status"] == "prepared"
        assert result["result_json"]["action"] == "warmup_start_gate"
        assert result["result_json"]["send_result"]["sent"] == 5
        assert len(sent) == 5
        assert all(recipient in recipients for recipient in sent)
    finally:
        execute("DELETE FROM email_events WHERE payload_json->>'warmup_run_id' = %s", (warmup_id,))
        execute("DELETE FROM warmup_runs WHERE id = %s", (warmup_id,))
        execute("DELETE FROM mail_qa_runs WHERE id = %s", (mail_run["id"],))


def test_send_outreach_high_risk_blocked():
    result = store_owner_command(
        {
            "mailbox": "owner",
            "uid": uuid.uuid4().hex,
            "message_id": uuid.uuid4().hex,
            "sender": owner_email(),
            "reply_to": owner_email(),
            "subject": "SEND OUTREACH",
            "body": "SEND OUTREACH",
            "authentication_results": "dkim=pass",
        }
    )
    assert result["status"] == "review_required"
    assert result["result_json"]["reason"] == "high_risk_command_blocked"


def test_mail_qa_can_pass_with_tls_and_approved_pool(monkeypatch):
    import app.p0 as p0

    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def ehlo(self): pass
        def starttls(self, context=None): pass
        def login(self, user, password): pass

    class FakeIMAP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def login(self, user, password): pass
        def select(self, *args, **kwargs): pass
        def logout(self): pass

    def fake_dig(record_type: str, name: str) -> str:
        if name.startswith("dkim."):
            return "v=DKIM1; p=test"
        if name.startswith("_dmarc."):
            return "v=DMARC1; p=none"
        return "ok"

    monkeypatch.setattr(p0, "_dig", fake_dig)
    monkeypatch.setattr(p0.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(p0.imaplib, "IMAP4_SSL", FakeIMAP)
    monkeypatch.setattr(p0, "approved_test_inbox_emails", lambda settings=None: ["qa@example.test"])
    monkeypatch.setattr(p0, "run_deliverability_diagnostics", lambda settings, recipients, smtp_ready: {"sent": 0, "skipped": "mocked"})
    result = run_mail_qa()
    assert result["decision"] == "PASS"


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
