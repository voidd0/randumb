from __future__ import annotations

import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.mailer_action_queue import enqueue_mailer_action, send_customer_mail
from app.mailer_closed_loop import mailer_closed_loop_summary, run_mailer_closed_loop
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(marker: str) -> None:
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{marker}%",))
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{marker}%",))


def _clean_mail_gates(monkeypatch, *, signals: dict | None = None) -> None:
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
    monkeypatch.setattr(queue, "mail_signal_summary", lambda hours=24: signals or {"bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0, "items": [], "window_hours": hours})
    monkeypatch.setattr(queue, "latest_mail_qa_decision", lambda: "PASS")
    monkeypatch.setattr(queue, "throttle_decision", lambda scope, scope_key, min_delay_seconds=600: {"allowed": True, "reason": "allowed", "checks": {}})


def _send_ready_action(marker: str, raw_email: str = "p27@example.test") -> dict:
    action = enqueue_mailer_action(
        {
            "action_type": "customer_onboarding",
            "recipient_email": raw_email,
            "template_key": "payment_onboarding",
            "customer_id": f"customer-{marker}",
            "source_event": "transaction.paid",
            "paddle_transaction_id": f"txn-{marker}",
            "product_key": "monitor_monthly",
            "marker": marker,
        }
    )
    execute("UPDATE mailer_action_queue SET status = 'send_ready' WHERE id = %s", (action["id"],))
    return action


def test_customer_mail_action_idempotency_key_dedupes():
    marker = "p27-idempotency"
    try:
        _cleanup(marker)
        payload = {
            "action_type": "customer_onboarding",
            "recipient_email": "p27-idem@example.test",
            "template_key": "payment_onboarding",
            "customer_id": "customer-p27-idem",
            "source_event": "transaction.paid",
            "paddle_transaction_id": "txn-p27-idem",
            "product_key": "monitor_monthly",
            "marker": marker,
        }
        first = enqueue_mailer_action(payload)
        second = enqueue_mailer_action(payload)
        count = fetch_one("SELECT count(*) AS count FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{marker}%",))
        assert first["id"] == second["id"]
        assert int(count["count"]) == 1
    finally:
        _cleanup(marker)


def test_customer_mail_resolver_missing_blocks_and_records_ledger(monkeypatch):
    marker = "p27-resolver-block"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch)
        action = _send_ready_action(marker)
        result = send_customer_mail(10)
        sent = next(item for item in result["actions"] if item["id"] == action["id"])
        assert sent["status"] == "transport_blocked"
        assert "customer_id_invalid" in sent["result_json"]["blockers"]
        ledger = fetch_one("SELECT status, result_json FROM mailer_send_ledger WHERE action_id = %s", (action["id"],))
        assert ledger["status"] == "transport_blocked"
        assert "customer_id_invalid" in ledger["result_json"]["blockers"]
    finally:
        _cleanup(marker)


def test_customer_mail_ledger_is_idempotent_per_action(monkeypatch):
    marker = "p27-ledger-idempotent"
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch)
        action = _send_ready_action(marker)
        send_customer_mail(10)
        send_customer_mail(10)
        count = fetch_one("SELECT count(*) AS count FROM mailer_send_ledger WHERE action_id = %s", (action["id"],))
        assert int(count["count"]) == 1
    finally:
        _cleanup(marker)


def test_blocked_recent_signals_prevent_customer_transport(monkeypatch):
    import app.mailer_action_queue as queue

    marker = "p27-signal-block"
    called = {"smtp": 0}
    try:
        _cleanup(marker)
        _clean_mail_gates(monkeypatch, signals={"bounce_or_dsn_count": 1, "rate_limit_count": 0, "spam_signal_count": 0, "items": [], "window_hours": 24})
        monkeypatch.setattr(queue, "send_customer_mail_via_smtp", lambda action, preview: called.__setitem__("smtp", called["smtp"] + 1))
        _send_ready_action(marker)
        result = send_customer_mail(10)
        action = next(item for item in result["actions"] if item["action_type"] == "customer_onboarding")
        assert action["status"] == "transport_blocked"
        assert "recent_bounce_or_dsn" in action["gate_result_json"]["blockers"]
        assert called["smtp"] == 0
    finally:
        _cleanup(marker)


def test_closed_loop_executor_records_agent_run():
    marker = "p27-agent-run"
    try:
        _cleanup(marker)
        enqueue_mailer_action({"action_type": "owner_report", "recipient_email": "p27-agent@example.test", "marker": marker})
        result = run_agent("autonomous_mailer_executor_agent", {"limit": 5})
        assert result["agent"] == "autonomous_mailer_executor_agent"
        assert result["status"] == "completed"
        assert result["result_json"]["send_mail"] is False
        stored = fetch_one("SELECT count(*) AS count FROM agent_runs WHERE agent = 'autonomous_mailer_executor_agent'")
        assert int(stored["count"]) >= 1
    finally:
        _cleanup(marker)


def test_closed_loop_summary_and_endpoint_hide_raw_recipients():
    marker = "p27-privacy"
    raw = "private-p27@example.test"
    try:
        _cleanup(marker)
        enqueue_mailer_action({"action_type": "customer_onboarding", "recipient_email": raw, "customer_id": "customer-p27-privacy", "source_event": "transaction.paid", "marker": marker})
        summary = mailer_closed_loop_summary()
        result = run_mailer_closed_loop(5)
        assert raw not in str(summary)
        assert raw not in str(result)
        assert summary["raw_recipient_addresses_included"] is False
        assert client.get("/admin/mailer/closed-loop").status_code == 401
        assert client.get("/admin/mailer/closed-loop", headers=admin_headers()).status_code == 200
    finally:
        _cleanup(marker)
