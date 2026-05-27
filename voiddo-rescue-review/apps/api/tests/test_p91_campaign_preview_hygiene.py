from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.campaign_preview_hygiene import archive_campaign_preview_artifacts, campaign_preview_hygiene_snapshot
from app.db import execute, fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM campaign_leads WHERE preview_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s", (f"%{token}%",))


def _preview(token: str, domain: str, country: str = "US", source: str = "scout_agent"):
    business = execute(
        """
        INSERT INTO businesses(name, domain, email, source, niche, country, status)
        VALUES (%s, %s, %s, %s, 'dentists', %s, 'scouted')
        RETURNING id
        """,
        (f"Hygiene {token}", domain, f"owner-{token}@{domain}", source, country),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, niche, country, language)
        VALUES (%s, %s, %s, 'scouted', 90, 'dentists', %s, 'en')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}", source, country),
    )
    campaign = execute(
        """
        INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
        VALUES (%s, 'preview_ready', %s, 'en', 'dentists', 'contact_form_repair', true)
        RETURNING id
        """,
        (f"hygiene-{token}", country),
    )
    row = execute(
        """
        INSERT INTO campaign_leads(campaign_id, lead_id, status, score, preview_json)
        VALUES (%s, %s, 'preview', 90, %s)
        RETURNING id
        """,
        (campaign["id"], lead["id"], Jsonb({"token": token, "dry_run": True})),
    )
    return row


def test_campaign_preview_hygiene_archives_test_artifacts_only():
    token = uuid.uuid4().hex[:8]
    try:
        test_row = _preview(token, f"hygiene-{token}.example.test", "P9", "p9_test")
        real_row = _preview(f"{token}real", f"hygiene-{token}.com", "US", "scout_agent")
        snapshot = campaign_preview_hygiene_snapshot(50)
        assert snapshot["artifact_count"] >= 1
        result = archive_campaign_preview_artifacts(50, apply=True)
        assert result["archived_count"] >= 1
        assert result["send_mail"] is False
        archived = fetch_one("SELECT status, preview_json FROM campaign_leads WHERE id = %s", (test_row["id"],))
        real = fetch_one("SELECT status FROM campaign_leads WHERE id = %s", (real_row["id"],))
        assert archived["status"] == "archived_test_artifact"
        assert archived["preview_json"]["campaign_preview_hygiene"]["live_outreach_allowed"] is False
        assert real["status"] == "preview"
    finally:
        _cleanup(token)
        _cleanup(f"{token}real")


def test_campaign_preview_hygiene_endpoints_and_agent_are_admin_gated_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        _preview(token, f"hygiene-{token}.example.test", "P91", "p91_test")
        assert client.get("/admin/campaign-preview/hygiene").status_code == 401
        ok = client.get("/admin/campaign-preview/hygiene", headers=admin_headers())
        assert ok.status_code == 200
        assert ok.json()["hygiene"]["send_mail"] is False
        run = client.post("/admin/campaign-preview/archive-artifacts", json={"limit": 50, "apply": False}, headers=admin_headers())
        assert run.status_code == 200
        assert run.json()["hygiene"]["live_outreach_allowed"] is False
        agent = run_agent("campaign_preview_hygiene_snapshot_agent", {"limit": 50})
        assert agent["status"] == "completed"
        assert agent["result_json"]["raw_recipient_addresses_included"] is False
    finally:
        _cleanup(token)
