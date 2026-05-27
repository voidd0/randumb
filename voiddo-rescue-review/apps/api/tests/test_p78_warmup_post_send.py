from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.p0 import recipient_hash
from app.warmup_post_send import latest_warmup_post_send_checks, observe_warmup_post_send


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM warmup_post_send_checks WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM mail_signals WHERE source = %s", (f"p78-{token}",))
    execute("DELETE FROM email_events WHERE payload_json::text LIKE %s OR message_id LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM warmup_schedule WHERE result_json::text LIKE %s OR recipient_email LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM runtime_controls WHERE key = 'pause_warmup' AND source = 'warmup_post_send_observer'")
    execute("DELETE FROM agent_runs WHERE agent = 'warmup_post_send_observer_agent' AND result_json::text LIKE %s", (f"%{token}%",))


def _seed_sent_warmup(token: str, recipient: str | None = None) -> tuple[str, str, str]:
    email = recipient or f"warmup-{token}@example.test"
    message_id = f"<p78-{token}@voiddorescue.com>"
    schedule = execute(
        """
        INSERT INTO warmup_schedule(recipient_email, sender_mailbox, day_number, scheduled_for, status, sent_at, result_json)
        VALUES (%s, 'support@voiddorescue.com', 1, now() - interval '10 minutes', 'sent', now() - interval '9 minutes', %s)
        RETURNING id
        """,
        (email, Jsonb({"message_id": message_id, "token": token})),
    )
    execute(
        """
        INSERT INTO email_events(event_type, payload_json, mailbox, message_id)
        VALUES ('warmup_sent', %s, 'support@voiddorescue.com', %s)
        """,
        (Jsonb({"schedule_id": str(schedule["id"]), "recipient_hash": recipient_hash(email), "token": token}), message_id),
    )
    return str(schedule["id"]), message_id, email


def test_warmup_post_send_observer_marks_clean_sent_warmup_without_sending():
    token = uuid.uuid4().hex[:8]
    try:
        schedule_id, _message_id, _email = _seed_sent_warmup(token)
        result = observe_warmup_post_send(10, pause_on_blocker=True)
        assert result["status"] == "observed_clean"
        assert result["checked_count"] >= 1
        assert result["blocked_count"] == 0
        assert result["paused_warmup"] is False
        assert result["checked_schedule_ids"][schedule_id] is True
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
        assert f"warmup-{token}@" not in str(result)
    finally:
        _cleanup(token)


def test_warmup_post_send_observer_pauses_warmup_on_blocking_signal():
    token = uuid.uuid4().hex[:8]
    try:
        _schedule_id, message_id, email = _seed_sent_warmup(token)
        execute(
            """
            INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, message_id, raw_summary)
            VALUES ('bounce', 'warning', %s, 'support@voiddorescue.com', %s, 'example.test', %s, 'test bounce signal')
            """,
            (f"p78-{token}", recipient_hash(email), message_id),
        )
        result = observe_warmup_post_send(10, pause_on_blocker=True)
        assert result["status"] == "paused_warmup_on_signal"
        assert result["blocked_count"] >= 1
        assert result["paused_warmup"] is True
        control = fetch_one("SELECT value, source FROM runtime_controls WHERE key = 'pause_warmup'")
        assert control["value"] is True
        assert control["source"] == "warmup_post_send_observer"
        assert result["raw_recipient_addresses_included"] is False
    finally:
        _cleanup(token)


def test_warmup_post_send_observer_endpoint_and_agent_are_admin_gated():
    token = uuid.uuid4().hex[:8]
    try:
        _seed_sent_warmup(token)
        assert client.get("/admin/warmup/post-send-checks").status_code == 401
        assert client.post("/admin/warmup/post-send-observe", json={"limit": 10}).status_code == 401
        response = client.post("/admin/warmup/post-send-observe", json={"limit": 10}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["observation"]["send_mail"] is False
        history = client.get("/admin/warmup/post-send-checks", headers=admin_headers())
        assert history.status_code == 200
        assert history.json()["checks"]["count"] >= 1
        agent = run_agent("warmup_post_send_observer_agent", {"limit": 10})
        assert agent["status"] == "completed"
        assert agent["result_json"]["live_outreach_allowed"] is False
        assert latest_warmup_post_send_checks(5)["send_mail"] is False
    finally:
        _cleanup(token)
