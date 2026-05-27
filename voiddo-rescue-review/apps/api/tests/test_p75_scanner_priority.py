from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.scanner_priority import latest_scanner_priority_runs, prioritize_guided_scanner_jobs, scanner_guided_backlog


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM scanner_priority_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR business_name LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_source_performance_scores WHERE reasoning_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM scout_leads WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_runs WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM scout_sources WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent IN ('scanner_guided_backlog_agent', 'scanner_guided_priority_agent') AND result_json::text LIKE %s", (f"%{token}%",))


def _seed_queued_scanner_source(token: str, count: int = 2) -> str:
    source = execute(
        """
        INSERT INTO scout_sources(name, source_type, country, language, niche, status, config_json)
        VALUES (%s, 'manual_csv_scout', 'CA', 'en', 'dentists', 'active', '{}'::jsonb)
        RETURNING id
        """,
        (f"p75-source-{token}",),
    )
    run = execute(
        """
        INSERT INTO scout_runs(source_id, status, country, niche, language, found_count, accepted_count, completed_at)
        VALUES (%s, 'completed', 'CA', 'dentists', 'en', %s, %s, now())
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
        VALUES (%s, 'PASS_SOURCE_PERFORMANCE_NO_SEND', 5, 5, 2, 0.4, 77, 0.8, 0.5,
                'PROMOTE_SOURCE_FOR_MORE_SCOUTING', %s)
        """,
        (source["id"], Jsonb({"token": token})),
    )
    for index in range(count):
        domain = f"p75-{token}-{index}.clinic"
        scout_lead = execute(
            """
            INSERT INTO scout_leads(scout_run_id, business_name, domain, website_url, email, country, city, language, niche, source_url, confidence, status)
            VALUES (%s, %s, %s, %s, %s, 'CA', 'Priority City', 'en', 'dentists', %s, 90, 'accepted')
            RETURNING id
            """,
            (run["id"], f"P75 Clinic {token} {index}", domain, f"https://{domain}", f"owner-{token}-{index}@{domain}", f"https://source.test/{token}/{index}"),
        )
        execute(
            """
            INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, result_json)
            VALUES (%s, %s, false, 'queued', 100, %s)
            """,
            (
                f"https://{domain}",
                f"P75 Clinic {token} {index}",
                Jsonb({"scout_lead_id": str(scout_lead["id"]), "token": token}),
            ),
        )
    return str(source["id"])


def test_scanner_guided_backlog_and_priority_are_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        source_id = _seed_queued_scanner_source(token, 2)
        backlog = scanner_guided_backlog(20)
        source = next(item for item in backlog["sources"] if item["source_id"] == source_id)
        assert source["queued_count"] == 2
        assert source["latest_recommendation"] == "PROMOTE_SOURCE_FOR_MORE_SCOUTING"
        assert backlog["send_mail"] is False

        dry = prioritize_guided_scanner_jobs(5, dry_run=True)
        assert dry["candidate_count"] >= 2
        assert dry["prioritized_count"] == 0
        assert dry["send_mail"] is False
        assert f"owner-{token}" not in str(dry)

        result = prioritize_guided_scanner_jobs(5, dry_run=False)
        assert result["status"] == "prioritized"
        assert result["prioritized_count"] >= 2
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
        row = fetch_one(
            """
            SELECT min(priority) AS min_priority
            FROM scanner_jobs
            WHERE result_json->>'token' = %s
            """,
            (token,),
        )
        assert int(row["min_priority"]) >= 175
        history = latest_scanner_priority_runs(5)
        assert history["count"] >= 1
        assert history["send_mail"] is False
    finally:
        _cleanup(token)


def test_scanner_priority_endpoints_and_agents_are_admin_gated_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _seed_queued_scanner_source(token, 1)
        assert client.get("/admin/scanner/guided-backlog").status_code == 401
        assert client.post("/admin/scanner/prioritize-guided", json={"dry_run": True}).status_code == 401
        backlog = client.get("/admin/scanner/guided-backlog", headers=admin_headers())
        assert backlog.status_code == 200
        priority = client.post("/admin/scanner/prioritize-guided", json={"limit": 5, "dry_run": True}, headers=admin_headers())
        assert priority.status_code == 200
        assert priority.json()["priority"]["send_mail"] is False
        runs = client.get("/admin/scanner/priority-runs", headers=admin_headers())
        assert runs.status_code == 200
        backlog_agent = run_agent("scanner_guided_backlog_agent", {"limit": 20})
        priority_agent = run_agent("scanner_guided_priority_agent", {"limit": 5, "dry_run": True})
        assert backlog_agent["status"] == "completed"
        assert priority_agent["status"] == "completed"
        assert backlog_agent["result_json"]["send_mail"] is False
        assert priority_agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
