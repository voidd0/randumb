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

