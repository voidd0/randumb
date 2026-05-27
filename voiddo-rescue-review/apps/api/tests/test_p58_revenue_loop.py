from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.p0 import handle_paddle_event
from app.revenue_loop import prepare_revenue_loop, revenue_loop_snapshot


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _count(sql: str, params: tuple = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def _cleanup(token: str) -> None:
    execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM mailer_send_ledger WHERE result_json::text LIKE %s OR gate_result_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM recipient_resolver_audit WHERE customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM monitoring_runs WHERE result_json::text LIKE %s OR summary LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM monitoring_targets WHERE site_url LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM customer_journey_snapshots WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM customer_access_tokens WHERE customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM codex_tasks WHERE input_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM onboarding_tasks WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM fix_requests WHERE evidence_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM payments WHERE paddle_transaction_id LIKE %s", (f"%{token}%",))
    execute("DELETE FROM subscriptions WHERE paddle_subscription_id LIKE %s", (f"%{token}%",))
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s", (f"%{token}%", f"%{token}%"))


def _paid_customer(token: str, provisioning_paused: bool = True) -> str:
    result = handle_paddle_event(
        {
            "event_type": "transaction.paid",
            "data": {
                "id": f"txn_p58_{token}",
                "customer_id": f"ctm_p58_{token}",
                "customer": {"email": f"buyer-p58-{token}@voiddorescue.local"},
                "custom_data": {"product_key": "contact_form_repair"},
                "details": {"totals": {"total": "9900", "currency_code": "USD"}},
            },
        },
        provisioning_paused=provisioning_paused,
    )
    assert "payment_recorded" in result["actions"]
    row = fetch_one("SELECT id FROM customers WHERE paddle_customer_id = %s", (f"ctm_p58_{token}",))
    assert row
    return str(row["id"])


def test_revenue_loop_admin_endpoints_require_auth_and_return_no_send_snapshot():
    assert client.get("/admin/revenue-loop").status_code == 401
    response = client.get("/admin/revenue-loop", headers=admin_headers())
    assert response.status_code == 200
    loop = response.json()["revenue_loop"]
    assert loop["safety"]["send_mail"] is False
    assert loop["safety"]["live_outreach_allowed"] is False
    assert loop["safety"]["raw_recipient_addresses_included"] is False
    assert client.post("/admin/revenue-loop/prepare", json={"dry_run": True}).status_code == 401
    prepared = client.post("/admin/revenue-loop/prepare", json={"dry_run": True, "limit": 5}, headers=admin_headers())
    assert prepared.status_code == 200
    assert prepared.json()["revenue_loop"]["status"] == "preview_only"


def test_revenue_loop_dry_run_does_not_create_scanner_or_mail_or_scout_runs():
    before_scanner = _count("SELECT count(*) FROM scanner_jobs")
    before_scout = _count("SELECT count(*) FROM scout_runs")
    before_mail = _count("SELECT count(*) FROM mailer_action_queue")
    result = prepare_revenue_loop(limit=5, dry_run=True)
    assert result["status"] == "preview_only"
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert _count("SELECT count(*) FROM scanner_jobs") == before_scanner
    assert _count("SELECT count(*) FROM scout_runs") == before_scout
    assert _count("SELECT count(*) FROM mailer_action_queue") == before_mail


def test_revenue_loop_prepares_paid_customer_lifecycle_without_raw_email_or_send():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _paid_customer(token, provisioning_paused=True)
        result = prepare_revenue_loop(limit=20, dry_run=False, activate_sources=False, prepare_campaigns=False, prepare_customers=True)
        text = str(result)
        assert f"buyer-p58-{token}@voiddorescue.local" not in text
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
        assert result["customers"]["journey_snapshots_created"] >= 1
        assert result["customers"]["codex_tasks_created_or_confirmed"] >= 1
        assert result["customers"]["mailer_actions_queued_or_confirmed"] >= 2
        assert fetch_one("SELECT codex_task_id FROM fix_requests WHERE customer_id = %s", (customer_id,))["codex_task_id"] is not None
        queued = _count("SELECT count(*) FROM mailer_action_queue WHERE payload_json->>'customer_id' = %s", (customer_id,))
        assert queued >= 2
    finally:
        _cleanup(token)


def test_revenue_loop_separates_real_revenue_from_qa_payments():
    token = uuid.uuid4().hex[:8]
    before = revenue_loop_snapshot(5)["customers"]
    try:
        _paid_customer(token, provisioning_paused=True)
        after = revenue_loop_snapshot(5)["customers"]
        assert after["payment_count"] >= before["payment_count"] + 1
        assert after["qa_payment_count"] >= before["qa_payment_count"] + 1
        assert after["real_payment_count"] == before["real_payment_count"]
        assert after["real_paid_revenue_usd"] == before["real_paid_revenue_usd"]
    finally:
        _cleanup(token)


def test_revenue_loop_blocks_bulk_source_activation_without_explicit_source_id():
    result = prepare_revenue_loop(limit=5, dry_run=False, activate_sources=True, allow_bulk_source_activation=False)
    assert result["status"] == "blocked"
    assert "source_activation_requires_explicit_source_id" in result["blockers"]
    assert result["source_queue"]["status"] == "skipped"
    assert result["send_mail"] is False


def test_revenue_loop_agents_are_registered_and_no_send():
    snapshot_run = run_agent("revenue_loop_snapshot_agent", {"limit": 5})
    assert snapshot_run["status"] == "completed"
    assert snapshot_run["result_json"]["safety"]["send_mail"] is False
    prepare_run = run_agent("revenue_loop_prepare_agent", {"limit": 5})
    assert prepare_run["status"] == "completed"
    assert prepare_run["result_json"]["send_mail"] is False
