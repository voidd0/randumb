from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

import app.lead_discovery as discovery_module
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.lead_discovery import apollo_organization_discovery, lead_discovery_target_plan, overpass_lead_discovery, regional_lead_discovery_cycle, stockpile_expansion_discovery_cycle, stockpile_expansion_target_plan
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(name: str) -> None:
    execute("DELETE FROM scout_source_readiness_checks WHERE source_id IN (SELECT id FROM scout_sources WHERE name = %s)", (name,))
    execute("DELETE FROM scout_sources WHERE name = %s", (name,))
    execute("DELETE FROM agent_runs WHERE agent IN ('overpass_lead_discovery_agent', 'apollo_organization_discovery_agent') AND created_at >= now() - interval '2 hours'")


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
    assert plan["first_tier_market_count"] >= 100
    assert countries[:8] == ["US"] * 8
    assert {"US", "UK", "AU", "NZ", "CA", "IE"}.issubset(set(countries))
    assert plan["default_target"]["country"] == "US"
    assert plan["default_target"]["city"] == "Boise"
    assert all(target["country"] not in {"IL", "EE"} for target in plan["targets"])
    secondary = lead_discovery_target_plan(include_secondary=True)
    secondary_countries = {target["country"] for target in secondary["targets"]}
    assert {"IL", "EE"}.issubset(secondary_countries)


def test_overpass_query_uses_regional_area_aliases_for_au_nz():
    gold_coast_query = discovery_module._overpass_query("AU", "Gold Coast", "dentists", 10)
    tauranga_query = discovery_module._overpass_query("NZ", "Tauranga", "dentists", 10)
    assert 'area["name"="City of Gold Coast"]' in gold_coast_query
    assert 'area["name"="Tauranga City"]' in tauranga_query
    assert "out center tags 10" in gold_coast_query


def test_overpass_query_uses_broader_safe_trade_tags_for_contractors():
    query = discovery_module._overpass_query("CA", "Hamilton", "contractors", 15)
    assert 'node["craft"="plumber"]' in query
    assert 'node["craft"="electrician"]' in query
    assert 'node["craft"="roofer"]' in query
    assert 'node["shop"="doityourself"]' in query
    assert "out center tags 15" in query


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


def test_overpass_lead_discovery_records_empty_source_without_preflight_candidate(monkeypatch):
    token = uuid.uuid4().hex[:8]
    city = f"EmptyCity{token}"
    name = f"overpass-EE-{city}-dentists"
    monkeypatch.setitem(discovery_module.CITY_AREAS, ("EE", city.lower()), city)
    monkeypatch.setattr(discovery_module, "_fetch_overpass", lambda query: {"elements": []})
    try:
        result = overpass_lead_discovery("EE", city, "dentists", "en", 10, dry_run=False)
        assert result["status"] == "empty_source_recorded"
        assert result["source_status"] == "no_rows_public_source"
        assert result["found_count"] == 0
        assert result["empty_target_recorded"] is True
        source = fetch_one("SELECT status, config_json FROM scout_sources WHERE id = %s", (result["source_id"],))
        assert source["status"] == "no_rows_public_source"
        assert source["config_json"]["discovery_result"] == "no_public_rows_found"
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
    finally:
        _cleanup(name)


def test_apollo_organization_discovery_is_gated_and_redacted(monkeypatch):
    token = uuid.uuid4().hex[:8]
    city = f"ApolloCity{token}"
    source_name = f"apollo-org-US-{city}-dentists"
    dry = apollo_organization_discovery("US", city, "dentists", "en", 5, dry_run=True)
    assert dry["status"] == "dry_run"
    assert dry["credits_may_be_used_when_live"] is True
    assert dry["send_mail"] is False
    monkeypatch.setenv("APOLLO_API_KEY", "test-key")
    monkeypatch.delenv("APOLLO_DISCOVERY_ENABLED", raising=False)
    blocked = apollo_organization_discovery("US", city, "dentists", "en", 5, dry_run=False)
    assert blocked["status"] == "blocked_disabled"
    monkeypatch.setenv("APOLLO_DISCOVERY_ENABLED", "true")
    monkeypatch.setattr(
        discovery_module,
        "_fetch_apollo_organizations",
        lambda params, api_key: {
            "organizations": [
                {"name": f"Apollo Dental {token}", "primary_domain": f"apollo-{token}.clinic"},
                {"name": f"Apollo Dental Duplicate {token}", "domain": f"apollo-{token}.clinic"},
            ]
        },
    )
    try:
        live = apollo_organization_discovery("US", city, "dentists", "en", 5, dry_run=False)
        row = fetch_one("SELECT status, config_json FROM scout_sources WHERE name = %s", (source_name,))
        assert live["status"] == "source_created"
        assert live["found_count"] == 1
        assert live["with_email_count"] == 0
        assert live["send_mail"] is False
        assert live["live_outreach_allowed"] is False
        assert row["status"] == "preflight_ready"
        assert row["config_json"]["personal_email_reveal"] is False
        assert row["config_json"]["phone_reveal"] is False
        assert "test-key" not in str(live)
        agent = run_agent("apollo_organization_discovery_agent", {"country": "US", "city": city, "niche": "dentists", "dry_run": True})
        assert agent["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
    finally:
        _cleanup(source_name)


def test_apollo_organization_discovery_returns_structured_provider_error(monkeypatch):
    token = uuid.uuid4().hex[:8]
    monkeypatch.setenv("APOLLO_API_KEY", "test-key")
    monkeypatch.setenv("APOLLO_DISCOVERY_ENABLED", "true")
    monkeypatch.setattr(discovery_module, "_fetch_apollo_organizations", lambda params, api_key: (_ for _ in ()).throw(RuntimeError("apollo_down")))
    result = apollo_organization_discovery("US", f"ApolloErr{token}", "dentists", "en", 5, dry_run=False)
    assert result["status"] == "blocked_provider_error"
    assert result["error_type"] == "RuntimeError"
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert "test-key" not in str(result)
    assert "apollo_down" not in str(result)


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


def test_regional_lead_discovery_cycle_selects_unprocessed_targets(monkeypatch):
    token = uuid.uuid4().hex[:8]
    targets = [
        {"country": "EE", "city": f"CycleA{token}", "language": "en", "niche": "dentists", "priority": 90},
        {"country": "EE", "city": f"CycleB{token}", "language": "en", "niche": "dentists", "priority": 80},
    ]
    monkeypatch.setattr(discovery_module, "FIRST_TIER_TARGETS", targets)
    for target in targets:
        monkeypatch.setitem(discovery_module.CITY_AREAS, ("EE", target["city"].lower()), target["city"])
    try:
        dry = regional_lead_discovery_cycle(2, 5, dry_run=True)
        assert dry["status"] == "dry_run"
        assert dry["selected_count"] == 2
        assert dry["created_sources"] == 0
        assert dry["send_mail"] is False
        assert dry["live_outreach_allowed"] is False

        monkeypatch.setattr(
            discovery_module,
            "_fetch_overpass",
            lambda query: {
                "elements": [
                    {
                        "type": "node",
                        "id": 456,
                        "tags": {
                            "name": f"P69 Cycle {token}",
                            "website": f"https://p69-cycle-{token}.example.test",
                            "contact:email": f"team@p69-cycle-{token}.example.test",
                        },
                    }
                ]
            },
        )
        live = regional_lead_discovery_cycle(2, 5, dry_run=False)
        assert live["status"] == "completed"
        assert live["created_sources"] == 2
        assert live["found_count"] == 2
        assert live["with_email_count"] == 2
        assert live["send_mail"] is False
        assert live["smtp_called"] is False
        assert live["raw_recipient_addresses_included"] is False
        assert f"team@p69-cycle-{token}" not in str(live)
    finally:
        for target in targets:
            _cleanup(f"overpass-EE-{target['city']}-dentists")


def test_stockpile_expansion_target_plan_uses_approved_preview_segments(monkeypatch):
    token = uuid.uuid4().hex[:8]
    monkeypatch.setattr(
        discovery_module,
        "STOCKPILE_EXPANSION_TARGETS",
        [
            {"country": "IE", "city": f"YieldTown{token}", "language": "en", "niche": "local tourism", "priority": 100},
            {"country": "AU", "city": f"EmptyTown{token}", "language": "en", "niche": "contractors", "priority": 90},
        ],
    )

    def fake_fetch_all(sql, params=()):
        if "SELECT name FROM scout_sources" in sql:
            return []
        if "FROM scout_source_performance_scores" in sql:
            return [
                {
                    "country": "IE",
                    "niche": "local tourism",
                    "source_count": 4,
                    "qualified_rate": 0.35,
                    "average_final_score": 67,
                    "email_coverage": 0.9,
                    "issue_signal_rate": 0.8,
                    "promote_count": 2,
                    "pause_count": 0,
                }
            ]
        return [{"country": "IE", "niche": "local tourism", "approved_count": 8, "average_score": 81.5}]

    monkeypatch.setattr(discovery_module, "fetch_all", fake_fetch_all)
    plan = stockpile_expansion_target_plan(5)
    assert plan["status"] == "ready"
    assert plan["selected_count"] == 1
    assert plan["targets"][0]["city"] == f"YieldTown{token}"
    assert plan["targets"][0]["guidance"]["approved_count"] == 8
    assert plan["targets"][0]["guidance"]["source_performance"]["email_coverage"] == 0.9
    assert plan["send_mail"] is False
    assert plan["live_outreach_allowed"] is False


def test_stockpile_expansion_target_plan_ranks_by_quality_and_filters_weak_segments(monkeypatch):
    token = uuid.uuid4().hex[:8]
    monkeypatch.setattr(
        discovery_module,
        "STOCKPILE_EXPANSION_TARGETS",
        [
            {"country": "IE", "city": f"TourismTown{token}", "language": "en", "niche": "local tourism", "priority": 120},
            {"country": "IE", "city": f"DentalTown{token}", "language": "en", "niche": "dentists", "priority": 100},
            {"country": "US", "city": f"WeakTown{token}", "language": "en", "niche": "contractors", "priority": 99},
        ],
    )

    def fake_fetch_all(sql, params=()):
        if "SELECT name FROM scout_sources" in sql:
            return []
        if "FROM scout_source_performance_scores" in sql:
            return [
                {
                    "country": "IE",
                    "niche": "local tourism",
                    "source_count": 8,
                    "qualified_rate": 0.12,
                    "average_final_score": 49,
                    "email_coverage": 0.55,
                    "issue_signal_rate": 0.25,
                    "promote_count": 1,
                    "pause_count": 1,
                },
                {
                    "country": "IE",
                    "niche": "dentists",
                    "source_count": 5,
                    "qualified_rate": 0.4,
                    "average_final_score": 70,
                    "email_coverage": 0.85,
                    "issue_signal_rate": 0.7,
                    "promote_count": 3,
                    "pause_count": 0,
                },
                {
                    "country": "US",
                    "niche": "contractors",
                    "source_count": 5,
                    "qualified_rate": 0.02,
                    "average_final_score": 34,
                    "email_coverage": 0.1,
                    "issue_signal_rate": 0.0,
                    "promote_count": 0,
                    "pause_count": 4,
                },
            ]
        return [
            {"country": "IE", "niche": "local tourism", "approved_count": 7, "average_score": 80},
            {"country": "IE", "niche": "dentists", "approved_count": 3, "average_score": 85},
            {"country": "US", "niche": "contractors", "approved_count": 2, "average_score": 72},
        ]

    monkeypatch.setattr(discovery_module, "fetch_all", fake_fetch_all)
    plan = stockpile_expansion_target_plan(5)
    assert plan["status"] == "ready"
    assert [target["niche"] for target in plan["targets"]] == ["dentists", "local tourism"]
    assert all(target["niche"] != "contractors" for target in plan["targets"])
    assert plan["targets"][0]["expansion_score"] > plan["targets"][1]["expansion_score"]
    assert plan["raw_recipient_addresses_included"] is False


def test_stockpile_expansion_target_plan_explores_strong_performance_only_segments(monkeypatch):
    token = uuid.uuid4().hex[:8]
    monkeypatch.setattr(
        discovery_module,
        "STOCKPILE_EXPANSION_TARGETS",
        [
            {"country": "CA", "city": f"StrongPerf{token}", "language": "en", "niche": "contractors", "priority": 100},
            {"country": "UK", "city": f"WeakPerf{token}", "language": "en", "niche": "dentists", "priority": 99},
        ],
    )

    def fake_fetch_all(sql, params=()):
        if "SELECT name FROM scout_sources" in sql:
            return []
        if "FROM scout_source_performance_scores" in sql:
            return [
                {
                    "country": "CA",
                    "niche": "contractors",
                    "source_count": 1,
                    "qualified_rate": 1.0,
                    "average_final_score": 72,
                    "email_coverage": 1.0,
                    "issue_signal_rate": 1.0,
                    "promote_count": 0,
                    "pause_count": 0,
                },
                {
                    "country": "UK",
                    "niche": "dentists",
                    "source_count": 9,
                    "qualified_rate": 0.04,
                    "average_final_score": 38,
                    "email_coverage": 0.42,
                    "issue_signal_rate": 0.2,
                    "promote_count": 0,
                    "pause_count": 5,
                },
            ]
        return []

    monkeypatch.setattr(discovery_module, "fetch_all", fake_fetch_all)
    plan = stockpile_expansion_target_plan(5)
    assert plan["status"] == "ready"
    assert plan["selected_count"] == 1
    assert plan["targets"][0]["city"] == f"StrongPerf{token}"
    assert plan["targets"][0]["guidance"]["segment_origin"] == "performance_signal"
    assert plan["targets"][0]["guidance"]["approved_count"] == 0
    assert "send_mail" not in plan["targets"][0]
    assert plan["send_mail"] is False
    assert plan["live_outreach_allowed"] is False


def test_stockpile_expansion_discovery_cycle_is_no_send(monkeypatch):
    token = uuid.uuid4().hex[:8]
    city = f"StockpileCity{token}"
    monkeypatch.setattr(
        discovery_module,
        "stockpile_expansion_target_plan",
        lambda limit_targets=3: {
            "status": "ready",
            "selected_count": 1,
            "targets": [{"country": "EE", "city": city, "language": "en", "niche": "dentists", "guidance": {"approved_count": 2}}],
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    monkeypatch.setitem(discovery_module.CITY_AREAS, ("EE", city.lower()), city)
    monkeypatch.setattr(
        discovery_module,
        "_fetch_overpass",
        lambda query: {
            "elements": [
                {
                    "type": "node",
                    "id": 691,
                    "tags": {
                        "name": f"P69 Stockpile Clinic {token}",
                        "website": f"https://p69-stockpile-{token}.clinic",
                        "contact:email": f"hello-stockpile-{token}@p69-stockpile-{token}.clinic",
                    },
                }
            ]
        },
    )
    source_name = f"overpass-EE-{city}-dentists"
    try:
        dry = stockpile_expansion_discovery_cycle(1, 5, dry_run=True)
        assert dry["status"] == "dry_run"
        assert dry["created_sources"] == 0
        live = stockpile_expansion_discovery_cycle(1, 5, dry_run=False)
        assert live["status"] == "completed"
        assert live["created_sources"] == 1
        assert live["with_email_count"] == 1
        assert live["send_mail"] is False
        assert live["smtp_called"] is False
        assert f"hello-stockpile-{token}" not in str(live)
        agent = run_agent("stockpile_expansion_target_plan_agent", {"limit_targets": 1})
        assert agent["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
    finally:
        _cleanup(source_name)


def test_stockpile_expansion_discovery_records_failed_public_source_attempt(monkeypatch):
    token = uuid.uuid4().hex[:8]
    city = f"FailedTarget{token}"
    source_name = f"overpass-CA-{city}-contractors"
    monkeypatch.setattr(
        discovery_module,
        "stockpile_expansion_target_plan",
        lambda limit_targets=3: {
            "status": "ready",
            "selected_count": 1,
            "targets": [{"country": "CA", "city": city, "language": "en", "niche": "contractors", "guidance": {"segment_origin": "performance_signal"}}],
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    monkeypatch.setattr(discovery_module, "_fetch_overpass", lambda query: (_ for _ in ()).throw(RuntimeError("public_source_unavailable")))
    try:
        result = stockpile_expansion_discovery_cycle(1, 5, dry_run=False)
        row = fetch_one("SELECT status, config_json FROM scout_sources WHERE name = %s", (source_name,))
        assert result["status"] == "completed"
        assert result["failed_source_attempts"] == 1
        assert row["status"] == "source_attempt_failed"
        assert row["config_json"]["discovery_result"] == "source_attempt_failed"
        assert row["config_json"]["error_type"] == "RuntimeError"
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert "public_source_unavailable" not in str(result)
    finally:
        _cleanup(source_name)


def test_stockpile_expansion_discovery_respects_time_budget(monkeypatch):
    token = uuid.uuid4().hex[:8]
    targets = [
        {"country": "EE", "city": f"BudgetA{token}", "language": "en", "niche": "dentists", "guidance": {}},
        {"country": "EE", "city": f"BudgetB{token}", "language": "en", "niche": "dentists", "guidance": {}},
    ]
    monkeypatch.setattr(
        discovery_module,
        "stockpile_expansion_target_plan",
        lambda limit_targets=3: {"status": "ready", "selected_count": 2, "targets": targets, "send_mail": False, "live_outreach_allowed": False},
    )
    calls = []
    monkeypatch.setattr(
        discovery_module,
        "overpass_lead_discovery",
        lambda *args, **kwargs: calls.append(args) or {"status": "source_created", "source_id": "safe", "source_name": "safe", "found_count": 1, "with_email_count": 1},
    )
    times = iter([0, 0, 25, 25])
    monkeypatch.setattr(discovery_module.time, "monotonic", lambda: next(times))
    result = stockpile_expansion_discovery_cycle(2, 5, dry_run=False, max_seconds=20)
    assert len(calls) == 1
    assert result["skipped_target_count"] == 1
    assert result["skipped_targets"][0]["reason"] == "time_budget_exhausted"
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False


def test_regional_lead_discovery_endpoint_and_agent_are_no_send():
    assert client.post("/admin/lead-discovery/regional-cycle", json={"dry_run": True}).status_code == 401
    response = client.post(
        "/admin/lead-discovery/regional-cycle",
        json={"limit_targets": 1, "per_target_limit": 5, "dry_run": True},
        headers=admin_headers(),
    )
    assert response.status_code == 200
    assert response.json()["cycle"]["status"] == "dry_run"
    agent = run_agent("regional_lead_discovery_agent", {"limit_targets": 1, "per_target_limit": 5, "dry_run": True})
    assert agent["status"] == "completed"
    assert agent["result_json"]["status"] == "dry_run"
    assert agent["result_json"]["send_mail"] is False
