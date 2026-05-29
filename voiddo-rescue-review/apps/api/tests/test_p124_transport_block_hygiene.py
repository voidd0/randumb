from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db import execute, fetch_one
from app.main import app
from app.outreach_transport_block_hygiene import outreach_transport_block_hygiene
from app.p0 import execute_owner_command, parse_owner_command


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _insert_blocked_message(email_domain: str | None = None) -> tuple[str, str, str]:
    token = uuid.uuid4().hex
    domain = email_domain or f"hygiene-{token}.com"
    lead_id = execute(
        """
        INSERT INTO leads(email, status, score, source)
        VALUES (%s, 'qualified', 90, 'transport_block_hygiene_test')
        RETURNING id
        """,
        (f"lead-{token}@{domain}",),
    )["id"]
    message_id = execute(
        """
        INSERT INTO outreach_messages(lead_id, mailbox, subject, body, html_body, status)
        VALUES (%s, 'audit@voiddorescue.com', 'Diagnostic', 'Unsubscribe: https://go.rescue.voiddo.com/u/test', '<p>ok</p>', 'transport_blocked')
        RETURNING id
        """,
        (lead_id,),
    )["id"]
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('outreach.transport_blocked', 'warning', 'live_outreach_not_approved', %s)
        """,
        (
            Jsonb(
                {
                    "message_id": str(message_id),
                    "checks": {
                        "runtime_outreach_paused": True,
                        "outreach_paused": False,
                        "outreach_dry_run": False,
                        "first_live_send_flag": True,
                    },
                }
            ),
        ),
    )
    return str(lead_id), str(message_id), domain


def _cleanup(message_id: str, lead_id: str):
    execute("DELETE FROM system_events WHERE payload_json->>'message_id' = %s", (message_id,))
    execute("DELETE FROM outreach_messages WHERE id = %s", (message_id,))
    execute("DELETE FROM leads WHERE id = %s", (lead_id,))
    execute("DELETE FROM suppression_list WHERE source = 'transport_block_hygiene_test'")


def test_transport_block_hygiene_requeues_pause_gate_without_sending():
    lead_id, message_id, _domain = _insert_blocked_message()
    try:
        result = outreach_transport_block_hygiene(500, apply=True)
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert result["requeued_count"] >= 1
        row = fetch_one("SELECT status FROM outreach_messages WHERE id = %s", (message_id,))
        assert row["status"] == "queued"
        assert "@" not in str(result)
    finally:
        _cleanup(message_id, lead_id)


def test_transport_block_hygiene_keeps_suppressed_recipient_blocked():
    lead_id, message_id, domain = _insert_blocked_message()
    try:
        execute(
            """
            INSERT INTO suppression_list(domain, reason, source)
            VALUES (%s, 'test', 'transport_block_hygiene_test')
            """,
            (domain,),
        )
        result = outreach_transport_block_hygiene(500, apply=True)
        sample = [row for row in result["sample"] if row["outreach_message_id"] == message_id][0]
        assert sample["decision"] == "keep_blocked_recipient_suppressed"
        row = fetch_one("SELECT status FROM outreach_messages WHERE id = %s", (message_id,))
        assert row["status"] == "transport_blocked"
    finally:
        _cleanup(message_id, lead_id)


def test_transport_block_hygiene_endpoint_requires_admin():
    assert client.post("/admin/outreach/live-queue/transport-block-hygiene", json={"apply": False}).status_code == 401
    response = client.post(
        "/admin/outreach/live-queue/transport-block-hygiene",
        headers=admin_headers(),
        json={"apply": False, "limit": 1},
    )
    assert response.status_code == 200
    assert response.json()["hygiene"]["send_mail"] is False


def test_owner_command_show_transport_block_hygiene_is_safe_auto(monkeypatch):
    import app.outreach_transport_block_hygiene as hygiene_module

    monkeypatch.setattr(
        hygiene_module,
        "outreach_transport_block_hygiene",
        lambda limit=100, apply=False: {
            "send_mail": False,
            "live_outreach_allowed": False,
            "requeue_candidate_count": 0,
        },
    )
    parsed = parse_owner_command(os.environ.get("OWNER_COMMAND_EMAIL", "owner@example.test"), "SHOW TRANSPORT BLOCK HYGIENE", "")
    assert parsed["risk_level"] == "SAFE_AUTO"
    result = execute_owner_command(parsed)
    assert result["ok"] is True
    assert result["action"] == "transport_block_hygiene_status"
    assert result["hygiene"]["send_mail"] is False
