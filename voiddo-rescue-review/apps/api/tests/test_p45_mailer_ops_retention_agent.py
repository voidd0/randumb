from __future__ import annotations

from pathlib import Path
import os

from fastapi.testclient import TestClient

from app.main import app
from app.autonomous_agents import run_agent, run_daily_loop
from app.db import execute, fetch_one
from app.mailer_ops_actions import cleanup_mailer_ops_synthetic_history, mailer_ops_action_summary, mailer_ops_retention_report_history, run_mailer_ops_action


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _delete_run(run_id: str) -> None:
    execute("DELETE FROM mailer_ops_runs WHERE id = %s", (run_id,))


def _delete_retention_history(history_id: str) -> None:
    execute("DELETE FROM mailer_ops_retention_reports WHERE id = %s", (history_id,))


def test_mailer_ops_retention_agent_exists_and_is_no_send():
    run = run_agent("mailer_ops_retention_agent")
    result = run["result_json"]
    assert run["status"] == "completed"
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False
    assert result["raw_recipient_addresses_included"] is False


def test_mailer_ops_retention_agent_deletes_synthetic_only():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    synthetic = run_mailer_ops_action("customer_transport_dry_run", 1, source="pytest", is_synthetic=True)
    run = run_agent("mailer_ops_retention_agent")
    result = run["result_json"]
    assert result["deleted_count"] >= 1
    assert result["retained_real_count"] >= 1
    assert fetch_one("SELECT id FROM mailer_ops_runs WHERE id = %s", (real["run"]["id"],)) is not None
    assert fetch_one("SELECT id FROM mailer_ops_runs WHERE id = %s", (synthetic["run"]["id"],)) is None
    _delete_run(real["run"]["id"])


def test_mailer_ops_retention_helper_reports_counts_without_send():
    synthetic = run_mailer_ops_action("customer_simulation", source="pytest", is_synthetic=True)
    result = cleanup_mailer_ops_synthetic_history()
    assert result["cleaned"] is True
    assert result["deleted_count"] >= 1
    assert result["after_total_rows"] <= result["before_total_rows"]
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False
    assert fetch_one("SELECT id FROM mailer_ops_runs WHERE id = %s", (synthetic["run"]["id"],)) is None


def test_daily_loop_includes_mailer_ops_retention_agent():
    result = run_daily_loop()
    agents = [item["agent"] for item in result["runs"]]
    assert "mailer_ops_retention_agent" in agents
    retention_runs = [item for item in result["runs"] if item["agent"] == "mailer_ops_retention_agent"]
    assert retention_runs[0]["result_json"]["send_mail"] is False
    assert retention_runs[0]["result_json"]["live_outreach_allowed"] is False
    assert result["live_outreach"] is False


def test_ops_summary_exposes_retention_agent_evidence_without_send():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run_agent("mailer_ops_retention_agent")
    summary = mailer_ops_action_summary()
    assert summary["synthetic_count"] == 0
    assert summary["latest_real"]["action"] == "digest_history_cleanup"
    assert summary["latest_retention_agent"]["status"] == "completed"
    assert summary["latest_retention_agent"]["send_mail"] is False
    assert summary["latest_retention_agent"]["smtp_called"] is False
    assert summary["latest_retention_agent"]["live_outreach_allowed"] is False
    assert summary["latest_retention_agent"]["raw_recipient_addresses_included"] is False
    assert summary["retention_agent_runs"] >= 1
    _delete_run(real["run"]["id"])


def test_ops_summary_exposes_retention_report_metadata_without_send():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run = run_agent("mailer_ops_retention_agent")
    summary = mailer_ops_action_summary()
    report = summary["retention_agent_report"]
    assert report["exists"] is True
    assert report["path_stored"] is True
    assert report["modified_at"]
    assert report["send_mail"] is False
    assert report["smtp_called"] is False
    assert report["live_outreach_allowed"] is False
    assert report["raw_recipient_addresses_included"] is False
    assert report["secrets_included"] is False
    assert "owner-private@" not in str(report)
    assert "SMTP_PASSWORD" not in str(report)
    _delete_run(real["run"]["id"])


def test_mailer_ops_retention_agent_writes_runtime_report_file():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run = run_agent("mailer_ops_retention_agent")
    report = run["result_json"]["ops_retention_agent_report"]
    assert report["agent_run_id"] == str(run["id"])
    assert report["send_mail"] is False
    assert report["smtp_called"] is False
    assert report["live_outreach_allowed"] is False
    assert Path(report["path"]).exists()
    _delete_run(real["run"]["id"])


def test_mailer_ops_retention_agent_report_omits_raw_recipients_and_secrets():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run = run_agent("mailer_ops_retention_agent")
    report = run["result_json"]["ops_retention_agent_report"]
    text = Path(report["path"]).read_text(encoding="utf-8")
    assert "Raw recipient addresses" in text
    assert "owner-private@" not in text
    assert "voiddorescue.com" not in text
    assert "SMTP_PASSWORD" not in text
    assert "PADDLE_API_KEY" not in text
    assert report["raw_recipient_addresses_included"] is False
    assert report["secrets_included"] is False
    _delete_run(real["run"]["id"])


def test_daily_loop_exposes_mailer_ops_retention_report_metadata():
    result = run_daily_loop()
    retention_run = [item for item in result["runs"] if item["agent"] == "mailer_ops_retention_agent"][0]
    report = retention_run["result_json"]["ops_retention_agent_report"]
    assert Path(report["path"]).exists()
    assert report["send_mail"] is False
    assert report["live_outreach_allowed"] is False
    assert result["live_outreach"] is False


def test_mailer_ops_retention_agent_persists_history_row():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run = run_agent("mailer_ops_retention_agent")
    report = run["result_json"]["ops_retention_agent_report"]
    row = fetch_one("SELECT * FROM mailer_ops_retention_reports WHERE id = %s", (report["history_id"],))
    assert row is not None
    assert str(row["agent_run_id"]) == str(run["id"])
    assert row["report_path"] == report["path"]
    assert row["deleted_synthetic_count"] == report["deleted_synthetic_count"]
    assert row["retained_real_count"] == report["retained_real_count"]
    assert row["retained_synthetic_count"] == report["retained_synthetic_count"]
    _delete_retention_history(report["history_id"])
    _delete_run(real["run"]["id"])


def test_mailer_ops_retention_history_omits_raw_recipients_and_secrets():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run = run_agent("mailer_ops_retention_agent")
    report = run["result_json"]["ops_retention_agent_report"]
    row = fetch_one(
        """
        SELECT report_path, raw_recipient_addresses_included, secrets_included
        FROM mailer_ops_retention_reports
        WHERE id = %s
        """,
        (report["history_id"],),
    )
    assert row is not None
    serialized = str(dict(row))
    assert row["raw_recipient_addresses_included"] is False
    assert row["secrets_included"] is False
    assert "owner-private@" not in serialized
    assert "SMTP_PASSWORD" not in serialized
    assert "PADDLE_API_KEY" not in serialized
    _delete_retention_history(report["history_id"])
    _delete_run(real["run"]["id"])


def test_mailer_ops_retention_history_flags_remain_no_send():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run = run_agent("mailer_ops_retention_agent")
    report = run["result_json"]["ops_retention_agent_report"]
    row = fetch_one(
        """
        SELECT send_mail, smtp_called, live_outreach_allowed
        FROM mailer_ops_retention_reports
        WHERE id = %s
        """,
        (report["history_id"],),
    )
    assert row is not None
    assert row["send_mail"] is False
    assert row["smtp_called"] is False
    assert row["live_outreach_allowed"] is False
    _delete_retention_history(report["history_id"])
    _delete_run(real["run"]["id"])


def test_mailer_ops_retention_history_summary_is_redacted_no_send():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run = run_agent("mailer_ops_retention_agent")
    report = run["result_json"]["ops_retention_agent_report"]
    summary = mailer_ops_retention_report_history(5)
    assert summary["count"] >= 1
    assert summary["latest"]["id"] == report["history_id"]
    assert summary["latest"]["send_mail"] is False
    assert summary["latest"]["smtp_called"] is False
    assert summary["latest"]["live_outreach_allowed"] is False
    assert summary["raw_recipient_addresses_included"] is False
    assert summary["secrets_included"] is False
    assert "owner-private@" not in str(summary)
    assert "SMTP_PASSWORD" not in str(summary)
    _delete_retention_history(report["history_id"])
    _delete_run(real["run"]["id"])


def test_mailer_ops_retention_history_endpoint_requires_auth_and_is_no_send():
    real = run_mailer_ops_action("digest_history_cleanup", source="admin", is_synthetic=False)
    run = run_agent("mailer_ops_retention_agent")
    report = run["result_json"]["ops_retention_agent_report"]
    assert client.get("/admin/mailer/ops-retention-history").status_code == 401
    response = client.get("/admin/mailer/ops-retention-history", headers=admin_headers())
    assert response.status_code == 200
    history = response.json()["history"]
    assert history["count"] >= 1
    assert history["latest"]["send_mail"] is False
    assert history["latest"]["live_outreach_allowed"] is False
    assert history["raw_recipient_addresses_included"] is False
    assert history["secrets_included"] is False
    _delete_retention_history(report["history_id"])
    _delete_run(real["run"]["id"])
