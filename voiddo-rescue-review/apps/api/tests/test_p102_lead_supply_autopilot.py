from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app.lead_supply_autopilot as supply_module
import app.lead_supply_buildout as buildout_module
from app.autonomous_agents import run_agent, runtime_daily_loop_plan
from app.lead_supply_autopilot import lead_supply_autopilot
from app.lead_supply_buildout import lead_supply_buildout
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _health(approved: int, live_queue: int = 20, source_candidates: int = 0) -> dict:
    return {
        "decision": "STOCKPILE_READY_FOR_CANARY",
        "target_preview_count": 100,
        "canary_count": 20,
        "active_preview_count": approved + 4,
        "approved_preview_count": approved,
        "held_preview_count": 4,
        "rejected_preview_count": 0,
        "unreviewed_preview_count": 0,
        "candidate_count": approved + 6,
        "ready_candidate_count": approved + 5,
        "source_candidate_count": source_candidates,
        "scanner_active_count": 0,
        "live_queue_candidate_count": live_queue,
        "blockers": [],
        "next_actions": ["continue_source_expansion_until_target_preview_count"],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def test_lead_supply_autopilot_snapshot_is_no_send(monkeypatch):
    monkeypatch.setattr(supply_module, "lead_stockpile_health_snapshot", lambda *args: _health(50))
    result = lead_supply_autopilot(apply=False)
    assert result["status"] == "snapshot"
    assert result["decision"] == "SUPPLY_CANARY_READY_BUILD_STOCKPILE_NO_SEND"
    assert result["actions"] == []
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False
    assert result["raw_recipient_addresses_included"] is False


def test_lead_supply_autopilot_applies_enrichment_then_stockpile_without_raw_details(monkeypatch):
    calls: list[str] = []
    snapshots = iter([_health(45), _health(52)])
    monkeypatch.setattr(supply_module, "lead_stockpile_health_snapshot", lambda *args: next(snapshots))
    monkeypatch.setattr(
        supply_module,
        "contact_enrichment_candidates",
        lambda limit: {"candidate_count": 2, "send_mail": False, "live_outreach_allowed": False},
    )

    def _enrich(*args, **kwargs):
        calls.append("enrich")
        return {
            "status": "enriched",
            "candidate_count": 2,
            "scanned_count": 2,
            "enriched_count": 1,
            "skipped_count": 1,
            "results": [
                {"status": "enriched", "selected_hash": "abc123"},
                {"status": "no_safe_public_contact_email"},
            ],
            "send_mail": False,
            "live_outreach_allowed": False,
        }

    def _advance(*args, **kwargs):
        calls.append("stockpile")
        return {
            "status": "completed",
            "before": _health(45),
            "after": _health(52),
            "actions": {
                "executed": [
                    {
                        "name": "regional_lead_discovery_cycle",
                        "result": {"status": "completed", "created_sources": 3, "found_count": 5, "with_email_count": 2},
                    }
                ]
            },
            "send_mail": False,
            "live_outreach_allowed": False,
        }

    monkeypatch.setattr(supply_module, "run_public_contact_page_enrichment", _enrich)
    monkeypatch.setattr(supply_module, "run_lead_stockpile_health", _advance)
    result = lead_supply_autopilot(apply=True, enrichment_limit=2)
    assert calls == ["enrich", "stockpile"]
    assert result["status"] == "completed"
    assert result["actions"][1]["result"]["enriched_count"] == 1
    assert result["actions"][2]["result"]["executed"][0]["created_sources"] == 3
    assert "@" not in str(result)
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False


def test_lead_supply_autopilot_endpoint_and_agent_are_admin_gated(monkeypatch):
    monkeypatch.setattr(supply_module, "lead_stockpile_health_snapshot", lambda *args: _health(100, live_queue=20))
    assert client.get("/admin/lead-supply-autopilot").status_code == 401
    response = client.get("/admin/lead-supply-autopilot", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["supply"]["decision"] == "SUPPLY_TARGET_READY_NO_SEND"
    agent = run_agent("lead_supply_autopilot_agent", {"apply": False})
    assert agent["status"] == "completed"
    assert agent["result_json"]["send_mail"] is False
    assert agent["result_json"]["live_outreach_allowed"] is False


def test_lead_supply_buildout_dry_run_is_no_send(monkeypatch):
    monkeypatch.setattr(buildout_module, "lead_stockpile_health_snapshot", lambda *args: _health(50))
    result = lead_supply_buildout(apply=False)
    assert result["decision"] == "SUPPLY_BUILDOUT_DRY_RUN_NO_SEND"
    assert result["enrichment_limit"] == 0
    assert result["cycles"] == []
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False


def test_lead_supply_buildout_runs_bounded_safe_cycle(monkeypatch):
    snapshots = iter([
        _health(45, source_candidates=1),
        _health(45, source_candidates=1),
        _health(65, source_candidates=0),
        _health(65, source_candidates=0),
        _health(65, source_candidates=0),
    ])
    calls: list[str] = []
    monkeypatch.setattr(buildout_module, "lead_stockpile_health_snapshot", lambda *args: next(snapshots))

    def _advance(*args, **kwargs):
        calls.append("advance")
        return {"status": "completed", "accepted_count": 5, "created_scanner_jobs": 3, "send_mail": False}

    def _watch(*args, **kwargs):
        calls.append("watch")
        return {"status": "idle_no_new_completions", "completed_count": 0, "send_mail": False, "smtp_called": False}

    def _review(*args, **kwargs):
        calls.append("review")
        return {"status": "completed", "send_mail": False}

    def _refresh(*args, **kwargs):
        calls.append("refresh")
        return {"status": "completed", "send_mail": False}

    def _preflight(*args, **kwargs):
        calls.append("preflight")
        return {"status": "completed", "send_mail": False}

    monkeypatch.setattr(buildout_module, "advance_source_to_campaign", _advance)
    monkeypatch.setattr(buildout_module, "scanner_completion_watch", _watch)
    monkeypatch.setattr(buildout_module, "refresh_campaign_previews_if_needed", _refresh)
    monkeypatch.setattr(buildout_module, "auto_review_campaign_previews", _review)
    monkeypatch.setattr(buildout_module, "campaign_preflight_batch", _preflight)

    result = lead_supply_buildout(target_preview_count=100, max_cycles=1, apply=True)
    assert calls == ["advance", "watch", "refresh", "review", "preflight"]
    assert result["cycle_count"] == 1
    assert result["decision"] == "SUPPLY_BUILDOUT_CANARY_READY_NO_SEND"
    assert result["cycles"][0]["actions"][0]["name"] == "advance_source_to_campaign"
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False


def test_lead_supply_buildout_uses_stockpile_expansion_before_regional_fallback(monkeypatch):
    snapshots = iter([
        _health(45, source_candidates=0),
        _health(45, source_candidates=1),
        _health(45, source_candidates=1),
        _health(65, source_candidates=0),
        _health(65, source_candidates=0),
        _health(65, source_candidates=0),
    ])
    calls: list[str] = []
    monkeypatch.setattr(buildout_module, "lead_stockpile_health_snapshot", lambda *args: next(snapshots))

    def _stockpile(*args, **kwargs):
        calls.append("stockpile_expansion")
        return {"status": "completed", "created_sources": 1, "found_count": 3, "non_empty_sources": 1, "send_mail": False}

    def _regional(*args, **kwargs):
        calls.append("regional")
        return {"status": "completed", "created_sources": 1, "found_count": 2, "send_mail": False}

    def _advance(*args, **kwargs):
        calls.append("advance")
        return {"status": "completed", "source_queue": {"queued_count": 1}, "scout_processing": {"processed": 1, "results": [{"found": 3, "accepted": 2, "scanner_jobs": 2}]}, "send_mail": False}

    monkeypatch.setattr(buildout_module, "stockpile_expansion_discovery_cycle", _stockpile)
    monkeypatch.setattr(buildout_module, "regional_lead_discovery_cycle", _regional)
    monkeypatch.setattr(buildout_module, "advance_source_to_campaign", _advance)
    monkeypatch.setattr(buildout_module, "scanner_completion_watch", lambda *args, **kwargs: {"status": "idle_no_new_completions", "send_mail": False})
    monkeypatch.setattr(buildout_module, "refresh_campaign_previews_if_needed", lambda *args, **kwargs: {"status": "completed", "send_mail": False})
    monkeypatch.setattr(buildout_module, "auto_review_campaign_previews", lambda *args, **kwargs: {"status": "completed", "send_mail": False})
    monkeypatch.setattr(buildout_module, "campaign_preflight_batch", lambda *args, **kwargs: {"status": "completed", "send_mail": False})

    result = lead_supply_buildout(target_preview_count=100, max_cycles=1, apply=True)
    assert calls == ["stockpile_expansion", "advance"]
    assert result["cycles"][0]["actions"][0]["name"] == "stockpile_expansion_discovery_cycle"
    assert result["cycles"][0]["actions"][1]["accepted_count"] == 2
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False


def test_lead_supply_buildout_summarizes_nested_source_campaign_counts():
    result = buildout_module._action_summary(
        {
            "name": "advance_source_to_campaign",
            "status": "advanced",
            "source_queue": {"queued_count": 1, "created_scanner_jobs": 4},
            "scout_processing": {"processed": 1, "accepted": 3, "found_count": 7},
            "campaign_control_room": {"preview_generation": {"created": 2}},
            "blockers": [],
        }
    )
    assert result["queued_count"] == 1
    assert result["created_scanner_jobs"] == 4
    assert result["processed"] == 1
    assert result["accepted_count"] == 3
    assert result["found_count"] == 7
    assert result["campaign_previews_created"] == 2
    assert result["blocker_count"] == 0
    assert result["error_count"] == 0
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False


def test_lead_supply_buildout_summarizes_nested_scout_processing_results():
    result = buildout_module._action_summary(
        {
            "name": "advance_source_to_campaign",
            "status": "advanced",
            "source_queue": {"queued_count": 1},
            "scout_processing": {
                "processed": 2,
                "results": [
                    {"found": 2, "accepted": 1, "scanner_jobs": 1},
                    {"found": 3, "accepted": 2, "scanner_jobs": 2},
                ],
            },
            "campaign_control_room": {"preview_generation": {"created": 2}},
        }
    )
    assert result["processed"] == 2
    assert result["found_count"] == 5
    assert result["accepted_count"] == 3
    assert result["created_scanner_jobs"] == 3
    assert result["campaign_previews_created"] == 2
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False


def test_lead_supply_buildout_summarizes_discovery_error_types():
    result = buildout_module._action_summary(
        {
            "name": "regional_lead_discovery_cycle",
            "status": "failed",
            "errors": [
                {"country": "UK", "city": "St Albans", "error": "RuntimeError"},
                {"country": "UK", "city": "Guildford", "error": "TimeoutError"},
                {"country": "UK", "city": "Oxford", "error": "RuntimeError"},
            ],
        }
    )
    assert result["error_count"] == 3
    assert result["error_types"] == ["RuntimeError", "TimeoutError"]
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False


def test_lead_supply_buildout_endpoint_and_agent_are_admin_gated():
    assert client.get("/admin/lead-supply-buildout").status_code == 401
    response = client.get("/admin/lead-supply-buildout", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["supply"]["send_mail"] is False
    agent = run_agent("lead_supply_buildout_agent", {"apply": False})
    assert agent["status"] == "completed"
    assert agent["result_json"]["send_mail"] is False
    assert agent["result_json"]["live_outreach_allowed"] is False


def test_runtime_daily_loop_uses_bounded_supply_buildout_not_heavy_stockpile():
    plan = runtime_daily_loop_plan()
    agents = [agent for agent, _payload in plan]
    payloads = dict(plan)
    assert "lead_supply_buildout_agent" in agents
    assert "lead_stockpile_health_advance_agent" not in agents
    assert "regional_lead_discovery_agent" not in agents
    assert "apollo_organization_discovery_agent" not in agents
    assert agents.index("quality_aware_regional_target_plan_agent") < agents.index("lead_supply_buildout_agent")
    assert agents.index("lead_supply_buildout_agent") < agents.index("post_scan_campaign_cycle_agent")
    assert agents.index("post_scan_campaign_cycle_agent") < agents.index("outreach_preview_queue_agent")
    assert payloads["lead_supply_buildout_agent"]["max_cycles"] == 1
    assert payloads["lead_supply_buildout_agent"]["max_seconds"] <= 90
    assert payloads["lead_supply_buildout_agent"]["enrichment_limit"] == 5
    assert payloads["post_scan_campaign_cycle_agent"]["dry_run"] is False
