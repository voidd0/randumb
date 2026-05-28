from __future__ import annotations

import os
import types
import uuid
from io import BytesIO
from urllib.error import HTTPError

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

import app.contact_enrichment as enrichment_module
from app.autonomous_agents import run_agent
from app.contact_enrichment import contact_enrichment_candidates, run_hunter_contact_enrichment, run_public_contact_page_enrichment
from app.db import execute, fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM contact_enrichment_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM suppression_list WHERE email LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM lead_scores WHERE reasoning_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s", (f"%{token}%",))
    execute("DELETE FROM leads WHERE id IN (SELECT l.id FROM leads l JOIN businesses b ON b.id = l.business_id WHERE b.domain LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s", (f"%{token}%",))


def _seed_lead(token: str) -> dict[str, str]:
    domain = f"p95-{token}.clinic"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, status)
        VALUES (%s, 'UK', 'Cardiff', 'en', 'dentists', 'scout_agent', %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P95 Clinic {token}", f"https://{domain}", domain),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, source, status, score, language, country, city, niche)
        VALUES (%s, 'scout_agent', 'scouted', 76, 'en', 'UK', 'Cardiff', 'dentists')
        RETURNING id
        """,
        (business["id"],),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 64, 'Public contact path issue.', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"p95-{token}"),
    )
    execute(
        """
        INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
        VALUES (%s, 'contact_path', 'high', 'Contact path issue', 'Visible from public browser session.', 'Review public contact path.')
        """,
        (audit["id"],),
    )
    return {"domain": domain, "lead_id": str(lead["id"]), "business_id": str(business["id"])}


def test_contact_enrichment_candidates_are_redacted_and_no_send():
    token = uuid.uuid4().hex[:8]
    try:
        seeded = _seed_lead(token)
        result = contact_enrichment_candidates(25)
        match = next(item for item in result["candidates"] if item["lead_id"] == seeded["lead_id"])
        assert match["domain"] == seeded["domain"]
        assert match["domain_hash"]
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_hunter_enrichment_prefers_role_email_and_updates_lead(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        seeded = _seed_lead(token)
        monkeypatch.setattr(enrichment_module, "get_settings", lambda: types.SimpleNamespace(hunter_api_key="test-key"))
        monkeypatch.setattr(
            enrichment_module,
            "hunter_domain_search",
            lambda domain, api_key, limit=10: {
                "data": {
                    "emails": [
                        {"value": f"owner@{seeded['domain']}", "confidence": 99},
                        {"value": f"hello@{seeded['domain']}", "confidence": 80},
                    ]
                }
            },
        )
        result = run_hunter_contact_enrichment(10, dry_run=False)
        assert result["enriched_count"] >= 1
        assert result["send_mail"] is False
        assert f"hello@{seeded['domain']}" not in str(result)
        row = fetch_one("SELECT email FROM leads WHERE id = %s", (seeded["lead_id"],))
        assert row["email"] == f"hello@{seeded['domain']}"
    finally:
        _cleanup(token)


def test_contact_enrichment_agent_and_endpoints_are_admin_gated(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        _seed_lead(token)
        assert client.get("/admin/leads/contact-enrichment/candidates").status_code == 401
        response = client.get("/admin/leads/contact-enrichment/candidates", headers=admin_headers())
        assert response.status_code == 200
        monkeypatch.setattr(enrichment_module, "get_settings", lambda: types.SimpleNamespace(hunter_api_key=""))
        agent = run_agent("contact_enrichment_agent", {"limit": 5, "dry_run": True})
        assert agent["status"] == "completed"
        assert agent["result_json"]["status"] == "blocked_missing_hunter_api_key"
        assert agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_public_contact_page_enrichment_updates_lead_without_raw_email(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        seeded = _seed_lead(token)

        def _fetch(url: str):
            if url.endswith("/contact"):
                return 200, f"<html><a href='mailto:hello@{seeded['domain']}'>Email us</a></html>", url
            return 200, "<html><a href='/contact'>Contact</a></html>", url

        monkeypatch.setattr(enrichment_module, "fetch_public_contact_page", _fetch)
        result = run_public_contact_page_enrichment(10, dry_run=False, max_pages_per_domain=4)
        assert result["enriched_count"] >= 1
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert f"hello@{seeded['domain']}" not in str(result)
        row = fetch_one("SELECT email FROM leads WHERE id = %s", (seeded["lead_id"],))
        assert row["email"] == f"hello@{seeded['domain']}"
    finally:
        _cleanup(token)


def test_public_contact_page_enrichment_respects_suppression(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        seeded = _seed_lead(token)
        execute(
            "INSERT INTO suppression_list(email, domain, reason, source) VALUES (%s, %s, 'test', 'p95')",
            (f"hello@{seeded['domain']}", seeded["domain"]),
        )
        monkeypatch.setattr(
            enrichment_module,
            "fetch_public_contact_page",
            lambda url: (200, f"<html>hello@{seeded['domain']}</html>", url),
        )
        result = run_public_contact_page_enrichment(10, dry_run=False, max_pages_per_domain=4)
        assert result["enriched_count"] == 0
        row = fetch_one("SELECT email FROM leads WHERE id = %s", (seeded["lead_id"],))
        assert row["email"] is None
        assert result["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_public_contact_page_enrichment_stops_on_time_budget(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        _seed_lead(token)
        ticks = iter([0.0, 0.0, 10.0])
        monkeypatch.setattr(enrichment_module.time, "monotonic", lambda: next(ticks))
        result = run_public_contact_page_enrichment(10, dry_run=False, max_pages_per_domain=4, max_seconds=5)
        assert result["status"] == "partial_time_budget_exhausted"
        assert result["time_budget_exhausted"] is True
        assert result["scanned_count"] == 1
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_public_contact_page_agent_and_endpoint_are_admin_gated(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        seeded = _seed_lead(token)
        monkeypatch.setattr(
            enrichment_module,
            "fetch_public_contact_page",
            lambda url: (200, f"<html>contact@{seeded['domain']}</html>", url),
        )
        assert client.post("/admin/leads/contact-enrichment/public-contact-pages", json={"limit": 5}).status_code == 401
        response = client.post(
            "/admin/leads/contact-enrichment/public-contact-pages",
            headers=admin_headers(),
            json={"limit": 5, "dry_run": True},
        )
        assert response.status_code == 200
        assert response.json()["enrichment"]["dry_run"] is True
        agent = run_agent("contact_page_enrichment_agent", {"limit": 5, "dry_run": True})
        assert agent["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
    finally:
        _cleanup(token)


def test_public_contact_page_agent_enriches_by_default_with_time_budget(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        seeded = _seed_lead(token)
        monkeypatch.setattr(
            enrichment_module,
            "fetch_public_contact_page",
            lambda url: (200, f"<html><a href='mailto:office@{seeded['domain']}'>Office</a></html>", url),
        )
        agent = run_agent("contact_page_enrichment_agent", {"limit": 5, "max_seconds": 10})
        result = agent["result_json"]
        assert agent["status"] == "completed"
        assert result["dry_run"] is False
        assert result["enriched_count"] >= 1
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert f"office@{seeded['domain']}" not in str(result)
        row = fetch_one("SELECT email FROM leads WHERE id = %s", (seeded["lead_id"],))
        assert row["email"] == f"office@{seeded['domain']}"
    finally:
        _cleanup(token)


def test_hunter_enrichment_stops_on_rate_limit(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        _seed_lead(token)
        monkeypatch.setattr(enrichment_module, "get_settings", lambda: types.SimpleNamespace(hunter_api_key="test-key"))

        def _rate_limited(domain: str, api_key: str, limit: int = 10):
            raise HTTPError("https://api.hunter.io/v2/domain-search", 429, "Too Many Requests", {}, BytesIO(b"{}"))

        monkeypatch.setattr(enrichment_module, "hunter_domain_search", _rate_limited)
        result = run_hunter_contact_enrichment(10, dry_run=False)
        assert result["status"] == "provider_rate_limited"
        assert result["scanned_count"] == 1
        assert result["enriched_count"] == 0
        assert result["results"][0]["http_status"] == 429
        assert result["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
