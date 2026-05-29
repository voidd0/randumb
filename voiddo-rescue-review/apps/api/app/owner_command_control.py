from __future__ import annotations

import hashlib
from typing import Any

from .db import fetch_all


def _hash(value: str) -> str:
    return hashlib.sha256((value or "").strip().lower().encode("utf-8")).hexdigest()[:24]


def owner_command_control_summary(limit: int = 20) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, mailbox, sender, reply_to, command, risk_level, status, result_json, created_at, executed_at
        FROM owner_commands
        WHERE COALESCE(result_json->>'action', '') <> 'reclassified_platform_alert'
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    commands: list[dict[str, Any]] = []
    for row in rows:
        result = row["result_json"] or {}
        commands.append(
            {
                "id": str(row["id"]),
                "mailbox": row.get("mailbox") or "",
                "sender_hash": _hash(row.get("sender") or ""),
                "reply_to_hash": _hash(row.get("reply_to") or ""),
                "command": row["command"],
                "risk_level": row["risk_level"],
                "status": row["status"],
                "result_action": result.get("action"),
                "result_ok": result.get("ok"),
                "created_at": row["created_at"],
                "executed_at": row["executed_at"],
            }
        )
    risk_counts = {
        row["risk_level"]: int(row["count"])
        for row in fetch_all(
            "SELECT risk_level, count(*) AS count FROM owner_commands WHERE COALESCE(result_json->>'action', '') <> 'reclassified_platform_alert' GROUP BY risk_level"
        )
    }
    status_counts = {
        row["status"]: int(row["count"])
        for row in fetch_all(
            "SELECT status, count(*) AS count FROM owner_commands WHERE COALESCE(result_json->>'action', '') <> 'reclassified_platform_alert' GROUP BY status"
        )
    }
    review_tasks = fetch_all(
        """
        SELECT priority, status, count(*) AS count
        FROM codex_tasks
        WHERE type = 'owner_command_review'
        GROUP BY priority, status
        ORDER BY priority, status
        """
    )
    return {
        "count": len(commands),
        "commands": commands,
        "risk_counts": risk_counts,
        "status_counts": status_counts,
        "review_tasks": [dict(row) for row in review_tasks],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_private_addresses_included": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
