from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import json_safe
from .scouts import create_campaign, infer_country_from_domain


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
    if "example.test" in domain or domain in {"example.com", "localhost"}:
        return "test_domain"
    if campaign_country.startswith(TEST_COUNTRY_PREFIXES):
        return "test_campaign_country"
    if lead_source.endswith("_test") or lead_source in {"p7_test", "p8_test", "p9_test", "p74_test"}:
        return "test_lead_source"
    if campaign_name.startswith(("p7-", "p8-", "p9-", "p74-")):
        return "test_campaign_name"
    if campaign_name in {"x", "test", "demo"} and not campaign_country:
        return "test_campaign_missing_geo"
    if "legacy_stale_preview" in preview_text:
        return "legacy_stale_preview"
    return ""


def _campaign_artifact_reason(row: dict[str, Any]) -> str:
    name = str(row.get("campaign_name") or "").lower()
    country = str(row.get("campaign_country") or "").upper()
    if country.startswith(TEST_COUNTRY_PREFIXES):
        return "test_campaign_country"
    if name.startswith(("p7-", "p8-", "p9-", "p59", "p60", "p61", "p62", "p63", "p68", "p72", "p73", "p74")):
        return "test_campaign_name"
    if "synthetic" in name:
        return "synthetic_campaign_name"
    if name in {"x", "test", "demo"} and not country:
        return "test_campaign_missing_geo"
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


def campaign_shell_hygiene_snapshot(limit: int = 500) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    rows = fetch_all(
        """
        SELECT c.id AS campaign_id, c.name AS campaign_name, c.country AS campaign_country,
               c.status AS campaign_status,
               count(cl.id) FILTER (WHERE cl.status = 'preview') AS active_preview_rows,
               count(cl.id) FILTER (WHERE cl.status = 'archived_test_artifact') AS archived_artifact_rows
        FROM campaigns c
        LEFT JOIN campaign_leads cl ON cl.campaign_id = c.id
        WHERE c.status IN ('preview_ready', 'draft')
        GROUP BY c.id, c.name, c.country, c.status
        ORDER BY c.updated_at DESC, c.created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    artifact_reasons: dict[str, int] = {}
    artifact_count = 0
    real_campaign_count = 0
    for row in rows:
        reason = _campaign_artifact_reason(dict(row))
        if reason:
            artifact_count += 1
            artifact_reasons[reason] = artifact_reasons.get(reason, 0) + 1
        else:
            real_campaign_count += 1
    return json_safe(
        {
            "status": "artifacts_found" if artifact_count else "clean",
            "inspected_count": len(rows),
            "artifact_count": artifact_count,
            "real_campaign_count": real_campaign_count,
            "artifact_reasons": artifact_reasons,
            **SAFE_FLAGS,
        }
    )


def archive_campaign_shell_artifacts(limit: int = 500, apply: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    rows = fetch_all(
        """
        SELECT c.id AS campaign_id, c.name AS campaign_name, c.country AS campaign_country,
               c.status AS campaign_status,
               count(cl.id) FILTER (WHERE cl.status = 'preview') AS active_preview_rows,
               count(cl.id) FILTER (WHERE cl.status = 'archived_test_artifact') AS archived_artifact_rows
        FROM campaigns c
        LEFT JOIN campaign_leads cl ON cl.campaign_id = c.id
        WHERE c.status IN ('preview_ready', 'draft')
        GROUP BY c.id, c.name, c.country, c.status
        ORDER BY c.updated_at DESC, c.created_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )
    artifacts = []
    for row in rows:
        reason = _campaign_artifact_reason(dict(row))
        if not reason:
            continue
        artifacts.append(
            {
                "campaign_id": str(row["campaign_id"]),
                "reason": reason,
                "active_preview_rows": int(row["active_preview_rows"] or 0),
                "archived_artifact_rows": int(row["archived_artifact_rows"] or 0),
                **SAFE_FLAGS,
            }
        )
        if apply:
            execute(
                """
                UPDATE campaigns
                SET status = 'archived_test_artifact',
                    updated_at = now()
                WHERE id = %s
                  AND status IN ('preview_ready', 'draft')
                """,
                (row["campaign_id"],),
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
        VALUES ('campaign_shell.hygiene', 'info', 'Campaign shell hygiene evaluated', %s)
        """,
        (Jsonb(result),),
    )
    return result


def campaign_geo_hygiene_snapshot(limit: int = 500) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    rows = _campaign_geo_mismatch_rows(safe_limit)
    by_country: dict[str, int] = {}
    for row in rows:
        key = f"{row['campaign_country']}->{row['inferred_country']}"
        by_country[key] = by_country.get(key, 0) + 1
    return json_safe(
        {
            "status": "mismatches_found" if rows else "clean",
            "inspected_limit": safe_limit,
            "mismatch_count": len(rows),
            "by_country": by_country,
            "sample": [_redacted_geo_row(row) for row in rows[:25]],
            **SAFE_FLAGS,
        }
    )


def repair_campaign_geo_mismatches(limit: int = 500, apply: bool = False) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    rows = _campaign_geo_mismatch_rows(safe_limit)
    repaired = []
    archived_duplicates = 0
    for row in rows:
        target_campaign = _target_campaign_for_geo_row(row) if apply else None
        action = "planned_move"
        if apply and target_campaign:
            duplicate = fetch_one(
                """
                SELECT id
                FROM campaign_leads
                WHERE campaign_id = %s
                  AND lead_id = %s
                  AND id <> %s
                LIMIT 1
                """,
                (target_campaign["id"], row["lead_id"], row["campaign_lead_id"]),
            )
            patch = Jsonb(
                {
                    "campaign_geo_hygiene": {
                        "previous_campaign_id": str(row["campaign_id"]),
                        "previous_campaign_country": row["campaign_country"],
                        "inferred_country": row["inferred_country"],
                        "domain_suffix": row["domain_suffix"],
                        "send_mail": False,
                        "live_outreach_allowed": False,
                    }
                }
            )
            execute(
                "UPDATE businesses SET country = %s, updated_at = now() WHERE id = %s",
                (row["inferred_country"], row["business_id"]),
            )
            execute(
                "UPDATE leads SET country = %s, updated_at = now() WHERE id = %s",
                (row["inferred_country"], row["lead_id"]),
            )
            execute(
                """
                UPDATE scout_leads
                SET country = %s
                WHERE lower(COALESCE(domain, '')) = lower(%s)
                   OR lower(COALESCE(website_url, '')) LIKE %s
                """,
                (row["inferred_country"], row["domain"], f"%{row['domain']}%"),
            )
            if duplicate:
                execute(
                    """
                    UPDATE campaign_leads
                    SET status = 'archived_geo_mismatch_duplicate',
                        preview_json = COALESCE(preview_json, '{}'::jsonb) || %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (patch, row["campaign_lead_id"]),
                )
                archived_duplicates += 1
                action = "archived_duplicate"
            else:
                execute(
                    """
                    UPDATE campaign_leads
                    SET campaign_id = %s,
                        preview_json = COALESCE(preview_json, '{}'::jsonb) || %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (target_campaign["id"], patch, row["campaign_lead_id"]),
                )
                action = "moved_to_inferred_country_campaign"
        repaired.append(
            {
                **_redacted_geo_row(row),
                "action": action,
                "target_campaign_id": str(target_campaign["id"]) if target_campaign else None,
                **SAFE_FLAGS,
            }
        )
    result = json_safe(
        {
            "status": "applied" if apply and rows else ("planned" if rows else "clean"),
            "applied": bool(apply),
            "inspected_limit": safe_limit,
            "mismatch_count": len(rows),
            "repaired_count": len(rows) if apply else 0,
            "archived_duplicate_count": archived_duplicates,
            "items": repaired[:50],
            **SAFE_FLAGS,
        }
    )
    execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('campaign_geo.hygiene', 'info', 'Campaign geo hygiene evaluated', %s)
        """,
        (Jsonb(result),),
    )
    return result


def _campaign_geo_mismatch_rows(limit: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT cl.id AS campaign_lead_id, cl.campaign_id, cl.lead_id,
               c.country AS campaign_country, c.language AS campaign_language,
               c.niche AS campaign_niche, c.offer_key,
               l.country AS lead_country, l.language AS lead_language,
               b.id AS business_id, b.domain
        FROM campaign_leads cl
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN leads l ON l.id = cl.lead_id
        JOIN businesses b ON b.id = l.business_id
        WHERE cl.status = 'preview'
          AND upper(COALESCE(c.country, '')) NOT LIKE 'P%%'
          AND lower(COALESCE(b.domain, '')) NOT LIKE '%%.example.test'
        ORDER BY cl.updated_at DESC, cl.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    mismatches = []
    for row in rows:
        domain = str(row["domain"] or "")
        inferred = infer_country_from_domain(domain)
        campaign_country = str(row["campaign_country"] or "").upper()
        lead_country = str(row["lead_country"] or "").upper()
        if not inferred or (campaign_country == inferred and lead_country == inferred):
            continue
        suffix = ".".join(domain.lower().split(".")[-2:])
        mismatches.append({**dict(row), "inferred_country": inferred, "domain_suffix": suffix})
    return mismatches


def _redacted_geo_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign_lead_id": str(row["campaign_lead_id"]),
        "campaign_country": row["campaign_country"],
        "lead_country": row["lead_country"],
        "inferred_country": row["inferred_country"],
        "domain_suffix": row["domain_suffix"],
    }


def _target_campaign_for_geo_row(row: dict[str, Any]) -> dict[str, Any]:
    existing = fetch_one(
        """
        SELECT *
        FROM campaigns
        WHERE country = %s
          AND language = %s
          AND niche = %s
          AND offer_key = %s
          AND status IN ('draft', 'preview_ready')
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (
            row["inferred_country"],
            row["campaign_language"] or row["lead_language"] or "en",
            row["campaign_niche"],
            row["offer_key"],
        ),
    )
    if existing:
        return dict(existing)
    return create_campaign(
        {
            "name": f"Rescue {row['inferred_country']} {row['campaign_niche']} preview",
            "country": row["inferred_country"],
            "language": row["campaign_language"] or row["lead_language"] or "en",
            "niche": row["campaign_niche"],
            "offer_key": row["offer_key"],
            "dry_run": True,
        }
    )
