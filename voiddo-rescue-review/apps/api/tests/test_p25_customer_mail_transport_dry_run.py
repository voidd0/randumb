from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.db import execute
from app.mailer_action_queue import enqueue_mailer_action, transport_dry_run
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(marker: str) -> None:
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{marker}%",))


def _send_ready_action(marker: str):
    action = enqueue_mailer_action({"action_type": "customer_onboarding", "recipient_email": "p25@example.test", "marker": marker})
    execute("UPDATE mailer_action_queue SET status = 'send_ready' WHERE id = %s", (action["id"],))
    return action


def test_transport_dry_run_does_not_call_smtp():
    marker = "p25-dry-run"
    try:
        _cleanup(marker)
        _send_ready_action(marker)
        result = transport_dry_run(10)
        action = next(item for item in result["actions"] if item["action_type"] == "customer_onboarding")
        assert action["status"] == "dry_run_recorded"
        assert action["result_json"]["smtp_called"] is False
        assert result["send_mail"] is False
    finally:
        _cleanup(marker)


def test_transport_dry_run_records_sanitized_result():
    marker = "p25-sanitized"
    raw = "private-p25@example.test"
    try:
        _cleanup(marker)
        action = enqueue_mailer_action({"action_type": "customer_onboarding", "recipient_email": raw, "marker": marker})
        execute("UPDATE mailer_action_queue SET status = 'send_ready' WHERE id = %s", (action["id"],))
        result = transport_dry_run(10)
        text = str(result)
        assert raw not in text
        recorded = next(item for item in result["actions"] if item["id"] == action["id"])
        assert recorded["result_json"]["raw_recipient_included"] is False
        assert recorded["result_json"]["message_id"].endswith("@voiddorescue.local>")
    finally:
        _cleanup(marker)


def test_transport_dry_run_ignores_non_ready_actions():
    marker = "p25-not-ready"
    try:
        _cleanup(marker)
        enqueue_mailer_action({"action_type": "customer_onboarding", "recipient_email": "p25@example.test", "marker": marker})
        result = transport_dry_run(10)
        assert all(marker not in str(item) for item in result["actions"])
    finally:
        _cleanup(marker)


def test_transport_dry_run_endpoint_requires_auth():
    assert client.post("/admin/mailer/action-queue/transport-dry-run", json={"limit": 1}).status_code == 401
    assert client.post("/admin/mailer/action-queue/transport-dry-run", json={"limit": 1}, headers=admin_headers()).status_code == 200
