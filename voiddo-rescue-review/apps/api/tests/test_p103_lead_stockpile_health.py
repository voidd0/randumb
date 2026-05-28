from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app.lead_stockpile_health as stockpile_module
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.lead_stockpile_health import lead_stockpile_health_snapshot, latest_lead_stockpile_health_runs, run_lead_stockpile_health
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _patch_snapshot_inputs(monkeypatch, *, approved: int = 25, live_candidates: int = 20, source_candidates: int = 0, scanner_active: int = 0) -> None:
    monkeypatch.setattr(
        stockpile_module,
        "_preview_counts",
        lambda: {
            "active_preview_count": approved,
            "approved_preview_count": approved,
            "held_preview_count": 0,
            "rejected_preview_count": 0,
            "unreviewed_preview_count": 0,
        },
    )
    monkeypatch.setattr(
        stockpile_module,
        "_preflight_counts",
        lambda: {"preflight_pass_count": 3, "preflight_failed_count": 0},
    )
    monkeypatch.setattr(
        stockpile_module,
        "_scanner_counts",
        lambda: {"scanner_queued_count": scanner_active, "scanner_running_count": 0, "scanner_failed_count": 0},
    )
    monkeypatch.setattr(
        stockpile_module,
        "source_campaign_operator_snapshot",
        lambda limit=25: {
            "candidate_count": source_candidates,
            "queued_or_running_runs": [],
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    monkeypatch.setattr(
        stockpile_module,
        "campaign_control_room_snapshot",
        lambda limit=100, threshold=70: {
            "candidate_count": max(approved, 1),
            "ready_candidate_count": approved,
            "first_batch_preview_count": approved,
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    monkeypatch.setattr(
        stockpile_module,
        "live_outreach_queue_candidates",
        lambda limit=20: {
            "candidate_count": live_candidates,
            "candidates": [],
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )


def test_lead_stockpile_health_snapshot_decides_canary_ready_without_sending(monkeypatch):
    _patch_snapshot_inputs(monkeypatch, approved=25, live_candidates=20)
    result = lead_stockpile_health_snapshot(50, 20, 100)
    assert result["decision"] == "STOCKPILE_READY_FOR_CANARY"
    assert result["approved_preview_count"] == 25
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False
    assert result["raw_recipient_addresses_included"] is False


def test_lead_stockpile_health_snapshot_points_to_source_advance(monkeypatch):
    _patch_snapshot_inputs(monkeypatch, approved=8, live_candidates=8, source_candidates=2)
    result = lead_stockpile_health_snapshot(50, 20, 100)
    assert result["decision"] == "STOCKPILE_NEEDS_SOURCE_ADVANCE"
    assert "advance_ready_scout_source" in result["next_actions"]
    assert result["send_mail"] is False


def test_lead_stockpile_run_records_evidence_without_apply(monkeypatch):
    _patch_snapshot_inputs(monkeypatch, approved=50, live_candidates=20)
    result = run_lead_stockpile_health(50, 20, 100, apply=False)
    try:
        assert result["status"] == "completed"
        assert result["after"]["decision"] == "STOCKPILE_TARGET_READY"
        assert result["actions"]["apply"] is False
        assert result["actions"]["executed"] == []
        assert result["send_mail"] is False
        row = fetch_one("SELECT decision, approved_preview_count FROM lead_stockpile_health_runs WHERE id = %s", (result["run_id"],))
        assert row["decision"] == "STOCKPILE_TARGET_READY"
        assert int(row["approved_preview_count"]) == 50
        history = latest_lead_stockpile_health_runs(1)
        assert history["runs"][0]["id"] == result["run_id"]
    finally:
        execute("DELETE FROM lead_stockpile_health_runs WHERE id = %s", (result["run_id"],))


def test_lead_stockpile_apply_discovers_sources_when_target_stockpile_is_short(monkeypatch):
    _patch_snapshot_inputs(monkeypatch, approved=25, live_candidates=20, source_candidates=0)
    calls: list[str] = []

    def fake_stockpile_expansion(limit_targets=3, per_target_limit=35, dry_run=False):
        calls.append("stockpile_expansion")
        return {
            "status": "no_stockpile_expansion_targets",
            "selected_count": 0,
            "created_sources": 0,
            "found_count": 0,
            "with_email_count": 0,
            "send_mail": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }

    def fake_discovery(limit_targets=3, per_target_limit=25, dry_run=False):
        calls.append("discovery")
        return {
            "status": "completed",
            "created_sources": 2,
            "found_count": 12,
            "with_email_count": 3,
            "send_mail": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }

    monkeypatch.setattr(stockpile_module, "stockpile_expansion_discovery_cycle", fake_stockpile_expansion)
    monkeypatch.setattr(stockpile_module, "regional_lead_discovery_cycle", fake_discovery)
    monkeypatch.setattr(stockpile_module, "refresh_campaign_previews_if_needed", lambda *args, **kwargs: {"status": "refreshed_no_send", "send_mail": False})
    monkeypatch.setattr(stockpile_module, "auto_review_campaign_previews", lambda *args, **kwargs: {"status": "completed", "send_mail": False})
    monkeypatch.setattr(stockpile_module, "queue_outreach_preview", lambda *args, **kwargs: {"created": 0, "send_mail": False})
    monkeypatch.setattr(stockpile_module, "campaign_preflight_batch", lambda *args, **kwargs: {"status": "completed", "send_mail": False})

    result = run_lead_stockpile_health(50, 20, 100, apply=True)
    try:
        assert calls == ["stockpile_expansion", "discovery"]
        action_names = [item["name"] for item in result["actions"]["executed"]]
        assert "stockpile_expansion_discovery_cycle" in action_names
        assert "regional_lead_discovery_cycle" in action_names
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
    finally:
        execute("DELETE FROM lead_stockpile_health_runs WHERE id = %s", (result["run_id"],))


def test_lead_stockpile_apply_does_not_generic_fallback_after_ranked_target_attempt(monkeypatch):
    _patch_snapshot_inputs(monkeypatch, approved=25, live_candidates=20, source_candidates=0)
    calls: list[str] = []

    monkeypatch.setattr(
        stockpile_module,
        "stockpile_expansion_discovery_cycle",
        lambda *args, **kwargs: {
            "status": "completed",
            "selected_count": 2,
            "created_sources": 2,
            "non_empty_sources": 0,
            "empty_sources": 2,
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    monkeypatch.setattr(stockpile_module, "regional_lead_discovery_cycle", lambda *args, **kwargs: calls.append("regional") or {})
    monkeypatch.setattr(stockpile_module, "refresh_campaign_previews_if_needed", lambda *args, **kwargs: {"status": "refreshed_no_send", "send_mail": False})
    monkeypatch.setattr(stockpile_module, "auto_review_campaign_previews", lambda *args, **kwargs: {"status": "completed", "send_mail": False})
    monkeypatch.setattr(stockpile_module, "queue_outreach_preview", lambda *args, **kwargs: {"created": 0, "send_mail": False})
    monkeypatch.setattr(stockpile_module, "campaign_preflight_batch", lambda *args, **kwargs: {"status": "completed", "send_mail": False})

    result = run_lead_stockpile_health(50, 20, 100, apply=True)
    try:
        assert calls == []
        assert [item["name"] for item in result["actions"]["executed"]].count("stockpile_expansion_discovery_cycle") == 1
        assert "regional_lead_discovery_cycle" not in [item["name"] for item in result["actions"]["executed"]]
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
    finally:
        execute("DELETE FROM lead_stockpile_health_runs WHERE id = %s", (result["run_id"],))


def test_lead_stockpile_admin_and_agents_are_gated_no_send(monkeypatch):
    _patch_snapshot_inputs(monkeypatch, approved=21, live_candidates=20)
    assert client.get("/admin/lead-stockpile-health").status_code == 401
    response = client.get("/admin/lead-stockpile-health", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["health"]["send_mail"] is False
    run_response = client.post("/admin/lead-stockpile-health/run", json={"apply": False}, headers=admin_headers())
    run_id = run_response.json()["health"]["run_id"]
    try:
        assert run_response.status_code == 200
        assert run_response.json()["health"]["send_mail"] is False
        agent = run_agent("lead_stockpile_health_agent", {"limit": 5})
        advance = run_agent("lead_stockpile_health_advance_agent", {"limit": 5, "apply": False})
        assert agent["status"] == "completed"
        assert advance["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
        assert advance["result_json"]["send_mail"] is False
        assert advance["result_json"]["live_outreach_allowed"] is False
        advance_run_id = advance["result_json"]["run_id"]
    finally:
        execute("DELETE FROM lead_stockpile_health_runs WHERE id = %s", (run_id,))
        if "advance_run_id" in locals():
            execute("DELETE FROM lead_stockpile_health_runs WHERE id = %s", (advance_run_id,))
