from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
import app.source_campaign_operator as operator_module
from app.scouts import prepare_scout_source_from_adapter
from app.source_campaign_operator import advance_source_to_campaign, source_campaign_operator_snapshot


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(source_id: str | None = None, token: str = "") -> None:
    if source_id:
        execute("DELETE FROM scanner_jobs WHERE result_json::text LIKE %s", (f"%{source_id}%",))
        execute("DELETE FROM scout_leads WHERE scout_run_id IN (SELECT id FROM scout_runs WHERE source_id = %s)", (source_id,))
        execute("DELETE FROM scout_runs WHERE source_id = %s", (source_id,))
        execute("DELETE FROM scout_source_readiness_checks WHERE source_id = %s", (source_id,))
        execute("DELETE FROM scout_sources WHERE id = %s", (source_id,))
    if token:
        execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
        execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
        execute("DELETE FROM businesses WHERE domain LIKE %s", (f"%{token}%",))
        execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s", (f"%{token}%",))


def _source(token: str) -> str:
    result = prepare_scout_source_from_adapter(
        "directory",
        {
            "name": f"p60-source-{token}",
            "csv": f"name,website,email,city,source_url\nP60,https://p60-{token}.example.test,owner@p60-{token}.example.test,Tallinn,https://directory.example.test/p60-{token}\n",
            "country": "EE",
            "language": "en",
            "niche": "dentists",
        },
    )
    assert result["readiness"]["status"] == "PASS_SOURCE_READY"
    return result["source"]["id"]


def _allow_expansion(monkeypatch) -> None:
    gate = {
        "allowed": True,
        "blockers": [],
        "matrix_count": 1,
        "latest_coverage_score": 100,
        "latest_fail_count": 0,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
    monkeypatch.setattr(operator_module, "scout_campaign_expansion_gate", lambda: gate)


def test_source_campaign_operator_snapshot_is_no_send_and_redacted():
    token = uuid.uuid4().hex[:8]
    source_id = _source(token)
    try:
        snapshot = source_campaign_operator_snapshot(10, source_id)
        text = str(snapshot)
        assert snapshot["candidate_count"] >= 1
        assert snapshot["send_mail"] is False
        assert snapshot["live_outreach_allowed"] is False
        assert snapshot["raw_recipient_addresses_included"] is False
        assert f"owner@p60-{token}" not in text
    finally:
        _cleanup(source_id, token)


def test_source_campaign_operator_dry_run_requires_no_side_effects(monkeypatch):
    token = uuid.uuid4().hex[:8]
    source_id = _source(token)
    before_runs = fetch_one("SELECT count(*) AS count FROM scout_runs WHERE source_id = %s", (source_id,))["count"]
    try:
        _allow_expansion(monkeypatch)
        result = advance_source_to_campaign(source_id, 10, dry_run=True, process_scout=True)
        assert result["status"] == "preview_only"
        assert result["source_queue"]["queued_count"] == 0
        assert result["send_mail"] is False
        assert fetch_one("SELECT count(*) AS count FROM scout_runs WHERE source_id = %s", (source_id,))["count"] == before_runs
    finally:
        _cleanup(source_id, token)


def test_source_campaign_operator_can_advance_explicit_ready_source_without_sending(monkeypatch):
    token = uuid.uuid4().hex[:8]
    source_id = _source(token)
    try:
        _allow_expansion(monkeypatch)
        result = advance_source_to_campaign(source_id, 10, dry_run=False, process_scout=False, prepare_campaigns=False)
        assert result["status"] == "advanced"
        assert result["source_queue"]["queued_count"] == 1
        assert result["source_queue"]["created_scanner_jobs"] == 0
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert fetch_one("SELECT count(*) AS count FROM scout_runs WHERE source_id = %s", (source_id,))["count"] == 1
    finally:
        _cleanup(source_id, token)


def test_source_campaign_operator_auto_selects_ready_source_without_sending(monkeypatch):
    token = uuid.uuid4().hex[:8]
    source_id = _source(token)
    try:
        _allow_expansion(monkeypatch)
        result = advance_source_to_campaign(None, 10, dry_run=False, process_scout=False, prepare_campaigns=False)
        assert result["status"] == "advanced"
        assert result["auto_selected_source"] is True
        assert result["source_id"] == source_id
        assert result["source_queue"]["queued_count"] == 1
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
    finally:
        _cleanup(source_id, token)


def test_source_campaign_operator_admin_and_agents_are_no_send():
    assert client.get("/admin/source-campaign-operator").status_code == 401
    assert client.post("/admin/source-campaign-operator/advance", json={"dry_run": True}).status_code == 401
    response = client.get("/admin/source-campaign-operator", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["operator"]["send_mail"] is False
    agent = run_agent("source_campaign_operator_agent", {"limit": 5})
    advance = run_agent("source_campaign_operator_advance_agent", {"limit": 5, "dry_run": True})
    assert agent["status"] == "completed"
    assert advance["status"] == "completed"
    assert agent["result_json"]["send_mail"] is False
    assert advance["result_json"]["send_mail"] is False
