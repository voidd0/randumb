from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.scanner_ops import retry_transient_scanner_failures, scanner_queue_health_snapshot


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM agent_runs WHERE agent IN ('scanner_agent', 'scanner_retry_agent') AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scanner_jobs WHERE url LIKE %s OR result_json::text LIKE %s", (f"%{token}%", f"%{token}%"))


def _failed_job(token: str, error: str = "TimeoutError", retry_count: int = 0) -> str:
    row = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, status, error, result_json, completed_at)
        VALUES (%s, %s, 'failed', %s, %s, now())
        RETURNING id
        """,
        (
            f"https://p71-{token}.example.test",
            f"P71 {token}",
            error,
            Jsonb({"token": token, "scanner_retry_count": retry_count}),
        ),
    )
    return str(row["id"])


def test_scanner_queue_health_counts_retryable_transients():
    token = uuid.uuid4().hex[:8]
    try:
        _failed_job(token, "TimeoutError", 0)
        snapshot = scanner_queue_health_snapshot(50)
        assert snapshot["status"] == "ready"
        assert snapshot["retryable_transient_count"] >= 1
        assert snapshot["send_mail"] is False
        assert snapshot["smtp_called"] is False
        assert snapshot["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_scanner_retry_dry_run_does_not_requeue():
    token = uuid.uuid4().hex[:8]
    try:
        job_id = _failed_job(token, "TimeoutError", 0)
        result = retry_transient_scanner_failures(5, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["requeued_count"] == 0
        assert result["send_mail"] is False
        row = fetch_one("SELECT status FROM scanner_jobs WHERE id = %s", (job_id,))
        assert row["status"] == "failed"
    finally:
        _cleanup(token)


def test_scanner_retry_requeues_once_and_marks_retry_count():
    token = uuid.uuid4().hex[:8]
    try:
        job_id = _failed_job(token, "TimeoutError", 0)
        result = retry_transient_scanner_failures(5, dry_run=False)
        assert result["status"] in {"requeued", "idle"}
        assert result["requeued_count"] >= 1
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        row = fetch_one("SELECT status, error, result_json FROM scanner_jobs WHERE id = %s", (job_id,))
        assert row["status"] == "queued"
        assert row["error"] is None
        assert int(row["result_json"]["scanner_retry_count"]) == 1

        execute("UPDATE scanner_jobs SET status = 'failed', error = 'TimeoutError', updated_at = now() WHERE id = %s", (job_id,))
        second = retry_transient_scanner_failures(5, dry_run=False)
        row = fetch_one("SELECT status, result_json FROM scanner_jobs WHERE id = %s", (job_id,))
        assert row["status"] == "failed"
        assert int(row["result_json"]["scanner_retry_count"]) == 1
        assert second["send_mail"] is False
    finally:
        _cleanup(token)


def test_scanner_ops_admin_and_agents_are_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _failed_job(token, "TimeoutError", 0)
        assert client.get("/admin/scanner/queue-health").status_code == 401
        assert client.post("/admin/scanner/retry-transient", json={"dry_run": True}).status_code == 401
        response = client.get("/admin/scanner/queue-health", headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["scanner"]["send_mail"] is False
        retry = client.post("/admin/scanner/retry-transient", json={"limit": 5, "dry_run": True}, headers=admin_headers())
        assert retry.status_code == 200
        assert retry.json()["scanner"]["status"] == "dry_run"
        health_agent = run_agent("scanner_agent", {"limit": 20})
        retry_agent = run_agent("scanner_retry_agent", {"limit": 5, "dry_run": True})
        assert health_agent["status"] == "completed"
        assert retry_agent["status"] == "completed"
        assert health_agent["result_json"]["send_mail"] is False
        assert retry_agent["result_json"]["send_mail"] is False
    finally:
        _cleanup(token)
