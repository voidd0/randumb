from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.scout_run_recovery import recover_stale_scout_runs, stale_scout_run_recovery_snapshot
from app.scouts import create_scout_run, create_scout_source, process_scout_run


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM scout_leads WHERE scout_run_id IN (SELECT id FROM scout_runs WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s))", (f"%{token}%",))
    execute("DELETE FROM scout_runs WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM scout_sources WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s", (f"%{token}%",))


def _stale_run(token: str, retries: int = 0):
    source = execute(
        """
        INSERT INTO scout_sources(name, source_type, country, language, niche, status, config_json)
        VALUES (%s, 'manual_csv_scout', 'US', 'en', 'dentists', 'active', '{}'::jsonb)
        RETURNING id
        """,
        (f"stale-source-{token}",),
    )
    return execute(
        """
        INSERT INTO scout_runs(source_id, status, country, niche, language, started_at, result_json)
        VALUES (%s, 'running', 'US', 'dentists', 'en', now() - interval '4 hours', %s)
        RETURNING id
        """,
        (source["id"], Jsonb({"token": token, "stale_recovery_count": retries})),
    )


def test_stale_scout_run_recovery_requeues_first_stale_run():
    token = uuid.uuid4().hex[:8]
    try:
        run = _stale_run(token)
        snapshot = stale_scout_run_recovery_snapshot(10, 120)
        assert snapshot["stale_count"] >= 1
        result = recover_stale_scout_runs(10, 120, apply=True)
        assert result["recovered_count"] >= 1
        assert result["send_mail"] is False
        row = fetch_one("SELECT status, started_at, result_json FROM scout_runs WHERE id = %s", (run["id"],))
        assert row["status"] == "queued"
        assert row["started_at"] is None
        assert row["result_json"]["stale_recovery"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_stale_scout_run_recovery_sends_repeated_stale_runs_to_review():
    token = uuid.uuid4().hex[:8]
    try:
        run = _stale_run(token, retries=2)
        result = recover_stale_scout_runs(10, 120, apply=True)
        assert result["review_required_count"] >= 1
        row = fetch_one("SELECT status, error FROM scout_runs WHERE id = %s", (run["id"],))
        assert row["status"] == "review_required"
        assert row["error"] == "stale_running_recovery_limit"
    finally:
        _cleanup(token)


def test_stale_scout_run_recovery_endpoints_and_agent_are_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _stale_run(token)
        assert client.get("/admin/scouts/stale-runs").status_code == 401
        ok = client.get("/admin/scouts/stale-runs", headers=admin_headers())
        assert ok.status_code == 200
        assert ok.json()["recovery"]["send_mail"] is False
        run = client.post("/admin/scouts/recover-stale-runs", json={"apply": False}, headers=admin_headers())
        assert run.status_code == 200
        assert run.json()["recovery"]["live_outreach_allowed"] is False
        agent = run_agent("scout_run_recovery_snapshot_agent", {"limit": 10})
        assert agent["status"] == "completed"
        assert agent["result_json"]["raw_recipient_addresses_included"] is False
    finally:
        _cleanup(token)


def test_scout_run_duplicate_empty_email_does_not_crash_reprocessed_source():
    token = uuid.uuid4().hex[:8]
    csv_text = (
        "business_name,website_url,email,country,niche,source_url,confidence\n"
        f"Dup One,https://dup-{token}.com,,US,dentists,https://source.example/{token}/1,90\n"
        f"Dup Two,https://dup-{token}.com,,US,dentists,https://source.example/{token}/2,90\n"
    )
    try:
        source = create_scout_source(
            {
                "name": f"dup-empty-email-{token}",
                "source_type": "manual_csv_scout",
                "country": "US",
                "language": "en",
                "niche": "dentists",
                "config_json": {"csv": csv_text},
            }
        )
        run = create_scout_run(str(source["id"]))
        result = process_scout_run(str(run["id"]))
        assert result["found"] == 2
        assert result["accepted"] == 1
        assert result["rejected"] == 1
        stored = fetch_one("SELECT count(*) AS count FROM scout_leads WHERE domain = %s", (f"dup-{token}.com",))
        assert int(stored["count"]) == 1
    finally:
        _cleanup(token)
        execute("DELETE FROM scanner_jobs WHERE url LIKE %s", (f"%dup-{token}.com%",))
        execute("DELETE FROM leads WHERE business_id IN (SELECT id FROM businesses WHERE domain LIKE %s)", (f"%dup-{token}.com%",))
        execute("DELETE FROM businesses WHERE domain LIKE %s", (f"%dup-{token}.com%",))
        execute("DELETE FROM scout_leads WHERE domain LIKE %s", (f"%dup-{token}.com%",))
