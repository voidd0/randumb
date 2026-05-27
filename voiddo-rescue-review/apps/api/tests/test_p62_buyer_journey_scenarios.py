from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.buyer_journey_scenarios import buyer_journey_readiness_scoreboard, run_buyer_journey_scenario
from app.db import fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _count(sql: str, params: tuple = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def test_buyer_journey_scenario_runs_end_to_end_and_cleans_runtime_data():
    before_queue = _count("SELECT count(*) FROM mailer_action_queue")
    before_customers = _count("SELECT count(*) FROM customers WHERE email LIKE %s", ("%@voiddorescue.local",))
    result = run_buyer_journey_scenario(cleanup=True)
    token = result["token"]
    text = str(result)
    assert result["business_created"] is True
    assert result["lead_created"] is True
    assert result["audit_created"] is True
    assert result["campaign_preview_count"] == 1
    assert result["preview_quality_status"] == "PASS_PREVIEW_QUALITY"
    assert "payment_recorded" in result["paddle_actions"]
    assert result["dashboard_ready"] is True
    assert result["fix_request_count"] >= 1
    assert result["mailer_actions_queued"] >= 2
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert "owner-" not in text
    assert "buyer-" not in text.replace(token, "")
    assert _count("SELECT count(*) FROM mailer_action_queue") == before_queue
    assert _count("SELECT count(*) FROM customers WHERE email LIKE %s", ("%@voiddorescue.local",)) == before_customers


def test_buyer_journey_scoreboard_is_no_send():
    scoreboard = buyer_journey_readiness_scoreboard()
    assert "checkout_paid_events" in scoreboard
    assert scoreboard["send_mail"] is False
    assert scoreboard["live_outreach_allowed"] is False


def test_buyer_journey_admin_endpoints_and_agents_are_protected_no_send():
    assert client.get("/admin/scenarios/buyer-journey").status_code == 401
    assert client.post("/admin/scenarios/buyer-journey/run", json={"cleanup": True}).status_code == 401
    response = client.get("/admin/scenarios/buyer-journey", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["scoreboard"]["send_mail"] is False
    run_response = client.post("/admin/scenarios/buyer-journey/run", json={"cleanup": True}, headers=admin_headers())
    assert run_response.status_code == 200
    assert run_response.json()["scenario"]["send_mail"] is False
    agent = run_agent("buyer_journey_scoreboard_agent")
    scenario_agent = run_agent("buyer_journey_scenario_agent")
    assert agent["status"] == "completed"
    assert scenario_agent["status"] == "completed"
    assert agent["result_json"]["send_mail"] is False
    assert scenario_agent["result_json"]["send_mail"] is False
