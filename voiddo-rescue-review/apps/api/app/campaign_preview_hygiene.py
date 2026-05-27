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


TEST_COUNTRY_PREFIXES = ("P7", "P8", "P9", "P10", "P11", "P12", "P59", "P60", "P61", "P62", "P63", "P68", "P72", "P73", "P74")


def _artifact_reason(row: dict[str, Any]) -> str:
    domain = str(row.get("domain") or "").lower()
    campaign_country = str(row.get("campaign_country") or "").upper()
    lead_source = str(row.get("lead_source") or "").lower()
    campaign_name = str(row.get("campaign_name") or "").lower()
    preview_text = str(row.get("preview_json") or "").lower()
    if domain.endswith(".example.test") or domain in {"example.com", "localhost"}:
        return "test_domain"
    if campaign_country.startswith(TEST_COUNTRY_PREFIXES):
        return "test_campaign_country"
    if lead_source.endswith("_test") or lead_source in {"p7_test", "p8_test", "p9_test", "p74_test"}:
        return "test_lead_source"
    if campaign_name.startswith(("p7-", "p8-", "p9-", "p74-")):
        return "test_campaign_name"
    if "legacy_stale_preview" in preview_text:
        return "legacy_stale_preview"
    return ""


def campaign_preview_hygiene_snapshot(limit: int = 500) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    rows = fetch_all(
        """
        SELECT cl.id AS campaign_lead_id, cl.status, cl.preview_json,
               c.name AS campaign_name, c.country AS campaign_country, c.niche AS campaign_niche,
               l.source AS lead_source, b.domain
        FROM campaign_leads cl
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN leads l ON l.id = cl.lead_id
        JOIN businesses b ON b.id = l.business_id
        WHERE cl.status = 'preview'
        ORDER BY cl.updated_at DESC, cl.created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    artifact_reasons: dict[str, int] = {}
    artifact_count = 0
    real_preview_count = 0
    for row in rows:
        reason = _artifact_reason(dict(row))
        if reason:
            artifact_count += 1
            artifact_reasons[reason] = artifact_reasons.get(reason, 0) + 1
        else:
            real_preview_count += 1
    return json_safe(
        {
            "status": "artifacts_found" if artifact_count else "clean",
            "inspected_count": len(rows),
            "artifact_count": artifact_count,
            "real_preview_count": real_preview_count,
            "artifact_reasons": artifact_reasons,
            **SAFE_FLAGS,
        }
    )


def archive_campaign_preview_artifacts(limit: int = 500, apply: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    rows = fetch_all(
        """
        SELECT cl.id AS campaign_lead_id, cl.preview_json,
               c.name AS campaign_name, c.country AS campaign_country, c.niche AS campaign_niche,
               l.source AS lead_source, b.domain
        FROM campaign_leads cl
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN leads l ON l.id = cl.lead_id
        JOIN businesses b ON b.id = l.business_id
        WHERE cl.status = 'preview'
        ORDER BY cl.updated_at DESC, cl.created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    artifacts = []
    for row in rows:
        reason = _artifact_reason(dict(row))
        if not reason:
            continue
        artifacts.append(
            {
                "campaign_lead_id": str(row["campaign_lead_id"]),
                "reason": reason,
                "domain_suffix": ".".join(str(row["domain"] or "").split(".")[-2:]),
                **SAFE_FLAGS,
            }
        )
        if apply:
            execute(
                """
                UPDATE campaign_leads
                SET status = 'archived_test_artifact',
                    preview_json = COALESCE(preview_json, '{}'::jsonb) || %s::jsonb,
                    updated_at = now()
                WHERE id = %s AND status = 'preview'
                """,
                (
                    Jsonb(
                        {
                            "campaign_preview_hygiene": {
                                "reason": reason,
                                "archived": True,
                                "send_mail": False,
                                "live_outreach_allowed": False,
                            }
                        }
                    ),
                    row["campaign_lead_id"],
                ),
            )
    result = json_safe(
        {
            "status": "applied" if apply and artifacts else ("planned" if artifacts else "clean"),
            "applied": bool(apply),
            "inspected_count": len(rows),
            "archived_count": len(artifacts) if apply else 0,
            "artifact_count": len(artifacts),
            "artifacts": artifacts[:50],
            **SAFE_FLAGS,
        }
    )
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('campaign_preview.hygiene', %s, 'Campaign preview hygiene evaluated', %s)
        """,
        ("info" if artifacts else "info", Jsonb(result)),
    )
    return result
