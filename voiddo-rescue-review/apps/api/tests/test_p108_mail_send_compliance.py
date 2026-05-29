from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.mail_send_compliance import mail_send_compliance_snapshot, run_mail_send_compliance_agent
from app.p0 import persist_inbound_message, signed_unsubscribe_url_for_lead, suppress_unsubscribe_token


def cleanup(token: str) -> None:
    execute("DELETE FROM email_events WHERE message_id LIKE %s OR payload_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM outreach_messages WHERE subject LIKE %s OR provider_message_id LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM warmup_schedule WHERE result_json::text LIKE %s OR sender_mailbox LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM suppression_list WHERE email LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))


def test_mail_send_compliance_accepts_registered_outreach_with_one_click_unsubscribe():
    token = uuid.uuid4().hex[:8]
    message_id = f"<compliance-{token}@voiddorescue.com>"
    try:
        unsubscribe = f"https://go.rescue.voiddo.com/unsubscribe/u_00000000-0000-0000-0000-000000000000.{token}"
        outreach = execute(
            """
            INSERT INTO outreach_messages(mailbox, subject, body, status, provider_message_id, sent_at)
            VALUES ('audit@voiddorescue.com', %s, %s, 'sent', %s, now())
            RETURNING id
            """,
            (f"Compliance {token}", f"Public check.\nUnsubscribe: {unsubscribe}", message_id),
        )
        execute(
            """
            INSERT INTO email_events(outreach_message_id, event_type, payload_json, mailbox, message_id)
            VALUES (%s, 'outreach_sent', %s, 'audit@voiddorescue.com', %s)
            """,
            (
                outreach["id"],
                Jsonb(
                    {
                        "token": token,
                        "recipient_hash": "hash-only",
                        "unsubscribe_one_click_ready": True,
                        "list_unsubscribe_header": True,
                        "raw_recipient_included": False,
                    }
                ),
                message_id,
            ),
        )
        result = mail_send_compliance_snapshot()
        assert result["checks"]["outreach_sent_without_event"] == 0
        assert result["checks"]["outreach_sent_missing_signed_unsubscribe"] == 0
        assert result["checks"]["outreach_sent_event_missing_one_click_headers"] == 0
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
    finally:
        cleanup(token)


def test_mail_send_compliance_blocks_sent_outreach_without_unsubscribe_or_event():
    token = uuid.uuid4().hex[:8]
    message_id = f"<bad-compliance-{token}@voiddorescue.com>"
    try:
        execute(
            """
            INSERT INTO outreach_messages(mailbox, subject, body, status, provider_message_id, sent_at)
            VALUES ('audit@voiddorescue.com', %s, 'No footer here.', 'sent', %s, now())
            RETURNING id
            """,
            (f"Compliance missing {token}", message_id),
        )
        result = mail_send_compliance_snapshot()
        assert result["decision"] == "FAIL_BLOCK_SEND"
        assert result["checks"]["outreach_sent_without_event"] >= 1
        assert result["checks"]["outreach_sent_missing_signed_unsubscribe"] >= 1
    finally:
        cleanup(token)


def test_mail_send_compliance_blocks_raw_recipient_in_outgoing_event_payload():
    token = uuid.uuid4().hex[:8]
    try:
        execute(
            """
            INSERT INTO email_events(event_type, payload_json, mailbox, message_id)
            VALUES ('warmup_sent', %s, 'audit@voiddorescue.com', %s)
            """,
            (Jsonb({"token": token, "recipient": f"{token}@example.com", "raw_recipient_included": True}), f"<raw-{token}@voiddorescue.com>"),
        )
        result = mail_send_compliance_snapshot()
        assert result["decision"] == "FAIL_BLOCK_SEND"
        assert result["checks"]["recent_outgoing_event_payload_raw_email"] >= 1
    finally:
        cleanup(token)


def test_mail_send_compliance_agent_records_no_send_run():
    result = run_mail_send_compliance_agent(write_report=False)
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False

    agent = run_agent("mail_send_compliance_agent", {"window_hours": 24})
    assert agent["status"] == "completed"
    assert agent["result_json"]["send_mail"] is False
    assert agent["result_json"]["live_outreach_allowed"] is False
    assert fetch_one("SELECT count(*) AS count FROM agent_runs WHERE agent = 'mail_send_compliance_agent'")["count"] >= 1


def test_one_click_unsubscribe_is_idempotent_and_hash_only():
    token = uuid.uuid4().hex[:8]
    try:
        business = execute(
            """
            INSERT INTO businesses(name, domain, website_url, email)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (f"Unsub {token}", f"{token}.example.test", f"https://{token}.example.test", f"team@{token}.example.test"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, status)
            VALUES (%s, %s, 'new')
            RETURNING id
            """,
            (business["id"], f"lead@{token}.example.test"),
        )
        unsubscribe_url = signed_unsubscribe_url_for_lead(str(lead["id"]))
        unsubscribe_token = unsubscribe_url.rsplit("/", 1)[-1]

        first = suppress_unsubscribe_token(unsubscribe_token)
        second = suppress_unsubscribe_token(unsubscribe_token)

        assert first["ok"] is True
        assert first["suppressed"] is True
        assert second["ok"] is True
        assert second["status"] == "already_suppressed"
        assert "recipient_hash" in first
        assert "lead@" not in str(first)
        row = fetch_one("SELECT count(*) AS count FROM suppression_list WHERE lower(email) = lower(%s)", (f"lead@{token}.example.test",))
        assert int(row["count"] or 0) == 1
    finally:
        cleanup(token)


def test_unsubscribe_reply_suppression_is_idempotent():
    token = uuid.uuid4().hex[:8]
    sender = f"reply-{token}@example.test"
    try:
        message = {
            "mailbox": "audit@voiddorescue.com",
            "uid": f"uid-{token}",
            "message_id": f"<reply-{token}@example.test>",
            "sender": sender,
            "subject": "unsubscribe",
            "body": "Please unsubscribe me.",
        }
        first = persist_inbound_message(message)
        second = persist_inbound_message(message)
        assert first["stored"] is True
        assert first["classification"] == "unsubscribe"
        assert second["duplicate"] is True
        row = fetch_one(
            "SELECT count(*) AS count FROM suppression_list WHERE lower(email) = lower(%s) AND reason = 'unsubscribe_reply'",
            (sender,),
        )
        assert int(row["count"] or 0) == 1
    finally:
        cleanup(token)
