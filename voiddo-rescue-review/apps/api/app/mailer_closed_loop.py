from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .mailer_action_queue import mailer_action_queue_summary, process_mailer_action_queue, send_customer_mail
from .p0 import json_safe, mail_signal_summary


def _count(sql: str, params: tuple = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def mailer_closed_loop_summary() -> dict[str, Any]:
    latest_ledger = [
        dict(row)
        for row in fetch_all(
            """
            SELECT action_id, action_type, mailbox, recipient_hash, template_key, status, result_json, updated_at
            FROM mailer_send_ledger
            ORDER BY updated_at DESC
            LIMIT 10
            """
        )
    ]
    unresolved_threads = [
        dict(row)
        for row in fetch_all(
            """
            SELECT id, mailbox, classification, human_review_required, updated_at
            FROM inbox_threads
            WHERE human_review_required
            ORDER BY updated_at DESC
            LIMIT 10
            """
        )
    ]
    owner_commands = [
        dict(row)
        for row in fetch_all(
            """
            SELECT id, command, risk_level, status, created_at
            FROM owner_commands
            ORDER BY created_at DESC
            LIMIT 10
            """
        )
    ]
    return json_safe(
        {
            "queue": mailer_action_queue_summary(),
            "send_ledger": {
                "total": _count("SELECT count(*) FROM mailer_send_ledger"),
                "sent": _count("SELECT count(*) FROM mailer_send_ledger WHERE status = 'sent'"),
                "transport_blocked": _count("SELECT count(*) FROM mailer_send_ledger WHERE status = 'transport_blocked'"),
                "failed": _count("SELECT count(*) FROM mailer_send_ledger WHERE status = 'failed'"),
                "latest": latest_ledger,
            },
            "inbound": {
                "human_review_required": _count("SELECT count(*) FROM inbox_threads WHERE human_review_required"),
                "unresolved": unresolved_threads,
            },
            "owner_commands": {
                "total": _count("SELECT count(*) FROM owner_commands"),
                "latest": owner_commands,
            },
            "signals": mail_signal_summary(24),
            "raw_recipient_addresses_included": False,
            "send_mail": False,
            "live_outreach_allowed": False,
        }
    )


def write_mailer_closed_loop_report(summary: dict[str, Any]) -> str:
    path = Path(get_settings().storage_root) / "reports" / "mailer_closed_loop_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        [
            "# Mailer Closed Loop Runtime Report",
            "",
            "## State",
            "",
            f"- queued: `{summary['queue']['queued']}`",
            f"- prepared: `{summary['queue']['prepared']}`",
            f"- send_ready: `{summary['queue']['send_ready']}`",
            f"- transport_blocked: `{summary['queue']['transport_blocked']}`",
            f"- failed: `{summary['queue']['failed']}`",
            f"- ledger total: `{summary['send_ledger']['total']}`",
            f"- human review required: `{summary['inbound']['human_review_required']}`",
            f"- live outreach allowed: `{str(summary['live_outreach_allowed']).lower()}`",
            f"- send_mail: `{str(summary['send_mail']).lower()}`",
            "",
            "Raw recipient addresses are not included in this report.",
        ]
    )
    path.write_text(text + "\n", encoding="utf-8")
    return str(path)


def run_mailer_closed_loop(limit: int = 10) -> dict[str, Any]:
    queued = process_mailer_action_queue(limit)
    transport = send_customer_mail(limit)
    summary = mailer_closed_loop_summary()
    report_path = write_mailer_closed_loop_report(summary)
    event = execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('mailer.closed_loop', 'info', 'Mailer closed-loop executor completed', %s)
        RETURNING id, created_at
        """,
        (
            Jsonb(
                json_safe(
                    {
                        "queued_processed": queued["processed"],
                        "transport_processed": transport["processed"],
                        "report_path": report_path,
                        "send_mail": False,
                        "live_outreach_allowed": False,
                    }
                )
            ),
        ),
    )
    return json_safe(
        {
            "queued": queued,
            "transport": transport,
            "summary": summary,
            "report_path": report_path,
            "event": dict(event),
            "send_mail": False,
            "live_outreach_allowed": False,
        }
    )
