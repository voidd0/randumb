from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .customer_mail_simulation import run_customer_mail_simulation
from .db import execute, fetch_all
from .mailer_action_queue import enqueue_mailer_action, process_mailer_action_queue, transport_dry_run
from .p0 import json_safe


ALLOWED_OPS_ACTIONS = {
    "customer_simulation",
    "closed_loop_dry_run",
    "customer_transport_dry_run",
    "owner_report_action",
}


def _sanitize_result(value: dict[str, Any]) -> dict[str, Any]:
    safe = json_safe(value)
    text = str(safe)
    return {
        **safe,
        "raw_recipient_addresses_included": "@" in text and "voiddorescue.com" not in text,
    }


def run_mailer_ops_action(action: str, limit: int = 10) -> dict[str, Any]:
    action = str(action or "").strip().lower()
    limit = max(1, min(int(limit or 10), 25))
    if action not in ALLOWED_OPS_ACTIONS:
        result = {
            "status": "blocked",
            "reason": "unknown_or_unsafe_action",
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    elif action == "customer_simulation":
        result = {
            "status": "completed",
            "simulation": run_customer_mail_simulation(write_report=False),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    elif action == "closed_loop_dry_run":
        queued = process_mailer_action_queue(limit)
        transport = transport_dry_run(limit)
        result = {
            "status": "completed",
            "queued": queued,
            "transport": transport,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    elif action == "customer_transport_dry_run":
        result = {
            "status": "completed",
            "transport": transport_dry_run(limit),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    else:
        enqueued = enqueue_mailer_action(
            {
                "action_type": "owner_report",
                "risk_level": "SAFE_AUTO",
                "mailbox": "support@voiddorescue.com",
                "template_key": "owner_status_report",
                "payload_json": {"source": "admin_ops_action"},
            }
        )
        processed = process_mailer_action_queue(1)
        result = {
            "status": "completed",
            "enqueued": enqueued,
            "processed": processed,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    result = _sanitize_result(result)
    row = execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('mailer.ops_action', %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            "warning" if result["status"] == "blocked" else "info",
            f"Mailer ops action {action} {result['status']}",
            Jsonb(json_safe({"action": action, "result": result})),
        ),
    )
    return json_safe({"action": action, "result": result, "event": dict(row), "send_mail": False, "live_outreach_allowed": False})


def mailer_ops_action_summary(limit: int = 8) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in fetch_all(
            """
            SELECT id, severity, message, payload_json, created_at
            FROM system_events
            WHERE type = 'mailer.ops_action'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (max(1, min(int(limit or 8), 25)),),
        )
    ]
    return json_safe(
        {
            "latest": rows,
            "count": len(rows),
            "send_mail": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    )

