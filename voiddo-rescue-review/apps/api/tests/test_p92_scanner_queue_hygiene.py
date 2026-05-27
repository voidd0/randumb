from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.scanner_queue_hygiene import archive_scanner_queue_artifacts, scanner_queue_hygiene_snapshot


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM scanner_jobs WHERE url LIKE %s OR business_name LIKE %s OR result_json::text LIKE %s", (f"%{token}%", f"%{token}%", f"%{token}%"))
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s", (f"%{token}%",))


def _job(token: str, url: str, name: str):
    return execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, result_json)
        VALUES (%s, %s, false, 'queued', 999, '{}'::jsonb)
        RETURNING id
        """,
        (url, name),
    )


def test_scanner_queue_hygiene_archives_queued_test_jobs_only():
    token = uuid.uuid4().hex[:8]
    try:
        test_job = _job(token, f"https://sim-{token}.example.test", f"sim-{token}")
        real_job = _job(token, f"https://real-{token}.com", f"Real {token}")
        snapshot = scanner_queue_hygiene_snapshot(50)
        assert snapshot["artifact_count"] >= 1
        result = archive_scanner_queue_artifacts(50, apply=True)
        assert result["archived_count"] >= 1
        assert result["send_mail"] is False
        archived = fetch_one("SELECT status, result_json FROM scanner_jobs WHERE id = %s", (test_job["id"],))
        real = fetch_one("SELECT status FROM scanner_jobs WHERE id = %s", (real_job["id"],))
        assert archived["status"] == "archived_test_artifact"
        assert archived["result_json"]["scanner_queue_hygiene"]["live_outreach_allowed"] is False
        assert real["status"] == "queued"
    finally:
        _cleanup(token)


def test_scanner_queue_hygiene_endpoints_and_agent_are_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _job(token, f"https://sim-{token}.example.test", f"sim-{token}")
        assert client.get("/admin/scanner/queue-hygiene").status_code == 401
        ok = client.get("/admin/scanner/queue-hygiene", headers=admin_headers())
        assert ok.status_code == 200
        assert ok.json()["hygiene"]["raw_recipient_addresses_included"] is False
        run = client.post("/admin/scanner/archive-artifacts", json={"limit": 50, "apply": False}, headers=admin_headers())
        assert run.status_code == 200
        assert run.json()["hygiene"]["live_outreach_allowed"] is False
        agent = run_agent("scanner_queue_hygiene_snapshot_agent", {"limit": 50})
        assert agent["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
    finally:
        _cleanup(token)
