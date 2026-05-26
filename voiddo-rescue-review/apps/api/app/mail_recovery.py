from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute
from .email_templates import qa_email_template, render_email_template
from .p0 import latest_mail_qa_decision, mail_signal_summary, recipient_hash


def check_mail_clean_window(window_hours: int = 24) -> dict[str, Any]:
    signals = mail_signal_summary(window_hours)
    mail_qa = latest_mail_qa_decision()
    blocking = signals["bounce_or_dsn_count"] > 0 or signals["rate_limit_count"] > 0 or signals["spam_signal_count"] > 0 or mail_qa != "PASS"
    status = "blocked" if blocking else "ready_for_mail_qa_recheck"
    next_action = "wait_for_clean_window" if blocking else "rerun_mail_qa_then_prepare_warmup"
    row = execute(
        """
        INSERT INTO mail_clean_window_checks(status, window_hours, bounce_or_dsn_count, rate_limit_count, spam_signal_count, mail_qa_decision, next_action, result_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (status, window_hours, signals["bounce_or_dsn_count"], signals["rate_limit_count"], signals["spam_signal_count"], mail_qa, next_action, Jsonb(signals)),
    )
    return dict(row)


def create_mailer_draft(template_key: str, category: str, mailbox: str, recipient_email: str = "", language: str = "en", data: dict[str, Any] | None = None) -> dict[str, Any]:
    rendered = render_email_template(template_key, language, data or {})
    qa = qa_email_template(rendered)
    status = "draft_ready" if qa["passed"] else "draft_blocked"
    row = execute(
        """
        INSERT INTO mailer_drafts(direction, category, mailbox, recipient_hash, subject, body, status, qa_json)
        VALUES ('outbound', %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (category, mailbox, recipient_hash(recipient_email) if recipient_email else "", rendered["subject"], rendered["text"], status, Jsonb(qa)),
    )
    return dict(row)
