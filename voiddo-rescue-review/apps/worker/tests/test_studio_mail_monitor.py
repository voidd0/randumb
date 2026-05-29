from __future__ import annotations

from email.message import EmailMessage

from worker import studio_mail_monitor as monitor


def test_read_password_from_redacted_secret_file(tmp_path, monkeypatch):
    secret_file = tmp_path / "mailbox-creds"
    secret_file.write_text("# old\nem@voiddo.com secret-value\n", encoding="utf-8")
    monkeypatch.delenv("STUDIO_MAIL_PASSWORD", raising=False)
    monkeypatch.setenv("STUDIO_MAILBOX_CREDS_FILE", str(secret_file))
    assert monitor._read_password("em@voiddo.com") == "secret-value"


def test_message_payload_maps_catchall_headers_without_logging_raw_recipient():
    msg = EmailMessage()
    msg["Message-ID"] = "<studio-test@example.test>"
    msg["From"] = "Owner <owner@example.test>"
    msg["To"] = "em@voiddo.com"
    msg["Delivered-To"] = "em@voiddo.com"
    msg["X-Original-To"] = "support@voiddo.com"
    msg["Subject"] = "STATUS"
    msg["Authentication-Results"] = "dkim=pass"
    msg.set_content("STATUS")

    payload = monitor._message_payload("em@voiddo.com", "42", msg.as_bytes())
    assert payload["uid"] == "42"
    assert payload["message_id"] == "<studio-test@example.test>"
    assert payload["x_original_to"] == "support@voiddo.com"
    assert payload["authentication_results"] == "dkim=pass"
    assert payload["body"].strip() == "STATUS"


def test_poll_disabled_is_noop(monkeypatch):
    monkeypatch.setenv("STUDIO_MAIL_MONITOR_ENABLED", "false")
    result = monitor.poll_studio_mailbox()
    assert result["enabled"] is False
    assert result["submitted"] == 0


def test_submit_messages_posts_empty_heartbeat(monkeypatch):
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ingest": {"stored_count": 0, "owner_command_count": 0}}

    class FakeClient:
        def __init__(self, timeout=30.0):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setenv("API_INTERNAL_BASE_URL", "http://api:8080")
    monkeypatch.setenv("ADMIN_AUTH_TOKEN", "test-token")
    monkeypatch.setattr(monitor.httpx, "Client", FakeClient)
    result = monitor._submit_messages([])
    assert result["stored_count"] == 0
    assert calls[0]["json"] == {"messages": [], "dry_run": False}


def test_submit_messages_safely_fails_closed(monkeypatch):
    def boom(messages):
        raise monitor.httpx.ReadTimeout("api stuck")

    monkeypatch.setattr(monitor, "_submit_messages", boom)
    ingest, error = monitor._submit_messages_safely([])
    assert ingest == {}
    assert error == "api_submit_failed:ReadTimeout"
