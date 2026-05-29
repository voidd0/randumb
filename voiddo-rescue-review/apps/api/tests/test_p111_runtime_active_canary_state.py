from __future__ import annotations

import app.p0 as p0


def test_runtime_state_next_action_matches_active_canary(monkeypatch):
    counts = {
        "SELECT count(*) FROM outreach_messages WHERE status = 'sent'": 12,
        "SELECT count(*) FROM outreach_messages WHERE status = 'queued'": 8,
    }

    def fake_count(sql: str) -> int:
        return counts.get(sql, 0)

    monkeypatch.setenv("OUTREACH_DRY_RUN", "false")
    monkeypatch.setenv("OUTREACH_PAUSED", "false")
    monkeypatch.setenv("FIRST_LIVE_SEND_FLAG", "true")
    monkeypatch.setattr(p0, "latest_mail_qa_decision", lambda: "PASS")
    monkeypatch.setattr(p0, "recent_mail_signal_count", lambda signal_types, hours: 0)
    monkeypatch.setattr(p0, "_count", fake_count)
    monkeypatch.setattr(p0, "launch_readiness_state", lambda: "LIVE_OUTREACH_READY")
    monkeypatch.setattr(p0, "mailer_policy_trend_snapshot", lambda: {})
    monkeypatch.setattr(p0, "mailer_business_kpi_report_snapshot", lambda: {})
    monkeypatch.setattr(p0, "scout_campaign_quality_trend_snapshot", lambda: {})
    monkeypatch.setattr(p0, "scout_source_readiness_trend_snapshot", lambda: {})
    monkeypatch.setattr(p0, "scout_source_queue_preview_snapshot", lambda: {})

    snapshot = p0.runtime_state_snapshot()
    assert snapshot["next_allowed_action"] == "continue_active_canary_under_post_send_observer_and_hard_spacing"
    assert snapshot["live_outreach_sent_count"] == 12
