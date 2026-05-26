from __future__ import annotations

import os
from typing import Any

from psycopg.types.json import Jsonb

from .customer_mail_simulation import run_customer_mail_simulation
from .db import execute, fetch_all, fetch_one
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


def _is_synthetic(source: str, is_synthetic: bool | None = None) -> bool:
    if is_synthetic is not None:
        return bool(is_synthetic)
    if source == "pytest":
        return True
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def run_mailer_ops_action(action: str, limit: int = 10, source: str = "admin", is_synthetic: bool | None = None) -> dict[str, Any]:
    action = str(action or "").strip().lower()
    source = str(source or "admin").strip().lower()
    synthetic = _is_synthetic(source, is_synthetic)
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
    run = execute(
        """
        INSERT INTO mailer_ops_runs(action, status, result_json, raw_recipient_addresses_included, send_mail, smtp_called, live_outreach_allowed)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, action, status, raw_recipient_addresses_included, send_mail, smtp_called, live_outreach_allowed, created_at
        """,
        (
            action,
            result["status"],
            Jsonb(json_safe(result)),
            bool(result.get("raw_recipient_addresses_included")),
            bool(result.get("send_mail")),
            bool(result.get("smtp_called")),
            bool(result.get("live_outreach_allowed")),
        ),
    )
    execute(
        "UPDATE mailer_ops_runs SET source = %s, is_synthetic = %s WHERE id = %s",
        (source, synthetic, run["id"]),
    )
    run = fetch_one(
        """
        SELECT id, action, status, source, is_synthetic, raw_recipient_addresses_included, send_mail, smtp_called, live_outreach_allowed, created_at
        FROM mailer_ops_runs
        WHERE id = %s
        """,
        (run["id"],),
    )
    event = execute(
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
    return json_safe({"action": action, "result": result, "run": dict(run), "event": dict(event), "send_mail": False, "live_outreach_allowed": False})


def mailer_ops_action_summary(limit: int = 8) -> dict[str, Any]:
    latest = [
        dict(row)
        for row in fetch_all(
            """
            SELECT id, action, status, source, is_synthetic, raw_recipient_addresses_included, send_mail, smtp_called, live_outreach_allowed, created_at
            FROM mailer_ops_runs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (max(1, min(int(limit or 8), 25)),),
        )
    ]
    by_action = [
        dict(row)
        for row in fetch_all(
            """
            SELECT action, status, count(*) AS count
            FROM mailer_ops_runs
            GROUP BY action, status
            ORDER BY action, status
            """
        )
    ]
    total_row = fetch_one("SELECT count(*) AS count FROM mailer_ops_runs")
    total = int(total_row["count"]) if total_row else 0
    real_row = fetch_one("SELECT count(*) AS count FROM mailer_ops_runs WHERE NOT is_synthetic")
    synthetic_row = fetch_one("SELECT count(*) AS count FROM mailer_ops_runs WHERE is_synthetic")
    blocked_row = fetch_one("SELECT count(*) AS count FROM mailer_ops_runs WHERE status = 'blocked'")
    latest_real = fetch_one(
        """
        SELECT id, action, status, source, raw_recipient_addresses_included, send_mail, smtp_called, live_outreach_allowed, created_at
        FROM mailer_ops_runs
        WHERE NOT is_synthetic
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    return json_safe(
        {
            "latest": latest,
            "by_action": by_action,
            "count": total,
            "real_count": int(real_row["count"]) if real_row else 0,
            "synthetic_count": int(synthetic_row["count"]) if synthetic_row else 0,
            "blocked_unsafe_count": int(blocked_row["count"]) if blocked_row else 0,
            "latest_real": dict(latest_real) if latest_real else None,
            "send_mail": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    )


def cleanup_synthetic_mailer_ops_runs() -> dict[str, Any]:
    row = execute("DELETE FROM mailer_ops_runs WHERE is_synthetic RETURNING 1")
    _ = row
    summary = mailer_ops_action_summary()
    return json_safe({"cleaned": True, "summary": summary, "send_mail": False, "live_outreach_allowed": False})
