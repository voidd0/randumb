from __future__ import annotations

from types import SimpleNamespace

from app.db import execute
from app.mailer_action_queue import enqueue_mailer_action, process_mailer_action_queue, render_customer_mail_preview


def _cleanup(marker: str) -> None:
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{marker}%",))


def test_customer_mail_stays_prepared_with_flag_false():
    marker = "p24-flag-false"
    try:
        _cleanup(marker)
        enqueue_mailer_action({"action_type": "customer_onboarding", "recipient_email": "p24@example.test", "marker": marker})
        result = process_mailer_action_queue(100)
        action = next(item for item in result["actions"] if item["action_type"] == "customer_onboarding")
        assert action["status"] == "prepared"
        assert "customer_mail_sending_flag_false" in action["gate_result_json"]["blockers"]
        assert action["gate_result_json"]["send_mail"] is False
    finally:
        _cleanup(marker)


def test_customer_mail_becomes_send_ready_under_mocked_clean_gates(monkeypatch):
    import app.mailer_action_queue as queue

    marker = "p24-clean"
    try:
        _cleanup(marker)
        monkeypatch.setattr(queue, "get_settings", lambda: SimpleNamespace(outreach_paused=True, first_live_send_flag=False, auto_replies_paused=True, customer_mail_sending_enabled=True))
        monkeypatch.setattr(queue, "mail_signal_summary", lambda hours=24: {"bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0, "items": [], "window_hours": hours})
        monkeypatch.setattr(queue, "latest_mail_qa_decision", lambda: "PASS")
        monkeypatch.setattr(queue, "throttle_decision", lambda scope, scope_key, min_delay_seconds=600: {"allowed": True, "reason": "allowed", "checks": {}})
        enqueue_mailer_action({"action_type": "customer_onboarding", "recipient_email": "p24@example.test", "marker": marker})
        result = process_mailer_action_queue(100)
        action = next(item for item in result["actions"] if item["action_type"] == "customer_onboarding")
        assert action["status"] == "send_ready"
        assert action["gate_result_json"]["send_ready"] is True
        assert action["gate_result_json"]["send_mail"] is False
    finally:
        _cleanup(marker)


def test_customer_mail_throttle_failure_blocks_send_ready(monkeypatch):
    import app.mailer_action_queue as queue

    marker = "p24-throttle"
    try:
        _cleanup(marker)
        monkeypatch.setattr(queue, "get_settings", lambda: SimpleNamespace(outreach_paused=True, first_live_send_flag=False, auto_replies_paused=True, customer_mail_sending_enabled=True))
        monkeypatch.setattr(queue, "mail_signal_summary", lambda hours=24: {"bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0, "items": [], "window_hours": hours})
        monkeypatch.setattr(queue, "latest_mail_qa_decision", lambda: "PASS")
        monkeypatch.setattr(queue, "throttle_decision", lambda scope, scope_key, min_delay_seconds=600: {"allowed": False, "reason": "min_delay", "checks": {}})
        enqueue_mailer_action({"action_type": "customer_onboarding", "recipient_email": "p24@example.test", "marker": marker})
        result = process_mailer_action_queue(100)
        action = next(item for item in result["actions"] if item["action_type"] == "customer_onboarding")
        assert action["status"] == "prepared"
        assert "throttle:min_delay" in action["gate_result_json"]["blockers"]
    finally:
        _cleanup(marker)


def test_customer_mail_rendered_messages_pass_email_qa():
    samples = [
        {"action_type": "customer_onboarding", "template_key": "payment_onboarding", "payload_json": {"product_key": "monitor_monthly"}},
        {"action_type": "fix_request_created", "template_key": "fix_request_created", "payload_json": {"product_key": "contact_form_repair"}},
        {"action_type": "monitoring_report", "template_key": "monitoring_setup_reminder", "payload_json": {"product_key": "monitor_monthly"}},
    ]
    for sample in samples:
        preview = render_customer_mail_preview(sample)
        assert preview["qa"]["passed"], preview
        assert "{{" not in preview["rendered"]["text"]


def test_customer_mail_gate_does_not_include_raw_customer_email():
    marker = "p24-privacy"
    raw = "private-p24@example.test"
    try:
        _cleanup(marker)
        action = enqueue_mailer_action({"action_type": "customer_onboarding", "recipient_email": raw, "marker": marker})
        assert raw not in str(action)
        result = process_mailer_action_queue(100)
        assert raw not in str(result)
    finally:
        _cleanup(marker)
