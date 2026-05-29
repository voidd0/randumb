from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app.canary_scale_plan as scale_module
from app.autonomous_agents import run_agent
from app.canary_scale_plan import canary_scale_plan
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _patch_clean_dependencies(monkeypatch, *, sent: int = 6, queued: int = 14, blocked: int = 0):
    def fake_count(query: str, params=()):
        normalized = " ".join(query.split()).lower()
        if "status = 'sent'" in normalized:
            return sent
        if "status = 'queued'" in normalized:
            return queued
        if "status in ('failed', 'blocked', 'transport_blocked')" in normalized:
            return blocked
        if "status = 'preview'" in normalized:
            return 100
        if "from inbox_threads" in normalized:
            return 2
        if "from email_events" in normalized:
            return 1
        return 0

    def fake_fetch_one(query: str, params=()):
        normalized = " ".join(query.split()).lower()
        if "min(sent_at)" in normalized:
            return {"first_sent_at": "2026-05-29T05:42:00Z"}
        if "order by om.sent_at" in normalized:
            return {"id": "00000000-0000-0000-0000-000000000001", "sent_at": "2026-05-29T07:45:00Z", "recipient_domain": "example.com"}
        return {}

    monkeypatch.setattr(scale_module, "_count", fake_count)
    monkeypatch.setattr(scale_module, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(scale_module, "latest_mail_qa_decision", lambda: "PASS")
    monkeypatch.setattr(
        scale_module,
        "mail_signal_summary",
        lambda _hours: {
            "bounce_or_dsn_count": 0,
            "rate_limit_count": 0,
            "spam_signal_count": 0,
            "mail_auth_failure_count": 0,
        },
    )
    monkeypatch.setattr(scale_module, "mail_send_compliance_snapshot", lambda _hours: {"decision": "PASS"})
    monkeypatch.setattr(scale_module, "launch_readiness_scoreboard", lambda _limit: {"state": "LIVE_OUTREACH_READY", "score": 100, "blocker_count": 0})


def test_canary_scale_plan_continues_existing_queued_canary(monkeypatch):
    _patch_clean_dependencies(monkeypatch, sent=6, queued=14)
    result = canary_scale_plan(20, 40, store=False)
    assert result["decision"] == "CONTINUE_CURRENT_CANARY"
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert result["queued_count"] == 14
    assert "@" not in str(result)


def test_canary_scale_plan_blocks_on_mail_auth_failure(monkeypatch):
    _patch_clean_dependencies(monkeypatch, sent=6, queued=14)
    monkeypatch.setattr(
        scale_module,
        "mail_signal_summary",
        lambda _hours: {
            "bounce_or_dsn_count": 0,
            "rate_limit_count": 0,
            "spam_signal_count": 0,
            "mail_auth_failure_count": 1,
        },
    )
    result = canary_scale_plan(20, 40, store=False)
    assert result["decision"] == "PAUSE_AND_REVIEW_CANARY"
    assert "recent_mail_auth_failure" in result["blockers"]
    assert result["send_mail"] is False


def test_canary_scale_plan_ready_for_next_batch_only_after_clean_completion(monkeypatch):
    _patch_clean_dependencies(monkeypatch, sent=20, queued=0)
    result = canary_scale_plan(20, 40, store=False)
    assert result["decision"] == "READY_FOR_NEXT_BATCH_DRY_RUN"
    assert result["recommended_next_batch_limit"] == 40
    assert result["next_action"] == "prepare_next_batch_preview_and_preflight_only_no_send"


def test_canary_scale_plan_endpoint_requires_admin_and_is_no_send(monkeypatch):
    _patch_clean_dependencies(monkeypatch, sent=6, queued=14)
    monkeypatch.setattr(scale_module, "execute", lambda *args, **kwargs: {"id": "stored"})
    assert client.get("/admin/outreach/live-queue/scale-plan").status_code == 401
    response = client.get("/admin/outreach/live-queue/scale-plan", headers=admin_headers())
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["send_mail"] is False
    assert plan["raw_recipient_addresses_included"] is False


def test_canary_scale_plan_agent_is_no_send(monkeypatch):
    import app.autonomous_agents as agents_module

    monkeypatch.setattr(
        agents_module,
        "canary_scale_plan",
        lambda canary_limit, next_batch_limit, store=True: {
            "send_mail": False,
            "live_outreach_allowed": False,
            "decision": "READY_FOR_NEXT_BATCH_DRY_RUN",
        },
    )
    result = run_agent("canary_scale_plan_agent", {"canary_limit": 20, "next_batch_limit": 40})
    assert result["status"] == "completed"
    assert result["result_json"]["send_mail"] is False
    assert result["result_json"]["live_outreach_allowed"] is False
    assert result["result_json"]["decision"] == "READY_FOR_NEXT_BATCH_DRY_RUN"
