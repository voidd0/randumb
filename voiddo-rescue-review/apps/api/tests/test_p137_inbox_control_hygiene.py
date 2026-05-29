from __future__ import annotations

import uuid

from app.db import execute, fetch_one
from app.inbox_control_hygiene import inbox_control_signal_hygiene


def test_inbox_control_signal_hygiene_reclassifies_warmup_control_reply():
    thread_id = None
    marker = f"p137-{uuid.uuid4().hex}"
    try:
        row = execute(
            """
            INSERT INTO inbox_threads(mailbox, external_thread_id, classification, human_review_required, last_message_preview)
            VALUES ('support', %s, 'human_review_required', true, %s)
            RETURNING id
            """,
            (marker, "This is a requested mail delivery diagnostic for Vøiddo Rescue. No action is required."),
        )
        thread_id = row["id"]
        execute(
            """
            INSERT INTO email_events(event_type, payload_json, mailbox, uid, message_id, classification, human_review_required)
            VALUES ('inbound_reply', '{}'::jsonb, 'support', %s, %s, 'human_review_required', true)
            """,
            (marker, marker),
        )
        result = inbox_control_signal_hygiene(20, apply=True)
        assert result["updated"] >= 1
        assert result["raw_previews_included"] is False
        saved = fetch_one("SELECT classification, human_review_required FROM inbox_threads WHERE id = %s", (thread_id,))
        assert saved["classification"] == "control_mail_signal"
        assert saved["human_review_required"] is False
        event = fetch_one("SELECT classification, human_review_required FROM email_events WHERE message_id = %s", (marker,))
        assert event["classification"] == "control_mail_signal"
        assert event["human_review_required"] is False
    finally:
        execute("DELETE FROM email_events WHERE message_id = %s", (marker,))
        if thread_id:
            execute("DELETE FROM inbox_threads WHERE id = %s", (thread_id,))


def test_inbox_control_signal_hygiene_does_not_reclassify_unknown_review():
    thread_id = None
    marker = f"p137-{uuid.uuid4().hex}"
    try:
        row = execute(
            """
            INSERT INTO inbox_threads(mailbox, external_thread_id, classification, human_review_required, last_message_preview)
            VALUES ('support', %s, 'human_review_required', true, %s)
            RETURNING id
            """,
            (marker, "Please call me about this website tomorrow."),
        )
        thread_id = row["id"]
        result = inbox_control_signal_hygiene(20, apply=True)
        saved = fetch_one("SELECT classification, human_review_required FROM inbox_threads WHERE id = %s", (thread_id,))
        assert saved["classification"] == "human_review_required"
        assert saved["human_review_required"] is True
        assert marker not in str(result)
    finally:
        if thread_id:
            execute("DELETE FROM inbox_threads WHERE id = %s", (thread_id,))

