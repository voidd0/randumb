from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app.canary_resume_plan as resume_module
from app.autonomous_agents import run_agent
from app.canary_resume_plan import canary_resume_plan
from app.main import app
from app.p0 import execute_owner_command, parse_owner_command


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _patch_clean(monkeypatch, *, paused: bool = True):
    monkeypatch.setattr(
        resume_module,
        "mail_signal_summary",
        lambda _hours: {
            "bounce_or_dsn_count": 0,
            "rate_limit_count": 0,
            "spam_signal_count": 0,
            "mail_auth_failure_count": 0,
        },
    )
    monkeypatch.setattr(resume_module, "_latest_blocking_signal_at", lambda _hours: None)
    monkeypatch.setattr(resume_module, "latest_mail_qa_decision", lambda: "PASS")
    monkeypatch.setattr(resume_module, "mail_send_compliance_snapshot", lambda _hours: {"decision": "PASS"})
    monkeypatch.setattr(
        resume_module,
        "canary_scale_plan",
        lambda canary_limit=20, next_batch_limit=40, store=False: {
            "decision": "CONTINUE_CURRENT_CANARY",
            "queued_count": 7,
            "sent_count": 12,
            "sent_or_bounced_count": 12,
            "smtp_sent_count": 11,
            "bounced_count": 1,
            "blocked_count": 0,
            "blockers": [],
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    monkeypatch.setattr(
        resume_module,
        "_queued_campaign_preflights",
        lambda _limit=20: {
            "campaign_count": 3,
            "allowed_count": 3,
            "blocked_count": 0,
            "blocked_reasons": [],
            "policy_stale_count": 0,
            "current_policy_count": 3,
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    monkeypatch.setattr(resume_module, "runtime_control_enabled", lambda _key: paused)


def test_canary_resume_plan_blocks_recent_bounce_without_clearing_pause(monkeypatch):
    _patch_clean(monkeypatch)
    calls = []
    monkeypatch.setattr(
        resume_module,
        "mail_signal_summary",
        lambda _hours: {
            "bounce_or_dsn_count": 1,
            "rate_limit_count": 0,
            "spam_signal_count": 0,
            "mail_auth_failure_count": 0,
        },
    )
    monkeypatch.setattr(resume_module, "set_runtime_control", lambda *args, **kwargs: calls.append(args))
    result = canary_resume_plan(24, apply=True, store=False)
    assert result["decision"] == "KEEP_PAUSED"
    assert "recent_bounce_or_dsn" in result["blockers"]
    assert calls == []
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert result["sent_or_bounced_count"] == 12
    assert result["smtp_sent_count"] == 11
    assert result["bounced_count"] == 1


def test_canary_resume_plan_clears_pause_only_when_all_gates_pass(monkeypatch):
    _patch_clean(monkeypatch)
    calls = []
    monkeypatch.setattr(resume_module, "set_runtime_control", lambda *args, **kwargs: calls.append(args) or {"ok": True})
    result = canary_resume_plan(24, apply=True, store=False)
    assert result["decision"] == "RESUMED_CANARY"
    assert result["blockers"] == []
    assert calls and calls[0][0] == "pause_outreach" and calls[0][1] is False
    assert result["smtp_called"] is False


def test_canary_resume_plan_blocks_stale_queued_preflight(monkeypatch):
    _patch_clean(monkeypatch)
    monkeypatch.setattr(
        resume_module,
        "_queued_campaign_preflights",
        lambda _limit=20: {
            "campaign_count": 1,
            "allowed_count": 0,
            "blocked_count": 1,
            "blocked_reasons": ["campaign_preflight_policy_stale"],
            "policy_stale_count": 1,
            "current_policy_count": 0,
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    result = canary_resume_plan(24, apply=False, store=False)
    assert result["decision"] == "KEEP_PAUSED"
    assert "queued_campaign_preflight_not_current_pass" in result["blockers"]


def test_canary_resume_plan_endpoint_requires_admin(monkeypatch):
    _patch_clean(monkeypatch)
    monkeypatch.setattr(resume_module, "execute", lambda *args, **kwargs: {"id": "stored"})
    assert client.get("/admin/outreach/live-queue/resume-plan").status_code == 401
    response = client.get("/admin/outreach/live-queue/resume-plan", headers=admin_headers())
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["send_mail"] is False
    assert plan["raw_recipient_addresses_included"] is False


def test_canary_resume_plan_agent_is_no_send(monkeypatch):
    import app.autonomous_agents as agents_module

    monkeypatch.setattr(
        agents_module,
        "canary_resume_plan",
        lambda window_hours=24, apply=False, store=True: {
            "decision": "KEEP_PAUSED",
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    result = run_agent("canary_resume_plan_agent", {"window_hours": 24, "apply": False})
    assert result["status"] == "completed"
    assert result["result_json"]["send_mail"] is False
    assert result["result_json"]["live_outreach_allowed"] is False


def test_owner_command_show_canary_resume_is_safe_auto(monkeypatch):
    monkeypatch.setattr(
        resume_module,
        "canary_resume_plan",
        lambda window_hours=24, apply=False, store=True: {
            "decision": "KEEP_PAUSED",
            "send_mail": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        },
    )
    monkeypatch.setattr(resume_module, "latest_canary_resume_plan_runs", lambda limit=5: {"count": 0, "runs": []})
    parsed = parse_owner_command(os.environ.get("OWNER_COMMAND_EMAIL", "owner@example.test"), "SHOW CANARY RESUME", "")
    assert parsed["risk_level"] == "SAFE_AUTO"
    result = execute_owner_command(parsed)
    assert result["ok"] is True
    assert result["action"] == "canary_resume_status"
    assert result["plan"]["send_mail"] is False
