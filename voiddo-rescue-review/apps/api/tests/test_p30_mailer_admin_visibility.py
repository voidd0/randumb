from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.customer_mail_simulation import run_customer_mail_simulation
from app.mailer_closed_loop import mailer_closed_loop_summary
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_closed_loop_summary_exposes_resolver_audit_counts_without_raw():
    summary = mailer_closed_loop_summary()
    assert "resolver_audit" in summary
    assert {"total", "resolved", "blocked"}.issubset(summary["resolver_audit"].keys())
    assert summary["raw_recipient_addresses_included"] is False
    assert "@example" not in str(summary)


def test_customer_mail_simulation_summary_is_admin_safe():
    simulation = run_customer_mail_simulation(False)
    assert simulation["case_count"] == 126
    assert simulation["blocking_failures"] == 0
    assert simulation["raw_recipient_addresses_included"] is False
    assert simulation["real_smtp_called"] is False


def test_mailer_visibility_endpoints_require_auth_and_return_counts():
    assert client.get("/admin/mailer/closed-loop").status_code == 401
    assert client.post("/admin/mailer/customer-simulation", json={"write_report": False}).status_code == 401
    closed = client.get("/admin/mailer/closed-loop", headers=admin_headers())
    sim = client.post("/admin/mailer/customer-simulation", json={"write_report": False}, headers=admin_headers())
    assert closed.status_code == 200
    assert sim.status_code == 200
    assert "resolver_audit" in closed.json()["closed_loop"]
    assert sim.json()["simulation"]["case_count"] == 126


def test_mailer_visibility_payloads_keep_sending_disabled():
    closed = client.get("/admin/mailer/closed-loop", headers=admin_headers()).json()["closed_loop"]
    sim = client.post("/admin/mailer/customer-simulation", json={"write_report": False}, headers=admin_headers()).json()["simulation"]
    assert closed["send_mail"] is False
    assert closed["live_outreach_allowed"] is False
    assert sim["send_mail"] is False
    assert sim["live_outreach_allowed"] is False
