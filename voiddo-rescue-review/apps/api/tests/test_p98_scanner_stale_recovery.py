from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.scanner_ops import recover_stale_running_scanner_jobs, scanner_stale_running_snapshot


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM scanner_stale_recovery_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s AND agent LIKE %s", (f"%{token}%", "scanner_stale_%"))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR business_name LIKE %s", (f"%{token}%", f"%{token}%"))


def _cleanup_p98_artifacts() -> None:
    execute("DELETE FROM scanner_stale_recovery_runs WHERE result_json::text LIKE %s", ("%P98 stale scanner%",))
    execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s AND agent LIKE %s", ("%P98 stale scanner%", "scanner_stale_%"))
    execute("DELETE FROM scanner_jobs WHERE business_name LIKE %s", ("P98 stale scanner %",))


def _running_job(token: str, recovery_count: int = 0) -> str:
    row = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, started_at, updated_at, result_json)
        VALUES (%s, %s, false, 'running', 120, now() - interval '3 hours', now() - interval '3 hours', %s)
        RETURNING id
        """,
        (
            f"https://p98-{token}.example",
            f"P98 stale scanner {token}",
            Jsonb({"token": token, "scanner_stale_recovery_count": recovery_count}),
        ),
    )
    return str(row["id"])


def test_stale_running_snapshot_and_recovery_requeue_without_sending():
    token = uuid.uuid4().hex[:8]
    try:
        _cleanup_p98_artifacts()
        job_id = _running_job(token)
        snapshot = scanner_stale_running_snapshot(10, 5)
        assert snapshot["candidate_count"] >= 1
        assert any(item["id"] == job_id for item in snapshot["candidates"])
        assert snapshot["send_mail"] is False
        assert snapshot["live_outreach_allowed"] is False

        dry = recover_stale_running_scanner_jobs(10, 5, dry_run=True)
        assert dry["status"] == "dry_run"
        assert dry["requeued_count"] == 0

        result = recover_stale_running_scanner_jobs(10, 5, dry_run=False)
        assert result["status"] == "recovered"
        assert result["requeued_count"] >= 1
        assert result["failed_count"] == 0
        row = fetch_one("SELECT status, started_at, error, result_json FROM scanner_jobs WHERE id = %s", (job_id,))
        assert row["status"] == "queued"
        assert row["started_at"] is None
        assert row["error"] is None
        assert row["result_json"]["scanner_stale_recovery_count"] == 1
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
    finally:
        _cleanup(token)


def test_stale_running_recovery_fails_job_after_requeue_limit():
    token = uuid.uuid4().hex[:8]
    try:
        _cleanup_p98_artifacts()
        job_id = _running_job(token, recovery_count=1)
        result = recover_stale_running_scanner_jobs(10, 5, dry_run=False, max_requeue_count=1)
        assert result["status"] == "recovered"
        assert result["failed_count"] >= 1
        row = fetch_one("SELECT status, error, result_json FROM scanner_jobs WHERE id = %s", (job_id,))
        assert row["status"] == "failed"
        assert row["error"] == "StaleRunningScannerJob"
        assert row["result_json"]["scanner_stale_recovery_count"] == 2
    finally:
        _cleanup(token)


def test_stale_running_endpoints_and_agent_are_admin_gated_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _cleanup_p98_artifacts()
        _running_job(token)
        assert client.get("/admin/scanner/stale-running").status_code == 401
        assert client.post("/admin/scanner/recover-stale-running", json={"dry_run": True}).status_code == 401

        snapshot = client.get("/admin/scanner/stale-running?older_than_minutes=5", headers=admin_headers())
        assert snapshot.status_code == 200
        assert snapshot.json()["scanner"]["live_outreach_allowed"] is False

        recovery = client.post(
            "/admin/scanner/recover-stale-running",
            json={"limit": 10, "older_than_minutes": 5, "dry_run": True},
            headers=admin_headers(),
        )
        assert recovery.status_code == 200
        assert recovery.json()["scanner"]["send_mail"] is False

        agent = run_agent("scanner_stale_running_snapshot_agent", {"limit": 10, "older_than_minutes": 5})
        assert agent["status"] == "completed"
        assert agent["result_json"]["live_outreach_allowed"] is False

        agent_recovery = run_agent(
            "scanner_stale_recovery_agent",
            {"limit": 10, "older_than_minutes": 5, "dry_run": True},
        )
        assert agent_recovery["status"] == "completed"
        assert agent_recovery["result_json"]["send_mail"] is False
    finally:
        _cleanup(token)
