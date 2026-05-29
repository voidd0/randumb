from __future__ import annotations

import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db import execute
from app.mailer_action_queue import enqueue_mailer_action, mailer_action_queue_summary, process_mailer_action_queue, send_customer_mail
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(marker: str) -> None:
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{marker}%",))


def _send_ready_action(marker: str, raw_email: str = "p26@example.test") -> dict:
    action = enqueue_mailer_action({"action_type": "customer_onboarding", "recipient_email": raw_email, "marker": marker})
    execute("UPDATE mailer_action_queue SET status = 'send_ready' WHERE id = %s", (action["id"],))
    return action


def _clean_mail_gates(
    monkeypatch,
    *,
    sending_enabled: bool = True,
    real_enabled: bool = True,
    owner_report_enabled: bool = False,
    owner_sale_enabled: bool = False,
) -> None:
    import app.mailer_action_queue as queue

    monkeypatch.setattr(
        queue,
        "get_settings",
        lambda: SimpleNamespace(
            outreach_paused=True,
            first_live_send_flag=False,
            auto_replies_paused=True,
            customer_mail_sending_enabled=sending_enabled,
            customer_mail_real_send_enabled=real_enabled,
            owner_report_email_enabled=owner_report_enabled,
            owner_sale_email_enabled=owner_sale_enabled,
            owner_command_email="owner-p26@example.test",
            smtp_from_default="audit@voiddorescue.com",
            smtp_host="mail.example.test",
            smtp_port=587,
            smtp_username="audit@example.test",
            smtp_password="secret",
        ),
    )
    monkeypatch.setattr(queue, "mail_signal_summary", lambda hours=24: {"bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0, "items": [], "window_hours": hours})
    monkeypatch.setattr(queue, "latest_mail_qa_decision", lambda: "PASS")
    monkeypatch.setattr(queue, "throttle_decision", lambda scope, scope_key, min_delay_seconds=600: {"allowed": True, "reason": "allowed", "checks": {}})
    monkeypatch.setattr(queue, "record_throttle_send", lambda scope, scope_key, reason="sent": {"scope": scope, "scope_key": scope_key, "reason": reason})


def test_owner_report_gate_ignores_cold_bounce_signal(monkeypatch):
    import app.mailer_action_queue as queue

    marker = "p26-owner-report-bounce-does-not-block"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch, owner_report_enabled=True)
        monkeypatch.setattr(queue, "mail_signal_summary", lambda hours=24: {"bounce_or_dsn_count": 3, "rate_limit_count": 0, "spam_signal_count": 2, "mail_auth_failure_count": 0, "items": [], "window_hours": hours})
        action = enqueue_mailer_action(
            {
                "action_type": "owner_report",
                "risk_level": "SAFE_AUTO",
                "mailbox": "support@voiddorescue.com",
                "template_key": "owner_status_report",
                "payload_json": {"source": marker, "report_date": marker},
            }
        )
        result = process_mailer_action_queue(10)
        processed = next(item for item in result["actions"] if item["id"] == action["id"])
        assert processed["status"] == "send_ready"
        assert "recent_bounce_or_dsn" not in processed["gate_result_json"]["blockers"]
        assert "recent_spam_signal" not in processed["gate_result_json"]["blockers"]
    finally:
        _cleanup(marker)


def test_owner_report_gate_still_blocks_rate_limit_signal(monkeypatch):
    import app.mailer_action_queue as queue

    marker = "p26-owner-report-rate-limit-blocks"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch, owner_report_enabled=True)
        monkeypatch.setattr(queue, "mail_signal_summary", lambda hours=24: {"bounce_or_dsn_count": 0, "rate_limit_count": 1, "spam_signal_count": 0, "mail_auth_failure_count": 0, "items": [], "window_hours": hours})
        action = enqueue_mailer_action(
            {
                "action_type": "owner_report",
                "risk_level": "SAFE_AUTO",
                "mailbox": "support@voiddorescue.com",
                "template_key": "owner_status_report",
                "payload_json": {"source": marker, "report_date": marker},
            }
        )
        result = process_mailer_action_queue(10)
        processed = next(item for item in result["actions"] if item["id"] == action["id"])
        assert processed["status"] == "prepared"
        assert "recent_rate_limit" in processed["gate_result_json"]["blockers"]
    finally:
        _cleanup(marker)


def test_owner_sale_gate_ignores_cold_bounce_signal(monkeypatch):
    import app.mailer_action_queue as queue

    marker = "p26-owner-sale-bounce-does-not-block"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch, owner_sale_enabled=True)
        monkeypatch.setattr(queue, "mail_signal_summary", lambda hours=24: {"bounce_or_dsn_count": 3, "rate_limit_count": 0, "spam_signal_count": 2, "mail_auth_failure_count": 0, "items": [], "window_hours": hours})
        action = enqueue_mailer_action(
            {
                "action_type": "owner_sale_notification",
                "risk_level": "SAFE_AUTO",
                "mailbox": "support@voiddorescue.com",
                "template_key": "owner_sale_notification",
                "source_event": "paddle_webhook",
                "product_key": "contact_form_repair",
                "amount": 99,
                "currency": "USD",
                "customer_hash": marker,
                "paddle_transaction_id": marker,
            }
        )
        result = process_mailer_action_queue(10)
        processed = next(item for item in result["actions"] if item["id"] == action["id"])
        assert processed["status"] == "send_ready"
        assert processed["gate_result_json"]["reason"] == "send_ready_no_send_gate"
        assert "recent_bounce_or_dsn" not in processed["gate_result_json"]["blockers"]
        assert "recent_spam_signal" not in processed["gate_result_json"]["blockers"]
    finally:
        _cleanup(marker)


def test_owner_sale_gate_still_blocks_rate_limit_signal(monkeypatch):
    import app.mailer_action_queue as queue

    marker = "p26-owner-sale-rate-limit-blocks"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch, owner_sale_enabled=True)
        monkeypatch.setattr(queue, "mail_signal_summary", lambda hours=24: {"bounce_or_dsn_count": 0, "rate_limit_count": 1, "spam_signal_count": 0, "mail_auth_failure_count": 0, "items": [], "window_hours": hours})
        action = enqueue_mailer_action(
            {
                "action_type": "owner_sale_notification",
                "risk_level": "SAFE_AUTO",
                "mailbox": "support@voiddorescue.com",
                "template_key": "owner_sale_notification",
                "source_event": "paddle_webhook",
                "product_key": "contact_form_repair",
                "amount": 99,
                "currency": "USD",
                "customer_hash": marker,
                "paddle_transaction_id": marker,
            }
        )
        result = process_mailer_action_queue(10)
        processed = next(item for item in result["actions"] if item["id"] == action["id"])
        assert processed["status"] == "prepared"
        assert "recent_rate_limit" in processed["gate_result_json"]["blockers"]
    finally:
        _cleanup(marker)


def test_customer_mail_real_send_default_blocked(monkeypatch):
    marker = "p26-default-blocked"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch, sending_enabled=True, real_enabled=False)
        _send_ready_action(marker)
        result = send_customer_mail(10)
        action = next(item for item in result["actions"] if item["action_type"] == "customer_onboarding")
        assert action["status"] == "transport_blocked"
        assert "customer_mail_real_send_flag_false" in action["gate_result_json"]["blockers"]
        assert action["result_json"]["send_mail"] is False
    finally:
        _cleanup(marker)


def test_customer_mail_real_send_missing_flag_blocks(monkeypatch):
    marker = "p26-real-flag-missing"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch, sending_enabled=True, real_enabled=False)
        _send_ready_action(marker)
        result = send_customer_mail(10)
        action = next(item for item in result["actions"] if item["action_type"] == "customer_onboarding")
        assert action["status"] == "transport_blocked"
        assert "customer_mail_real_send_flag_false" in action["gate_result_json"]["blockers"]
        assert action["result_json"]["smtp_called"] is False
    finally:
        _cleanup(marker)


def test_customer_mail_mocked_real_send_records_sent(monkeypatch):
    import app.mailer_action_queue as queue

    marker = "p26-mocked-sent"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch, sending_enabled=True, real_enabled=True)
        monkeypatch.setattr(queue, "send_customer_mail_via_smtp", lambda action, preview: {"sent": True, "smtp_called": True, "provider_message_id": "<mock-p26@voiddorescue.test>"})
        _send_ready_action(marker)
        result = send_customer_mail(10)
        action = next(item for item in result["actions"] if item["action_type"] == "customer_onboarding")
        assert action["status"] == "sent"
        assert action["result_json"]["provider_message_id"] == "<mock-p26@voiddorescue.test>"
        assert action["result_json"]["smtp_called"] is True
        assert result["send_mail"] is True
    finally:
        _cleanup(marker)


def test_customer_mail_smtp_failure_records_failed(monkeypatch):
    import app.mailer_action_queue as queue

    marker = "p26-smtp-failed"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch, sending_enabled=True, real_enabled=True)

        def fail_transport(action, preview):
            raise RuntimeError("synthetic smtp failure")

        monkeypatch.setattr(queue, "send_customer_mail_via_smtp", fail_transport)
        _send_ready_action(marker)
        result = send_customer_mail(10)
        action = next(item for item in result["actions"] if item["action_type"] == "customer_onboarding")
        assert action["status"] == "failed"
        assert action["result_json"]["error_type"] == "RuntimeError"
        assert action["result_json"]["send_mail"] is False
    finally:
        _cleanup(marker)


def test_owner_report_mail_sends_only_with_owner_flag(monkeypatch):
    import app.mailer_action_queue as queue

    marker = "p26-owner-report-send"
    try:
        _cleanup(marker)

        monkeypatch.setattr(
            queue,
            "get_settings",
            lambda: SimpleNamespace(
                outreach_paused=True,
                first_live_send_flag=False,
                auto_replies_paused=True,
                customer_mail_sending_enabled=False,
                customer_mail_real_send_enabled=False,
                owner_report_email_enabled=True,
                owner_sale_email_enabled=False,
                owner_command_email="owner-p26@example.test",
                smtp_from_default="audit@voiddorescue.com",
                smtp_host="mail.example.test",
                smtp_port=587,
                smtp_username="audit@example.test",
                smtp_password="secret",
            ),
        )
        monkeypatch.setattr(queue, "mail_signal_summary", lambda hours=24: {"bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0, "mail_auth_failure_count": 0, "items": [], "window_hours": hours})
        monkeypatch.setattr(queue, "latest_mail_qa_decision", lambda: "PASS")
        monkeypatch.setattr(queue, "throttle_decision", lambda scope, scope_key, min_delay_seconds=600: {"allowed": True, "reason": "allowed", "checks": {}})
        monkeypatch.setattr(queue, "record_throttle_send", lambda scope, scope_key, reason="sent": {"scope": scope, "scope_key": scope_key, "reason": reason})
        monkeypatch.setattr(queue, "send_customer_mail_via_smtp", lambda action, preview: {"sent": True, "smtp_called": True, "provider_message_id": "<owner-p26@voiddorescue.test>"})

        action = enqueue_mailer_action(
            {
                "action_type": "owner_report",
                "mailbox": "support@voiddorescue.com",
                "template_key": "owner_status_report",
                "marker": marker,
                "payload_json": {"report_date": "2026-05-29", "source": marker},
            }
        )
        processed = queue.process_mailer_action_queue(10)
        processed_action = next(item for item in processed["actions"] if item["id"] == action["id"])
        assert processed_action["status"] == "send_ready"

        result = send_customer_mail(10)
        sent = next(item for item in result["actions"] if item["id"] == action["id"])
        assert sent["status"] == "sent"
        assert sent["result_json"]["send_mail"] is True
        assert result["send_mail"] is True
        assert "owner-p26@example.test" not in str(result)
    finally:
        _cleanup(marker)


def test_customer_mail_real_send_result_hides_raw_email():
    marker = "p26-privacy"
    raw = "private-p26@example.test"
    try:
        _cleanup(marker)
        _send_ready_action(marker, raw)
        result = send_customer_mail(10)
        summary = mailer_action_queue_summary()
        assert raw not in str(result)
        assert raw not in str(summary)
        assert "recipient_hash" in str(result)
    finally:
        _cleanup(marker)


def test_customer_mail_real_send_endpoint_requires_auth():
    assert client.post("/admin/mailer/action-queue/send-customer-mail", json={"limit": 1}).status_code == 401
    assert client.post("/admin/mailer/action-queue/send-customer-mail", json={"limit": 1}, headers=admin_headers()).status_code == 200
