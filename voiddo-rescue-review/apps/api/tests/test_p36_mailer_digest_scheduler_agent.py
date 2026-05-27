from __future__ import annotations

from pathlib import Path

from app.autonomous_agents import run_agent, run_daily_loop
from app.db import execute, fetch_one


def _cleanup(action_id: str | None = None) -> None:
    if action_id:
        execute("DELETE FROM mailer_action_queue WHERE id = %s", (action_id,))
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", ("%daily_digest_hook%",))
    execute("DELETE FROM mailer_digest_reports WHERE report_path LIKE %s", ("%mailer_digest_agent_report.md%",))


def _clean_trend_runtime() -> None:
    execute("DELETE FROM mailer_send_ledger")
    execute("DELETE FROM recipient_resolver_audit")
    execute("DELETE FROM mailer_action_queue")


def test_mailer_digest_agent_exists_and_generates_report():
    run = run_agent("mailer_digest_agent")
    result = run["result_json"]
    assert run["status"] == "completed"
    assert result["email_sent"] is False
    assert Path(result["path"]).exists()
    assert result["owner_report_action"]["action_type"] == "owner_report"
    _cleanup(result["owner_report_action"]["id"])


def test_mailer_digest_agent_queues_no_send_owner_report_action():
    run = run_agent("mailer_digest_agent")
    action = run["result_json"]["owner_report_action"]
    row = fetch_one("SELECT status, recipient_hash, payload_json FROM mailer_action_queue WHERE id = %s", (action["id"],))
    assert row["status"] == "queued"
    assert row["recipient_hash"] == ""
    assert row["payload_json"]["payload_json"]["email_sent"] is False
    _cleanup(action["id"])


def test_daily_loop_includes_mailer_digest_agent():
    result = run_daily_loop()
    agents = [item["agent"] for item in result["runs"]]
    assert "mailer_digest_agent" in agents
    assert agents.index("mailer_ops_retention_agent") < agents.index("mailer_digest_agent")
    digest_runs = [item for item in result["runs"] if item["agent"] == "mailer_digest_agent"]
    assert digest_runs[0]["result_json"]["email_sent"] is False
    assert digest_runs[0]["result_json"]["mailer_ops_retention_history"]["count"] >= 1
    assert digest_runs[0]["result_json"]["digest_agent_report"]["mailer_ops_retention_history"]["latest_send_mail"] is False
    assert result["live_outreach"] is False
    _cleanup(digest_runs[0]["result_json"]["owner_report_action"]["id"])


def test_mailer_digest_agent_does_not_send_warmup_or_outreach():
    run = run_agent("mailer_digest_agent")
    result = run["result_json"]
    assert result["state"]["warmup_sent_count"] == 0
    assert result["state"]["live_outreach_sent_count"] == 0
    assert result["email_sent"] is False
    _cleanup(result["owner_report_action"]["id"])


def test_mailer_digest_agent_records_agent_run_evidence():
    run = run_agent("mailer_digest_agent")
    row = fetch_one("SELECT agent, status FROM agent_runs WHERE id = %s", (run["id"],))
    assert row["agent"] == "mailer_digest_agent"
    assert row["status"] == "completed"
    _cleanup(run["result_json"]["owner_report_action"]["id"])


def test_mailer_digest_agent_writes_runtime_report_file():
    run = run_agent("mailer_digest_agent")
    report = run["result_json"]["digest_agent_report"]
    assert report["agent_run_id"] == str(run["id"])
    assert report["email_sent"] is False
    assert report["mailer_ops_retention_history"]["latest_send_mail"] is False
    assert report["mailer_ops_retention_history"]["raw_recipient_addresses_included"] is False
    assert report["mailer_ops_retention_history"]["secrets_included"] is False
    assert Path(report["path"]).exists()
    _cleanup(run["result_json"]["owner_report_action"]["id"])


def test_mailer_digest_agent_runtime_report_omits_raw_recipients():
    run = run_agent("mailer_digest_agent")
    text = Path(run["result_json"]["digest_agent_report"]["path"]).read_text(encoding="utf-8")
    assert "Raw recipient addresses" in text
    assert "owner-private@" not in text
    assert "voiddorescue.com" not in text
    assert "SMTP_PASSWORD" not in text
    _cleanup(run["result_json"]["owner_report_action"]["id"])


def test_mailer_digest_agent_runtime_report_confirms_no_send_counts():
    run = run_agent("mailer_digest_agent")
    report = run["result_json"]["digest_agent_report"]
    assert report["warmup_sent_count"] == 0
    assert report["live_outreach_sent_count"] == 0
    assert report["email_sent"] is False
    text = Path(report["path"]).read_text(encoding="utf-8")
    assert "mailer_ops_retention_history_rows" in text
    assert "mailer_ops_retention_latest_send_mail: `false`" in text
    assert "mailer_ops_retention_raw_recipients: `false`" in text
    assert "mailer_ops_retention_secrets: `false`" in text
    _cleanup(run["result_json"]["owner_report_action"]["id"])


def test_daily_loop_digest_agent_exposes_runtime_report_path():
    result = run_daily_loop()
    digest_run = [item for item in result["runs"] if item["agent"] == "mailer_digest_agent"][0]
    report = digest_run["result_json"]["digest_agent_report"]
    assert Path(report["path"]).exists()
    assert report["email_sent"] is False
    _cleanup(digest_run["result_json"]["owner_report_action"]["id"])


def test_mailer_digest_agent_persists_history_row():
    run = run_agent("mailer_digest_agent")
    report = run["result_json"]["digest_agent_report"]
    row = fetch_one(
        "SELECT agent_run_id, report_path, email_sent, warmup_sent_count, live_outreach_sent_count FROM mailer_digest_reports WHERE id = %s",
        (report["history_id"],),
    )
    assert str(row["agent_run_id"]) == str(run["id"])
    assert row["report_path"].endswith("mailer_digest_agent_report.md")
    assert row["email_sent"] is False
    assert row["warmup_sent_count"] == 0
    assert row["live_outreach_sent_count"] == 0
    _cleanup(run["result_json"]["owner_report_action"]["id"])


def test_mailer_digest_history_omits_raw_recipients_and_secrets():
    run = run_agent("mailer_digest_agent")
    row = fetch_one("SELECT report_path, blockers_json FROM mailer_digest_reports WHERE id = %s", (run["result_json"]["digest_agent_report"]["history_id"],))
    assert "owner-private@" not in str(row)
    assert "SMTP_PASSWORD" not in str(row)
    assert "voiddorescue.com" not in str(row)
    _cleanup(run["result_json"]["owner_report_action"]["id"])


def test_mailer_digest_retention_agent_exists_and_is_no_send():
    run = run_agent("mailer_digest_retention_agent")
    result = run["result_json"]
    assert run["status"] == "completed"
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert result["raw_recipient_addresses_included"] is False


def test_mailer_digest_retention_agent_deletes_old_history_rows():
    execute("DELETE FROM mailer_digest_reports WHERE report_path LIKE %s", ("%p42-retention-%",))
    execute(
        """
        INSERT INTO mailer_digest_reports(report_path, email_sent, blockers_json, created_at)
        SELECT '/app/storage/reports/p42-retention-' || gs::text || '.md',
               false, '[]'::jsonb, now() - (gs || ' minutes')::interval
        FROM generate_series(1, 95) AS gs
        """
    )
    run = run_agent("mailer_digest_retention_agent")
    result = run["result_json"]
    rows = fetch_one("SELECT count(*) AS count FROM mailer_digest_reports WHERE report_path LIKE %s", ("%p42-retention-%",))
    assert result["deleted_count"] >= 5
    assert rows["count"] <= 90
    execute("DELETE FROM mailer_digest_reports WHERE report_path LIKE %s", ("%p42-retention-%",))


def test_daily_loop_includes_mailer_digest_retention_agent():
    result = run_daily_loop()
    agents = [item["agent"] for item in result["runs"]]
    assert "mailer_digest_retention_agent" in agents
    retention_runs = [item for item in result["runs"] if item["agent"] == "mailer_digest_retention_agent"]
    assert retention_runs[0]["result_json"]["send_mail"] is False
    assert result["live_outreach"] is False
    digest_runs = [item for item in result["runs"] if item["agent"] == "mailer_digest_agent"]
    if digest_runs:
        _cleanup(digest_runs[0]["result_json"]["owner_report_action"]["id"])


def test_mailer_digest_trend_guard_agent_passes_clean_history():
    _clean_trend_runtime()
    run_agent("mailer_ops_retention_agent")
    digest_run = run_agent("mailer_digest_agent")
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (digest_run["result_json"]["owner_report_action"]["id"],))
    run = run_agent("mailer_digest_trend_guard_agent")
    assert run["status"] == "completed"
    assert run["result_json"]["decision"] == "PASS_NO_SEND"
    assert run["result_json"]["send_mail"] is False
    assert run["result_json"]["live_outreach_allowed"] is False
    assert run["result_json"]["raw_recipient_addresses_included"] is False
    assert run["result_json"]["secrets_included"] is False


def test_mailer_digest_trend_guard_agent_blocks_queue_regression():
    _clean_trend_runtime()
    run_agent("mailer_ops_retention_agent")
    digest_run = run_agent("mailer_digest_agent")
    run = run_agent("mailer_digest_trend_guard_agent")
    assert run["status"] == "completed"
    assert run["result_json"]["decision"] == "FAIL_BLOCK_LAUNCH"
    assert "mailer_action_queue_not_empty" in run["result_json"]["regressions"]
    assert run["result_json"]["send_mail"] is False
    _cleanup(digest_run["result_json"]["owner_report_action"]["id"])


def test_daily_loop_includes_mailer_digest_trend_guard_agent_after_digest():
    result = run_daily_loop()
    agents = [item["agent"] for item in result["runs"]]
    assert "mailer_digest_trend_guard_agent" in agents
    assert agents.index("mailer_digest_agent") < agents.index("mailer_digest_trend_guard_agent")
    assert agents.index("mailer_ops_retention_agent") < agents.index("mailer_digest_trend_guard_agent")
    guard_run = [item for item in result["runs"] if item["agent"] == "mailer_digest_trend_guard_agent"][0]
    assert guard_run["result_json"]["send_mail"] is False
    assert guard_run["result_json"]["live_outreach_allowed"] is False
    assert result["live_outreach"] is False
    digest_runs = [item for item in result["runs"] if item["agent"] == "mailer_digest_agent"]
    if digest_runs:
        _cleanup(digest_runs[0]["result_json"]["owner_report_action"]["id"])


def test_mailer_digest_retention_agent_does_not_touch_action_queue_or_send_ledger():
    action = execute(
        """
        INSERT INTO mailer_action_queue(action_type, risk_level, status, payload_json)
        VALUES ('owner_report', 'SAFE_AUTO', 'queued', '{"source":"p42-retention-test"}'::jsonb)
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
    run = run_agent("mailer_digest_retention_agent")
    assert run["result_json"]["send_mail"] is False
    assert fetch_one("SELECT count(*) AS count FROM mailer_action_queue WHERE id = %s", (action["id"],))["count"] == 1
    assert fetch_one("SELECT count(*) AS count FROM mailer_send_ledger WHERE action_id = %s", (action["id"],))["count"] == 1
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (action["id"],))
