from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app.launch_repair_cycle as cycle_module
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.launch_repair_cycle import run_launch_repair_cycle
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup() -> None:
    execute("DELETE FROM system_events WHERE type = 'launch_repair.cycle'")


def _scoreboard(score: int, blocker_count: int, codes: list[str] | None = None) -> dict:
    return {
        "state": "NOT_LAUNCH_READY" if blocker_count else "WARMUP_SCHEDULED_NO_OUTREACH",
        "score": score,
        "blocker_count": blocker_count,
        "blockers": [{"code": code, "severity": "high"} for code in (codes or [])],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def test_launch_repair_cycle_endpoint_requires_auth_and_defaults_to_dry_run():
    assert client.post("/admin/launch-repair-cycle", json={"limit": 5}).status_code == 401
    response = client.post("/admin/launch-repair-cycle", json={"limit": 5}, headers=admin_headers())
    assert response.status_code == 200
    cycle = response.json()["cycle"]
    assert cycle["execute_safe_auto"] is False
    assert cycle["execution"]["status"] == "dry_run"
    assert cycle["send_mail"] is False
    assert cycle["live_outreach_allowed"] is False
    assert cycle["raw_recipient_addresses_included"] is False
    assert cycle["secrets_included"] is False


def test_launch_repair_cycle_dry_run_compares_before_after_without_execution(monkeypatch):
    monkeypatch.setattr(cycle_module, "launch_readiness_scoreboard", lambda limit=25: _scoreboard(50, 2, ["mail_qa_not_pass", "checkout_not_ready"]))
    monkeypatch.setattr(
        cycle_module,
        "launch_repair_plan",
        lambda limit=25: {"status": "planned", "safe_auto_count": 1, "review_required_count": 1, "actions": [{"blocker_code": "mail_qa_not_pass"}]},
    )
    monkeypatch.setattr(
        cycle_module,
        "execute_launch_repair_plan",
        lambda limit=25, dry_run=True: {"status": "dry_run", "executed_count": 0, "review_task_count": 0, "send_mail": False, "smtp_called": False, "live_outreach_allowed": False},
    )
    result = run_launch_repair_cycle(5, execute_safe_auto=False)
    assert result["decision"] == "DRY_RUN_READY"
    assert result["execution"]["executed_count"] == 0
    assert result["score_delta"] == 0
    assert result["send_mail"] is False


def test_launch_repair_cycle_records_progress_when_safe_auto_improves_state(monkeypatch):
    calls = {"count": 0}

    def scoreboard(limit=25):
        calls["count"] += 1
        if calls["count"] == 1:
            return _scoreboard(60, 1, ["mail_qa_not_pass"])
        return _scoreboard(85, 0, [])

    try:
        monkeypatch.setattr(cycle_module, "launch_readiness_scoreboard", scoreboard)
        monkeypatch.setattr(
            cycle_module,
            "launch_repair_plan",
            lambda limit=25: {"status": "planned", "safe_auto_count": 1, "review_required_count": 0, "actions": [{"blocker_code": "mail_qa_not_pass"}]},
        )
        monkeypatch.setattr(
            cycle_module,
            "execute_launch_repair_plan",
            lambda limit=25, dry_run=True: {"status": "executed", "executed_count": 1, "review_task_count": 0, "send_mail": False, "smtp_called": False, "live_outreach_allowed": False},
        )
        result = run_launch_repair_cycle(5, execute_safe_auto=True)
        assert result["decision"] == "NO_SEND_PROGRESS_RECORDED"
        assert result["score_delta"] == 25
        assert result["blocker_delta"] == 1
        assert fetch_one("SELECT id FROM system_events WHERE type = 'launch_repair.cycle' ORDER BY created_at DESC LIMIT 1")
    finally:
        _cleanup()


def test_launch_repair_cycle_blocks_send_flag_regression(monkeypatch):
    try:
        monkeypatch.setattr(cycle_module, "launch_readiness_scoreboard", lambda limit=25: {**_scoreboard(90, 0, []), "live_outreach_allowed": True})
        monkeypatch.setattr(cycle_module, "launch_repair_plan", lambda limit=25: {"status": "no_blockers", "safe_auto_count": 0, "review_required_count": 0, "actions": []})
        monkeypatch.setattr(
            cycle_module,
            "execute_launch_repair_plan",
            lambda limit=25, dry_run=True: {"status": "executed", "executed_count": 0, "review_task_count": 0, "send_mail": False, "smtp_called": False, "live_outreach_allowed": False},
        )
        result = run_launch_repair_cycle(5, execute_safe_auto=True)
        assert result["decision"] == "FAIL_SEND_FLAG_REGRESSION"
        assert result["live_outreach_allowed"] is False
    finally:
        _cleanup()


def test_launch_repair_cycle_agent_is_dry_run_no_send():
    run = run_agent("launch_repair_cycle_agent", {"limit": 5})
    assert run["status"] == "completed"
    assert run["result_json"]["execution"]["status"] == "dry_run"
    assert run["result_json"]["send_mail"] is False
    assert run["result_json"]["smtp_called"] is False
    assert run["result_json"]["live_outreach_allowed"] is False
