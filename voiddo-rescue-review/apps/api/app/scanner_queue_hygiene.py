from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _is_test_job(row: dict[str, Any]) -> str:
    url = str(row.get("url") or "").lower()
    business_name = str(row.get("business_name") or "").lower()
    result_text = str(row.get("result_json") or "").lower()
    if "example.test" in url or url.startswith("https://example.com") or url.startswith("http://example.com"):
        return "test_url"
    if business_name.startswith(("sim-", "p7 ", "p8 ", "p9 ", "p74 ", "self-")):
        return "test_business_name"
    if "example.test" in result_text or "pytest" in result_text:
        return "test_result_metadata"
    return ""


def scanner_queue_hygiene_snapshot(limit: int = 500) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    rows = fetch_all(
        """
        SELECT id, url, business_name, priority, result_json
        FROM scanner_jobs
        WHERE status = 'queued'
        ORDER BY priority DESC, queued_at ASC
        LIMIT %s
        """,
        (safe_limit,),
    )
    artifact_reasons: dict[str, int] = {}
    artifacts = 0
    for row in rows:
        reason = _is_test_job(dict(row))
        if reason:
            artifacts += 1
            artifact_reasons[reason] = artifact_reasons.get(reason, 0) + 1
    return json_safe(
        {
            "status": "artifacts_found" if artifacts else "clean",
            "queued_inspected": len(rows),
            "artifact_count": artifacts,
            "real_queued_count": len(rows) - artifacts,
            "artifact_reasons": artifact_reasons,
            **SAFE_FLAGS,
        }
    )


def archive_scanner_queue_artifacts(limit: int = 500, apply: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    rows = fetch_all(
        """
        SELECT id, url, business_name, priority, result_json
        FROM scanner_jobs
        WHERE status = 'queued'
        ORDER BY priority DESC, queued_at ASC
        LIMIT %s
        """,
        (safe_limit,),
    )
    artifacts = []
    for row in rows:
        reason = _is_test_job(dict(row))
        if not reason:
            continue
        artifacts.append(
            {
                "scanner_job_id": str(row["id"]),
                "reason": reason,
                "priority": int(row["priority"] or 0),
                **SAFE_FLAGS,
            }
        )
        if apply:
            execute(
                """
                UPDATE scanner_jobs
                SET status = 'archived_test_artifact',
                    result_json = COALESCE(result_json, '{}'::jsonb) || %s::jsonb,
                    updated_at = now()
                WHERE id = %s AND status = 'queued'
                """,
                (
                    Jsonb(
                        {
                            "scanner_queue_hygiene": {
                                "reason": reason,
                                "archived": True,
                                "send_mail": False,
                                "live_outreach_allowed": False,
                            }
                        }
                    ),
                    row["id"],
                ),
            )
    result = json_safe(
        {
            "status": "applied" if apply and artifacts else ("planned" if artifacts else "clean"),
            "applied": bool(apply),
            "inspected_count": len(rows),
            "artifact_count": len(artifacts),
            "archived_count": len(artifacts) if apply else 0,
            "artifacts": artifacts[:50],
            **SAFE_FLAGS,
        }
    )
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('scanner_queue.hygiene', 'info', 'Scanner queue hygiene evaluated', %s)
        """,
        (Jsonb(result),),
    )
    return result
