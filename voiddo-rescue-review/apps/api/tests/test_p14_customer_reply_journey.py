from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.customer_journey import customer_journey_snapshot
from app.db import execute, fetch_one
from app.main import app
from app.p0 import admin_metrics_from_db, handle_paddle_event
from app.reply_actions import plan_reply_action


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM customer_journey_snapshots WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM codex_tasks WHERE input_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM onboarding_tasks WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM fix_requests WHERE evidence_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM payments WHERE paddle_transaction_id LIKE %s", (f"%{token}%",))
    execute("DELETE FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s", (f"%{token}%", f"%{token}%"))


def _paid_customer(token: str) -> str:
    result = handle_paddle_event(
        {
            "event_type": "transaction.paid",
            "data": {
                "id": f"txn_p14_{token}",
                "customer_id": f"ctm_p14_{token}",
                "customer": {"email": f"buyer-p14-{token}@voiddorescue.local"},
                "custom_data": {"product_key": "contact_form_repair"},
                "details": {"totals": {"total": "9900", "currency_code": "USD"}},
            },
        },
        provisioning_paused=False,
    )
    assert "payment_recorded" in result["actions"]
    customer = fetch_one("SELECT id FROM customers WHERE paddle_customer_id = %s", (f"ctm_p14_{token}",))
    assert customer is not None
    return str(customer["id"])


def test_customer_journey_creates_fix_codex_task_and_dashboard_payload():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _paid_customer(token)
        journey = customer_journey_snapshot(customer_id=customer_id)
        payload = journey["result_json"]
        assert payload["dashboard_ready"] is True
        assert payload["fix_requests"][0]["codex_task_id"]
        assert payload["onboarding"][0]["task_type"] == "payment_onboarding"
        fix = fetch_one("SELECT codex_task_id FROM fix_requests WHERE customer_id = %s", (customer_id,))
        assert fix["codex_task_id"] is not None
    finally:
        _cleanup(token)


def test_customer_journey_default_snapshot_selects_latest_customer_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _paid_customer(token)
        journey = customer_journey_snapshot()
        assert journey["result_json"]["dashboard_ready"] is True
        assert journey["result_json"]["send_mail"] is False
        assert journey["customer_id"] == uuid.UUID(customer_id)
    finally:
        _cleanup(token)


def test_customer_journey_admin_endpoint_requires_auth_and_returns_fix_queue():
    token = uuid.uuid4().hex[:8]
    try:
        customer_id = _paid_customer(token)
        assert client.get(f"/admin/customers/{customer_id}/journey").status_code == 401
        response = client.get(f"/admin/customers/{customer_id}/journey", headers=admin_headers())
        assert response.status_code == 200
        data = response.json()["journey"]["result_json"]
        assert data["fix_requests"]
    finally:
        _cleanup(token)


def test_admin_metrics_include_mailer_control_room_and_customer_journey():
    metrics = admin_metrics_from_db()
    assert "latest_mailer_status" in metrics
    assert "customer_journey_snapshots" in metrics
    assert "clean_window_recovery_runs" in metrics
    assert "production" in metrics
    assert "qa_artifacts" in metrics
    assert "real_leads_total" in metrics["production"]
    assert "test_like_campaign_previews" in metrics["qa_artifacts"]


def test_reply_matrix_safe_categories_prepare_only_no_send():
    cases = [
        ("Price", "How much does it cost?", "ask_price", "prepare_safe_reply_draft"),
        ("Details", "What did you find in the screenshot?", "ask_details", "prepare_safe_reply_draft"),
        ("Wrong person", "I am not the right person, contact someone else", "wrong_person", "prepare_safe_reply_draft"),
        ("Unsubscribe", "Please unsubscribe and stop emailing", "unsubscribe", "suppress_sender_and_confirm_when_mail_qa_passes"),
    ]
    for subject, body, expected, action in cases:
        plan = plan_reply_action(subject, body, "support@voiddorescue.com")
        assert plan["classification"] == expected
        assert plan["safe_action"] == action
        assert plan["human_review_required"] is False


def test_reply_matrix_unsafe_categories_stop_thread():
    cases = [
        ("Angry", "This is spam and I will report you", "angry"),
        ("Legal", "My lawyer will send a GDPR complaint", "legal_threat"),
        ("Security", "This was an unauthorized security scan", "security_accusation"),
    ]
    for subject, body, expected in cases:
        plan = plan_reply_action(subject, body, "support@voiddorescue.com")
        assert plan["classification"] == expected
        assert plan["safe_action"] == "stop_thread_create_review_item"
        assert plan["auto_reply_allowed"] is False
        assert plan["human_review_required"] is True


def test_interested_reply_is_stored_without_auto_reply():
    plan = plan_reply_action("Interested", "Yes, we are interested, please fix it", "audit@voiddorescue.com")
    assert plan["classification"] == "interested"
    assert plan["safe_action"] == "store_and_wait"
    assert plan["auto_reply_allowed"] is False
    assert plan["human_review_required"] is False
