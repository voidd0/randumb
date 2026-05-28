from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.db import fetch_one
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
    assert result["run"]["step_count"] >= 9
    assert any(step["name"] == "canary_batch_quality_pass" for step in result["result"]["steps"])
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
