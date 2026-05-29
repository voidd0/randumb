from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import execute, fetch_one
from app.main import app
from app.autonomous_agents import run_agent
from app.owner_command_control import owner_command_control_summary
from app.p0 import execute_owner_command, parse_owner_command
from app.studio_mail_monitor import classify_studio_mail, ingest_studio_mail_messages, latest_studio_mail_messages, studio_mail_monitor_health


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
    execute("DELETE FROM mail_signals WHERE message_id LIKE %s OR raw_summary LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM codex_tasks WHERE input_json::text LIKE %s OR title LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{token}%",))


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
        summary = owner_command_control_summary(5)
        assert summary["send_mail"] is False
        assert summary["live_outreach_allowed"] is False
        assert summary["raw_private_addresses_included"] is False
        assert summary["commands"][0]["sender_hash"]
        assert "sender" not in summary["commands"][0]
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


def test_owner_command_show_studio_mail_is_safe_auto_and_redacted(monkeypatch):
    owner = "owner-studio-mail@example.test"
    monkeypatch.setenv("OWNER_COMMAND_EMAIL", owner)
    get_settings.cache_clear()
    try:
        parsed = parse_owner_command(owner, "SHOW STUDIO MAIL", "")
        assert parsed["risk_level"] == "SAFE_AUTO"
        assert parsed["status"] == "executed"
        result = execute_owner_command(parsed)
        assert result["ok"] is True
        assert result["action"] == "studio_mail_status"
        assert result["health"]["send_mail"] is False
        assert result["latest_messages"]["raw_private_addresses_included"] is False
        assert owner not in str(result)
    finally:
        get_settings.cache_clear()


def test_owner_command_summary_hides_reclassified_platform_alert():
    token = uuid.uuid4().hex[:8]
    try:
        execute(
            """
            INSERT INTO owner_commands(mailbox, uid, message_id, sender, body, command, risk_level, status, result_json)
            VALUES ('studio:voiddo', %s, %s, 'owner@example.test', 'body', 'FWD: Search Console', 'HIGH_RISK', 'reclassified', '{"action":"reclassified_platform_alert"}'::jsonb)
            """,
            (f"uid-{token}", f"<msg-{token}@example.test>"),
        )
        summary = owner_command_control_summary(20)
        assert all(command["command"] != "FWD: Search Console" for command in summary["commands"])
    finally:
        _cleanup(token)


def test_forwarded_search_console_alert_is_not_owner_command(monkeypatch):
    token = uuid.uuid4().hex[:8]
    owner = f"owner-{token}@example.test"
    monkeypatch.setenv("OWNER_COMMAND_EMAIL", owner)
    get_settings.cache_clear()
    try:
        message = _message(
            token,
            owner,
            "Fwd: New reasons prevent pages from being indexed on site voiddo.com",
            f"Google Search Console noticed page indexing issue {token}",
            "em@voiddo.com",
        )
        result = ingest_studio_mail_messages([message])
        assert result["owner_command_count"] == 0
        assert result["results"][0]["classification"] == "platform_seo_indexing_alert"
        assert result["results"][0]["triage_task"]["task_type"] == "deployment_issue"
        row = fetch_one("SELECT classification, owner_command_id FROM studio_mail_messages WHERE message_id = %s", (f"<msg-{token}@example.test>",))
        assert row["classification"] == "platform_seo_indexing_alert"
        assert row["owner_command_id"] is None
    finally:
        _cleanup(token)
        get_settings.cache_clear()


def test_studio_mail_high_risk_owner_command_creates_review_task(monkeypatch):
    token = uuid.uuid4().hex[:8]
    owner = f"owner-{token}@example.test"
    monkeypatch.setenv("OWNER_COMMAND_EMAIL", owner)
    get_settings.cache_clear()
    try:
        result = ingest_studio_mail_messages([_message(token, owner, "RUN SHELL", f"RUN SHELL {token}")])
        assert result["owner_command_count"] == 1
        command = fetch_one("SELECT command, risk_level, status, result_json FROM owner_commands WHERE message_id = %s", (f"<msg-{token}@example.test>",))
        assert command["command"] == "RUN SHELL"
        assert command["risk_level"] == "HIGH_RISK"
        assert command["status"] == "review_required"
        assert command["result_json"]["action"] == "review_required"
        assert command["result_json"]["codex_task_id"]
        task = fetch_one("SELECT type, status FROM codex_tasks WHERE id = %s", (command["result_json"]["codex_task_id"],))
        assert task["type"] == "owner_command_review"
        assert task["status"] == "open"
    finally:
        _cleanup(token)
        get_settings.cache_clear()


def test_owner_command_agent_is_redacted_no_send(monkeypatch):
    token = uuid.uuid4().hex[:8]
    owner = f"owner-{token}@example.test"
    monkeypatch.setenv("OWNER_COMMAND_EMAIL", owner)
    get_settings.cache_clear()
    try:
        ingest_studio_mail_messages([_message(token, owner, "STATUS", f"STATUS {token}")])
        run = run_agent("owner_command_agent", {"limit": 5})
        assert run["status"] == "completed"
        payload = run["result_json"]
        assert payload["send_mail"] is False
        assert payload["live_outreach_allowed"] is False
        assert payload["raw_private_addresses_included"] is False
        assert payload["commands"][0]["sender_hash"]
        assert "sender" not in payload["commands"][0]
    finally:
        _cleanup(token)
        get_settings.cache_clear()


def test_studio_mail_monitor_health_tracks_fresh_timer_runs():
    token = uuid.uuid4().hex[:8]
    try:
        result = ingest_studio_mail_messages([_message(token, f"sender-{token}@example.test", "health", f"health {token}")], dry_run=True)
        assert result["scanned_count"] == 1
        health = studio_mail_monitor_health(15)
        assert health["status"] == "PASS_STUDIO_MAIL_MONITOR_HEALTH"
        assert health["decision"] == "PASS"
        assert health["latest_run"]["age_seconds"] <= 15 * 60
        assert health["send_mail"] is False
        assert health["live_outreach_allowed"] is False
        agent = run_agent("studio_mail_monitor_health_agent", {"max_age_minutes": 15})
        assert agent["status"] == "completed"
        assert agent["result_json"]["status"] == "PASS_STUDIO_MAIL_MONITOR_HEALTH"
    finally:
        _cleanup(token)


def test_studio_mail_alias_uses_x_original_to_for_catchall_messages():
    token = uuid.uuid4().hex[:8]
    message = _message(token, f"person-{token}@example.test", "support", "support body", "em@voiddo.com")
    message["x_original_to"] = "support@voiddo.com"
    classified = classify_studio_mail(message)
    assert classified["alias"] == "support@voiddo.com"
    assert classified["classification"] == "studio_support_triage"
    assert classified["human_review_required"] is False


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


def test_studio_mail_bounce_records_mail_signal_without_raw_address():
    token = uuid.uuid4().hex[:8]
    sender = f"mailer-daemon-{token}@mx.example.test"
    try:
        result = ingest_studio_mail_messages([_message(token, sender, "Delivery Status Notification", f"Delivery failed {token}", "em@voiddo.com")])
        assert result["stored_count"] == 1
        assert result["results"][0]["classification"] == "bounce"
        assert result["results"][0]["mail_signal"]["signal_type"] == "bounce"
        signal = fetch_one("SELECT signal_type, raw_summary, recipient_hash FROM mail_signals WHERE message_id = %s", (f"<msg-{token}@example.test>",))
        assert signal["signal_type"] == "bounce"
        assert sender not in signal["raw_summary"]
        assert signal["recipient_hash"] != sender
    finally:
        _cleanup(token)


def test_studio_mail_dmarc_report_is_informational_not_failure_signal():
    token = uuid.uuid4().hex[:8]
    sender = f"reports-{token}@reports.example.test"
    try:
        result = ingest_studio_mail_messages([_message(token, sender, "Report domain: voiddo.com", f"DMARC aggregate report {token}", "dmarc@voiddo.com")])
        assert result["stored_count"] == 1
        assert result["results"][0]["classification"] == "dmarc_report"
        assert result["results"][0]["mail_signal"]["signal_type"] == "dmarc_report"
        signal = fetch_one("SELECT signal_type, severity, raw_summary, recipient_hash FROM mail_signals WHERE message_id = %s", (f"<msg-{token}@example.test>",))
        assert signal["signal_type"] == "dmarc_report"
        assert signal["severity"] == "info"
        assert sender not in signal["raw_summary"]
        assert signal["recipient_hash"] != sender
    finally:
        _cleanup(token)


def test_studio_billing_sale_signal_queues_redacted_owner_notification():
    token = uuid.uuid4().hex[:8]
    sender = f"noreply-{token}@paddle.com"
    try:
        result = ingest_studio_mail_messages([
            _message(token, sender, "Transaction paid", f"Payment received for checkout {token}", "billing@voiddo.com")
        ])
        assert result["stored_count"] == 1
        item = result["results"][0]
        assert item["classification"] == "billing"
        assert item["sale_notification"]["action_type"] == "owner_sale_notification"
        assert item["sale_notification"]["risk_level"] == "SAFE_AUTO"
        action = fetch_one("SELECT action_type, recipient_hash, payload_json FROM mailer_action_queue WHERE id = %s", (item["sale_notification"]["id"],))
        assert action["action_type"] == "owner_sale_notification"
        assert action["recipient_hash"]
        assert sender not in str(action["payload_json"])
        assert token not in str(action["payload_json"])
        assert action["payload_json"]["source_event"] == "studio_billing_mail"
        assert action["payload_json"]["raw_private_addresses_included"] is False
        execute("DELETE FROM mailer_action_queue WHERE id = %s", (item["sale_notification"]["id"],))
    finally:
        _cleanup(token)


def test_studio_billing_non_sale_does_not_queue_sale_notification():
    token = uuid.uuid4().hex[:8]
    sender = f"noreply-{token}@paddle.com"
    try:
        result = ingest_studio_mail_messages([
            _message(token, sender, "Paddle account notice", f"Monthly billing settings notice {token}", "billing@voiddo.com")
        ])
        assert result["stored_count"] == 1
        assert result["results"][0]["classification"] == "billing"
        assert result["results"][0]["sale_notification"] is None
        queued = fetch_one("SELECT count(*) AS count FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{token}%",))
        assert int(queued["count"]) == 0
    finally:
        _cleanup(token)


def test_studio_mail_support_is_autonomous_triage_and_redacted_in_listing():
    token = uuid.uuid4().hex[:8]
    sender = f"person-{token}@example.test"
    try:
        classified = classify_studio_mail(_message(token, sender, "hello", "A private support question", "support@voiddo.com"))
        assert classified["classification"] == "studio_support_triage"
        assert classified["human_review_required"] is False
        result = ingest_studio_mail_messages([_message(token, sender, "hello", "A private support question", "support@voiddo.com")])
        assert result["human_review_count"] == 0
        assert result["results"][0]["triage_task"]["task_type"] == "customer_fix_request"
        task = fetch_one("SELECT type, status, input_json FROM codex_tasks WHERE id = %s", (result["results"][0]["triage_task"]["codex_task_id"],))
        assert task["type"] == "customer_fix_request"
        assert task["status"] == "open"
        assert sender not in str(task["input_json"])
        listed = latest_studio_mail_messages(5)
        assert "person-" not in str(listed)
        assert "private support" not in str(listed).lower()
    finally:
        _cleanup(token)


def test_studio_mail_listing_normalizes_legacy_personal_category():
    token = uuid.uuid4().hex[:8]
    try:
        execute(
            """
            INSERT INTO studio_mail_messages(mailbox, uid, message_id, sender_hash, alias, classification, priority, human_review_required)
            VALUES ('studio:voiddo', %s, %s, %s, 'support@voiddo.com', 'personal_or_support', 'high', true)
            """,
            (f"uid-{token}", f"<msg-{token}@example.test>", "hash"),
        )
        listed = latest_studio_mail_messages(5)
        latest = listed["messages"][0]
        assert latest["classification"] == "studio_support_triage"
        assert latest["human_review_required"] is False
    finally:
        _cleanup(token)


def test_studio_mail_owner_only_escalation_is_narrow_and_redacted():
    token = uuid.uuid4().hex[:8]
    sender = f"platform-{token}@example.test"
    try:
        result = ingest_studio_mail_messages([
            _message(token, sender, "Verification code", f"2FA verification code required {token}", "support@voiddo.com")
        ])
        assert result["human_review_count"] == 1
        assert result["results"][0]["classification"] == "owner_only_escalation"
        assert result["results"][0]["triage_task"]["task_type"] == "deployment_issue"
        listed = latest_studio_mail_messages(5)
        assert sender not in str(listed)
        assert "verification code required" not in str(listed).lower()
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
