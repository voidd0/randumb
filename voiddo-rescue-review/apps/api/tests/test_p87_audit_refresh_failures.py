from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.audit_refresh_failures import audit_refresh_failure_snapshot, latest_audit_refresh_failure_runs, retry_failed_audit_refresh_jobs
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM audit_refresh_failure_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent IN ('audit_refresh_failure_agent', 'audit_refresh_retry_failures_agent') AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR url LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM audits WHERE public_slug LIKE %s", (f"%{token}%",))


def _failed_job(token: str, retry_count: int = 0, error: str = "Error") -> str:
    audit = execute(
        """
        INSERT INTO audits(domain, url, status, score, public_slug, checked_at)
        VALUES (%s, %s, 'completed', 44, %s, now())
        RETURNING id
        """,
        (f"p87-{token}.example.test", f"https://p87-{token}.example.test", f"p87-{token}"),
    )
    job = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, audit_id, error, result_json, completed_at)
        VALUES (%s, %s, false, 'failed', 220, %s, %s, %s, now())
        RETURNING id
        """,
        (
            f"https://p87-{token}.example.test",
            f"P87 {token}",
            audit["id"],
            error,
            Jsonb({"reason": "audit_evidence_remediation", "token": token, "scanner_retry_count": retry_count}),
        ),
    )
    return str(job["id"])


def test_audit_refresh_failure_retry_requeues_once_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        job_id = _failed_job(token)
        snapshot = audit_refresh_failure_snapshot(25)
        assert any(item["job_id"] == job_id and item["retryable"] for item in snapshot["jobs"])
        dry = retry_failed_audit_refresh_jobs(10, dry_run=True)
        assert dry["requeued_count"] == 0
        result = retry_failed_audit_refresh_jobs(10, dry_run=False, priority=260)
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert any(item["job_id"] == job_id for item in result["requeued"])
        row = fetch_one("SELECT status, priority, error, result_json FROM scanner_jobs WHERE id = %s", (job_id,))
        assert row["status"] == "queued"
        assert row["priority"] == 260
        assert row["error"] is None
        assert row["result_json"]["scanner_retry_count"] == 1
        assert row["result_json"]["scanner_retry_reason"] == "audit_evidence_remediation_transient_failure"
    finally:
        _cleanup(token)


def test_audit_refresh_failure_retry_does_not_retry_exhausted_jobs():
    token = uuid.uuid4().hex[:8]
    try:
        job_id = _failed_job(token, retry_count=1)
        result = retry_failed_audit_refresh_jobs(10, dry_run=False, priority=260)
        assert not any(item["job_id"] == job_id for item in result["requeued"])
        row = fetch_one("SELECT status, priority FROM scanner_jobs WHERE id = %s", (job_id,))
        assert row["status"] == "failed"
        assert row["priority"] == 220
    finally:
        _cleanup(token)


def test_audit_refresh_failure_scanner_fix_retry_requeues_exhausted_once():
    token = uuid.uuid4().hex[:8]
    try:
        job_id = _failed_job(token, retry_count=1)
        dry = retry_failed_audit_refresh_jobs(10, dry_run=True, priority=300, allow_scanner_fix_retry=True)
        assert dry["requeued_count"] == 0
        assert dry["scanner_fix_retryable_count"] >= 1
        result = retry_failed_audit_refresh_jobs(10, dry_run=False, priority=300, allow_scanner_fix_retry=True)
        assert any(item["job_id"] == job_id for item in result["requeued"])
        row = fetch_one("SELECT status, priority, error, result_json FROM scanner_jobs WHERE id = %s", (job_id,))
        assert row["status"] == "queued"
        assert row["priority"] == 300
        assert row["error"] is None
        assert row["result_json"]["scanner_retry_count"] == 1
        assert row["result_json"]["scanner_fix_retry_count"] == 1
        assert row["result_json"]["scanner_retry_reason"] == "audit_evidence_remediation_after_scanner_navigation_fix"
        second = retry_failed_audit_refresh_jobs(10, dry_run=False, priority=300, allow_scanner_fix_retry=True)
        assert not any(item["job_id"] == job_id for item in second["requeued"])
    finally:
        _cleanup(token)


def test_audit_refresh_failure_endpoints_and_agents_are_admin_gated():
    token = uuid.uuid4().hex[:8]
    try:
        _failed_job(token)
        assert client.get("/admin/audit-refresh/failures").status_code == 401
        assert client.post("/admin/audit-refresh/retry-failures", json={"dry_run": True}).status_code == 401
        response = client.post("/admin/audit-refresh/retry-failures", json={"dry_run": True}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["retry"]["send_mail"] is False
        history = client.get("/admin/audit-refresh/failure-runs", headers=admin_headers())
        assert history.status_code == 200
        assert latest_audit_refresh_failure_runs(5)["send_mail"] is False
        failure_agent = run_agent("audit_refresh_failure_agent", {"limit": 25})
        retry_agent = run_agent("audit_refresh_retry_failures_agent", {"limit": 10, "dry_run": True})
        assert failure_agent["status"] == "completed"
        assert retry_agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
