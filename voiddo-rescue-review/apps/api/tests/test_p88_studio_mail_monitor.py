from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import execute, fetch_one
from app.main import app
from app.studio_mail_monitor import classify_studio_mail, ingest_studio_mail_messages, latest_studio_mail_messages


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM studio_mail_monitor_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM studio_mail_messages WHERE message_id LIKE %s OR uid LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM email_events WHERE message_id LIKE %s OR uid LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM owner_commands WHERE message_id LIKE %s OR uid LIKE %s OR body LIKE %s", (f"%{token}%", f"%{token}%", f"%{token}%"))
    execute("DELETE FROM suppression_list WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{token}%",))


def _message(token: str, sender: str, subject: str, body: str, to: str = "support@voiddo.com") -> dict:
    return {
        "mailbox": "studio:voiddo",
        "uid": f"uid-{token}",
        "message_id": f"<msg-{token}@example.test>",
        "sender": sender,
        "reply_to": sender,
        "to": to,
        "subject": subject,
        "body": body,
        "authentication_results": "dkim=pass spf=pass",
    }


def test_studio_mail_owner_command_routes_to_global_owner_commands(monkeypatch):
    token = uuid.uuid4().hex[:8]
    owner = f"owner-{token}@example.test"
    monkeypatch.setenv("OWNER_COMMAND_EMAIL", owner)
    monkeypatch.setenv("STUDIO_OWNER_COMMAND_EMAILS", "")
    get_settings.cache_clear()
    try:
        result = ingest_studio_mail_messages([_message(token, owner, "STATUS", f"STATUS {token}")])
        assert result["stored_count"] == 1
        assert result["owner_command_count"] == 1
        assert result["send_mail"] is False
        command = fetch_one("SELECT command, risk_level, status FROM owner_commands WHERE message_id = %s", (f"<msg-{token}@example.test>",))
        assert command["command"] == "STATUS"
        assert command["risk_level"] == "SAFE_AUTO"
        assert command["status"] == "executed"
        row = fetch_one("SELECT classification, priority, owner_command_id FROM studio_mail_messages WHERE message_id = %s", (f"<msg-{token}@example.test>",))
        assert row["classification"] == "owner_command_global"
        assert row["priority"] == "critical"
        assert row["owner_command_id"] is not None
    finally:
        _cleanup(token)
        get_settings.cache_clear()


def test_studio_mail_owner_command_accepts_russian_alias(monkeypatch):
    token = uuid.uuid4().hex[:8]
    owner = f"owner-{token}@example.test"
    monkeypatch.setenv("OWNER_COMMAND_EMAIL", owner)
    get_settings.cache_clear()
    try:
        result = ingest_studio_mail_messages([_message(token, owner, "ПОКАЖИ ПРОГРЕВ", f"ПОКАЖИ ПРОГРЕВ {token}")])
        assert result["owner_command_count"] == 1
        command = fetch_one("SELECT command, risk_level, status FROM owner_commands WHERE message_id = %s", (f"<msg-{token}@example.test>",))
        assert command["command"] == "SHOW WARMUP"
        assert command["risk_level"] == "SAFE_AUTO"
        assert command["status"] == "executed"
    finally:
        _cleanup(token)
        get_settings.cache_clear()


def test_studio_mail_classifies_unsubscribe_and_suppresses_without_reply():
    token = uuid.uuid4().hex[:8]
    sender = f"stop-{token}@example.test"
    try:
        result = ingest_studio_mail_messages([_message(token, sender, "unsubscribe", "Please remove me", "unsubscribe@voiddo.com")])
        assert result["stored_count"] == 1
        assert result["high_priority_count"] == 1
        assert result["send_mail"] is False
        suppressed = fetch_one("SELECT reason, source FROM suppression_list WHERE email = %s", (sender,))
        assert suppressed["source"] == "studio_mail_monitor"
        event = fetch_one("SELECT classification, human_review_required FROM email_events WHERE message_id = %s", (f"<msg-{token}@example.test>",))
        assert event["classification"] == "unsubscribe"
        assert event["human_review_required"] is False
    finally:
        _cleanup(token)


def test_studio_mail_personal_support_is_human_review_and_redacted_in_listing():
    token = uuid.uuid4().hex[:8]
    sender = f"person-{token}@example.test"
    try:
        classified = classify_studio_mail(_message(token, sender, "hello", "A private support question", "support@voiddo.com"))
        assert classified["classification"] == "personal_or_support"
        assert classified["human_review_required"] is True
        result = ingest_studio_mail_messages([_message(token, sender, "hello", "A private support question", "support@voiddo.com")])
        assert result["human_review_count"] == 1
        listed = latest_studio_mail_messages(5)
        assert "person-" not in str(listed)
        assert "private support" not in str(listed).lower()
    finally:
        _cleanup(token)


def test_studio_mail_ingest_endpoint_is_admin_gated(monkeypatch):
    token = uuid.uuid4().hex[:8]
    owner = f"owner-{token}@example.test"
    monkeypatch.setenv("OWNER_COMMAND_EMAIL", owner)
    get_settings.cache_clear()
    try:
        payload = {"messages": [_message(token, owner, "STATUS", "STATUS")], "dry_run": True}
        assert client.post("/admin/studio-mail/ingest", json=payload).status_code == 401
        response = client.post("/admin/studio-mail/ingest", json=payload, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["ingest"]["owner_command_count"] == 1
        assert client.get("/admin/studio-mail/messages").status_code == 401
        assert client.get("/admin/studio-mail/messages", headers=admin_headers()).status_code == 200
        assert client.get("/admin/studio-mail/runs", headers=admin_headers()).status_code == 200
    finally:
        _cleanup(token)
        get_settings.cache_clear()
