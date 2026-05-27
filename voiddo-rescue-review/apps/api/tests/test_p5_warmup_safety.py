from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.db import execute, fetch_one
from app.p0 import (
    mailer_policy_trend_snapshot,
    parse_owner_command,
    record_mail_signal,
    run_deliverability_diagnostics,
    run_warmup_calendar_due,
    scout_campaign_quality_trend_snapshot,
    write_blockers_report,
    write_daily_business_report,
    write_runtime_state_report,
)


def _due_schedule(email: str | None = None) -> dict:
    email = email or f"p5-{uuid.uuid4().hex[:8]}@example.test"
    return execute(
        """
        INSERT INTO warmup_schedule(recipient_email, sender_mailbox, day_number, scheduled_for, status, result_json)
        VALUES (%s, 'audit@voiddorescue.com', 1, %s, 'scheduled', '{}'::jsonb)
        RETURNING id, recipient_email
        """,
        (email, datetime.now(timezone.utc) - timedelta(minutes=1)),
    )


def _cleanup(schedule_id=None, email=None, source=None):
    if schedule_id:
        execute("DELETE FROM warmup_schedule WHERE id = %s", (schedule_id,))
    if email:
        execute("DELETE FROM suppression_list WHERE lower(email) = lower(%s)", (email,))
        execute("DELETE FROM test_inboxes WHERE lower(email) = lower(%s)", (email,))
    if source:
        execute("DELETE FROM mail_signals WHERE source = %s", (source,))


def test_warmup_blocked_if_recent_bounce_exists(monkeypatch):
    schedule = _due_schedule()
    try:
        monkeypatch.setattr("app.p0.latest_mail_qa_decision", lambda: "PASS")
        monkeypatch.setattr("app.p0.effective_pause_state", lambda area, configured=False: False)
        record_mail_signal("bounce", "warning", "test_p5_bounce", recipient_email=schedule["recipient_email"])
        result = run_warmup_calendar_due(limit=1)
        row = fetch_one("SELECT status FROM warmup_schedule WHERE id = %s", (schedule["id"],))
        assert result["sent"] == 0
        assert row["status"] == "blocked_recent_bounce"
    finally:
        _cleanup(schedule["id"], source="test_p5_bounce")


def test_warmup_blocked_if_recent_rate_limit_exists(monkeypatch):
    schedule = _due_schedule()
    try:
        monkeypatch.setattr("app.p0.latest_mail_qa_decision", lambda: "PASS")
        monkeypatch.setattr("app.p0.effective_pause_state", lambda area, configured=False: False)
        monkeypatch.setattr("app.p0.recent_mail_signal_count", lambda types, hours=24: 1 if "smtp_rate_limit" in types else 0)
        result = run_warmup_calendar_due(limit=1)
        row = fetch_one("SELECT status FROM warmup_schedule WHERE id = %s", (schedule["id"],))
        assert result["sent"] == 0
        assert row["status"] == "blocked_recent_rate_limit"
    finally:
        _cleanup(schedule["id"])


def test_warmup_skipped_if_recipient_suppressed(monkeypatch):
    email = f"p5-suppressed-{uuid.uuid4().hex[:8]}@example.test"
    schedule = _due_schedule(email)
    try:
        execute("INSERT INTO suppression_list(email, reason, source) VALUES (%s, 'test', 'test_p5')", (email,))
        monkeypatch.setattr("app.p0.latest_mail_qa_decision", lambda: "PASS")
        monkeypatch.setattr("app.p0.effective_pause_state", lambda area, configured=False: False)
        monkeypatch.setattr("app.p0.recent_mail_signal_count", lambda types, hours=24: 0)
        result = run_warmup_calendar_due(limit=1)
        row = fetch_one("SELECT status FROM warmup_schedule WHERE id = %s", (schedule["id"],))
        assert result["sent"] == 0
        assert row["status"] == "skipped_suppressed"
    finally:
        _cleanup(schedule["id"], email=email)


def test_warmup_blocked_if_mail_qa_not_pass(monkeypatch):
    schedule = _due_schedule()
    try:
        monkeypatch.setattr("app.p0.latest_mail_qa_decision", lambda: "FAIL_BLOCK_LAUNCH")
        monkeypatch.setattr("app.p0.effective_pause_state", lambda area, configured=False: False)
        monkeypatch.setattr("app.p0.recent_mail_signal_count", lambda types, hours=24: 0)
        result = run_warmup_calendar_due(limit=1)
        row = fetch_one("SELECT status FROM warmup_schedule WHERE id = %s", (schedule["id"],))
        assert result["sent"] == 0
        assert row["status"] == "blocked_mail_qa"
    finally:
        _cleanup(schedule["id"])


def test_diagnostic_sends_no_more_than_one_per_minute(monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def ehlo(self): pass
        def starttls(self, context=None): pass
        def login(self, user, password): pass
        def send_message(self, msg):
            sent_messages.append(msg["To"])
            return {}

    monkeypatch.setattr("app.p0.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("app.p0.DIAGNOSTIC_DAILY_CAP", 100)
    emails = [f"p5-diag-{uuid.uuid4().hex[:8]}-{i}@example.test" for i in range(2)]
    try:
        execute("DELETE FROM mail_signals WHERE source = 'deliverability_diagnostic_sent'")
        result = run_deliverability_diagnostics(
            Settings(_env_file=None, smtp_username="audit", smtp_password="secret", smtp_from_default="audit@voiddorescue.com"),
            emails,
            smtp_ready=True,
        )
        assert result["sent"] == 1
        assert "diagnostic_minute_cap_reached" in result["errors"]
        assert len(sent_messages) == 1
    finally:
        for email in emails:
            _cleanup(email=email)
        execute("DELETE FROM mail_signals WHERE source = 'deliverability_diagnostic_sent'")


def test_runtime_state_report_generated(tmp_path):
    path = tmp_path / "runtime_state_report.md"
    result = write_runtime_state_report(path, "head-test", "sha-test")
    text = path.read_text()
    assert path.exists()
    assert "Raw recipient addresses are intentionally omitted" in text
    assert "mailer_policy_score_trend_direction" in text
    assert "mailer_policy_raw_recipients: false" in text
    assert "mailer_policy_secrets: false" in text
    assert "mailer_business_kpi_history_count" in text
    assert "mailer_business_kpi_latest_send_mail: false" in text
    assert "scout_campaign_quality_history_count" in text
    assert "scout_campaign_quality_latest_send_mail: false" in text
    assert result["current_branch_head"] == "head-test"
    assert result["mailer_policy_trend"]["raw_recipient_addresses_included"] is False
    assert result["mailer_policy_trend"]["secrets_included"] is False
    assert result["mailer_business_kpi"]["latest_send_mail"] is False
    assert result["scout_campaign_quality_trend"]["latest_send_mail"] is False


def test_policy_trend_snapshot_is_redacted():
    trend = mailer_policy_trend_snapshot()
    assert "policy_score_trend_direction" in trend
    assert trend["raw_recipient_addresses_included"] is False
    assert trend["secrets_included"] is False


def test_scout_campaign_quality_trend_snapshot_is_redacted():
    trend = scout_campaign_quality_trend_snapshot()
    assert "failed_count_trend_direction" in trend
    assert trend["raw_recipient_addresses_included"] is False
    assert trend["secrets_included"] is False


def test_daily_business_and_blockers_reports_include_policy_trend(tmp_path):
    business = write_daily_business_report(tmp_path / "daily_business_report.md")
    blockers = write_blockers_report(tmp_path / "blockers_report.md")
    business_text = (tmp_path / "daily_business_report.md").read_text()
    blockers_text = (tmp_path / "blockers_report.md").read_text()
    assert business["send_mail"] is False
    assert blockers["send_mail"] is False
    assert "mailer_policy_score_trend_direction" in business_text
    assert "mailer_policy_regression_guard_decision" in blockers_text
    assert "mailer_business_kpi_history_count" in business_text
    assert "mailer_business_kpi_latest_send_mail" in blockers_text
    assert "scout_campaign_quality_history_count" in business_text
    assert "scout_campaign_quality_regression_guard_decision" in blockers_text
    assert "No raw recipient addresses" in business_text
    assert "No raw recipient addresses" in blockers_text


def test_migration_manifest_exists():
    assert os.path.exists("/app/migrations/005_p3_checkout_manifest.sql") or os.path.exists("apps/api/migrations/005_p3_checkout_manifest.sql")


def test_send_outreach_remains_high_risk():
    owner = os.environ["OWNER_COMMAND_EMAIL"]
    parsed = parse_owner_command(owner, "SEND OUTREACH", "SEND OUTREACH", owner, "dkim=pass")
    assert parsed["risk_level"] == "HIGH_RISK"
    assert parsed["status"] == "review_required"
