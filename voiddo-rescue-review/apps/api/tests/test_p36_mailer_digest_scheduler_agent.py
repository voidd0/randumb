from __future__ import annotations

from pathlib import Path

from app.autonomous_agents import run_agent, run_daily_loop
from app.db import execute, fetch_one
from app.mailer_control_room import cleanup_mailer_policy_score_history, latest_mailer_digest_trend_guard_summary, latest_mailer_policy_score_history, latest_mailer_policy_score_regression_guard_summary, mailer_digest_summary, mailer_policy_score, mailer_policy_score_regression_guard, mailer_policy_score_retention_summary
from app.main import app
from fastapi.testclient import TestClient


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    import os

    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(action_id: str | None = None) -> None:
    if action_id:
        execute("DELETE FROM mailer_action_queue WHERE id = %s", (action_id,))
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", ("%daily_digest_hook%",))
    execute("DELETE FROM mailer_digest_reports WHERE report_path LIKE %s", ("%mailer_digest_agent_report.md%",))
    execute("DELETE FROM mailer_policy_score_history WHERE agent_run_id IS NULL OR created_at > now() - interval '1 hour'")
    execute("DELETE FROM system_events WHERE type = 'mailer.policy_score_regression'")
    execute("DELETE FROM codex_tasks WHERE input_json::text LIKE %s", ("%mailer_policy_score_regression_guard%",))


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


def test_latest_trend_guard_summary_is_compact_and_redacted():
    _clean_trend_runtime()
    run_agent("mailer_ops_retention_agent")
    digest_run = run_agent("mailer_digest_agent")
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (digest_run["result_json"]["owner_report_action"]["id"],))
    run_agent("mailer_digest_trend_guard_agent")
    summary = latest_mailer_digest_trend_guard_summary()
    assert summary["decision"] == "PASS_NO_SEND"
    assert summary["status"] == "completed"
    assert summary["regression_count"] == 0
    assert summary["queue_hygiene"]["mailer_action_queue_rows"] == 0
    assert summary["send_mail"] is False
    assert summary["smtp_called"] is False
    assert summary["live_outreach_allowed"] is False
    assert summary["raw_recipient_addresses_included"] is False
    assert summary["secrets_included"] is False
    assert summary["raw_history_rows_included"] is False
    serialized = str(summary)
    assert "report_path" not in serialized
    assert "blockers_json" not in serialized
    assert "owner-private@" not in serialized
    assert "SMTP_PASSWORD" not in serialized


def test_latest_trend_guard_summary_endpoint_requires_auth_and_is_no_send():
    _clean_trend_runtime()
    run_agent("mailer_ops_retention_agent")
    digest_run = run_agent("mailer_digest_agent")
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (digest_run["result_json"]["owner_report_action"]["id"],))
    run_agent("mailer_digest_trend_guard_agent")
    assert client.get("/admin/mailer/digest-trend-guard/latest").status_code == 401
    response = client.get("/admin/mailer/digest-trend-guard/latest", headers=admin_headers())
    assert response.status_code == 200
    summary = response.json()["trend_guard"]
    assert summary["decision"] == "PASS_NO_SEND"
    assert summary["send_mail"] is False
    assert summary["live_outreach_allowed"] is False
    assert summary["raw_recipient_addresses_included"] is False
    assert summary["secrets_included"] is False
    assert summary["raw_history_rows_included"] is False


def test_latest_trend_guard_summary_fails_closed_without_agent_run():
    execute("DELETE FROM agent_runs WHERE agent = 'mailer_digest_trend_guard_agent'")
    summary = latest_mailer_digest_trend_guard_summary()
    assert summary["decision"] == "FAIL_BLOCK_LAUNCH"
    assert summary["status"] == "missing"
    assert "missing_trend_guard_agent_run" in summary["regressions"]
    assert summary["send_mail"] is False
    assert summary["live_outreach_allowed"] is False


def _prepare_clean_policy_evidence() -> None:
    _clean_trend_runtime()
    execute("DELETE FROM mail_signals WHERE source LIKE %s", ("p57-%",))
    run_agent("mailer_ops_retention_agent")
    digest_run = run_agent("mailer_digest_agent")
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (digest_run["result_json"]["owner_report_action"]["id"],))
    run_agent("mailer_digest_trend_guard_agent")


def test_mailer_policy_score_passes_clean_no_send_evidence():
    _prepare_clean_policy_evidence()
    score = mailer_policy_score()
    assert score["score"] >= 90
    assert score["decision"] == "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"
    assert score["trend_guard_decision"] == "PASS_NO_SEND"
    assert score["send_mail"] is False
    assert score["smtp_called"] is False
    assert score["live_outreach_allowed"] is False
    assert score["raw_recipient_addresses_included"] is False
    assert score["secrets_included"] is False
    serialized = str(score)
    assert "owner-private@" not in serialized
    assert "SMTP_PASSWORD" not in serialized


def test_mailer_policy_score_blocks_current_queue_regression():
    _prepare_clean_policy_evidence()
    action = execute(
        """
        INSERT INTO mailer_action_queue(action_type, risk_level, status, payload_json)
        VALUES ('owner_report', 'SAFE_AUTO', 'queued', '{"source":"p57-policy-regression"}'::jsonb)
        RETURNING id
        """
    )
    score = mailer_policy_score()
    assert score["decision"] == "NO_SEND_BLOCKED_REPAIR"
    assert "current_mailer_action_queue_not_empty" in score["blockers"]
    assert score["queue_hygiene"]["mailer_action_queue_rows"] >= 1
    assert score["send_mail"] is False
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (action["id"],))


def test_mailer_policy_score_blocks_recent_bounce_signal():
    _prepare_clean_policy_evidence()
    execute(
        """
        INSERT INTO mail_signals(signal_type, severity, source, mailbox, raw_summary)
        VALUES ('bounce', 'warning', 'p57-policy-test', 'audit@voiddorescue.com', 'synthetic bounce signal')
        """
    )
    score = mailer_policy_score()
    assert score["decision"] == "NO_SEND_BLOCKED_REPAIR"
    assert "recent_bounce_or_dsn" in score["blockers"]
    assert score["signals"]["bounce_or_dsn_count"] >= 1
    assert score["send_mail"] is False
    execute("DELETE FROM mail_signals WHERE source = 'p57-policy-test'")


def test_mailer_policy_score_endpoint_requires_auth_and_is_no_send():
    _prepare_clean_policy_evidence()
    assert client.get("/admin/mailer/policy-score").status_code == 401
    response = client.get("/admin/mailer/policy-score", headers=admin_headers())
    assert response.status_code == 200
    score = response.json()["policy_score"]
    assert score["score"] >= 90
    assert score["send_mail"] is False
    assert score["live_outreach_allowed"] is False
    assert score["raw_recipient_addresses_included"] is False
    assert score["secrets_included"] is False


def test_mailer_policy_score_agent_exists_and_is_no_send():
    _prepare_clean_policy_evidence()
    run = run_agent("mailer_policy_score_agent")
    result = run["result_json"]
    assert run["status"] == "completed"
    assert result["score"] >= 90
    assert result["decision"] == "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False
    assert result["raw_recipient_addresses_included"] is False
    assert result["secrets_included"] is False
    assert result["policy_score_history"]["score"] >= 90
    assert result["policy_score_history"]["send_mail"] is False


def test_daily_loop_includes_mailer_policy_score_after_trend_guard():
    result = run_daily_loop()
    agents = [item["agent"] for item in result["runs"]]
    assert "mailer_policy_score_agent" in agents
    assert agents.index("mailer_digest_trend_guard_agent") < agents.index("mailer_policy_score_agent")
    assert "mailer_policy_score_retention_agent" in agents
    assert "mailer_policy_score_regression_guard_agent" in agents
    assert agents.index("mailer_policy_score_agent") < agents.index("mailer_policy_score_retention_agent")
    assert agents.index("mailer_policy_score_retention_agent") < agents.index("mailer_policy_score_regression_guard_agent")
    policy_run = [item for item in result["runs"] if item["agent"] == "mailer_policy_score_agent"][0]
    retention_run = [item for item in result["runs"] if item["agent"] == "mailer_policy_score_retention_agent"][0]
    guard_run = [item for item in result["runs"] if item["agent"] == "mailer_policy_score_regression_guard_agent"][0]
    assert policy_run["result_json"]["send_mail"] is False
    assert policy_run["result_json"]["smtp_called"] is False
    assert policy_run["result_json"]["live_outreach_allowed"] is False
    assert policy_run["result_json"]["raw_recipient_addresses_included"] is False
    assert policy_run["result_json"]["secrets_included"] is False
    assert retention_run["result_json"]["send_mail"] is False
    assert guard_run["result_json"]["send_mail"] is False
    assert guard_run["result_json"]["live_outreach_allowed"] is False
    assert result["live_outreach"] is False
    digest_runs = [item for item in result["runs"] if item["agent"] == "mailer_digest_agent"]
    if digest_runs:
        _cleanup(digest_runs[0]["result_json"]["owner_report_action"]["id"])


def test_mailer_policy_score_agent_persists_redacted_history():
    _prepare_clean_policy_evidence()
    before = fetch_one("SELECT count(*) AS count FROM mailer_policy_score_history")
    run = run_agent("mailer_policy_score_agent")
    history = run["result_json"]["policy_score_history"]
    after = fetch_one("SELECT count(*) AS count FROM mailer_policy_score_history")
    assert int(after["count"]) == int(before["count"]) + 1
    row = fetch_one(
        """
        SELECT score, decision, blocker_count, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included
        FROM mailer_policy_score_history
        WHERE id = %s
        """,
        (history["id"],),
    )
    assert row["score"] >= 90
    assert row["decision"] == "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"
    assert row["blocker_count"] == 0
    assert row["send_mail"] is False
    assert row["smtp_called"] is False
    assert row["live_outreach_allowed"] is False
    assert row["raw_recipient_addresses_included"] is False
    assert row["secrets_included"] is False
    execute("DELETE FROM mailer_policy_score_history WHERE id = %s", (history["id"],))


def test_policy_score_history_endpoint_requires_auth_and_is_redacted():
    _prepare_clean_policy_evidence()
    run = run_agent("mailer_policy_score_agent")
    assert client.get("/admin/mailer/policy-score/history").status_code == 401
    response = client.get("/admin/mailer/policy-score/history", headers=admin_headers())
    assert response.status_code == 200
    history = response.json()["history"]
    assert history["count"] >= 1
    assert history["latest_score"] >= 90
    assert history["latest_send_mail"] is False
    assert history["latest_live_outreach_allowed"] is False
    assert history["raw_recipient_addresses_included"] is False
    assert history["secrets_included"] is False
    assert history["raw_history_rows_included"] is False
    serialized = str(history)
    assert "owner-private@" not in serialized
    assert "SMTP_PASSWORD" not in serialized
    execute("DELETE FROM mailer_policy_score_history WHERE id = %s", (run["result_json"]["policy_score_history"]["id"],))


def test_mailer_digest_includes_policy_score_history_without_sending():
    _prepare_clean_policy_evidence()
    policy_run = run_agent("mailer_policy_score_agent")
    digest = mailer_digest_summary()
    policy_history = digest["mailer_policy_score_history"]
    assert policy_history["count"] >= 1
    assert policy_history["latest_score"] >= 90
    assert policy_history["latest_send_mail"] is False
    assert policy_history["raw_recipient_addresses_included"] is False
    assert policy_history["secrets_included"] is False
    execute("DELETE FROM mailer_policy_score_history WHERE id = %s", (policy_run["result_json"]["policy_score_history"]["id"],))


def test_mailer_digest_agent_report_includes_policy_score_history_evidence():
    _prepare_clean_policy_evidence()
    policy_run = run_agent("mailer_policy_score_agent")
    digest_run = run_agent("mailer_digest_agent")
    report = digest_run["result_json"]["digest_agent_report"]
    assert report["mailer_policy_score_history"]["count"] >= 1
    assert report["mailer_policy_score_history"]["latest_score"] >= 90
    assert report["mailer_policy_score_history"]["latest_send_mail"] is False
    text = Path(report["path"]).read_text(encoding="utf-8")
    assert "mailer_policy_score_history_rows" in text
    assert "mailer_policy_latest_score" in text
    assert "mailer_policy_history_raw_recipients: `false`" in text
    assert "mailer_policy_history_secrets: `false`" in text
    _cleanup(digest_run["result_json"]["owner_report_action"]["id"])
    execute("DELETE FROM mailer_policy_score_history WHERE id = %s", (policy_run["result_json"]["policy_score_history"]["id"],))


def test_policy_score_history_retention_deletes_old_rows_without_sending():
    execute("DELETE FROM mailer_policy_score_history WHERE decision LIKE %s", ("p60-retention-%",))
    execute(
        """
        INSERT INTO mailer_policy_score_history(score, decision, blocker_count, created_at)
        SELECT 100, 'p60-retention-' || gs::text, 0, now() - (gs || ' minutes')::interval
        FROM generate_series(1, 130) AS gs
        """
    )
    cleanup = cleanup_mailer_policy_score_history(120)
    summary = mailer_policy_score_retention_summary()
    remaining = fetch_one("SELECT count(*) AS count FROM mailer_policy_score_history WHERE decision LIKE %s", ("p60-retention-%",))
    assert cleanup["deleted_count"] >= 10
    assert summary["total_rows"] >= 120
    assert int(remaining["count"]) <= 120
    assert cleanup["send_mail"] is False
    assert cleanup["live_outreach_allowed"] is False
    assert cleanup["raw_recipient_addresses_included"] is False
    execute("DELETE FROM mailer_policy_score_history WHERE decision LIKE %s", ("p60-retention-%",))


def test_policy_score_regression_guard_passes_clean_history():
    _prepare_clean_policy_evidence()
    run_agent("mailer_policy_score_agent")
    run_agent("mailer_policy_score_agent")
    guard = mailer_policy_score_regression_guard()
    assert guard["decision"] == "PASS_NO_SEND"
    assert guard["regressions"] == []
    assert guard["send_mail"] is False
    assert guard["smtp_called"] is False
    assert guard["live_outreach_allowed"] is False
    assert guard["review_task_created"] is False


def test_policy_score_regression_guard_creates_review_task_on_score_drop():
    _prepare_clean_policy_evidence()
    run_agent("mailer_policy_score_agent")
    execute(
        """
        INSERT INTO mailer_policy_score_history(score, decision, blocker_count, blockers_json, mail_qa_decision)
        VALUES (65, 'NO_SEND_BLOCKED_REPAIR', 1, '["p60-regression"]'::jsonb, 'PASS')
        """
    )
    guard = mailer_policy_score_regression_guard()
    assert guard["decision"] == "FAIL_BLOCK_LAUNCH"
    assert "latest_policy_decision_not_ready" in guard["regressions"]
    assert "policy_score_drop" in guard["regressions"]
    assert guard["review_task_created"] is True
    assert guard["send_mail"] is False
    assert fetch_one("SELECT count(*) AS count FROM system_events WHERE type = 'mailer.policy_score_regression'")["count"] >= 1
    assert fetch_one("SELECT count(*) AS count FROM codex_tasks WHERE input_json::text LIKE %s", ("%mailer_policy_score_regression_guard%",))["count"] >= 1
    _cleanup()


def test_policy_score_retention_and_regression_endpoints_require_auth():
    _prepare_clean_policy_evidence()
    run_agent("mailer_policy_score_agent")
    run_agent("mailer_policy_score_regression_guard_agent")
    assert client.get("/admin/mailer/policy-score/retention").status_code == 401
    assert client.get("/admin/mailer/policy-score/regression-guard/latest").status_code == 401
    retention = client.get("/admin/mailer/policy-score/retention", headers=admin_headers())
    guard = client.get("/admin/mailer/policy-score/regression-guard/latest", headers=admin_headers())
    assert retention.status_code == 200
    assert guard.status_code == 200
    assert retention.json()["retention"]["latest_send_mail"] is False
    assert guard.json()["guard"]["send_mail"] is False
    assert guard.json()["guard"]["raw_recipient_addresses_included"] is False


def test_latest_policy_score_regression_guard_summary_fails_closed_without_run():
    execute("DELETE FROM agent_runs WHERE agent = 'mailer_policy_score_regression_guard_agent'")
    summary = latest_mailer_policy_score_regression_guard_summary()
    assert summary["decision"] == "MISSING"
    assert "missing_policy_score_regression_guard_run" in summary["regressions"]
    assert summary["send_mail"] is False
    assert summary["live_outreach_allowed"] is False


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
