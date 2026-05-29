from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app.canary_clean_window_forecast as forecast_module
from app.autonomous_agents import run_agent
from app.canary_clean_window_forecast import canary_clean_window_forecast
from app.main import app
from app.p0 import execute_owner_command, parse_owner_command


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_canary_clean_window_forecast_waits_until_eligible(monkeypatch):
    now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=2)

    def fake_fetch_one(query: str, params=()):
        if "FROM mail_signals" in query:
            return {"now_at": now, "last_signal_at": last, "signal_count": 1}
        return {"count": 0}

    monkeypatch.setattr(forecast_module, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(
        forecast_module,
        "mail_signal_summary",
        lambda _hours: {"bounce_or_dsn_count": 1, "rate_limit_count": 0, "spam_signal_count": 0, "mail_auth_failure_count": 0},
    )
    monkeypatch.setattr(forecast_module, "runtime_control_enabled", lambda _key: True)
    result = canary_clean_window_forecast(24, store=False)
    assert result["status"] == "waiting_clean_window"
    assert result["seconds_remaining"] == 22 * 60 * 60
    assert result["next_action"] == "wait_until_eligible_after_then_rerun_mail_qa_and_resume_plan"
    assert result["send_mail"] is False


def test_canary_clean_window_forecast_clean_recommends_resume(monkeypatch):
    now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        forecast_module,
        "fetch_one",
        lambda query, params=(): {"now_at": now, "last_signal_at": None, "signal_count": 0} if "FROM mail_signals" in query else {"count": 8},
    )
    monkeypatch.setattr(
        forecast_module,
        "mail_signal_summary",
        lambda _hours: {"bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0, "mail_auth_failure_count": 0},
    )
    monkeypatch.setattr(forecast_module, "runtime_control_enabled", lambda _key: True)
    result = canary_clean_window_forecast(24, store=False)
    assert result["status"] == "clean"
    assert result["seconds_remaining"] == 0
    assert result["next_action"] == "run_canary_resume_plan_apply_true"


def test_canary_clean_window_endpoint_requires_admin():
    assert client.get("/admin/outreach/live-queue/clean-window").status_code == 401
    response = client.get("/admin/outreach/live-queue/clean-window", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["forecast"]["send_mail"] is False


def test_canary_clean_window_agent_and_owner_command_are_no_send(monkeypatch):
    import app.autonomous_agents as agents_module
    import app.canary_clean_window_forecast as owner_module

    payload = {"status": "waiting_clean_window", "send_mail": False, "live_outreach_allowed": False}
    monkeypatch.setattr(agents_module, "canary_clean_window_forecast", lambda window_hours=24, store=True: payload)
    result = run_agent("canary_clean_window_forecast_agent", {"window_hours": 24})
    assert result["result_json"]["send_mail"] is False

    monkeypatch.setattr(owner_module, "canary_clean_window_forecast", lambda window_hours=24, store=True: payload)
    parsed = parse_owner_command(os.environ.get("OWNER_COMMAND_EMAIL", "owner@example.test"), "SHOW CANARY CLEAN WINDOW", "")
    assert parsed["risk_level"] == "SAFE_AUTO"
    executed = execute_owner_command(parsed)
    assert executed["action"] == "canary_clean_window_status"
    assert executed["forecast"]["send_mail"] is False

