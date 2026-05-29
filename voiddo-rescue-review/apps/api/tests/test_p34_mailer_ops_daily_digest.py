from __future__ import annotations

from pathlib import Path

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.mailer_control_room import mailer_digest_summary, write_owner_status_report
from app.mailer_ops_actions import run_mailer_ops_action


def test_daily_report_includes_mailer_ops_summary():
    run_mailer_ops_action("customer_simulation", source="admin", is_synthetic=False)
    report = write_owner_status_report(send_if_safe=False)
    text = Path(report["path"]).read_text()
    assert "mailer_ops_real_count" in text
    assert "mailer_ops_blocked_unsafe_count" in text
    assert "studio_mail_monitor_decision" in text
    assert report["studio_mail"]["send_mail"] is False
    assert report["studio_mail"]["live_outreach_allowed"] is False
    assert report["mailer_ops"]["real_count"] >= 1
    execute("DELETE FROM mailer_ops_runs")
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", ("%daily_digest_hook%",))


def test_owner_report_draft_uses_no_send_action_queue():
    report = write_owner_status_report(send_if_safe=False)
    action = report["owner_report_action"]
    assert action["action_type"] == "owner_report"
    assert action["status"] == "prepared"
    row = fetch_one("SELECT payload_json FROM mailer_action_queue WHERE id = %s", (action["id"],))
    assert row is not None
    assert row["payload_json"]["payload_json"]["source"] == "daily_digest_hook"
    assert "@" not in str(row["payload_json"]["payload_json"]["mailer_ops"])
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (action["id"],))


def test_owner_report_generation_sends_no_email():
    report = write_owner_status_report(send_if_safe=False)
    assert report["email_sent"] is False
    assert report["owner_report_action"]["action_type"] == "owner_report"
    assert report["state"]["live_outreach_sent_count"] >= 0
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (report["owner_report_action"]["id"],))


def test_daily_digest_keeps_live_outreach_blocked():
    report = write_owner_status_report(send_if_safe=False)
    assert report["mailer"]["live_outreach_allowed"] is False
    assert "recipient_hash" in report["owner_report_action"]
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (report["owner_report_action"]["id"],))


def test_owner_report_includes_mailer_ops_retention_history_without_send_or_secrets():
    run_agent("mailer_ops_retention_agent")
    report = write_owner_status_report(send_if_safe=False)
    text = Path(report["path"]).read_text()
    assert "mailer_ops_retention_history_rows" in text
    assert "mailer_ops_retention_latest_send_mail: `false`" in text
    assert "mailer_ops_retention_raw_recipients: `false`" in text
    assert "mailer_ops_retention_secrets: `false`" in text
    assert report["mailer_ops_retention_history"]["count"] >= 1
    assert report["mailer_ops_retention_history"]["raw_recipient_addresses_included"] is False
    assert report["mailer_ops_retention_history"]["secrets_included"] is False
    assert report["email_sent"] is False
    assert "owner-private@" not in text
    assert "SMTP_PASSWORD" not in text
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (report["owner_report_action"]["id"],))


def test_mailer_digest_summary_exposes_retention_history_without_send():
    run_agent("mailer_ops_retention_agent")
    summary = mailer_digest_summary()
    history = summary["mailer_ops_retention_history"]
    assert history["count"] >= 1
    assert history["latest"]["send_mail"] is False
    assert history["raw_recipient_addresses_included"] is False
    assert history["secrets_included"] is False
    assert summary["send_mail"] is False
    assert summary["live_outreach_allowed"] is False
