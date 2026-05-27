from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app.launch_operating_lane as lane_module
from app.autonomous_agents import run_agent
from app.launch_operating_lane import advance_launch_operating_lane, launch_operating_lane_snapshot
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_launch_operating_lane_endpoint_requires_auth_and_is_no_send():
    assert client.get("/admin/launch-operating-lane").status_code == 401
    response = client.get("/admin/launch-operating-lane", headers=admin_headers())
    assert response.status_code == 200
    lane = response.json()["lane"]
    assert "next_action" in lane
    assert lane["send_mail"] is False
    assert lane["smtp_called"] is False
    assert lane["live_outreach_allowed"] is False
    assert lane["raw_recipient_addresses_included"] is False
    assert lane["secrets_included"] is False


def test_launch_operating_lane_prioritizes_safety_over_pipeline(monkeypatch):
    monkeypatch.setattr(lane_module, "launch_readiness_scoreboard", lambda limit=25: {"state": "NOT_LAUNCH_READY", "score": 20, "blocker_count": 2})
    monkeypatch.setattr(
        lane_module,
        "launch_repair_plan",
        lambda limit=25: {
            "actions": [
                {"blocker_code": "campaign_preview_pipeline_empty", "action": "refresh_campaign_control_room_preview_only", "risk": "SAFE_AUTO", "auto_executable": True},
                {"blocker_code": "live_outreach_flags_not_blocked", "action": "create_live_flag_review_task", "risk": "HIGH_RISK", "auto_executable": False},
            ]
        },
    )
    lane = launch_operating_lane_snapshot(5)
    assert lane["top_work_item"]["blocker_code"] == "live_outreach_flags_not_blocked"
    assert lane["top_work_item"]["lane"] == "safety"
    assert lane["top_work_item"]["next_step_type"] == "review_task"
    assert lane["next_action"].startswith("create_review_task:")


def test_launch_operating_lane_exposes_safe_auto_when_high_priority_clean(monkeypatch):
    monkeypatch.setattr(lane_module, "launch_readiness_scoreboard", lambda limit=25: {"state": "NOT_LAUNCH_READY", "score": 70, "blocker_count": 1})
    monkeypatch.setattr(
        lane_module,
        "launch_repair_plan",
        lambda limit=25: {
            "actions": [
                {"blocker_code": "mail_qa_not_pass", "action": "run_mail_qa_without_deliverability_send", "risk": "SAFE_AUTO", "auto_executable": True}
            ]
        },
    )
    lane = launch_operating_lane_snapshot(5)
    assert lane["top_work_item"]["next_step_type"] == "safe_auto"
    assert lane["safe_auto_available"] is True
    assert lane["next_action"] == "run_safe_auto:run_mail_qa_without_deliverability_send"


def test_launch_operating_lane_advance_is_dry_run_by_default(monkeypatch):
    monkeypatch.setattr(lane_module, "launch_operating_lane_snapshot", lambda limit=25: {"safe_auto_available": True, "send_mail": False, "smtp_called": False, "live_outreach_allowed": False})
    monkeypatch.setattr(
        lane_module,
        "run_launch_repair_cycle",
        lambda limit=25, execute_safe_auto=False: {"decision": "DRY_RUN_READY", "execution": {"status": "dry_run"}, "score_delta": 0, "blocker_delta": 0},
    )
    result = advance_launch_operating_lane(5, execute_safe_auto=False)
    assert result["status"] == "dry_run"
    assert result["execute_safe_auto_applied"] is False
    assert result["cycle"]["execution"]["status"] == "dry_run"
    assert result["send_mail"] is False


def test_launch_operating_lane_agents_are_no_send():
    snapshot = run_agent("launch_operating_lane_agent", {"limit": 5})
    advance = run_agent("launch_operating_lane_advance_agent", {"limit": 5})
    assert snapshot["status"] == "completed"
    assert advance["status"] == "completed"
    assert snapshot["result_json"]["send_mail"] is False
    assert advance["result_json"]["send_mail"] is False
    assert advance["result_json"]["execute_safe_auto_applied"] is False
