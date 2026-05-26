from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from .customer_mail_simulation import run_customer_mail_simulation
from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .mailer_action_queue import enqueue_mailer_action, process_mailer_action_queue, transport_dry_run
from .p0 import json_safe


ALLOWED_OPS_ACTIONS = {
    "customer_simulation",
    "closed_loop_dry_run",
    "customer_transport_dry_run",
    "owner_report_action",
    "digest_history_cleanup",
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
    elif action == "digest_history_cleanup":
        from .mailer_control_room import cleanup_mailer_digest_history

        cleanup = cleanup_mailer_digest_history(90)
        result = {
            "status": "completed",
            "cleanup": cleanup,
            "deleted_count": cleanup["deleted_count"],
            "before_total_rows": cleanup["before"]["total_rows"],
            "after_total_rows": cleanup["after"]["total_rows"],
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
    latest_retention_agent = fetch_one(
        """
        SELECT id, status, result_json, started_at, completed_at
        FROM agent_runs
        WHERE agent = 'mailer_ops_retention_agent'
        ORDER BY started_at DESC
        LIMIT 1
        """
    )
    retention_agent_count = fetch_one("SELECT count(*) AS count FROM agent_runs WHERE agent = 'mailer_ops_retention_agent'")
    retention_agent = None
    if latest_retention_agent:
        result = latest_retention_agent["result_json"] or {}
        retention_agent = {
            "id": latest_retention_agent["id"],
            "status": latest_retention_agent["status"],
            "deleted_count": result.get("deleted_count", 0),
            "retained_real_count": result.get("retained_real_count", 0),
            "send_mail": bool(result.get("send_mail")),
            "smtp_called": bool(result.get("smtp_called")),
            "live_outreach_allowed": bool(result.get("live_outreach_allowed")),
            "raw_recipient_addresses_included": bool(result.get("raw_recipient_addresses_included")),
            "started_at": latest_retention_agent["started_at"],
            "completed_at": latest_retention_agent["completed_at"],
        }
    return json_safe(
        {
            "latest": latest,
            "by_action": by_action,
            "count": total,
            "real_count": int(real_row["count"]) if real_row else 0,
            "synthetic_count": int(synthetic_row["count"]) if synthetic_row else 0,
            "blocked_unsafe_count": int(blocked_row["count"]) if blocked_row else 0,
            "latest_real": dict(latest_real) if latest_real else None,
            "retention_agent_runs": int(retention_agent_count["count"]) if retention_agent_count else 0,
            "latest_retention_agent": retention_agent,
            "retention_agent_report": mailer_ops_retention_report_metadata(),
            "send_mail": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    )


def mailer_ops_retention_report_metadata() -> dict[str, Any]:
    path = Path(get_settings().storage_root) / "reports" / "mailer_ops_retention_agent_report.md"
    exists = path.exists()
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if exists else None
    return json_safe(
        {
            "exists": exists,
            "path": str(path) if exists else "",
            "path_stored": bool(exists),
            "modified_at": modified_at,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def cleanup_synthetic_mailer_ops_runs() -> dict[str, Any]:
    return cleanup_mailer_ops_synthetic_history()


def cleanup_mailer_ops_synthetic_history() -> dict[str, Any]:
    before = mailer_ops_action_summary()
    deleted_row = fetch_one("SELECT count(*) AS count FROM mailer_ops_runs WHERE is_synthetic")
    deleted_count = int(deleted_row["count"]) if deleted_row else 0
    execute("DELETE FROM mailer_ops_runs WHERE is_synthetic")
    after = mailer_ops_action_summary()
    return json_safe(
        {
            "cleaned": True,
            "deleted_count": deleted_count,
            "before_total_rows": before["count"],
            "after_total_rows": after["count"],
            "retained_real_count": after["real_count"],
            "before": before,
            "after": after,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
        }
    )


def write_mailer_ops_retention_agent_report(agent_run_id: str, retention: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    summary = mailer_ops_action_summary()
    latest_real = summary.get("latest_real") or {}
    path = Path(settings.storage_root) / "reports" / "mailer_ops_retention_agent_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Vøiddo Rescue Mailer Ops Retention Agent Report",
        "",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- agent_run_id: `{agent_run_id}`",
        f"- deleted_synthetic_count: `{retention.get('deleted_count', 0)}`",
        f"- retained_real_count: `{retention.get('retained_real_count', summary.get('real_count', 0))}`",
        f"- retained_synthetic_count: `{summary.get('synthetic_count', 0)}`",
        f"- latest_retained_real_action: `{latest_real.get('action', 'none')}`",
        f"- latest_retained_real_status: `{latest_real.get('status', 'none')}`",
        f"- send_mail: `{str(bool(retention.get('send_mail'))).lower()}`",
        f"- smtp_called: `{str(bool(retention.get('smtp_called'))).lower()}`",
        f"- live_outreach_allowed: `{str(bool(retention.get('live_outreach_allowed'))).lower()}`",
        f"- raw_recipient_addresses_included: `{str(bool(retention.get('raw_recipient_addresses_included'))).lower()}`",
        "",
        "Raw recipient addresses, message bodies, mailbox passwords, and secrets are intentionally omitted.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    history = execute(
        """
        INSERT INTO mailer_ops_retention_reports(
            agent_run_id,
            report_path,
            deleted_synthetic_count,
            retained_real_count,
            retained_synthetic_count,
            send_mail,
            smtp_called,
            live_outreach_allowed,
            raw_recipient_addresses_included,
            secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, created_at
        """,
        (
            agent_run_id,
            str(path),
            int(retention.get("deleted_count", 0) or 0),
            int(retention.get("retained_real_count", summary.get("real_count", 0)) or 0),
            int(summary.get("synthetic_count", 0) or 0),
        ),
    )
    return json_safe(
        {
            "path": str(path),
            "agent_run_id": agent_run_id,
            "history_id": history["id"],
            "history_created_at": history["created_at"],
            "deleted_synthetic_count": int(retention.get("deleted_count", 0) or 0),
            "retained_real_count": int(retention.get("retained_real_count", summary.get("real_count", 0)) or 0),
            "retained_synthetic_count": int(summary.get("synthetic_count", 0) or 0),
            "latest_retained_real_action": latest_real.get("action", "none"),
            "latest_retained_real_status": latest_real.get("status", "none"),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
