from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.customer_access import customer_dashboard_by_token, ensure_customer_access_token
from app.db import execute, fetch_one
from app.main import app
from app.monitoring import ensure_monitoring_target, run_monitoring_check
from app.p0 import admin_metrics_from_db, handle_paddle_event


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM monitoring_runs WHERE result_json::text LIKE %s OR summary LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM monitoring_targets WHERE site_url LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM customer_journey_snapshots WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM customer_access_tokens WHERE customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM codex_tasks WHERE input_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM onboarding_tasks WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM fix_requests WHERE evidence_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM payments WHERE paddle_transaction_id LIKE %s", (f"%{token}%",))
    execute("DELETE FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s", (f"%{token}%", f"%{token}%"))


def _customer(token: str) -> str:
    handle_paddle_event(
        {
            "event_type": "transaction.paid",
            "data": {
                "id": f"txn_p15_{token}",
                "customer_id": f"ctm_p15_{token}",
                "customer": {"email": f"buyer-p15-{token}@voiddorescue.local"},
                "custom_data": {"product_key": "contact_form_repair"},
                "details": {"totals": {"total": "9900", "currency_code": "USD"}},
            },
        },
        provisioning_paused=False,
    )
    row = fetch_one("SELECT id FROM customers WHERE paddle_customer_id = %s", (f"ctm_p15_{token}",))
    assert row
    return str(row["id"])


def test_customer_access_token_opens_only_customer_dashboard():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _customer(token)
        access = ensure_customer_access_token(customer_id)
        assert access["token_created"] is True
        dashboard = customer_dashboard_by_token(access["token"])
        assert dashboard["dashboard_ready"] is True
        assert dashboard["customer"]["id"] == customer_id
        assert dashboard["fix_requests"]
    finally:
        _cleanup(token)


def test_customer_dashboard_endpoint_rejects_bad_token_and_accepts_valid_token():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _customer(token)
        access = ensure_customer_access_token(customer_id)
        assert client.get("/customer/dashboard/not-a-real-token").status_code == 404
        response = client.get(f"/customer/dashboard/{access['token']}")
        assert response.status_code == 200
        assert response.json()["dashboard"]["customer"]["id"] == customer_id
    finally:
        _cleanup(token)


def test_admin_customer_access_token_endpoint_requires_auth():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _customer(token)
        assert client.post(f"/admin/customers/{customer_id}/access-token").status_code == 401
        response = client.post(f"/admin/customers/{customer_id}/access-token", headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["access"]["token_created"] in {True, False}
    finally:
        _cleanup(token)


def test_monitoring_target_and_dry_run_check_record_safe_result():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _customer(token)
        target = ensure_monitoring_target(customer_id, f"https://monitor-{token}.example.test")
        run = run_monitoring_check(str(target["id"]), dry_run=True)
        assert run["status"] == "completed"
        assert run["score"] is not None
        updated = fetch_one("SELECT last_checked_at FROM monitoring_targets WHERE id = %s", (target["id"],))
        assert updated["last_checked_at"] is not None
    finally:
        _cleanup(token)


def test_monitoring_admin_endpoints_require_auth_and_queue_safe_check():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _customer(token)
        assert client.post(f"/admin/customers/{customer_id}/monitoring-targets", json={"site_url": f"https://monitor-{token}.example.test"}).status_code == 401
        response = client.post(f"/admin/customers/{customer_id}/monitoring-targets", json={"site_url": f"https://monitor-{token}.example.test"}, headers=admin_headers())
        assert response.status_code == 200
        target_id = response.json()["target"]["id"]
        run_response = client.post(f"/admin/monitoring/{target_id}/run", json={"dry_run": True}, headers=admin_headers())
        assert run_response.status_code == 200
        assert run_response.json()["run"]["status"] == "completed"
    finally:
        _cleanup(token)


def test_metrics_include_customer_tokens_and_monitoring_runs():
    metrics = admin_metrics_from_db()
    assert "customer_access_tokens" in metrics
    assert "monitoring_runs" in metrics
