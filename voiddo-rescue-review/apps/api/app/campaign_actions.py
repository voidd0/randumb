from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from .campaign_control import campaign_readiness_snapshot
from .campaign_control_room import campaign_control_room_snapshot, prepare_campaign_control_room
from .campaign_preview_quality import campaign_preview_quality_pack
from .db import execute, fetch_all, fetch_one
from .p0 import json_safe

ALLOWED_ACTIONS = {"refresh_previews", "run_quality", "owner_preview_report", "safety_lock"}


def _record(action: str, status: str, result: dict[str, Any], campaign_id: str | None = None) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO campaign_action_runs(campaign_id, action, status, result_json, send_mail, smtp_called, live_outreach_allowed,
                                         raw_recipient_addresses_included, secrets_included)
        VALUES (%s, %s, %s, %s, false, false, false, false, false)
        RETURNING *
        """,
        (campaign_id, action, status, Jsonb(result)),
    )
    return dict(row)


def _campaign_summaries(limit: int = 20) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT c.id, c.name, c.status, c.country, c.language, c.niche, c.offer_key,
               count(cl.id) FILTER (WHERE cl.status = 'preview') AS preview_count,
               max(cl.score) AS top_score,
               max(cl.updated_at) AS latest_preview_at
        FROM campaigns c
        LEFT JOIN campaign_leads cl ON cl.campaign_id = c.id
        WHERE c.status IN ('draft', 'preview_ready', 'safety_locked')
        GROUP BY c.id
        ORDER BY preview_count DESC, c.updated_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 20), 100)),),
    )
    return [
        {
            "campaign_id": str(row["id"]),
            "name": row["name"],
            "status": row["status"],
            "country": row["country"],
            "language": row["language"],
            "niche": row["niche"],
            "offer_key": row["offer_key"],
            "preview_count": int(row["preview_count"] or 0),
            "top_score": int(row["top_score"] or 0),
            "latest_preview_at": row["latest_preview_at"],
        }
        for row in rows
    ]


def campaign_actions_summary(limit: int = 20) -> dict[str, Any]:
    runs = fetch_all(
        """
        SELECT id, campaign_id, action, status, result_json, created_at
        FROM campaign_action_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 20), 100)),),
    )
    counts = fetch_all("SELECT action, status, count(*) AS count FROM campaign_action_runs GROUP BY action, status ORDER BY action, status")
    room = campaign_control_room_snapshot(100, 70)
    return json_safe(
        {
            "status": "ready",
            "campaigns": _campaign_summaries(limit),
            "control_room": {
                "candidate_count": room.get("candidate_count", 0),
                "ready_candidate_count": room.get("ready_candidate_count", 0),
                "segment_count": room.get("segment_count", 0),
                "top_segments": room.get("top_segments", [])[:8],
            },
            "counts": [dict(row) for row in counts],
            "latest_runs": [
                {
                    "id": str(row["id"]),
                    "campaign_id": str(row["campaign_id"]) if row["campaign_id"] else None,
                    "action": row["action"],
                    "status": row["status"],
                    "result": row["result_json"],
                    "created_at": row["created_at"],
                }
                for row in runs
            ],
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def _write_owner_preview_report(payload: dict[str, Any]) -> str:
    report_dir = Path("/opt/voiddo-rescue/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "campaign_owner_preview_report.md"
    lines = [
        "# Vøiddo Rescue Campaign Preview",
        "",
        "This report is internal, no-send, and contains no raw recipient addresses.",
        "",
        f"Generated candidates: {payload.get('candidate_count', 0)}",
        f"Ready candidates: {payload.get('ready_candidate_count', 0)}",
        "",
        "## Segments",
    ]
    for segment in payload.get("top_segments", []):
        lines.append(f"- {segment.get('country')} / {segment.get('language')} / {segment.get('niche')}: {segment.get('ready_count')}/{segment.get('lead_count')} ready, lead score {segment.get('average_lead_score')}, audit strength {segment.get('average_audit_strength')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def run_campaign_action(action: str, campaign_id: str | None = None, limit: int = 100, dry_run: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 300))
    if action not in ALLOWED_ACTIONS:
        result = {"status": "blocked", "reason": "unknown_or_unsafe_campaign_action", "action": action}
        row = _record(action, "blocked", result, campaign_id)
        result["run_id"] = str(row["id"])
        return json_safe({**result, "send_mail": False, "smtp_called": False, "live_outreach_allowed": False, "raw_recipient_addresses_included": False, "secrets_included": False})

    if action == "refresh_previews":
        refreshed = prepare_campaign_control_room(safe_limit, 70, dry_run=dry_run, offer_key="contact_form_repair", max_segments=8)
        result = {"status": "completed" if not dry_run else "dry_run", "action": action, "refreshed": refreshed}
    elif action == "run_quality":
        campaigns = _campaign_summaries(min(safe_limit, 8))
        per_campaign_limit = max(1, min(safe_limit, 5))
        quality = []
        for campaign in campaigns:
            if campaign_id and campaign["campaign_id"] != campaign_id:
                continue
            if campaign["preview_count"] <= 0:
                continue
            quality.append({"campaign_id": campaign["campaign_id"], "country": campaign["country"], "niche": campaign["niche"], "quality": campaign_preview_quality_pack(campaign["campaign_id"], per_campaign_limit)})
        result = {"status": "completed", "action": action, "quality_count": len(quality), "quality": quality}
    elif action == "owner_preview_report":
        room = campaign_control_room_snapshot(safe_limit, 70)
        report_payload = {
            "candidate_count": room.get("candidate_count", 0),
            "ready_candidate_count": room.get("ready_candidate_count", 0),
            "top_segments": room.get("top_segments", [])[:10],
        }
        report_path = _write_owner_preview_report(report_payload) if not dry_run else "dry_run"
        result = {"status": "completed" if not dry_run else "dry_run", "action": action, "report_path": report_path, **report_payload}
    elif action == "safety_lock":
        if not campaign_id:
            result = {"status": "blocked", "reason": "campaign_id_required", "action": action}
        else:
            campaign = fetch_one("SELECT id, status FROM campaigns WHERE id = %s", (campaign_id,))
            if not campaign:
                result = {"status": "blocked", "reason": "campaign_not_found", "action": action, "campaign_id": campaign_id}
            elif dry_run:
                result = {"status": "dry_run", "action": action, "campaign_id": campaign_id, "would_set_status": "safety_locked"}
            else:
                execute("UPDATE campaigns SET status = 'safety_locked', dry_run = true, updated_at = now() WHERE id = %s", (campaign_id,))
                result = {"status": "completed", "action": action, "campaign_id": campaign_id, "new_status": "safety_locked"}
    else:  # pragma: no cover
        result = {"status": "blocked", "reason": "unreachable_action", "action": action}

    result.update({"send_mail": False, "smtp_called": False, "live_outreach_allowed": False, "raw_recipient_addresses_included": False, "secrets_included": False})
    row = _record(action, result["status"], result, campaign_id)
    result["run_id"] = str(row["id"])
    return json_safe(result)


def run_campaign_operator_cycle(limit: int = 25, refresh_previews: bool = True) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    refresh = (
        run_campaign_action("refresh_previews", limit=safe_limit, dry_run=False)
        if refresh_previews
        else {"status": "skipped_already_prepared_by_parent_cycle", "send_mail": False, "smtp_called": False, "live_outreach_allowed": False}
    )
    quality = run_campaign_action("run_quality", limit=min(safe_limit, 20), dry_run=False)
    summary = campaign_actions_summary(8)
    return json_safe(
        {
            "status": "completed",
            "agent": "campaign_operator_agent",
            "refresh_status": refresh.get("status"),
            "quality_status": quality.get("status"),
            "ready_candidate_count": summary.get("control_room", {}).get("ready_candidate_count", 0),
            "candidate_count": summary.get("control_room", {}).get("candidate_count", 0),
            "latest_action_runs": len(summary.get("latest_runs", [])),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
