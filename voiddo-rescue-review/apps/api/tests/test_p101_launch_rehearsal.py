from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.db import fetch_one
from app.canary_operator_packet import build_canary_operator_packet
from app.canary_send_window_plan import build_canary_send_window_plan
from app.launch_rehearsal import run_launch_rehearsal
from app.main import app
from app.p0 import execute_owner_command


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_launch_rehearsal_endpoint_requires_admin():
    assert client.get("/admin/launch-rehearsal").status_code == 401
    response = client.get("/admin/launch-rehearsal", headers=admin_headers())
    assert response.status_code == 200
    payload = response.json()["history"]
    assert payload["send_mail"] is False
    assert payload["live_outreach_allowed"] is False


def test_launch_rehearsal_is_dry_run_and_records_evidence():
    before = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    result = run_launch_rehearsal(5, apply_pause=False)
    after = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert result["result"]["staged_count"] == 0
    assert result["result"]["sent_count"] == 0
    assert result["result"]["preview_candidate_count"] >= 0
    assert result["run"]["step_count"] >= 11
    assert any(step["name"] == "canary_batch_quality_pass" for step in result["result"]["steps"])
    reply_step = next(step for step in result["result"]["steps"] if step["name"] == "reply_safety_rehearsal_pass")
    assert reply_step["passed"] is True
    assert reply_step["evidence"]["auto_replies_paused"] is True
    inbox_step = next(step for step in result["result"]["steps"] if step["name"] == "inbox_integrity_gate_pass")
    assert inbox_step["passed"] is True
    assert inbox_step["evidence"]["auto_replies_paused"] is True
    assert after["count"] == before["count"]
    assert "@" not in str(result)


def test_owner_command_run_launch_rehearsal_is_medium_risk_no_send():
    before = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    result = execute_owner_command({"command": "RUN LAUNCH REHEARSAL", "risk_level": "MEDIUM_RISK", "args_json": {}})
    after = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    assert result["ok"] is True
    assert result["action"] == "launch_rehearsal"
    assert result["rehearsal"]["send_mail"] is False
    assert result["rehearsal"]["result"]["sent_count"] == 0
    assert after["count"] == before["count"]


def test_canary_operator_packet_is_redacted_and_no_send():
    before = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    packet = build_canary_operator_packet(5, store=True, run_checkout_simulation=False)
    after = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    assert packet["send_mail"] is False
    assert packet["live_outreach_allowed"] is False
    assert packet["secrets_included"] is False
    assert packet["live_outreach_sent_count"] == 0
    assert packet["rehearsal_sent_count"] == 0
    assert "@" not in str(packet)
    assert after["count"] == before["count"]


def test_canary_send_window_plan_is_no_send_and_rate_limited():
    before = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    plan = build_canary_send_window_plan(5, store=True)
    after = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    assert plan["send_mail"] is False
    assert plan["live_outreach_allowed"] is False
    assert plan["planned_count"] <= 5
    assert plan["max_hourly_domain_count"] <= 5
    assert plan["daily_cap"] == 20
    assert "@" not in str(plan)
    assert after["count"] == before["count"]
