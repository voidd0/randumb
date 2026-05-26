from __future__ import annotations

from app.db import execute, fetch_one
from app.mailer_ops_actions import cleanup_synthetic_mailer_ops_runs, mailer_ops_action_summary, run_mailer_ops_action


def test_synthetic_cleanup_keeps_real_runs():
    real = run_mailer_ops_action("customer_simulation", source="admin", is_synthetic=False)
    synthetic = run_mailer_ops_action("customer_transport_dry_run", 1, source="pytest", is_synthetic=True)
    cleanup_synthetic_mailer_ops_runs()
    real_row = fetch_one("SELECT id FROM mailer_ops_runs WHERE id = %s", (real["run"]["id"],))
    synthetic_row = fetch_one("SELECT id FROM mailer_ops_runs WHERE id = %s", (synthetic["run"]["id"],))
    assert real_row is not None
    assert synthetic_row is None
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (real["run"]["id"],))


def test_real_runs_remain_sanitized():
    result = run_mailer_ops_action("closed_loop_dry_run", 1, source="admin", is_synthetic=False)
    assert result["run"]["is_synthetic"] is False
    assert result["run"]["source"] == "admin"
    assert result["result"]["raw_recipient_addresses_included"] is False
    assert result["result"]["send_mail"] is False
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (result["run"]["id"],))


def test_summary_separates_real_and_synthetic_counts():
    real = run_mailer_ops_action("customer_simulation", source="admin", is_synthetic=False)
    synthetic = run_mailer_ops_action("customer_simulation", source="pytest", is_synthetic=True)
    summary = mailer_ops_action_summary()
    assert summary["real_count"] >= 1
    assert summary["synthetic_count"] >= 1
    assert summary["raw_recipient_addresses_included"] is False
    execute("DELETE FROM mailer_ops_runs WHERE id IN (%s, %s)", (real["run"]["id"], synthetic["run"]["id"]))


def test_unknown_actions_remain_blocked_in_retention_summary():
    result = run_mailer_ops_action("run_shell", source="admin", is_synthetic=False)
    summary = mailer_ops_action_summary()
    assert result["run"]["status"] == "blocked"
    assert summary["blocked_unsafe_count"] >= 1
    assert result["result"]["live_outreach_allowed"] is False
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (result["run"]["id"],))


def test_digest_history_cleanup_ops_action_runs_and_persists():
    execute("DELETE FROM mailer_digest_reports WHERE report_path LIKE %s", ("%p43-retention-%",))
    execute(
        """
        INSERT INTO mailer_digest_reports(report_path, email_sent, blockers_json, created_at)
        SELECT '/app/storage/reports/p43-retention-' || gs::text || '.md',
               false, '[]'::jsonb, now() - (gs || ' minutes')::interval
        FROM generate_series(1, 95) AS gs
        """
    )
    result = run_mailer_ops_action("digest_history_cleanup", source="pytest", is_synthetic=True)
    row = fetch_one("SELECT action, status, result_json, send_mail, smtp_called, live_outreach_allowed FROM mailer_ops_runs WHERE id = %s", (result["run"]["id"],))
    assert row["action"] == "digest_history_cleanup"
    assert row["status"] == "completed"
    assert row["send_mail"] is False
    assert row["smtp_called"] is False
    assert row["live_outreach_allowed"] is False
    assert row["result_json"]["deleted_count"] >= 5
    assert row["result_json"]["after_total_rows"] <= 90
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (result["run"]["id"],))
    execute("DELETE FROM mailer_digest_reports WHERE report_path LIKE %s", ("%p43-retention-%",))


def test_digest_history_cleanup_ops_action_is_sanitized_no_send():
    result = run_mailer_ops_action("digest_history_cleanup", source="pytest", is_synthetic=True)
    assert result["result"]["send_mail"] is False
    assert result["result"]["smtp_called"] is False
    assert result["result"]["live_outreach_allowed"] is False
    assert result["result"]["raw_recipient_addresses_included"] is False
    assert "owner-private@" not in str(result)
    assert "SMTP_PASSWORD" not in str(result)
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (result["run"]["id"],))


def test_digest_history_cleanup_ops_action_does_not_touch_queue_or_ledger():
    action = execute(
        """
        INSERT INTO mailer_action_queue(action_type, risk_level, status, payload_json)
        VALUES ('owner_report', 'SAFE_AUTO', 'queued', '{"source":"p43-retention-test"}'::jsonb)
        RETURNING id
        """
    )
    execute(
        """
        INSERT INTO mailer_send_ledger(action_id, action_type, mailbox, status)
        VALUES (%s, 'owner_report', 'support@voiddorescue.com', 'transport_blocked')
        """,
        (action["id"],),
    )
    result = run_mailer_ops_action("digest_history_cleanup", source="pytest", is_synthetic=True)
    assert fetch_one("SELECT count(*) AS count FROM mailer_action_queue WHERE id = %s", (action["id"],))["count"] == 1
    assert fetch_one("SELECT count(*) AS count FROM mailer_send_ledger WHERE action_id = %s", (action["id"],))["count"] == 1
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (action["id"],))
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (result["run"]["id"],))
