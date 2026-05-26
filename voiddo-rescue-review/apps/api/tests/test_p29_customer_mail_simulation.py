from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.billing import PRODUCTS
from app.customer_mail_simulation import ACTION_TEMPLATES, SCENARIOS, run_customer_mail_simulation
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_customer_mail_simulation_covers_all_products():
    result = run_customer_mail_simulation(False)
    assert set(result["products"]) == set(PRODUCTS.keys())
    assert result["product_count"] == 6
    assert result["case_count"] == len(PRODUCTS) * len(ACTION_TEMPLATES) * len(SCENARIOS)


def test_customer_mail_simulation_covers_required_scenarios():
    result = run_customer_mail_simulation(False)
    scenarios = {item["scenario"] for item in result["items"]}
    assert scenarios == {name for name, _ in SCENARIOS}
    assert "mocked_smtp_success" in scenarios
    assert "mocked_smtp_failure" in scenarios
    assert "suppressed_customer" in scenarios


def test_customer_mail_simulation_omits_raw_recipients():
    result = run_customer_mail_simulation(False)
    text = str(result)
    assert result["raw_recipient_addresses_included"] is False
    assert "@example" not in text
    assert "recipient_hash" in text


def test_customer_mail_simulation_never_calls_real_smtp_or_live_outreach():
    result = run_customer_mail_simulation(False)
    assert result["real_smtp_called"] is False
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert all(item["smtp_called"] is False for item in result["items"] if not item["scenario"].startswith("mocked_smtp"))


def test_customer_mail_simulation_templates_pass_qa():
    result = run_customer_mail_simulation(False)
    assert result["blocking_failures"] == 0
    assert all(item["template_qa_passed"] for item in result["items"])


def test_customer_mail_simulation_endpoint_requires_auth():
    assert client.post("/admin/mailer/customer-simulation", json={"write_report": False}).status_code == 401
    response = client.post("/admin/mailer/customer-simulation", json={"write_report": False}, headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["simulation"]["case_count"] == len(PRODUCTS) * len(ACTION_TEMPLATES) * len(SCENARIOS)


def test_customer_mail_simulation_agent_records_no_send():
    run = run_agent("customer_mail_simulation_agent")
    assert run["agent"] == "customer_mail_simulation_agent"
    assert run["status"] == "completed"
    assert run["result_json"]["send_mail"] is False
    assert run["result_json"]["real_smtp_called"] is False
