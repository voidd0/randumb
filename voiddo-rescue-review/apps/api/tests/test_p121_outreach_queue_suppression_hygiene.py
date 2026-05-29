from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.outreach_queue_suppression_hygiene import outreach_queue_suppression_hygiene


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM agent_runs WHERE agent = 'outreach_queue_suppression_hygiene_agent' AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM email_events WHERE payload_json::text LIKE %s OR outreach_message_id IN (SELECT id FROM outreach_messages WHERE subject LIKE %s)", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM outreach_messages WHERE subject LIKE %s", (f"%{token}%",))
    execute("DELETE FROM suppression_list WHERE email LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))


def _queued_message(token: str) -> str:
    domain = f"p121-{token}.invalid"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, 'QA', 'Queue', 'en', 'dentists', 'p121', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"P121 {token}", f"https://{domain}", domain, f"owner@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'p121', 'qualified', 91, 'en', 'QA', 'Queue', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner@{domain}"),
    )
    message = execute(
        """
        INSERT INTO outreach_messages(lead_id, mailbox, subject, body, status)
        VALUES (%s, 'audit@voiddorescue.com', %s, 'Public non-invasive check.', 'queued')
        RETURNING id
        """,
        (lead["id"], f"p121 queue {token}"),
    )
    execute(
        "INSERT INTO suppression_list(domain, reason, source) VALUES (%s, 'bounce_domain_not_found', 'inbox_bounce_domain')",
        (domain,),
    )
    return str(message["id"])


def test_outreach_queue_suppression_hygiene_blocks_queued_suppressed_domain():
    token = uuid.uuid4().hex[:8]
    try:
        message_id = _queued_message(token)
        dry = outreach_queue_suppression_hygiene(100, apply=False)
        assert dry["matched_count"] >= 1
        assert dry["blocked_count"] == 0
        assert f"owner@p121-{token}.invalid" not in str(dry)
        result = outreach_queue_suppression_hygiene(100, apply=True)
        assert result["blocked_count"] >= 1
        row = fetch_one("SELECT status FROM outreach_messages WHERE id = %s", (message_id,))
        assert row["status"] == "transport_blocked"
        event = fetch_one("SELECT payload_json FROM email_events WHERE outreach_message_id = %s AND event_type = 'outreach_queue_suppression_block'", (message_id,))
        assert event["payload_json"]["recipient_domain_hash"]
        assert "@" not in str(result)
    finally:
        _cleanup(token)


def test_outreach_queue_suppression_hygiene_endpoint_requires_admin():
    assert client.post("/admin/outreach/live-queue/suppression-hygiene", json={"apply": False}).status_code == 401
    response = client.post("/admin/outreach/live-queue/suppression-hygiene", json={"apply": False}, headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["hygiene"]["send_mail"] is False


def test_outreach_queue_suppression_hygiene_agent_is_no_send(monkeypatch):
    import app.autonomous_agents as agents_module

    monkeypatch.setattr(
        agents_module,
        "outreach_queue_suppression_hygiene",
        lambda limit=100, apply=True: {"status": "clean", "send_mail": False, "live_outreach_allowed": False},
    )
    result = run_agent("outreach_queue_suppression_hygiene_agent", {"limit": 10, "apply": True})
    assert result["status"] == "completed"
    assert result["result_json"]["send_mail"] is False
    assert result["result_json"]["live_outreach_allowed"] is False
