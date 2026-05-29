from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.mailer_action_queue import archive_mailer_nonactionable_artifacts, process_mailer_action_queue
from app.mailer_control_room import cleanup_mailer_digest_history, mailer_digest_summary, mailer_digest_trend_guard, write_owner_status_report
from app.mailer_ops_actions import run_mailer_ops_action
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def clean_trend_guard_runtime() -> None:
    archive_mailer_nonactionable_artifacts()
    process_mailer_action_queue(100)
    archive_mailer_nonactionable_artifacts()


def test_digest_summary_endpoint_requires_auth_and_exposes_evidence():
    assert client.get("/admin/mailer/digest-summary").status_code == 401
    write_owner_status_report(send_if_safe=False)
    response = client.get("/admin/mailer/digest-summary", headers=admin_headers())
    assert response.status_code == 200
    digest = response.json()["digest"]
    assert "mailer_ops" in digest
    assert digest["owner_report_action_status"] in {"queued", "prepared", "blocked", "none"}
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", ("%daily_digest_hook%",))


def test_digest_summary_omits_raw_recipients_and_send_flags():
    digest = mailer_digest_summary()
    assert digest["raw_recipient_addresses_included"] is False
    assert digest["send_mail"] is False
    assert digest["live_outreach_allowed"] is False
    assert "@example" not in str(digest)


def test_digest_owner_report_draft_stays_no_send():
    report = write_owner_status_report(send_if_safe=False)
    digest = mailer_digest_summary()
    assert report["email_sent"] is False
    assert digest["email_sent"] is False
    assert digest["latest_owner_report_action"]["status"] == "prepared"
    assert digest["latest_owner_report_action"]["recipient_hash"]
    assert "@" not in digest["latest_owner_report_action"]["recipient_hash"]
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (report["owner_report_action"]["id"],))


def test_digest_summary_includes_latest_owner_report_state():
    report = write_owner_status_report(send_if_safe=False)
    digest = mailer_digest_summary()
    assert digest["latest_owner_report"] is not None
    assert digest["latest_owner_report"]["payload_json"]["email_sent"] is False
    assert digest["latest_owner_report"]["payload_json"]["send_decision"] == report["send_decision"]
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (report["owner_report_action"]["id"],))


def test_digest_summary_includes_runtime_report_metadata():
    run = run_agent("mailer_digest_agent")
    digest = mailer_digest_summary()
    report = digest["digest_agent_report"]
    assert report["exists"] is True
    assert report["path"].endswith("mailer_digest_agent_report.md")
    assert report["modified_at"]
    assert report["email_sent"] is False
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (run["result_json"]["owner_report_action"]["id"],))


def test_digest_report_metadata_omits_raw_recipients_and_secrets():
    run = run_agent("mailer_digest_agent")
    report = mailer_digest_summary()["digest_agent_report"]
    assert report["raw_recipient_addresses_included"] is False
    assert report["secrets_included"] is False
    assert "owner-private@" not in str(report)
    assert "SMTP_PASSWORD" not in str(report)
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (run["result_json"]["owner_report_action"]["id"],))


def test_digest_summary_endpoint_returns_report_metadata_behind_auth():
    run = run_agent("mailer_digest_agent")
    assert client.get("/admin/mailer/digest-summary").status_code == 401
    response = client.get("/admin/mailer/digest-summary", headers=admin_headers())
    assert response.status_code == 200
    report = response.json()["digest"]["digest_agent_report"]
    assert report["exists"] is True
    assert report["email_sent"] is False
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (run["result_json"]["owner_report_action"]["id"],))


def test_digest_summary_send_flags_remain_false_with_runtime_report():
    run = run_agent("mailer_digest_agent")
    digest = mailer_digest_summary()
    assert digest["send_mail"] is False
    assert digest["live_outreach_allowed"] is False
    assert digest["digest_agent_report"]["email_sent"] is False
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (run["result_json"]["owner_report_action"]["id"],))


def test_digest_summary_includes_sanitized_history():
    run = run_agent("mailer_digest_agent")
    digest = mailer_digest_summary()
    history = digest["digest_agent_history"]
    assert history["count"] >= 1
    assert history["latest"]["email_sent"] is False
    assert history["raw_recipient_addresses_included"] is False
    assert history["secrets_included"] is False
    assert "owner-private@" not in str(history)
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (run["result_json"]["owner_report_action"]["id"],))
    execute("DELETE FROM mailer_digest_reports WHERE id = %s", (run["result_json"]["digest_agent_report"]["history_id"],))


def test_digest_summary_includes_ops_retention_history_evidence():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run = run_agent("mailer_ops_retention_agent")
    digest = mailer_digest_summary()
    history = digest["mailer_ops_retention_history"]
    assert history["count"] >= 1
    assert history["latest"]["send_mail"] is False
    assert history["latest"]["smtp_called"] is False
    assert history["latest"]["live_outreach_allowed"] is False
    assert history["raw_recipient_addresses_included"] is False
    assert history["secrets_included"] is False
    assert digest["send_mail"] is False
    assert digest["live_outreach_allowed"] is False
    assert "owner-private@" not in str(history)
    assert "SMTP_PASSWORD" not in str(history)
    execute("DELETE FROM mailer_ops_retention_reports WHERE id = %s", (run["result_json"]["ops_retention_agent_report"]["history_id"],))
    execute("DELETE FROM agent_runs WHERE id = %s", (run["id"],))
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (real["run"]["id"],))


def test_digest_summary_endpoint_exposes_ops_retention_history_behind_auth():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run = run_agent("mailer_ops_retention_agent")
    response = client.get("/admin/mailer/digest-summary", headers=admin_headers())
    assert response.status_code == 200
    history = response.json()["digest"]["mailer_ops_retention_history"]
    assert history["count"] >= 1
    assert history["latest"]["send_mail"] is False
    assert history["raw_recipient_addresses_included"] is False
    assert history["secrets_included"] is False
    execute("DELETE FROM mailer_ops_retention_reports WHERE id = %s", (run["result_json"]["ops_retention_agent_report"]["history_id"],))
    execute("DELETE FROM agent_runs WHERE id = %s", (run["id"],))
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (real["run"]["id"],))


def test_digest_trend_guard_passes_clean_no_send_history():
    clean_trend_guard_runtime()
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    retention_run = run_agent("mailer_ops_retention_agent")
    digest_run = run_agent("mailer_digest_agent")
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (digest_run["result_json"]["owner_report_action"]["id"],))
    guard = mailer_digest_trend_guard()
    assert guard["decision"] == "PASS_NO_SEND"
    assert guard["regressions"] == []
    assert guard["send_mail"] is False
    assert guard["smtp_called"] is False
    assert guard["live_outreach_allowed"] is False
    assert guard["raw_recipient_addresses_included"] is False
    assert guard["secrets_included"] is False
    assert guard["queue_hygiene"]["mailer_action_queue_rows"] == 0
    assert "owner-private@" not in str(guard)
    assert "SMTP_PASSWORD" not in str(guard)
    execute("DELETE FROM mailer_digest_reports WHERE id = %s", (digest_run["result_json"]["digest_agent_report"]["history_id"],))
    execute("DELETE FROM mailer_ops_retention_reports WHERE id = %s", (retention_run["result_json"]["ops_retention_agent_report"]["history_id"],))
    execute("DELETE FROM agent_runs WHERE id IN (%s, %s)", (digest_run["id"], retention_run["id"]))
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (real["run"]["id"],))


def test_digest_trend_guard_blocks_queue_regression():
    clean_trend_guard_runtime()
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    retention_run = run_agent("mailer_ops_retention_agent")
    digest_run = run_agent("mailer_digest_agent")
    action = execute(
        """
        INSERT INTO mailer_action_queue(action_type, risk_level, status, payload_json)
        VALUES ('owner_report', 'SAFE_AUTO', 'queued', '{"source":"p53-trend-regression"}'::jsonb)
        RETURNING id
        """
    )
    guard = mailer_digest_trend_guard()
    assert guard["decision"] == "FAIL_BLOCK_LAUNCH"
    assert "mailer_action_queue_not_empty" in guard["regressions"]
    assert guard["send_mail"] is False
    execute("DELETE FROM mailer_action_queue WHERE id IN (%s, %s)", (action["id"], digest_run["result_json"]["owner_report_action"]["id"]))
    execute("DELETE FROM mailer_digest_reports WHERE id = %s", (digest_run["result_json"]["digest_agent_report"]["history_id"],))
    execute("DELETE FROM mailer_ops_retention_reports WHERE id = %s", (retention_run["result_json"]["ops_retention_agent_report"]["history_id"],))
    execute("DELETE FROM agent_runs WHERE id IN (%s, %s)", (digest_run["id"], retention_run["id"]))
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (real["run"]["id"],))


def test_digest_trend_guard_endpoint_requires_auth_and_is_no_send():
    clean_trend_guard_runtime()
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    retention_run = run_agent("mailer_ops_retention_agent")
    digest_run = run_agent("mailer_digest_agent")
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (digest_run["result_json"]["owner_report_action"]["id"],))
    assert client.get("/admin/mailer/digest-trend-guard").status_code == 401
    response = client.get("/admin/mailer/digest-trend-guard", headers=admin_headers())
    assert response.status_code == 200
    guard = response.json()["trend_guard"]
    assert guard["decision"] == "PASS_NO_SEND"
    assert guard["send_mail"] is False
    assert guard["live_outreach_allowed"] is False
    assert guard["raw_recipient_addresses_included"] is False
    assert guard["secrets_included"] is False
    execute("DELETE FROM mailer_digest_reports WHERE id = %s", (digest_run["result_json"]["digest_agent_report"]["history_id"],))
    execute("DELETE FROM mailer_ops_retention_reports WHERE id = %s", (retention_run["result_json"]["ops_retention_agent_report"]["history_id"],))
    execute("DELETE FROM agent_runs WHERE id IN (%s, %s)", (digest_run["id"], retention_run["id"]))
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (real["run"]["id"],))


def test_digest_history_cleanup_keeps_newest_rows():
    execute("DELETE FROM mailer_digest_reports WHERE report_path LIKE %s", ("%p41-retention-%",))
    execute(
        """
        INSERT INTO mailer_digest_reports(
            report_path, email_sent, warmup_sent_count, live_outreach_sent_count,
            bounce_or_dsn_count_24h, rate_limit_signal_count_24h, blockers_json, created_at
        )
        SELECT '/app/storage/reports/p41-retention-' || gs::text || '.md',
               false, 0, 0, 0, 0, '[]'::jsonb, now() - (gs || ' minutes')::interval
        FROM generate_series(1, 95) AS gs
        """
    )
    result = cleanup_mailer_digest_history(90)
    rows = fetch_one("SELECT count(*) AS count FROM mailer_digest_reports WHERE report_path LIKE %s", ("%p41-retention-%",))
    assert result["deleted_count"] >= 5
    assert rows["count"] <= 90
    assert result["after"]["total_rows"] <= 90
    execute("DELETE FROM mailer_digest_reports WHERE report_path LIKE %s", ("%p41-retention-%",))


def test_digest_history_cleanup_never_touches_action_queue_or_send_ledger():
    action = execute(
        """
        INSERT INTO mailer_action_queue(action_type, risk_level, status, payload_json)
        VALUES ('owner_report', 'SAFE_AUTO', 'queued', '{"source":"p41-retention-test"}'::jsonb)
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
    before_queue = fetch_one("SELECT count(*) AS count FROM mailer_action_queue WHERE id = %s", (action["id"],))["count"]
    before_ledger = fetch_one("SELECT count(*) AS count FROM mailer_send_ledger WHERE action_id = %s", (action["id"],))["count"]
    cleanup_mailer_digest_history(90)
    after_queue = fetch_one("SELECT count(*) AS count FROM mailer_action_queue WHERE id = %s", (action["id"],))["count"]
    after_ledger = fetch_one("SELECT count(*) AS count FROM mailer_send_ledger WHERE action_id = %s", (action["id"],))["count"]
    assert before_queue == after_queue == 1
    assert before_ledger == after_ledger == 1
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (action["id"],))


def test_digest_history_retention_summary_omits_raw_recipients_and_send_flags():
    run = run_agent("mailer_digest_agent")
    retention = mailer_digest_summary()["digest_agent_history"]["retention"]
    assert retention["latest_email_sent"] is False
    assert retention["raw_recipient_addresses_included"] is False
    assert retention["secrets_included"] is False
    assert "owner-private@" not in str(retention)
    assert "SMTP_PASSWORD" not in str(retention)
    execute("DELETE FROM mailer_action_queue WHERE id = %s", (run["result_json"]["owner_report_action"]["id"],))
    execute("DELETE FROM mailer_digest_reports WHERE id = %s", (run["result_json"]["digest_agent_report"]["history_id"],))


def test_digest_history_cleanup_endpoint_requires_auth_and_is_no_send():
    assert client.post("/admin/mailer/digest-history/cleanup", json={"keep": 90}).status_code == 401
    response = client.post("/admin/mailer/digest-history/cleanup", json={"keep": 90}, headers=admin_headers())
    assert response.status_code == 200
    cleanup = response.json()["cleanup"]
    assert cleanup["send_mail"] is False
    assert cleanup["live_outreach_allowed"] is False
    assert cleanup["raw_recipient_addresses_included"] is False
