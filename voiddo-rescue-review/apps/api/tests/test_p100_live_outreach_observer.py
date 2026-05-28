from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.db import execute, fetch_one
from app.main import app
from app.outreach_post_send_observer import outreach_post_send_observer
from app.launch_activation import launch_activation_runbook, rollback_live_outreach
from app.p0 import execute_owner_command, runtime_control_enabled, set_runtime_control


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_post_send_observer_endpoint_requires_admin():
    assert client.get("/admin/outreach/post-send-observer").status_code == 401
    response = client.get("/admin/outreach/post-send-observer", headers=admin_headers())
    assert response.status_code == 200
    payload = response.json()["history"]
    assert payload["send_mail"] is False
    assert payload["live_outreach_allowed"] is False


def test_post_send_observer_blocks_on_recent_bounce_without_raw_addresses():
    token = uuid.uuid4().hex[:10]
    try:
        execute(
            """
            INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, message_id, raw_summary)
            VALUES ('bounce', 'warning', 'p100', 'audit', %s, 'gmail', %s, %s)
            """,
            (f"hash-{token}", f"msg-{token}", f"p100 synthetic bounce {token}"),
        )
        result = outreach_post_send_observer(24, apply_pause=False)
        assert result["send_mail"] is False
        assert result["raw_recipient_addresses_included"] is False
        assert result["result"]["decision"] == "BLOCK_AND_PAUSE_OUTREACH"
        assert "recent_bounce_or_dsn_after_send" in result["result"]["blockers"]
        assert "@" not in str(result)
    finally:
        execute("DELETE FROM mail_signals WHERE raw_summary LIKE %s", (f"%{token}%",))
        execute("DELETE FROM outreach_post_send_observer_runs WHERE result_json::text LIKE %s", (f"%{token}%",))


def test_owner_command_show_live_queue_is_safe_auto_and_redacted():
    result = execute_owner_command({"command": "SHOW LIVE QUEUE", "risk_level": "SAFE_AUTO", "args_json": {}})
    assert result["ok"] is True
    assert result["action"] == "live_queue_status"
    assert result["queue"]["send_mail"] is False
    assert result["queue"]["raw_recipient_addresses_included"] is False
    assert "@" not in str(result["queue"])


def test_owner_command_prepare_live_canary_is_dry_run_and_never_queues():
    before = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    result = execute_owner_command({"command": "PREPARE LIVE CANARY", "risk_level": "MEDIUM_RISK", "args_json": {}})
    after = fetch_one("SELECT count(*) AS count FROM outreach_messages WHERE status = 'queued'")
    assert result["ok"] is True
    assert result["action"] == "live_canary_prepared_dry_run"
    assert result["queue"]["send_mail"] is False
    assert result["queue"]["result"]["staged_count"] == 0
    assert "dry_run_no_messages_staged" in result["queue"]["result"]["blockers"]
    assert after["count"] == before["count"]


def test_owner_command_send_outreach_remains_review_required():
    result = execute_owner_command({"command": "SEND OUTREACH", "risk_level": "HIGH_RISK", "args_json": {}})
    assert result["ok"] is False
    assert result["action"] == "review_required"
    assert result["reason"] == "high_risk_command_blocked"


def test_launch_runbook_is_no_send_and_contains_rollback_env():
    runbook = launch_activation_runbook(5)
    assert runbook["send_mail"] is False
    assert runbook["live_outreach_allowed"] is False
    assert runbook["rollback_env"]["OUTREACH_DRY_RUN"] == "true"
    assert runbook["rollback_env"]["OUTREACH_WORKER_ENABLED"] == "false"
    assert runbook["operator_guard"].startswith("No live activation")


def test_owner_command_show_launch_runbook_is_safe_auto():
    result = execute_owner_command({"command": "SHOW LAUNCH RUNBOOK", "risk_level": "SAFE_AUTO", "args_json": {}})
    assert result["ok"] is True
    assert result["action"] == "launch_runbook"
    assert result["runbook"]["send_mail"] is False
    assert result["runbook"]["live_outreach_allowed"] is False


def test_rollback_live_outreach_sets_persistent_pause_controls():
    previous_outreach = runtime_control_enabled("pause_outreach")
    previous_auto = runtime_control_enabled("pause_auto_replies")
    try:
        result = rollback_live_outreach("p100_test")
        assert result["ok"] is True
        assert result["send_mail"] is False
        assert result["env_change_performed"] is False
        assert runtime_control_enabled("pause_outreach") is True
        assert runtime_control_enabled("pause_auto_replies") is True
    finally:
        set_runtime_control("pause_outreach", previous_outreach, "p100_test_cleanup", "restore")
        set_runtime_control("pause_auto_replies", previous_auto, "p100_test_cleanup", "restore")
