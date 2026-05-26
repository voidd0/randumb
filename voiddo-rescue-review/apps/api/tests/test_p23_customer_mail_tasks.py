from __future__ import annotations

from app.db import execute, fetch_one
from app.mailer_action_queue import enqueue_mailer_action, mailer_action_queue_summary, process_mailer_action_queue
from app.p0 import handle_paddle_event


def _cleanup(marker: str) -> None:
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{marker}%",))
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{marker}%",))
    execute("DELETE FROM onboarding_tasks WHERE payload_json::text LIKE %s", (f"%{marker}%",))
    execute("DELETE FROM fix_requests WHERE evidence_json::text LIKE %s", (f"%{marker}%",))
    execute("DELETE FROM payments WHERE paddle_transaction_id LIKE %s", (f"%{marker}%",))
    execute("DELETE FROM subscriptions WHERE paddle_subscription_id LIKE %s", (f"%{marker}%",))
    execute("DELETE FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s", (f"%{marker}%", f"%{marker}%"))


def test_paid_transaction_enqueues_customer_onboarding_action():
    marker = "p23-onboard"
    try:
        result = handle_paddle_event(
            {
                "event_type": "transaction.paid",
                "data": {
                    "id": f"txn_{marker}",
                    "customer_id": f"ctm_{marker}",
                    "customer": {"email": f"buyer-{marker}@voiddorescue.local"},
                    "custom_data": {"product_key": "monitor_monthly"},
                    "details": {"totals": {"total": "1900", "currency_code": "USD"}},
                },
            },
            provisioning_paused=False,
        )
        assert "customer_onboarding_mail_action_queued" in result["actions"]
        row = fetch_one(
            """
            SELECT count(*) AS count
            FROM mailer_action_queue
            WHERE action_type = 'customer_onboarding'
              AND payload_json->>'paddle_transaction_id' = %s
            """,
            (f"txn_{marker}",),
        )
        assert row["count"] == 1
    finally:
        _cleanup(marker)


def test_one_time_fix_purchase_enqueues_fix_action():
    marker = "p23-fix"
    try:
        result = handle_paddle_event(
            {
                "event_type": "transaction.paid",
                "data": {
                    "id": f"txn_{marker}",
                    "customer_id": f"ctm_{marker}",
                    "customer": {"email": f"buyer-{marker}@voiddorescue.local"},
                    "custom_data": {"product_key": "contact_form_repair"},
                    "details": {"totals": {"total": "9900", "currency_code": "USD"}},
                },
            },
            provisioning_paused=False,
        )
        assert "fix_request_mail_action_queued" in result["actions"]
        row = fetch_one(
            """
            SELECT count(*) AS count
            FROM mailer_action_queue
            WHERE action_type = 'fix_request_created'
              AND payload_json->>'paddle_transaction_id' = %s
            """,
            (f"txn_{marker}",),
        )
        assert row["count"] == 1
    finally:
        _cleanup(marker)


def test_customer_mail_action_prepared_but_not_sent_when_signals_block():
    marker = "p23-prepare"
    try:
        enqueue_mailer_action({"action_type": "customer_onboarding", "recipient_email": "customer-p23@example.test", "marker": marker})
        result = process_mailer_action_queue(10)
        action = next(item for item in result["actions"] if item["action_type"] == "customer_onboarding")
        assert action["status"] == "prepared"
        assert action["gate_result_json"]["send_mail"] is False
        assert "customer_mail_sending_flag_false" in action["gate_result_json"]["blockers"]
    finally:
        _cleanup(marker)


def test_customer_email_omitted_from_action_queue_summary():
    marker = "p23-privacy"
    raw = "private-customer-p23@example.test"
    try:
        enqueue_mailer_action({"action_type": "monitoring_report", "recipient_email": raw, "marker": marker})
        summary = mailer_action_queue_summary()
        assert raw not in str(summary)
        assert summary["raw_recipient_addresses_included"] is False
    finally:
        _cleanup(marker)
