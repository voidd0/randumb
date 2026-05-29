from __future__ import annotations

from worker.inbox_engine import InboxMessage, is_owner_sender, submit_owner_command


def test_owner_sender_matches_owner_command_email(monkeypatch):
    monkeypatch.setenv("OWNER_COMMAND_EMAIL", "owner@example.test")
    monkeypatch.setenv("STUDIO_OWNER_COMMAND_EMAILS", "")
    assert is_owner_sender("Owner <owner@example.test>", "owner@example.test") is True
    assert is_owner_sender("Client <client@example.test>", "") is False


def test_submit_owner_command_posts_to_protected_api(monkeypatch):
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"command": {"status": "executed", "command": "STATUS"}}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": self.timeout})
            return FakeResponse()

    monkeypatch.setenv("ADMIN_AUTH_TOKEN", "admin-token")
    monkeypatch.setenv("API_INTERNAL_BASE_URL", "http://api:8080")
    monkeypatch.setattr("worker.inbox_engine.httpx.Client", FakeClient)
    item = InboxMessage(
        mailbox="support",
        uid="123",
        sender="owner@example.test",
        reply_to="owner@example.test",
        message_id="<owner-123@example.test>",
        subject="STATUS",
        body="STATUS",
        authentication_results="dkim=pass",
        classification="owner_command",
        human_review_required=False,
        auto_reply_allowed=False,
    )
    result = submit_owner_command(item)
    assert result == {"status": "executed", "command": "STATUS"}
    assert calls[0]["url"] == "http://api:8080/owner/commands"
    assert calls[0]["headers"]["X-Admin-Token"] == "admin-token"
    assert calls[0]["json"]["mailbox"] == "support"
    assert calls[0]["json"]["subject"] == "STATUS"
