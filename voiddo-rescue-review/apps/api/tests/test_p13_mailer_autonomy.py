from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.db import fetch_one
from app.main import app
from app.mailer_autonomy import (
    email_template_autonomy_qa,
    mailer_status_snapshot,
    record_mail_signal_lessons,
    run_clean_window_recovery,
)


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def clean_signals() -> dict:
    return {"window_hours": 24, "items": [], "bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0}


def risky_signals() -> dict:
    return {
        "window_hours": 24,
        "items": [{"signal_type": "smtp_rate_limit", "severity": "warning", "count": 1}],
        "bounce_or_dsn_count": 0,
        "rate_limit_count": 1,
        "spam_signal_count": 0,
    }


def test_mailer_status_blocks_on_recent_signals(monkeypatch):
    import app.mailer_autonomy as autonomy

    monkeypatch.setattr(autonomy, "mail_signal_summary", lambda hours=24: risky_signals())
    monkeypatch.setattr(autonomy, "latest_mail_qa_decision", lambda: "PASS")
    snapshot = mailer_status_snapshot()
    assert snapshot["status"] == "blocked_recent_mail_signals"
    assert snapshot["next_safe_action"] == "wait_until_recent_signal_window_clears"


def test_mailer_status_ready_when_clean(monkeypatch):
    import app.mailer_autonomy as autonomy

    monkeypatch.setattr(autonomy, "mail_signal_summary", lambda hours=24: clean_signals())
    monkeypatch.setattr(autonomy, "latest_mail_qa_decision", lambda: "PASS")
    monkeypatch.setattr(autonomy, "throttle_decision", lambda scope, scope_key, min_delay_seconds=600: {"allowed": True, "reason": "allowed", "checks": {}})
    monkeypatch.setattr(autonomy, "latest_quality_summary", lambda: {"all_pass": True, "blockers": []})
    snapshot = mailer_status_snapshot()
    assert snapshot["status"] == "ready_scheduler_no_outreach"
    assert snapshot["result_json"]["live_outreach_allowed"] is False


def test_clean_window_recovery_blocks_recent_signals(monkeypatch):
    import app.mailer_autonomy as autonomy

    monkeypatch.setattr(autonomy, "mail_signal_summary", lambda hours=24: risky_signals())
    monkeypatch.setattr(autonomy, "latest_mail_qa_decision", lambda: "PASS")
    recovery = run_clean_window_recovery(24)
    assert recovery["status"] == "blocked_recent_signals"
    assert recovery["sends_started"] is False


def test_clean_window_recovery_clean_applies_spacing_without_send(monkeypatch):
    import app.mailer_autonomy as autonomy

    monkeypatch.setattr(autonomy, "mail_signal_summary", lambda hours=24: clean_signals())
    monkeypatch.setattr(autonomy, "run_mail_qa", lambda allow_deliverability_send=False: {"decision": "PASS", "allow_deliverability_send": allow_deliverability_send})
    monkeypatch.setattr(autonomy, "apply_provider_spacing_when_safe", lambda limit=50: {"id": None, "status": "applied_safe_gate", "applied": True})
    recovery = run_clean_window_recovery(24)
    assert recovery["status"] == "spacing_applied"
    assert recovery["sends_started"] is False
    assert recovery["result_json"]["mail_qa"]["allow_deliverability_send"] is False


def test_signal_learning_records_redacted_lesson(monkeypatch):
    import app.mailer_autonomy as autonomy

    monkeypatch.setattr(autonomy, "mail_signal_summary", lambda hours=24: risky_signals())
    learned = record_mail_signal_lessons(24)
    assert learned["lessons_recorded"] == 1
    lesson = fetch_one("SELECT lesson_json FROM mail_signal_lessons WHERE lesson_key = 'smtp_rate_limit:warning'")
    assert lesson["lesson_json"]["no_raw_recipient_addresses"] is True


def test_email_template_autonomy_qa_passes_no_operator_language():
    qa = email_template_autonomy_qa()
    assert qa["passed"] is True
    assert qa["checked"] >= 10


def test_admin_mailer_status_requires_auth_and_returns_snapshot():
    assert client.get("/admin/mailer/status").status_code == 401
    response = client.get("/admin/mailer/status", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_admin_clean_window_recovery_requires_auth():
    assert client.post("/admin/mailer/clean-window-recovery", json={"window_hours": 24}).status_code == 401
    response = client.post("/admin/mailer/clean-window-recovery", json={"window_hours": 24}, headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["ok"] is True
