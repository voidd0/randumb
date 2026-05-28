from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app.lead_supply_autopilot as supply_module
from app.autonomous_agents import run_agent
from app.lead_supply_autopilot import lead_supply_autopilot
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
