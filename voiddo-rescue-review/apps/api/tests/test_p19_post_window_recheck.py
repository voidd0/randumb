from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.clean_window_recheck import post_window_recheck_scheduler, post_window_recheck_summary
from app.db import fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_post_window_recheck_not_due_before_next_safe_at(monkeypatch):
    import app.clean_window_recheck as recheck

    monkeypatch.setattr(
        recheck,
        "clean_window_recheck_summary",
        lambda: {"next_safe_at": "2026-05-27T11:19:56+00:00", "live_outreach_allowed": False, "sends_started": False},
    )
    result = post_window_recheck_scheduler(24, now=datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc))
    assert result["status"] == "not_due"
    assert result["recheck_due"] is False
    assert result["transition_decision"] == "WAIT_UNTIL_NEXT_SAFE_AT"
    assert result["sends_started"] is False


def test_post_window_recheck_due_after_next_safe_at_runs_no_send(monkeypatch):
    import app.clean_window_recheck as recheck

    monkeypatch.setattr(recheck, "clean_window_recheck_summary", lambda: {"next_safe_at": "2026-05-27T10:00:00+00:00"})
    monkeypatch.setattr(
        recheck,
        "clean_window_recheck",
        lambda window_hours=24, run_recovery_if_clear=True: {"status": "blocked_recent_signals", "sends_started": False},
    )
    result = post_window_recheck_scheduler(24, now=datetime(2026, 5, 27, 11, 0, tzinfo=timezone.utc))
    assert result["status"] == "recheck_executed"
    assert result["recheck_due"] is True
    assert result["transition_decision"] == "WAIT_RECENT_SIGNALS"
    assert result["sends_started"] is False


def test_post_window_recheck_transition_ready_pending_natural_timer(monkeypatch):
    import app.clean_window_recheck as recheck

    monkeypatch.setattr(recheck, "clean_window_recheck_summary", lambda: {"next_safe_at": None})
    monkeypatch.setattr(
        recheck,
        "clean_window_recheck",
        lambda window_hours=24, run_recovery_if_clear=True: {"status": "ready_natural_warmup_only", "sends_started": False},
    )
    result = post_window_recheck_scheduler(24, now=datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc))
    assert result["transition_decision"] == "WARMUP_READY_PENDING_NATURAL_TIMER"
    assert result["result_json"]["live_outreach_allowed"] is False
    assert result["sends_started"] is False


def test_admin_post_window_recheck_endpoints_require_auth():
    assert client.get("/admin/mailer/post-window-recheck").status_code == 401
    assert client.post("/admin/mailer/post-window-recheck", json={"window_hours": 24}).status_code == 401
    response = client.get("/admin/mailer/post-window-recheck", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["summary"]["live_outreach_allowed"] is False


def test_admin_post_window_recheck_post_records_no_send_result():
    response = client.post("/admin/mailer/post-window-recheck", json={"window_hours": 24, "run_recovery_if_due": False}, headers=admin_headers())
    assert response.status_code == 200
    run = response.json()["run"]
    assert run["sends_started"] is False
    row = fetch_one("SELECT id FROM post_window_recheck_runs WHERE id = %s", (run["id"],))
    assert row


def test_post_window_recheck_summary_never_unlocks_live_outreach():
    summary = post_window_recheck_summary()
    assert summary["live_outreach_allowed"] is False
    assert summary["sends_started"] is False
