from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app.launch_repair_planner as planner_module
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.launch_repair_planner import execute_launch_repair_plan, launch_repair_plan
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup() -> None:
    execute("DELETE FROM system_events WHERE type = 'launch_repair.plan_executed'")
    execute(
        "DELETE FROM codex_tasks WHERE input_json->>'source' = 'launch_repair_planner' AND title LIKE %s",
        ("Review launch blocker:%",),
    )
    execute("DELETE FROM agent_runs WHERE agent = 'mailer_digest_trend_guard_agent' AND result_json::text LIKE %s", ("%p64-trend-guard%",))


def test_launch_repair_plan_endpoint_requires_auth_and_is_no_send():
    assert client.get("/admin/launch-repair-plan").status_code == 401
    response = client.get("/admin/launch-repair-plan", headers=admin_headers())
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert "actions" in plan
    assert plan["send_mail"] is False
    assert plan["smtp_called"] is False
    assert plan["live_outreach_allowed"] is False
    assert plan["raw_recipient_addresses_included"] is False
    assert plan["secrets_included"] is False


def test_launch_repair_plan_maps_scoreboard_blockers_to_risk_actions(monkeypatch):
    monkeypatch.setattr(
        planner_module,
        "launch_readiness_scoreboard",
        lambda limit=25: {
            "state": "NOT_LAUNCH_READY",
            "score": 55,
            "blockers": [
                {"code": "mail_qa_not_pass", "severity": "critical"},
                {"code": "checkout_not_ready", "severity": "high"},
                {"code": "huanshu_not_pass", "severity": "high"},
            ],
        },
    )
    plan = launch_repair_plan(5)
    actions = {item["blocker_code"]: item for item in plan["actions"]}
    assert actions["mail_qa_not_pass"]["risk"] == "SAFE_AUTO"
    assert actions["mail_qa_not_pass"]["auto_executable"] is True
    assert actions["checkout_not_ready"]["risk"] == "HIGH_RISK"
    assert actions["checkout_not_ready"]["auto_executable"] is False
    assert actions["huanshu_not_pass"]["risk"] == "MEDIUM_RISK"
    assert plan["send_mail"] is False


def test_launch_repair_execute_dry_run_does_not_execute(monkeypatch):
    monkeypatch.setattr(
        planner_module,
        "launch_repair_plan",
        lambda limit=25: {
            "status": "planned",
            "scoreboard_state": "NOT_LAUNCH_READY",
            "score": 50,
            "blocker_count": 1,
            "actions": [{"blocker_code": "mail_qa_not_pass", "severity": "critical", "action": "run_mail_qa_without_deliverability_send", "risk": "SAFE_AUTO", "handler": "mail_qa_no_send", "auto_executable": True}],
            "safe_auto_count": 1,
            "review_required_count": 0,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        },
    )
    result = execute_launch_repair_plan(5, dry_run=True)
    assert result["status"] == "dry_run"
    assert result["executed_count"] == 0
    assert result["send_mail"] is False


def test_launch_repair_execute_safe_auto_without_sending(monkeypatch):
    try:
        monkeypatch.setattr(
            planner_module,
            "launch_repair_plan",
            lambda limit=25: {
                "status": "planned",
                "scoreboard_state": "NOT_LAUNCH_READY",
                "score": 60,
                "blocker_count": 1,
                "actions": [{"blocker_code": "mailer_policy_score_not_ready", "severity": "high", "action": "recompute_mailer_policy_score", "risk": "SAFE_AUTO", "handler": "mailer_policy_score", "auto_executable": True}],
                "safe_auto_count": 1,
                "review_required_count": 0,
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
                "raw_recipient_addresses_included": False,
                "secrets_included": False,
            },
        )
        monkeypatch.setattr(planner_module, "mailer_digest_trend_guard", lambda: {"decision": "PASS_NO_SEND", "regressions": [], "marker": "p64-trend-guard", "send_mail": False, "smtp_called": False, "live_outreach_allowed": False})
        monkeypatch.setattr(planner_module, "mailer_policy_score", lambda: {"score": 90, "decision": "NO_SEND_OBSERVE", "send_mail": False, "smtp_called": False, "live_outreach_allowed": False})
        monkeypatch.setattr(planner_module, "record_mailer_policy_score_history", lambda agent_run_id, score: {"id": "history-test", "agent_run_id": agent_run_id, "send_mail": False, "smtp_called": False, "live_outreach_allowed": False})
        result = execute_launch_repair_plan(5, dry_run=False)
        assert result["status"] == "executed"
        assert result["executed_count"] == 1
        assert result["review_task_count"] == 0
        assert result["results"][0]["result"]["trend_guard"]["send_mail"] is False
        assert result["results"][0]["result"]["score"]["send_mail"] is False
        assert result["results"][0]["result"]["history"]["send_mail"] is False
        assert fetch_one("SELECT id FROM system_events WHERE type = 'launch_repair.plan_executed' ORDER BY created_at DESC LIMIT 1")
    finally:
        _cleanup()


def test_launch_repair_execute_high_risk_creates_review_task_only(monkeypatch):
    try:
        monkeypatch.setattr(
            planner_module,
            "launch_repair_plan",
            lambda limit=25: {
                "status": "planned",
                "scoreboard_state": "NOT_LAUNCH_READY",
                "score": 40,
                "blocker_count": 1,
                "actions": [{"blocker_code": "checkout_not_ready", "severity": "high", "action": "create_checkout_configuration_review_task", "risk": "HIGH_RISK", "handler": None, "auto_executable": False}],
                "safe_auto_count": 0,
                "review_required_count": 1,
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
                "raw_recipient_addresses_included": False,
                "secrets_included": False,
            },
        )
        result = execute_launch_repair_plan(5, dry_run=False)
        assert result["executed_count"] == 0
        assert result["review_task_count"] == 1
        assert result["results"][0]["status"] in {"created_review_task", "existing_review_task"}
        assert result["send_mail"] is False
    finally:
        _cleanup()


def test_launch_repair_agents_are_no_send():
    plan = run_agent("launch_repair_plan_agent", {"limit": 5})
    executor = run_agent("launch_repair_executor_agent", {"limit": 5})
    assert plan["status"] == "completed"
    assert executor["status"] == "completed"
    assert plan["result_json"]["send_mail"] is False
    assert executor["result_json"]["send_mail"] is False
    assert executor["result_json"]["status"] == "dry_run"
