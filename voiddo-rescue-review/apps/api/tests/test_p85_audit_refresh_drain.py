from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.audit_refresh_drain import audit_refresh_drain_snapshot, latest_audit_refresh_drain_runs, prioritize_audit_refresh_jobs
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM audit_refresh_drain_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent IN ('audit_refresh_drain_agent', 'audit_refresh_prioritize_agent') AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR url LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM audits WHERE public_slug LIKE %s", (f"%{token}%",))


def _job(token: str, priority: int = 120) -> str:
    audit = execute(
        """
        INSERT INTO audits(domain, url, status, score, public_slug, checked_at)
        VALUES (%s, %s, 'completed', 50, %s, now())
        RETURNING id
        """,
        (f"p85-{token}.example.test", f"https://p85-{token}.example.test", f"p85-{token}"),
    )
    job = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, audit_id, result_json)
        VALUES (%s, %s, false, 'queued', %s, %s, %s)
        RETURNING id
        """,
        (
            f"https://p85-{token}.example.test",
            f"P85 {token}",
            priority,
            audit["id"],
            Jsonb({"reason": "audit_evidence_remediation", "token": token, "send_mail": False}),
        ),
    )
    return str(job["id"])


def test_audit_refresh_drain_prioritizes_remediation_jobs_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        job_id = _job(token, priority=299)
        snapshot = audit_refresh_drain_snapshot(25)
        assert any(item["id"] == job_id for item in snapshot["jobs"])
        dry = prioritize_audit_refresh_jobs(25, dry_run=True, priority=300)
        assert dry["prioritized_count"] == 0
        result = prioritize_audit_refresh_jobs(25, dry_run=False, priority=300)
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        row = fetch_one("SELECT priority, result_json FROM scanner_jobs WHERE id = %s", (job_id,))
        assert row["priority"] == 300
        assert row["result_json"]["audit_refresh_drain_prioritized"] is True
    finally:
        _cleanup(token)


def test_audit_refresh_drain_endpoints_and_agents_are_admin_gated():
    token = uuid.uuid4().hex[:8]
    try:
        _job(token)
        assert client.get("/admin/audit-refresh/drain").status_code == 401
        assert client.post("/admin/audit-refresh/prioritize", json={"dry_run": True}).status_code == 401
        response = client.post("/admin/audit-refresh/prioritize", json={"limit": 25, "dry_run": True}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["priority"]["send_mail"] is False
        history = client.get("/admin/audit-refresh/drain-runs", headers=admin_headers())
        assert history.status_code == 200
        assert latest_audit_refresh_drain_runs(5)["send_mail"] is False
        drain_agent = run_agent("audit_refresh_drain_agent", {"limit": 25})
        priority_agent = run_agent("audit_refresh_prioritize_agent", {"limit": 25, "dry_run": True})
        assert drain_agent["status"] == "completed"
        assert priority_agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
