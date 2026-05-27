from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

import app.lead_discovery as discovery_module
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.lead_discovery import lead_discovery_target_plan, overpass_lead_discovery
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(name: str) -> None:
    execute("DELETE FROM scout_source_readiness_checks WHERE source_id IN (SELECT id FROM scout_sources WHERE name = %s)", (name,))
    execute("DELETE FROM scout_sources WHERE name = %s", (name,))
    execute("DELETE FROM agent_runs WHERE agent = 'overpass_lead_discovery_agent' AND created_at >= now() - interval '2 hours'")


def test_overpass_lead_discovery_dry_run_is_no_send():
    result = overpass_lead_discovery("US", "Boise", "dentists", "en", 10, dry_run=True)
    assert result["status"] == "dry_run"
    assert result["country"] == "US"
    assert result["city"] == "Boise"
    assert "query_preview" in result
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False
    assert result["raw_recipient_addresses_included"] is False
    assert result["secrets_included"] is False


def test_target_plan_prioritizes_first_tier_english_markets():
    plan = lead_discovery_target_plan()
    countries = [target["country"] for target in plan["targets"]]
    assert plan["primary_tier"] == "US_UK_AU_NZ_CA_IE"
    assert plan["depth_strategy"] == "regional_and_secondary_cities_first"
    assert plan["first_tier_market_count"] >= 50
    assert countries[:8] == ["US"] * 8
    assert {"US", "UK", "AU", "NZ", "CA", "IE"}.issubset(set(countries))
    assert plan["default_target"]["country"] == "US"
    assert plan["default_target"]["city"] == "Boise"
    assert all(target["country"] not in {"IL", "EE"} for target in plan["targets"])
    secondary = lead_discovery_target_plan(include_secondary=True)
    secondary_countries = {target["country"] for target in secondary["targets"]}
    assert {"IL", "EE"}.issubset(secondary_countries)


def test_overpass_lead_discovery_creates_redacted_source_from_public_rows(monkeypatch):
    token = uuid.uuid4().hex[:8]
    city = f"TestCity{token}"
    name = f"overpass-EE-{city}-dentists"
    monkeypatch.setitem(discovery_module.CITY_AREAS, ("EE", city.lower()), city)
    monkeypatch.setattr(
        discovery_module,
        "_fetch_overpass",
        lambda query: {
            "elements": [
                {
                    "type": "node",
                    "id": 123,
                    "tags": {
                        "name": f"P69 Clinic {token}",
                        "website": f"https://p69-{token}.example.test",
                        "contact:email": f"hello@p69-{token}.example.test",
                    },
                }
            ]
        },
    )
    try:
        result = overpass_lead_discovery("EE", city, "dentists", "en", 10, dry_run=False)
        assert result["status"] == "source_created"
        assert result["found_count"] == 1
        assert result["with_email_count"] == 1
        assert result["created_scout_runs"] == 0
        assert result["created_scanner_jobs"] == 0
        assert result["raw_recipient_addresses_included"] is False
        source = fetch_one("SELECT id, config_json FROM scout_sources WHERE id = %s", (result["source_id"],))
        assert source
        assert "csv" in source["config_json"]
        assert f"hello@p69-{token}" not in str(result)
    finally:
        _cleanup(name)


def test_overpass_lead_discovery_endpoint_and_agent_are_safe():
    assert client.post("/admin/lead-discovery/overpass", json={"dry_run": True}).status_code == 401
    response = client.post(
        "/admin/lead-discovery/overpass",
        json={"country": "US", "city": "Boise", "niche": "dentists", "limit": 5, "dry_run": True},
        headers=admin_headers(),
    )
    assert response.status_code == 200
    assert response.json()["discovery"]["status"] == "dry_run"
    targets_response = client.get("/admin/lead-discovery/targets", headers=admin_headers())
    assert targets_response.status_code == 200
    assert targets_response.json()["plan"]["primary_tier"] == "US_UK_AU_NZ_CA_IE"
    agent = run_agent("overpass_lead_discovery_agent", {"limit": 5})
    assert agent["status"] == "completed"
    assert agent["result_json"]["status"] == "dry_run"
    assert agent["result_json"]["country"] == "US"
    assert agent["result_json"]["send_mail"] is False
