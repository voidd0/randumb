from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.scanner_completion_watch import latest_scanner_completion_watches, scanner_completion_watch


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute(
        """
        DELETE FROM scanner_completion_watches
        WHERE result_json::text LIKE %s
           OR priority_run_id IN (
             SELECT id FROM scanner_priority_runs WHERE result_json::text LIKE %s
           )
        """,
        (f"%{token}%", f"%{token}%"),
    )
    execute("DELETE FROM scanner_priority_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM post_scan_campaign_cycles WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_action_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_readiness_snapshots WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaign_leads WHERE preview_json::text LIKE %s OR campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaigns WHERE name LIKE %s OR country = %s", (f"%{token}%", f"P76{token[:3].upper()}"))
    execute("DELETE FROM audit_strength_scores WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s OR business_name LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_leads WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM scout_runs WHERE source_id IN (SELECT id FROM scout_sources WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM scout_sources WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent = 'scanner_completion_watch_agent' AND result_json::text LIKE %s", (f"%{token}%",))


def _seed_priority_completion_candidate(token: str) -> tuple[str, str]:
    country = f"P76{token[:3].upper()}"
    domain = f"p76-{token}.clinic"
    source = execute(
        """
        INSERT INTO scout_sources(name, source_type, country, language, niche, status, config_json)
        VALUES (%s, 'manual_csv_scout', %s, 'en', 'dentists', 'active', '{}'::jsonb)
        RETURNING id
        """,
        (f"p76-source-{token}", country),
    )
    run = execute(
        """
        INSERT INTO scout_runs(source_id, status, country, niche, language, found_count, accepted_count, completed_at)
        VALUES (%s, 'completed', %s, 'dentists', 'en', 1, 1, now())
        RETURNING id
        """,
        (source["id"], country),
    )
    scout_lead = execute(
        """
        INSERT INTO scout_leads(scout_run_id, business_name, domain, website_url, email, country, city, language, niche, source_url, confidence, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'Watcher City', 'en', 'dentists', %s, 90, 'accepted')
        RETURNING id
        """,
        (run["id"], f"P76 Clinic {token}", domain, f"https://{domain}", f"owner-{token}@{domain}", country, f"https://source.test/{token}"),
    )
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, %s, 'Watcher City', 'en', 'dentists', 'p76_suite', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P76 Clinic {token}", country, f"https://{domain}", domain, f"owner-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p76_suite', 'scouted', 0, 'en', %s, 'Watcher City', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}", country),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 58, %s, %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"Public enquiry path issue {token}", f"p76-{token}"),
    )
    for issue_type in ["contact_path", "mobile_cta", "metadata"]:
        execute(
            """
            INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
            VALUES (%s, %s, 'high', 'Public enquiry path may be weak', 'Visible from a public browser session.', 'Review the public enquiry path.')
            """,
            (audit["id"], issue_type),
        )
    completed_job = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, audit_id, priority, result_json, completed_at)
        VALUES (%s, %s, false, 'completed', %s, 175, %s, now())
        RETURNING id
        """,
        (
            f"https://{domain}",
            f"P76 Clinic {token}",
            audit["id"],
            Jsonb({"lead_id": str(lead["id"]), "scout_lead_id": str(scout_lead["id"]), "token": token}),
        ),
    )
    queued_job = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, priority, result_json)
        VALUES (%s, %s, false, 'queued', 175, %s)
        RETURNING id
        """,
        (
            f"https://queued-{domain}",
            f"P76 Clinic queued {token}",
            Jsonb({"scout_lead_id": str(scout_lead["id"]), "token": token}),
        ),
    )
    priority_run = execute(
        """
        INSERT INTO scanner_priority_runs(
          status, dry_run, candidate_count, prioritized_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES ('prioritized', false, 2, 2, %s, false, false, false, false, false)
        RETURNING id
        """,
        (
            Jsonb(
                {
                    "status": "prioritized",
                    "token": token,
                    "prioritized": [
                        {"job_id": str(completed_job["id"]), "source_id": str(source["id"])},
                        {"job_id": str(queued_job["id"]), "source_id": str(source["id"])},
                    ],
                    "send_mail": False,
                    "live_outreach_allowed": False,
                }
            ),
        ),
    )
    return str(priority_run["id"]), str(queued_job["id"])


def test_scanner_completion_watch_triggers_post_scan_refresh_only_on_new_completed_jobs():
    token = uuid.uuid4().hex[:8]
    try:
        priority_run_id, queued_job_id = _seed_priority_completion_candidate(token)
        dry = scanner_completion_watch(100, 1, dry_run=True)
        assert dry["status"] == "dry_run_ready"
        assert dry["priority_run_id"] == priority_run_id
        assert dry["completed_count"] == 1
        assert dry["send_mail"] is False
        assert f"owner-{token}@" not in str(dry)

        execute("UPDATE scanner_jobs SET status = 'completed', completed_at = now(), updated_at = now() WHERE id = %s", (queued_job_id,))
        result = scanner_completion_watch(100, 1, dry_run=False)
        assert result["status"] == "refreshed_no_send"
        assert result["new_completed_count"] == 1
        assert result["cycle"]["status"] == "completed_no_send"
        assert result["cycle"]["steps"]["backfill"]["scored_count"] >= 1
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False

        again = scanner_completion_watch(100, 1, dry_run=False)
        assert again["status"] == "idle_no_new_completions"
        assert again["trigger_ready"] is False
        assert latest_scanner_completion_watches(5)["send_mail"] is False
    finally:
        _cleanup(token)


def test_scanner_completion_watch_endpoint_and_agent_are_admin_gated_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _seed_priority_completion_candidate(token)
        assert client.get("/admin/scanner/completion-watches").status_code == 401
        assert client.post("/admin/scanner/completion-watch", json={"dry_run": True}).status_code == 401
        response = client.post(
            "/admin/scanner/completion-watch",
            json={"limit": 100, "min_new_completed": 1, "dry_run": True},
            headers=admin_headers(),
        )
        assert response.status_code == 200
        assert response.json()["watch"]["send_mail"] is False
        history = client.get("/admin/scanner/completion-watches", headers=admin_headers())
        assert history.status_code == 200
        assert history.json()["watches"]["count"] >= 1
        agent = run_agent("scanner_completion_watch_agent", {"limit": 100, "min_new_completed": 1, "dry_run": True})
        assert agent["status"] == "completed"
        assert agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
