from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent, runtime_daily_loop_plan
from app.db import execute, fetch_one
from app.p0 import recipient_hash
from app.warmup_signal_sanitizer import warmup_signal_sanitizer


def _cleanup(token: str) -> None:
    execute("DELETE FROM system_events WHERE type = 'warmup.signal_sanitizer' AND payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM mail_signals WHERE source = %s", (f"p145-{token}",))
    execute("DELETE FROM warmup_schedule WHERE recipient_email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM warmup_recipients WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM suppression_list WHERE email LIKE %s", (f"%{token}%",))


def test_warmup_signal_sanitizer_quarantines_matching_recipient_without_raw_result():
    token = uuid.uuid4().hex[:8]
    email = f"p145-{token}@example.net"
    try:
        execute(
            """
            INSERT INTO warmup_recipients(email, mailbox, source, status, approved)
            VALUES (%s, 'audit@voiddorescue.com', 'pytest', 'approved_test_pool', true)
            """,
            (email,),
        )
        execute(
            """
            INSERT INTO warmup_schedule(recipient_email, sender_mailbox, day_number, scheduled_for, status, result_json)
            VALUES (%s, 'audit@voiddorescue.com', 1, %s, 'scheduled', %s)
            """,
            (email, datetime.now(timezone.utc) + timedelta(hours=3), Jsonb({"token": token})),
        )
        execute(
            """
            INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, raw_summary)
            VALUES ('bounce', 'warning', %s, 'audit@voiddorescue.com', %s, 'other_external', %s)
            """,
            (f"p145-{token}", recipient_hash(email), f"synthetic p145 bounce {token}"),
        )

        result = warmup_signal_sanitizer(window_hours=24, limit=20, apply=True, source=f"p145-{token}")

        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
        assert result["matched_recipient_count"] == 1
        assert result["quarantined_recipient_count"] == 1
        assert result["schedule_quarantined_count"] == 1
        assert email not in str(result)
        recipient = fetch_one("SELECT status, approved FROM warmup_recipients WHERE lower(email) = lower(%s)", (email,))
        schedule = fetch_one("SELECT status, result_json FROM warmup_schedule WHERE lower(recipient_email) = lower(%s)", (email,))
        suppression = fetch_one("SELECT reason, source FROM suppression_list WHERE lower(email) = lower(%s)", (email,))
        assert recipient["status"] == "suppressed_mail_signal"
        assert recipient["approved"] is False
        assert schedule["status"] == "skipped_suppressed"
        assert schedule["result_json"]["warmup_signal_sanitizer"]["send_mail"] is False
        assert suppression["source"] == "warmup_signal_sanitizer"
    finally:
        _cleanup(token)


def test_warmup_signal_sanitizer_agent_and_core_loop_are_no_send():
    run = run_agent("warmup_signal_sanitizer_agent", {"window_hours": 1, "limit": 1, "apply": False})
    assert run["status"] == "completed"
    assert run["result_json"]["send_mail"] is False
    assert run["result_json"]["live_outreach_allowed"] is False
    assert "warmup_signal_sanitizer_agent" in [agent for agent, _payload in runtime_daily_loop_plan()]
