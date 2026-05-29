from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

import app.autonomous_agents as agents_module
import app.revenue_autonomy_gap as gap_module
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.revenue_autonomy_gap import create_revenue_autonomy_gap_actions, revenue_autonomy_gap_snapshot


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup_token(token: str) -> None:
    execute("DELETE FROM self_operating_cycles WHERE scope LIKE %s OR result_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM self_fix_tasks WHERE title LIKE %s OR evidence_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM self_build_queue WHERE title LIKE %s OR acceptance_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM self_learning_events WHERE lesson LIKE %s OR payload_json::text LIKE %s", (f"%{token}%", f"%{token}%"))


def test_revenue_autonomy_gap_snapshot_is_redacted_and_no_send():
    snapshot = revenue_autonomy_gap_snapshot(target_mrr_cents=500_000, approved_preview_target=110)
    assert snapshot["target_mrr_cents"] == 500_000
    assert snapshot["send_mail"] is False
    assert snapshot["smtp_called"] is False
    assert snapshot["live_outreach_allowed"] is False
    assert snapshot["raw_recipient_addresses_included"] is False
    assert snapshot["secrets_included"] is False
    assert "gaps" in snapshot


def test_revenue_autonomy_gap_actions_are_idempotent_for_custom_gap(monkeypatch):
    token = uuid.uuid4().hex[:8]

    def fake_snapshot(target_mrr_cents: int = 500_000, approved_preview_target: int = 110, assumed_conversion_rate: float = 0.015):
        return {
            "status": "gap",
            "target_mrr_cents": target_mrr_cents,
            "current_real_mrr_cents": 0,
            "real_customer_count": 0,
            "approved_previews": 0,
            "ready_candidates": 0,
            "active_scout_sources": 0,
            "recent_scout_accepted_24h": 0,
            "recent_audits_24h": 0,
            "launch_readiness_state": "PREVIEW_PIPELINE_READY_NO_OUTREACH",
            "gaps": [{"code": f"qa_{token}_gap", "severity": "high"}],
            "gap_count": 1,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }

    monkeypatch.setattr(gap_module, "revenue_autonomy_gap_snapshot", fake_snapshot)
    try:
        first = create_revenue_autonomy_gap_actions(apply=True)
        second = create_revenue_autonomy_gap_actions(apply=True)
        assert first["actions_created"] >= 2
        assert second["actions_created"] == 0
        tasks = fetch_one("SELECT count(*) AS count FROM self_fix_tasks WHERE title LIKE %s", (f"%{token}%",))
        lessons = fetch_one("SELECT count(*) AS count FROM self_learning_events WHERE lesson LIKE %s", (f"%{token}%",))
        assert tasks["count"] == 1
        assert lessons["count"] == 1
    finally:
        _cleanup_token(token)


def test_revenue_gap_mrr_queues_broader_no_send_revenue_modules(monkeypatch):
    token = uuid.uuid4().hex[:8]

    def fake_snapshot(target_mrr_cents: int = 500_000, approved_preview_target: int = 110, assumed_conversion_rate: float = 0.015):
        return {
            "status": "gap",
            "target_mrr_cents": target_mrr_cents,
            "current_real_mrr_cents": 0,
            "real_customer_count": 0,
            "approved_previews": 120,
            "ready_candidates": 120,
            "active_scout_sources": 10,
            "recent_scout_accepted_24h": 10,
            "recent_audits_24h": 10,
            "launch_readiness_state": "CHECKOUT_READY_NOT_WARMED",
            "gaps": [{"code": "mrr_below_target", "severity": "critical", "token": token}],
            "gap_count": 1,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }

    monkeypatch.setattr(gap_module, "revenue_autonomy_gap_snapshot", fake_snapshot)
    try:
        result = create_revenue_autonomy_gap_actions(apply=True)
        modules = {item.get("module") for item in result["actions"] if item["action"] == "self_build_queued"}
        assert modules >= {
            "conversion_pipeline",
            "checkout_conversion",
            "offer_economics",
            "visual_conversion_quality",
            "mailer_policy",
            "daily_loop_readiness",
        }
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
    finally:
        _cleanup_token(token)


def test_revenue_autonomy_gap_endpoint_and_agents_are_admin_gated(monkeypatch):
    token = uuid.uuid4().hex[:8]
    assert client.get("/admin/revenue-autonomy-gap").status_code == 401
    authed = client.get("/admin/revenue-autonomy-gap", headers=admin_headers())
    assert authed.status_code == 200
    assert authed.json()["gap"]["live_outreach_allowed"] is False

    monkeypatch.setattr(
        agents_module,
        "create_revenue_autonomy_gap_actions",
        lambda *args, **kwargs: {
            "status": f"qa-{token}",
            "actions_created": 0,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        },
    )
    monkeypatch.setattr(
        agents_module,
        "revenue_autonomy_gap_snapshot",
        lambda *args, **kwargs: {
            "status": f"qa-{token}",
            "gap_count": 0,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        },
    )
    action_agent = run_agent("revenue_autonomy_gap_agent", {"apply": True})
    snapshot_agent = run_agent("revenue_autonomy_gap_snapshot_agent")
    assert action_agent["status"] == "completed"
    assert snapshot_agent["status"] == "completed"
    assert action_agent["result_json"]["live_outreach_allowed"] is False
    assert snapshot_agent["result_json"]["live_outreach_allowed"] is False
