from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.source_scanner_queue import latest_source_scanner_queue_runs, queue_source_scanner_jobs, source_scanner_backlog


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM source_scanner_queue_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR business_name LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_source_performance_scores WHERE reasoning_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scout_leads WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_runs WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM scout_sources WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent IN ('source_scanner_backlog_agent', 'source_scanner_queue_agent') AND result_json::text LIKE %s", (f"%{token}%",))


def _seed_accepted_scout_leads(token: str, count: int = 2) -> str:
    source = execute(
        """
        INSERT INTO scout_sources(name, source_type, country, language, niche, status, config_json)
        VALUES (%s, 'manual_csv_scout', 'IE', 'en', 'dentists', 'active', '{}'::jsonb)
        RETURNING id
        """,
        (f"p77-source-{token}",),
    )
    run = execute(
        """
        INSERT INTO scout_runs(source_id, status, country, niche, language, found_count, accepted_count, completed_at)
        VALUES (%s, 'completed', 'IE', 'dentists', 'en', %s, %s, now())
        RETURNING id
        """,
        (source["id"], count, count),
    )
    execute(
        """
        INSERT INTO scout_source_performance_scores(
          source_id, status, scanned_count, scored_count, qualified_count,
          qualified_rate, average_final_score, email_coverage, issue_signal_rate,
          recommendation, reasoning_json
        )
        VALUES (%s, 'PASS_SOURCE_PERFORMANCE_NO_SEND', 4, 4, 2, 0.5, 81, 0.75, 0.6,
                'PROMOTE_SOURCE_FOR_MORE_SCOUTING', %s)
        """,
        (source["id"], Jsonb({"token": token})),
    )
    for index in range(count):
        domain = f"p77-{token}-{index}.clinic"
        execute(
            """
            INSERT INTO scout_leads(scout_run_id, business_name, domain, website_url, email, country, city, language, niche, source_url, confidence, status)
            VALUES (%s, %s, %s, %s, %s, 'IE', 'Queue City', 'en', 'dentists', %s, 91, 'accepted')
            """,
            (run["id"], f"P77 Clinic {token} {index}", domain, f"https://{domain}", f"owner-{token}-{index}@{domain}", f"https://source.test/{token}/{index}"),
        )
    return str(source["id"])


def test_source_scanner_queue_creates_scanner_jobs_without_send_and_dedupes():
    token = uuid.uuid4().hex[:8]
    try:
        source_id = _seed_accepted_scout_leads(token, 2)
        backlog = source_scanner_backlog(20, source_id)
        assert backlog["candidate_count"] == 2
        assert backlog["source_count"] == 1
        assert backlog["send_mail"] is False

        dry = queue_source_scanner_jobs(20, dry_run=True, source_id=source_id)
        assert dry["candidate_count"] == 2
        assert dry["queued_count"] == 0
        assert fetch_one("SELECT count(*) AS count FROM scanner_jobs WHERE result_json::text LIKE %s", (f"%{token}%",))["count"] == 0

        result = queue_source_scanner_jobs(20, dry_run=False, source_id=source_id)
        assert result["status"] == "queued"
        assert result["queued_count"] == 2
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
        assert f"owner-{token}@" not in str(result)
        assert fetch_one("SELECT count(*) AS count FROM scanner_jobs WHERE result_json::text LIKE %s", (f"%{token}%",))["count"] == 2

        second = queue_source_scanner_jobs(20, dry_run=False, source_id=source_id)
        assert second["status"] == "idle"
        assert second["queued_count"] == 0
        assert second["candidate_count"] == 0
        assert latest_source_scanner_queue_runs(5)["send_mail"] is False
    finally:
        _cleanup(token)


def test_source_scanner_queue_endpoints_and_agents_are_admin_gated_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        source_id = _seed_accepted_scout_leads(token, 1)
        assert client.get("/admin/scanner/source-backlog").status_code == 401
        assert client.post("/admin/scanner/queue-source-leads", json={"dry_run": True}).status_code == 401
        backlog = client.get(f"/admin/scanner/source-backlog?source_id={source_id}", headers=admin_headers())
        assert backlog.status_code == 200
        queue = client.post(
            "/admin/scanner/queue-source-leads",
            json={"limit": 20, "source_id": source_id, "dry_run": True},
            headers=admin_headers(),
        )
        assert queue.status_code == 200
        assert queue.json()["queue"]["send_mail"] is False
        history = client.get("/admin/scanner/source-queue-runs", headers=admin_headers())
        assert history.status_code == 200
        backlog_agent = run_agent("source_scanner_backlog_agent", {"limit": 20, "source_id": source_id})
        queue_agent = run_agent("source_scanner_queue_agent", {"limit": 20, "source_id": source_id, "dry_run": True})
        assert backlog_agent["status"] == "completed"
        assert queue_agent["status"] == "completed"
        assert backlog_agent["result_json"]["send_mail"] is False
        assert queue_agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
