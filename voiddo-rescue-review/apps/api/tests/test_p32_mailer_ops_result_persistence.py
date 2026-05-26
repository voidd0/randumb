from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.db import fetch_one
from app.mailer_ops_actions import mailer_ops_action_summary, run_mailer_ops_action
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_ops_run_row_is_written_without_send():
    result = run_mailer_ops_action("customer_simulation")
    run_id = result["run"]["id"]
    row = fetch_one("SELECT action, status, send_mail, smtp_called, live_outreach_allowed FROM mailer_ops_runs WHERE id = %s", (run_id,))
    assert row["action"] == "customer_simulation"
    assert row["status"] == "completed"
    assert row["send_mail"] is False
    assert row["smtp_called"] is False
    assert row["live_outreach_allowed"] is False


def test_ops_summary_omits_raw_recipients():
    run_mailer_ops_action("closed_loop_dry_run", 1)
    summary = mailer_ops_action_summary()
    assert summary["count"] >= 1
    assert summary["raw_recipient_addresses_included"] is False
    assert "@example" not in str(summary)


def test_unknown_ops_action_persists_as_blocked():
    result = run_mailer_ops_action("execute")
    run_id = result["run"]["id"]
    row = fetch_one("SELECT action, status, result_json FROM mailer_ops_runs WHERE id = %s", (run_id,))
    assert row["action"] == "execute"
    assert row["status"] == "blocked"
    assert row["result_json"]["reason"] == "unknown_or_unsafe_action"


def test_ops_summary_endpoint_returns_persisted_runs():
    run_mailer_ops_action("customer_transport_dry_run", 1)
    response = client.get("/admin/mailer/ops-actions", headers=admin_headers())
    assert response.status_code == 200
    payload = response.json()["ops_actions"]
    assert payload["count"] >= 1
    assert payload["send_mail"] is False
    assert payload["live_outreach_allowed"] is False

