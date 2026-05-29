from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import fetch_one
from app.mailer_autonomy import run_clean_window_recovery
from app.mailer_control_room import mailer_control_room_summary, monitoring_control_room_summary, write_owner_status_report
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_admin_mailer_control_room_requires_auth_and_reports_blockers():
    assert client.get("/admin/mailer/control-room").status_code == 401
    response = client.get("/admin/mailer/control-room", headers=admin_headers())
    assert response.status_code == 200
    payload = response.json()["control_room"]
    assert payload["live_outreach_allowed"] is False
    assert "next_allowed_action" in payload
    assert "signals" in payload


def test_admin_monitoring_summary_requires_auth_and_is_no_send():
    assert client.get("/admin/monitoring/summary").status_code == 401
    response = client.get("/admin/monitoring/summary", headers=admin_headers())
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["sends_started"] is False
    assert summary["policy"] == "safe_public_checks_only_no_customer_website_changes"


def test_mailer_control_room_summary_exposes_warmup_gate_without_addresses():
    summary = mailer_control_room_summary(write_snapshot=True)
    assert summary["live_outreach_allowed"] is False
    assert "warmup_blocked_reason" in summary
    text = str(summary)
    assert "@" not in text


def test_monitoring_control_room_summary_contains_due_count_and_latest_runs():
    summary = monitoring_control_room_summary()
    assert "due_now" in summary
    assert "latest_runs" in summary
    assert summary["sends_started"] is False


def test_owner_status_report_file_only_when_mail_signals_recent():
    report = write_owner_status_report(send_if_safe=False)
    assert report["email_sent"] is False
    assert report["send_decision"] in {"blocked_owner_mail_gate", "not_sent_draft_only"}
    path = Path(report["path"])
    assert path.exists()
    text = path.read_text()
    assert "live_outreach_sent_count" in text
    assert "email_sent: `False`" in text
    event = fetch_one("SELECT id FROM system_events WHERE type = 'owner_report.generated' ORDER BY created_at DESC LIMIT 1")
    assert event


def test_clean_window_recovery_remains_no_send():
    recovery = run_clean_window_recovery(24)
    assert recovery["sends_started"] is False
