from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.audit_refresh_repair import audit_refresh_attachment_repair_snapshot, repair_audit_refresh_attachments
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent LIKE %s AND result_json::text LIKE %s", ("audit_refresh_attachment_repair%", f"%{token}%"))
    execute("DELETE FROM screenshots WHERE public_url LIKE %s OR file_path LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM audit_issues WHERE public_text LIKE %s OR title LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR url LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s OR summary LIKE %s", (f"%{token}%", f"%{token}%", f"%{token}%"))


def _mismatch(token: str) -> tuple[str, str, str]:
    original = execute(
        """
        INSERT INTO audits(domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, 'completed', 21, %s, %s, now())
        RETURNING id
        """,
        (f"p90-original-{token}.test", f"https://p90-original-{token}.test", f"old {token}", f"p90-original-{token}"),
    )
    duplicate = execute(
        """
        INSERT INTO audits(domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, 'completed', 88, %s, %s, now())
        RETURNING id
        """,
        (f"p90-new-{token}.test", f"https://p90-new-{token}.test", f"new {token}", f"p90-new-{token}"),
    )
    execute(
        """
        INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
        VALUES (%s, 'availability', 'critical', %s, %s, 'Check hosting.')
        """,
        (duplicate["id"], f"P90 issue {token}", f"P90 public {token}"),
    )
    execute(
        """
        INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport)
        VALUES (%s, 'desktop', %s, %s, 'desktop')
        """,
        (duplicate["id"], f"/tmp/p90-{token}.png", f"/media/p90-{token}.png"),
    )
    job = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, audit_id, result_json, completed_at)
        VALUES (%s, %s, false, 'completed', 300, %s, %s, now())
        RETURNING id
        """,
        (
            f"https://p90-new-{token}.test",
            f"P90 {token}",
            duplicate["id"],
            Jsonb({"job_meta": {"reason": "audit_evidence_remediation", "audit_id": str(original["id"]), "token": token}}),
        ),
    )
    return str(job["id"]), str(original["id"]), str(duplicate["id"])


def test_audit_refresh_attachment_repair_reattaches_duplicate_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        job_id, original_id, duplicate_id = _mismatch(token)
        snapshot = audit_refresh_attachment_repair_snapshot(25)
        assert any(item["job_id"] == job_id for item in snapshot["jobs"])
        dry = repair_audit_refresh_attachments(25, dry_run=True)
        assert dry["repaired_count"] == 0
        result = repair_audit_refresh_attachments(25, dry_run=False)
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert any(item["job_id"] == job_id for item in result["repaired"])
        original = fetch_one("SELECT domain, score, summary FROM audits WHERE id = %s", (original_id,))
        duplicate = fetch_one("SELECT status FROM audits WHERE id = %s", (duplicate_id,))
        job = fetch_one("SELECT audit_id, result_json FROM scanner_jobs WHERE id = %s", (job_id,))
        assert original["domain"] == f"p90-new-{token}.test"
        assert original["score"] == 88
        assert original["summary"] == f"new {token}"
        assert duplicate["status"] == "superseded"
        assert str(job["audit_id"]) == original_id
        assert job["result_json"]["audit_refresh_attachment_repaired"] is True
        assert fetch_one("SELECT count(*) AS count FROM audit_issues WHERE audit_id = %s", (original_id,))["count"] == 1
        assert fetch_one("SELECT count(*) AS count FROM screenshots WHERE audit_id = %s", (original_id,))["count"] == 1
    finally:
        _cleanup(token)


def test_audit_refresh_attachment_repair_endpoint_and_agent_are_admin_gated():
    token = uuid.uuid4().hex[:8]
    try:
        _mismatch(token)
        assert client.get("/admin/audit-refresh/attachment-repair").status_code == 401
        assert client.post("/admin/audit-refresh/attachment-repair", json={"dry_run": True}).status_code == 401
        response = client.post("/admin/audit-refresh/attachment-repair", json={"dry_run": True}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["repair"]["send_mail"] is False
        agent = run_agent("audit_refresh_attachment_repair_agent", {"limit": 25, "dry_run": True})
        assert agent["status"] == "completed"
        assert agent["result_json"]["smtp_called"] is False
    finally:
        _cleanup(token)
