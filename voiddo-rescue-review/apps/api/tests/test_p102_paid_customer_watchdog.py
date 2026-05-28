from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.customer_revenue_watchdog import run_paid_customer_watchdog
from app.db import execute, fetch_one
from app.main import app
from app.p0 import handle_paddle_event


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM paid_customer_watchdog_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM monitoring_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM monitoring_targets WHERE site_url LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM customer_journey_snapshots WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM codex_tasks WHERE input_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM onboarding_tasks WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM fix_requests WHERE evidence_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM payments WHERE paddle_transaction_id LIKE %s", (f"%{token}%",))
    execute("DELETE FROM subscriptions WHERE paddle_subscription_id LIKE %s", (f"%{token}%",))
    execute("DELETE FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM audits WHERE public_slug LIKE %s", (f"%{token}%",))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s", (f"%{token}%",))


def test_paid_customer_watchdog_endpoint_requires_admin():
    assert client.get("/admin/customers/revenue-watchdog").status_code == 401
    response = client.get("/admin/customers/revenue-watchdog", headers=admin_headers())
    assert response.status_code == 200
    payload = response.json()["history"]
    assert payload["send_mail"] is False
    assert payload["live_outreach_allowed"] is False


def test_paddle_paid_audit_context_and_watchdog_repair_chain():
    token = uuid.uuid4().hex[:10]
    try:
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
            VALUES (%s, 'US', 'Control', 'en', 'dentists', 'p102', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"P102 {token}", f"https://p102-{token}.com", f"p102-{token}.com", f"owner@p102-{token}.com"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
            VALUES (%s, %s, 'p102', 'qualified', 90, 'en', 'US', 'Control', 'dentists')
            RETURNING id
            """,
            (business["id"], f"owner@p102-{token}.com"),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 91, 'P102 paid context audit', %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], f"p102-{token}.com", f"https://p102-{token}.com", f"p102-{token}"),
        )
        event = handle_paddle_event(
            {
                "event_type": "transaction.paid",
                "data": {
                    "id": f"txn_{token}",
                    "customer_id": f"ctm_{token}",
                    "customer": {"email": f"buyer-{token}@example.test"},
                    "custom_data": {"product_key": "contact_form_repair", "audit_slug": f"p102-{token}"},
                    "details": {"totals": {"total": "9900", "currency_code": "USD"}},
                },
            },
            provisioning_paused=False,
        )
        assert "payment_recorded" in event["actions"]
        customer = fetch_one("SELECT id, business_id FROM customers WHERE paddle_customer_id = %s", (f"ctm_{token}",))
        assert str(customer["business_id"]) == str(business["id"])
        fix = fetch_one("SELECT audit_id, codex_task_id FROM fix_requests WHERE customer_id = %s", (customer["id"],))
        assert str(fix["audit_id"]) == str(audit["id"])

        result = run_paid_customer_watchdog(10, repair=True)
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert result["result"]["checked_customer_count"] >= 1
        assert result["result"]["sent_count"] if "sent_count" in result["result"] else 0 == 0
        assert "@" not in str(result["result"]["customers"])
        monitoring = fetch_one("SELECT id FROM monitoring_targets WHERE customer_id = %s AND domain = %s", (customer["id"], f"p102-{token}.com"))
        assert monitoring
        task = fetch_one("SELECT codex_task_id FROM fix_requests WHERE customer_id = %s", (customer["id"],))
        assert task["codex_task_id"]
    finally:
        _cleanup(token)
