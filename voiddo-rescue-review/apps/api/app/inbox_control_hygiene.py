from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import json_safe


CONTROL_MARKERS = (
    "no action is required",
    "mail warmup check",
    "warmup message",
    "mail delivery diagnostic",
    "mail diagnostic",
    "requested mail delivery diagnostic",
    "requested vøiddo rescue mail warmup",
)


def _preview_hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="replace")).hexdigest()[:24]


def _is_control_preview(preview: str) -> bool:
    text = (preview or "").lower()
    return any(marker in text for marker in CONTROL_MARKERS)


def inbox_control_signal_hygiene(limit: int = 100, apply: bool = False) -> dict[str, Any]:
    capped = max(1, min(int(limit or 100), 500))
    rows = [
        dict(row)
        for row in fetch_all(
            """
            SELECT id, mailbox, external_thread_id, classification, human_review_required, last_message_preview
            FROM inbox_threads
            WHERE human_review_required = true
              AND COALESCE(classification, '') = 'human_review_required'
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (capped,),
        )
    ]
    candidates = [row for row in rows if _is_control_preview(str(row.get("last_message_preview") or ""))]
    updated = 0
    if apply and candidates:
        for row in candidates:
            execute(
                """
                UPDATE inbox_threads
                SET classification = 'control_mail_signal',
                    human_review_required = false,
                    updated_at = now()
                WHERE id = %s
                """,
                (row["id"],),
            )
            execute(
                """
                UPDATE email_events
                SET classification = 'control_mail_signal',
                    human_review_required = false
                WHERE mailbox = %s
                  AND message_id = %s
                  AND classification = 'human_review_required'
                """,
                (row["mailbox"], row["external_thread_id"]),
            )
            updated += 1
        execute(
            "INSERT INTO system_events(type, severity, message, payload_json) VALUES (%s, %s, %s, %s)",
            (
                "inbox.control_signal_hygiene",
                "info",
                "Control/warmup inbox messages reclassified out of human review",
                Jsonb({"updated": updated, "raw_previews_included": False}),
            ),
        )
    return json_safe(
        {
            "status": "updated" if updated else ("candidates_found" if candidates else "clean"),
            "checked": len(rows),
            "candidate_count": len(candidates),
            "updated": updated,
            "apply": apply,
            "samples": [
                {
                    "thread_id": str(row["id"]),
                    "mailbox": row["mailbox"],
                    "preview_hash": _preview_hash(str(row.get("last_message_preview") or "")),
                }
                for row in candidates[:10]
            ],
            "raw_previews_included": False,
            "send_mail": False,
            "live_outreach_allowed": False,
        }
    )

