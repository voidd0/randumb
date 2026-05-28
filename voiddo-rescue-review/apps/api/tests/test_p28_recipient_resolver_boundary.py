from __future__ import annotations

from types import SimpleNamespace

from app.db import execute, fetch_one
from app.mailer_action_queue import enqueue_mailer_action, mailer_action_queue_summary, resolve_customer_recipient, send_customer_mail
from app.mailer_closed_loop import run_mailer_closed_loop


def _cleanup(marker: str) -> None:
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{marker}%",))
    execute("DELETE FROM suppression_list WHERE source = %s", (marker,))
    execute("DELETE FROM customers WHERE email LIKE %s", (f"%{marker}%",))


def _customer(marker: str, email: str | None = None) -> str:
    row = execute(
        "INSERT INTO customers(email, status) VALUES (%s, 'active') RETURNING id",
        (email or f"customer-{marker}@example.test",),
    )
    return str(row["id"])


def _send_ready_action(marker: str, customer_id: str) -> dict:
    action = enqueue_mailer_action(
        {
            "action_type": "customer_onboarding",
            "recipient_email": f"hash-source-{marker}@example.test",
            "template_key": "payment_onboarding",
            "customer_id": customer_id,
            "source_event": "transaction.paid",
            "paddle_transaction_id": f"txn-{marker}",
            "product_key": "monitor_monthly",
            "marker": marker,
        }
    )
    execute("UPDATE mailer_action_queue SET status = 'send_ready' WHERE id = %s", (action["id"],))
    return {**action, "status": "send_ready"}


def _clean_mail_gates(monkeypatch) -> None:
    import app.mailer_action_queue as queue

    monkeypatch.setattr(
        queue,
        "get_settings",
        lambda: SimpleNamespace(
            outreach_paused=True,
            first_live_send_flag=False,
            auto_replies_paused=True,
            customer_mail_sending_enabled=True,
            customer_mail_real_send_enabled=True,
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
    monkeypatch.setattr(queue, "record_throttle_send", lambda scope, scope_key, reason="sent": {"scope": scope, "scope_key": scope_key})


def test_resolver_returns_customer_email_only_inside_transport_boundary():
    marker = "p28-resolve"
    raw = f"buyer-{marker}@gmail.com"
    try:
        _cleanup(marker)
        customer_id = _customer(marker, raw)
        action = _send_ready_action(marker, customer_id)
        row = fetch_one("SELECT * FROM mailer_action_queue WHERE id = %s", (action["id"],))
        resolved = resolve_customer_recipient(dict(row))
        summary = mailer_action_queue_summary()
        assert resolved["resolved"] is True
        assert resolved["recipient_email"] == raw
        assert raw not in str(summary)
    finally:
        _cleanup(marker)


def test_missing_customer_blocks_transport(monkeypatch):
    marker = "p28-missing-customer"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch)
        action = _send_ready_action(marker, "00000000-0000-0000-0000-000000000000")
        result = send_customer_mail(10)
        item = next(row for row in result["actions"] if row["id"] == action["id"])
        assert item["status"] == "transport_blocked"
        assert "customer_not_found" in item["result_json"]["blockers"]
    finally:
        _cleanup(marker)


def test_suppressed_customer_blocks_transport(monkeypatch):
    marker = "p28-suppressed"
    raw = f"buyer-{marker}@gmail.com"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch)
        customer_id = _customer(marker, raw)
        execute("INSERT INTO suppression_list(email, reason, source) VALUES (%s, 'test', %s)", (raw, marker))
        action = _send_ready_action(marker, customer_id)
        result = send_customer_mail(10)
        item = next(row for row in result["actions"] if row["id"] == action["id"])
        assert item["status"] == "transport_blocked"
        assert "recipient_suppressed" in item["result_json"]["blockers"]
    finally:
        _cleanup(marker)


def test_resolver_audit_omits_raw_customer_email():
    marker = "p28-audit-privacy"
    raw = f"buyer-{marker}@gmail.com"
    try:
        _cleanup(marker)
        customer_id = _customer(marker, raw)
        action = _send_ready_action(marker, customer_id)
        row = fetch_one("SELECT * FROM mailer_action_queue WHERE id = %s", (action["id"],))
        resolve_customer_recipient(dict(row))
        audit = fetch_one("SELECT * FROM recipient_resolver_audit WHERE action_id = %s ORDER BY created_at DESC LIMIT 1", (action["id"],))
        assert audit["status"] == "resolved"
        assert raw not in str(audit)
        assert audit["recipient_hash"]
    finally:
        _cleanup(marker)


def test_test_customer_email_domain_blocks_transport(monkeypatch):
    marker = "p28-test-domain-block"
    raw = f"buyer-{marker}@voiddorescue.local"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch)
        customer_id = _customer(marker, raw)
        action = _send_ready_action(marker, customer_id)
        result = send_customer_mail(10)
        item = next(row for row in result["actions"] if row["id"] == action["id"])
        assert item["status"] == "transport_blocked"
        assert "customer_email_test_domain" in item["result_json"]["blockers"]
        audit = fetch_one("SELECT * FROM recipient_resolver_audit WHERE action_id = %s ORDER BY created_at DESC LIMIT 1", (action["id"],))
        assert audit["status"] == "blocked"
        assert audit["reason"] == "customer_email_test_domain"
        assert raw not in str(result)
        assert raw not in str(audit)
    finally:
        _cleanup(marker)


def test_closed_loop_default_flags_keep_customer_mail_unsent():
    marker = "p28-default-no-send"
    raw = f"buyer-{marker}@example.test"
    try:
        _cleanup(marker)
        customer_id = _customer(marker, raw)
        enqueue_mailer_action(
            {
                "action_type": "customer_onboarding",
                "recipient_email": raw,
                "customer_id": customer_id,
                "source_event": "transaction.paid",
                "paddle_transaction_id": f"txn-{marker}",
                "marker": marker,
            }
        )
        result = run_mailer_closed_loop(10)
        assert result["send_mail"] is False
        assert result["transport"]["send_mail"] is False
        assert raw not in str(result)
    finally:
        _cleanup(marker)
