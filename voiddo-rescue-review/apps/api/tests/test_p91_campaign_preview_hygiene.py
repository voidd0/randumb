from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.campaign_preview_hygiene import archive_campaign_preview_artifacts, archive_campaign_shell_artifacts, campaign_geo_hygiene_snapshot, campaign_preview_hygiene_snapshot, campaign_shell_hygiene_snapshot, repair_campaign_geo_mismatches
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


def test_campaign_shell_hygiene_archives_synthetic_campaigns_without_touching_real_campaigns():
    token = uuid.uuid4().hex[:8]
    try:
        synthetic = execute(
            """
            INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
            VALUES (%s, 'preview_ready', 'P91', 'en', 'dentists', 'contact_form_repair', true)
            RETURNING id
            """,
            (f"P91 synthetic {token}",),
        )
        real = execute(
            """
            INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
            VALUES (%s, 'preview_ready', 'US', 'en', 'dentists', 'contact_form_repair', true)
            RETURNING id
            """,
            (f"Real shell {token}",),
        )
        snapshot = campaign_shell_hygiene_snapshot(50)
        assert snapshot["artifact_count"] >= 1
        result = archive_campaign_shell_artifacts(50, apply=True)
        assert result["archived_count"] >= 1
        assert result["send_mail"] is False
        archived = fetch_one("SELECT status FROM campaigns WHERE id = %s", (synthetic["id"],))
        untouched = fetch_one("SELECT status FROM campaigns WHERE id = %s", (real["id"],))
        assert archived["status"] == "archived_test_artifact"
        assert untouched["status"] == "preview_ready"
    finally:
        _cleanup(token)


def test_campaign_hygiene_archives_generic_test_campaign_missing_geo():
    token = uuid.uuid4().hex[:8]
    try:
        business = execute(
            """
            INSERT INTO businesses(name, domain, email, source, niche, country, status)
            VALUES (%s, %s, %s, 'scout_agent', 'dentists', 'US', 'scouted')
            RETURNING id
            """,
            (f"Generic test campaign {token}", f"generic-{token}.clinic", f"owner-{token}@generic-{token}.clinic"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, niche, country, language)
            VALUES (%s, %s, 'scout_agent', 'scouted', 90, 'dentists', 'US', 'en')
            RETURNING id
            """,
            (business["id"], f"owner-{token}@generic-{token}.clinic"),
        )
        campaign = execute(
            """
            INSERT INTO campaigns(name, status, offer_key, dry_run)
            VALUES ('x', 'preview_ready', 'contact_form_repair', true)
            RETURNING id
            """
        )
        preview = execute(
            """
            INSERT INTO campaign_leads(campaign_id, lead_id, status, score, preview_json)
            VALUES (%s, %s, 'preview', 90, %s)
            RETURNING id
            """,
            (campaign["id"], lead["id"], Jsonb({"token": token})),
        )

        preview_result = archive_campaign_preview_artifacts(50, apply=True)
        shell_result = archive_campaign_shell_artifacts(50, apply=True)
        assert preview_result["archived_count"] >= 1
        assert shell_result["archived_count"] >= 1
        assert fetch_one("SELECT status FROM campaign_leads WHERE id = %s", (preview["id"],))["status"] == "archived_test_artifact"
        assert fetch_one("SELECT status FROM campaigns WHERE id = %s", (campaign["id"],))["status"] == "archived_test_artifact"
    finally:
        _cleanup(token)


def test_campaign_shell_hygiene_endpoint_and_agent_are_admin_gated_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        execute(
            """
            INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
            VALUES (%s, 'preview_ready', 'P91', 'en', 'dentists', 'contact_form_repair', true)
            RETURNING id
            """,
            (f"P91 endpoint {token}",),
        )
        assert client.get("/admin/campaign-shell-hygiene").status_code == 401
        ok = client.get("/admin/campaign-shell-hygiene", headers=admin_headers())
        assert ok.status_code == 200
        assert ok.json()["hygiene"]["raw_recipient_addresses_included"] is False
        run = client.post("/admin/campaign-shell-hygiene/archive-artifacts", json={"limit": 50, "apply": False}, headers=admin_headers())
        assert run.status_code == 200
        assert run.json()["hygiene"]["live_outreach_allowed"] is False
        agent = run_agent("campaign_shell_hygiene_snapshot_agent", {"limit": 50})
        assert agent["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_geo_hygiene_moves_preview_to_inferred_country_campaign():
    token = uuid.uuid4().hex[:8]
    try:
        row = _preview(token, f"geo-{token}.ca", "UK", "scout_agent")
        snapshot = campaign_geo_hygiene_snapshot(50)
        assert snapshot["mismatch_count"] >= 1
        assert any(item["campaign_lead_id"] == str(row["id"]) and item["inferred_country"] == "CA" for item in snapshot["sample"])
        result = repair_campaign_geo_mismatches(50, apply=True)
        assert result["repaired_count"] >= 1
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        moved = fetch_one(
            """
            SELECT c.country AS campaign_country, l.country AS lead_country, b.country AS business_country, cl.preview_json
            FROM campaign_leads cl
            JOIN campaigns c ON c.id = cl.campaign_id
            JOIN leads l ON l.id = cl.lead_id
            JOIN businesses b ON b.id = l.business_id
            WHERE cl.id = %s
            """,
            (row["id"],),
        )
        assert moved["campaign_country"] == "CA"
        assert moved["lead_country"] == "CA"
        assert moved["business_country"] == "CA"
        assert moved["preview_json"]["campaign_geo_hygiene"]["live_outreach_allowed"] is False
        agent = run_agent("campaign_geo_hygiene_snapshot_agent", {"limit": 50})
        assert agent["status"] == "completed"
        assert agent["result_json"]["raw_recipient_addresses_included"] is False
    finally:
        _cleanup(token)
