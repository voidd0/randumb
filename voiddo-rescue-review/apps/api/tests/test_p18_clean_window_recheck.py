from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.clean_window_recheck import clean_window_recheck, clean_window_recheck_summary, warmup_resume_precheck
from app.db import fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def clean_signals() -> dict:
    return {"window_hours": 24, "items": [], "bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0}


def risky_signals() -> dict:
    return {
        "window_hours": 24,
        "items": [{"signal_type": "dsn", "severity": "warning", "count": 1}],
        "bounce_or_dsn_count": 1,
        "rate_limit_count": 0,
        "spam_signal_count": 0,
    }


def test_clean_window_recheck_blocks_recent_signals_and_starts_no_sends(monkeypatch):
    import app.clean_window_recheck as recheck

    monkeypatch.setattr(recheck, "mail_signal_summary", lambda hours=24: risky_signals())
    monkeypatch.setattr(recheck, "latest_blocking_signal_next_safe_at", lambda hours=24: "2026-05-27T10:00:00+00:00")
    monkeypatch.setattr(recheck, "latest_mail_qa_decision", lambda: "PASS")
    result = clean_window_recheck(24, run_recovery_if_clear=True)
    assert result["status"] == "blocked_recent_signals"
    assert result["sends_started"] is False
    assert result["signal_window_clear"] is False


def test_clean_window_recheck_ready_when_clean_and_mail_qa_pass(monkeypatch):
    import app.clean_window_recheck as recheck

    recovery = {"status": "spacing_applied", "mail_qa_decision": "PASS", "sends_started": False}
    monkeypatch.setattr(recheck, "mail_signal_summary", lambda hours=24: clean_signals())
    monkeypatch.setattr(recheck, "latest_blocking_signal_next_safe_at", lambda hours=24: None)
    monkeypatch.setattr(recheck, "latest_mail_qa_decision", lambda: "PASS")
    monkeypatch.setattr(recheck, "run_clean_window_recovery", lambda window_hours=24: recovery)
    monkeypatch.setattr(
        recheck,
        "warmup_calendar_health",
        lambda: {"scheduled_total": 2, "due_now": 0, "sent_today": 0, "blocked_today": 0, "latest_mail_qa_decision": "PASS"},
    )
    result = clean_window_recheck(24, run_recovery_if_clear=True)
    assert result["status"] == "ready_natural_warmup_only"
    assert result["sends_started"] is False
    assert result["result_json"]["live_outreach_allowed"] is False


def test_warmup_resume_precheck_keeps_live_outreach_out_of_scope():
    gate = warmup_resume_precheck(clean_signals(), "PASS")
    assert "policy" in gate
    assert gate["policy"] == "precheck_only_no_send"


def test_admin_clean_window_recheck_endpoints_require_auth():
    assert client.get("/admin/mailer/clean-window-recheck").status_code == 401
    assert client.post("/admin/mailer/clean-window-recheck", json={"window_hours": 24}).status_code == 401
    response = client.get("/admin/mailer/clean-window-recheck", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["summary"]["sends_started"] is False


def test_admin_clean_window_recheck_post_records_no_send_result():
    response = client.post("/admin/mailer/clean-window-recheck", json={"window_hours": 24, "run_recovery_if_clear": False}, headers=admin_headers())
    assert response.status_code == 200
    recheck = response.json()["recheck"]
    assert recheck["sends_started"] is False
    row = fetch_one("SELECT id FROM clean_window_recheck_runs WHERE id = %s", (recheck["id"],))
    assert row


def test_clean_window_recheck_summary_never_allows_live_outreach():
    summary = clean_window_recheck_summary()
    assert summary["live_outreach_allowed"] is False
    assert summary["sends_started"] is False
