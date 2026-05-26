from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.db import execute
from app.mailer_control_room import mailer_digest_summary, write_owner_status_report
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_digest_summary_endpoint_requires_auth_and_exposes_evidence():
    assert client.get("/admin/mailer/digest-summary").status_code == 401
    write_owner_status_report(send_if_safe=False)
    response = client.get("/admin/mailer/digest-summary", headers=admin_headers())
    assert response.status_code == 200
    digest = response.json()["digest"]
    assert "mailer_ops" in digest
    assert digest["owner_report_action_status"] in {"queued", "prepared", "blocked", "none"}
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", ("%daily_digest_hook%",))


def test_digest_summary_omits_raw_recipients_and_send_flags():
    digest = mailer_digest_summary()
    assert digest["raw_recipient_addresses_included"] is False
    assert digest["send_mail"] is False
    assert digest["live_outreach_allowed"] is False
    assert "@example" not in str(digest)


def test_digest_owner_report_draft_stays_no_send():
    report = write_owner_status_report(send_if_safe=False)
    digest = mailer_digest_summary()
    assert report["email_sent"] is False
    assert digest["email_sent"] is False
    assert digest["latest_owner_report_action"]["status"] == "queued"
    assert digest["latest_owner_report_action"]["recipient_hash"] == ""
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (report["owner_report_action"]["id"],))


def test_digest_summary_includes_latest_owner_report_state():
    report = write_owner_status_report(send_if_safe=False)
    digest = mailer_digest_summary()
    assert digest["latest_owner_report"] is not None
    assert digest["latest_owner_report"]["payload_json"]["email_sent"] is False
    assert digest["latest_owner_report"]["payload_json"]["send_decision"] == report["send_decision"]
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (report["owner_report_action"]["id"],))


def test_digest_summary_includes_runtime_report_metadata():
    run = run_agent("mailer_digest_agent")
    digest = mailer_digest_summary()
    report = digest["digest_agent_report"]
    assert report["exists"] is True
    assert report["path"].endswith("mailer_digest_agent_report.md")
    assert report["modified_at"]
    assert report["email_sent"] is False
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (run["result_json"]["owner_report_action"]["id"],))


def test_digest_report_metadata_omits_raw_recipients_and_secrets():
    run = run_agent("mailer_digest_agent")
    report = mailer_digest_summary()["digest_agent_report"]
    assert report["raw_recipient_addresses_included"] is False
    assert report["secrets_included"] is False
    assert "gkorner@" not in str(report)
    assert "SMTP_PASSWORD" not in str(report)
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (run["result_json"]["owner_report_action"]["id"],))


def test_digest_summary_endpoint_returns_report_metadata_behind_auth():
    run = run_agent("mailer_digest_agent")
    assert client.get("/admin/mailer/digest-summary").status_code == 401
    response = client.get("/admin/mailer/digest-summary", headers=admin_headers())
    assert response.status_code == 200
    report = response.json()["digest"]["digest_agent_report"]
    assert report["exists"] is True
    assert report["email_sent"] is False
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (run["result_json"]["owner_report_action"]["id"],))


def test_digest_summary_send_flags_remain_false_with_runtime_report():
    run = run_agent("mailer_digest_agent")
    digest = mailer_digest_summary()
    assert digest["send_mail"] is False
    assert digest["live_outreach_allowed"] is False
    assert digest["digest_agent_report"]["email_sent"] is False
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (run["result_json"]["owner_report_action"]["id"],))
