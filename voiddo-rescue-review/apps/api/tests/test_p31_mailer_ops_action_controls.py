from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.mailer_ops_actions import run_mailer_ops_action
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_ops_action_endpoint_requires_auth():
    assert client.get("/admin/mailer/ops-actions").status_code == 401
    assert client.post("/admin/mailer/ops-actions", json={"action": "customer_simulation"}).status_code == 401
    assert client.get("/admin/mailer/ops-actions", headers=admin_headers()).status_code == 200


def test_customer_simulation_ops_action_is_no_send():
    result = run_mailer_ops_action("customer_simulation")
    assert result["result"]["status"] == "completed"
    assert result["result"]["simulation"]["case_count"] == 126
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert result["result"]["raw_recipient_addresses_included"] is False


def test_closed_loop_ops_action_uses_dry_run_transport_only():
    response = client.post("/admin/mailer/ops-actions", json={"action": "closed_loop_dry_run", "limit": 2}, headers=admin_headers())
    assert response.status_code == 200
    payload = response.json()["ops_action"]
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["send_mail"] is False
    assert payload["result"]["smtp_called"] is False
    assert payload["result"]["live_outreach_allowed"] is False


def test_unknown_ops_action_blocks_without_shell_or_send():
    result = run_mailer_ops_action("run_shell")
    assert result["result"]["status"] == "blocked"
    assert result["result"]["reason"] == "unknown_or_unsafe_action"
    assert result["result"]["send_mail"] is False
    assert result["result"]["smtp_called"] is False
    assert result["result"]["live_outreach_allowed"] is False

