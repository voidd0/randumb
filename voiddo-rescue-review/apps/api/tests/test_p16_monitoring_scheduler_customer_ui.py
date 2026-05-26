from __future__ import annotations

import os
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient

from app.customer_access import customer_dashboard_by_token, ensure_customer_access_token
from app.db import execute, fetch_one
from app.main import app
from app.monitoring import ensure_monitoring_target, process_due_monitoring_targets
from app.p0 import handle_paddle_event


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{token}%",))
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
                "id": f"txn_p16_{token}",
                "customer_id": f"ctm_p16_{token}",
                "customer": {"email": f"buyer-p16-{token}@voiddorescue.local"},
                "custom_data": {"product_key": "contact_form_repair"},
                "details": {"totals": {"total": "9900", "currency_code": "USD"}},
            },
        },
        provisioning_paused=False,
    )
    row = fetch_one("SELECT id FROM customers WHERE paddle_customer_id = %s", (f"ctm_p16_{token}",))
    assert row
    return str(row["id"])


def _unpause_monitoring(monkeypatch) -> None:
    import app.monitoring as monitoring

    monkeypatch.setattr(monitoring, "get_settings", lambda: SimpleNamespace(global_kill_switch=False, scanning_paused=False))
    monkeypatch.setattr(monitoring, "effective_pause_state", lambda name, default: False)


def test_due_monitoring_scheduler_blocks_when_scanning_paused():
    result = process_due_monitoring_targets(limit=1, dry_run=True)
    assert result["status"] == "blocked_paused"
    assert result["sends_started"] is False


def test_due_monitoring_scheduler_processes_due_target_when_unpaused(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        _unpause_monitoring(monkeypatch)
        customer_id = _customer(token)
        ensure_monitoring_target(customer_id, f"https://monitor-p16-{token}.example.test")
        result = process_due_monitoring_targets(limit=1, dry_run=True)
        assert result["status"] == "completed"
        assert result["processed"] == 1
        assert result["sends_started"] is False
    finally:
        _cleanup(token)


def test_monitoring_scheduler_failure_records_event_and_review_task(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        _unpause_monitoring(monkeypatch)
        import app.monitoring as monitoring

        customer_id = _customer(token)
        target = ensure_monitoring_target(customer_id, f"https://monitor-p16-fail-{token}.example.test")

        def fail_check(target_id: str, dry_run: bool = True):
            raise RuntimeError(f"p16_scheduler_failure_{token}")

        monkeypatch.setattr(monitoring, "run_monitoring_check", fail_check)
        result = process_due_monitoring_targets(limit=1, dry_run=True)
        assert result["failed"] == 1
        event = fetch_one("SELECT id FROM system_events WHERE type = 'monitoring.run_failed' AND payload_json::text LIKE %s", (f"%{target['id']}%",))
        task = fetch_one("SELECT id FROM codex_tasks WHERE type = 'scanner_failed_case' AND input_json::text LIKE %s", (f"%{target['id']}%",))
        assert event
        assert task
    finally:
        _cleanup(token)


def test_admin_monitoring_run_due_endpoint_requires_auth():
    assert client.post("/admin/monitoring/run-due", json={"limit": 1, "dry_run": True}).status_code == 401
    response = client.post("/admin/monitoring/run-due", json={"limit": 1, "dry_run": True}, headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_customer_token_dashboard_payload_hides_internal_task_fields():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _customer(token)
        access = ensure_customer_access_token(customer_id)
        dashboard = customer_dashboard_by_token(access["token"])
        assert dashboard["fix_requests"]
        text = str(dashboard)
        assert "codex_task_id" not in text
        assert "token_hash" not in text
        assert "studio_task_status" in dashboard["fix_requests"][0]
    finally:
        _cleanup(token)


def test_customer_dashboard_token_endpoint_serves_public_payload():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _customer(token)
        access = ensure_customer_access_token(customer_id)
        response = client.get(f"/customer/dashboard/{access['token']}")
        assert response.status_code == 200
        assert response.json()["dashboard"]["customer"]["id"] == customer_id
    finally:
        _cleanup(token)
