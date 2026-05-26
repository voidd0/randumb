from __future__ import annotations

import csv
import io
import re
from typing import Any
from urllib.parse import urlparse

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .lead_scoring import score_lead

EXCLUDED_NICHES = {"government", "banks", "bank", "hospitals", "hospital", "gambling", "adult", "crypto", "political"}
SUPPORTED_SCOUT_TYPES = {
    "manual_csv_scout",
    "sitemap/domain_list_scout",
    "business_directory_import_scout",
    "search_result_import_scout",
    "wordpress_footprint_scout",
}


def normalize_domain(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    domain = parsed.netloc or parsed.path.split("/")[0]
    return domain.removeprefix("www.").strip("/")


def website_url_for(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith(("http://", "https://")):
        return raw
    return f"https://{normalize_domain(raw)}"


def infer_language(country: str, language: str = "") -> str:
    if language:
        return language
    return {"IL": "he", "EE": "et", "UK": "en", "IE": "en", "US": "en"}.get((country or "").upper(), "en")


def create_scout_source(payload: dict[str, Any]) -> dict[str, Any]:
    source_type = payload.get("source_type") or "manual_csv_scout"
    if source_type not in SUPPORTED_SCOUT_TYPES:
        raise ValueError("unsupported_scout_type")
    row = execute(
        """
        INSERT INTO scout_sources(name, source_type, country, language, niche, status, config_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            payload.get("name") or source_type,
            source_type,
            payload.get("country"),
            payload.get("language"),
            payload.get("niche"),
            payload.get("status", "active"),
            Jsonb(payload.get("config_json") or {}),
        ),
    )
    return dict(row)


def create_scout_run(source_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    source = fetch_one("SELECT * FROM scout_sources WHERE id = %s", (source_id,))
    if not source:
        raise ValueError("scout_source_not_found")
    overrides = overrides or {}
    row = execute(
        """
        INSERT INTO scout_runs(source_id, status, country, city, niche, language)
        VALUES (%s, 'queued', %s, %s, %s, %s)
        RETURNING *
        """,
        (
            source_id,
            overrides.get("country") or source["country"],
            overrides.get("city"),
            overrides.get("niche") or source["niche"],
            overrides.get("language") or source["language"],
        ),
    )
    return dict(row)


def get_scout_run(run_id: str) -> dict[str, Any] | None:
    row = fetch_one("SELECT * FROM scout_runs WHERE id = %s", (run_id,))
    if not row:
        return None
    leads = fetch_all("SELECT business_name, domain, country, city, language, niche, confidence, status, rejection_reason FROM scout_leads WHERE scout_run_id = %s ORDER BY created_at", (run_id,))
    payload = dict(row)
    payload["leads"] = [dict(item) for item in leads]
    return payload


def _rows_from_source(source: dict[str, Any]) -> list[dict[str, str]]:
    config = source.get("config_json") or {}
    source_type = source["source_type"]
    if source_type == "manual_csv_scout" or source_type in {"business_directory_import_scout", "search_result_import_scout"}:
        reader = csv.DictReader(io.StringIO(config.get("csv", "")))
        return [dict(row) for row in reader]
    if source_type in {"sitemap/domain_list_scout", "wordpress_footprint_scout"}:
        domains = re.split(r"[\s,;]+", config.get("domains", ""))
        return [{"website_url": item, "business_name": normalize_domain(item)} for item in domains if item.strip()]
    return []


def process_scout_run(run_id: str) -> dict[str, Any]:
    run = fetch_one("SELECT * FROM scout_runs WHERE id = %s", (run_id,))
    if not run:
        raise ValueError("scout_run_not_found")
    source = fetch_one("SELECT * FROM scout_sources WHERE id = %s", (run["source_id"],))
    if not source:
        raise ValueError("scout_source_not_found")
    execute("UPDATE scout_runs SET status = 'running', started_at = now() WHERE id = %s", (run_id,))
    rows = _rows_from_source(dict(source))
    accepted = 0
    rejected = 0
    scanner_jobs = 0
    previews: list[dict[str, Any]] = []
    for item in rows:
        website = item.get("website_url") or item.get("url") or item.get("domain") or item.get("site") or ""
        domain = normalize_domain(website)
        niche = (item.get("niche") or run["niche"] or source["niche"] or "").strip().lower()
        country = (item.get("country") or run["country"] or source["country"] or "").upper()
        language = infer_language(country, item.get("language") or run["language"] or source["language"] or "")
        email = (item.get("email") or "").strip().lower()
        business_name = item.get("business_name") or item.get("name") or domain
        rejection_reason = ""
        if not domain:
            rejection_reason = "missing_domain"
        elif niche in EXCLUDED_NICHES:
            rejection_reason = "excluded_niche"
        elif fetch_one("SELECT 1 FROM businesses WHERE lower(domain) = lower(%s)", (domain,)):
            rejection_reason = "duplicate_domain"
        elif email and fetch_one("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (email,)):
            rejection_reason = "suppressed_email"
        status = "accepted" if not rejection_reason else "rejected"
        if status == "accepted":
            accepted += 1
        else:
            rejected += 1
        scout_lead = execute(
            """
            INSERT INTO scout_leads(scout_run_id, business_name, domain, website_url, email, phone, country, city,
                                    language, niche, source_url, confidence, status, rejection_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                run_id,
                business_name,
                domain,
                website_url_for(website),
                email or None,
                item.get("phone"),
                country,
                item.get("city") or run["city"],
                language,
                niche,
                item.get("source_url"),
                int(item.get("confidence") or 70),
                status,
                rejection_reason or None,
            ),
        )
        if status != "accepted":
            continue
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, phone, status)
            VALUES (%s, %s, %s, %s, %s, 'scout_agent', %s, %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (business_name, country, item.get("city") or run["city"], language, niche, website_url_for(website), domain, email or None, item.get("phone")),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, contact_name, role, source, status, score, language, country, city, niche)
            VALUES (%s, %s, %s, %s, 'scout_agent', 'scouted', 0, %s, %s, %s, %s)
            RETURNING id
            """,
            (business["id"], email or None, item.get("contact_name"), item.get("role"), language, country, item.get("city") or run["city"], niche),
        )
        job = execute(
            """
            INSERT INTO scanner_jobs(url, business_name, dry_run, status, result_json)
            VALUES (%s, %s, false, 'queued', %s)
            RETURNING id
            """,
            (website_url_for(website), business_name, Jsonb({"lead_id": str(lead["id"]), "scout_lead_id": str(scout_lead["id"])})),
        )
        scanner_jobs += 1
        previews.append({"lead_id": str(lead["id"]), "domain": domain, "scanner_job_id": str(job["id"])})
        score_lead(str(lead["id"]))
    result = {"found": len(rows), "accepted": accepted, "rejected": rejected, "scanner_jobs": scanner_jobs, "previews": previews[:20]}
    execute(
        """
        UPDATE scout_runs
        SET status = 'completed', found_count = %s, accepted_count = %s, rejected_count = %s,
            result_json = %s, completed_at = now()
        WHERE id = %s
        """,
        (len(rows), accepted, rejected, Jsonb(result), run_id),
    )
    return result


def create_campaign(payload: dict[str, Any]) -> dict[str, Any]:
    row = execute(
        """
        INSERT INTO campaigns(name, status, country, language, niche, offer_key, max_daily_sends, max_hourly_sends, dry_run)
        VALUES (%s, 'draft', %s, %s, %s, %s, %s, %s, true)
        RETURNING *
        """,
        (
            payload.get("name") or "Rescue dry-run campaign",
            payload.get("country"),
            payload.get("language"),
            payload.get("niche"),
            payload.get("offer_key") or "contact_form_repair",
            int(payload.get("max_daily_sends") or 20),
            int(payload.get("max_hourly_sends") or 5),
        ),
    )
    return dict(row)


def prepare_campaign(campaign_id: str, threshold: int = 70, limit: int = 20) -> dict[str, Any]:
    campaign = fetch_one("SELECT * FROM campaigns WHERE id = %s", (campaign_id,))
    if not campaign:
        raise ValueError("campaign_not_found")
    rows = fetch_all(
        """
        SELECT l.id AS lead_id, l.email, l.country, l.language, l.niche, b.name AS business_name, b.domain,
               a.id AS audit_id, a.public_slug, COALESCE(ls.final_score, l.score, 0) AS final_score
        FROM leads l
        JOIN businesses b ON b.id = l.business_id
        LEFT JOIN audits a ON a.lead_id = l.id OR a.business_id = b.id
        LEFT JOIN LATERAL (
          SELECT final_score FROM lead_scores WHERE lead_id = l.id ORDER BY created_at DESC LIMIT 1
        ) ls ON true
        WHERE COALESCE(ls.final_score, l.score, 0) >= %s
          AND (%s::text IS NULL OR l.country = %s)
          AND (%s::text IS NULL OR l.language = %s)
          AND (%s::text IS NULL OR l.niche = %s)
          AND l.email IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(s.email) = lower(l.email))
        ORDER BY COALESCE(ls.final_score, l.score, 0) DESC, l.created_at DESC
        LIMIT %s
        """,
        (threshold, campaign["country"], campaign["country"], campaign["language"], campaign["language"], campaign["niche"], campaign["niche"], limit),
    )
    created = 0
    for row in rows:
        preview = {
            "business_name": row["business_name"],
            "domain": row["domain"],
            "audit_slug": row["public_slug"],
            "offer_key": campaign["offer_key"],
            "dry_run": True,
        }
        execute(
            """
            INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json)
            VALUES (%s, %s, %s, 'preview', %s, %s)
            ON CONFLICT (campaign_id, lead_id) DO UPDATE
              SET score = EXCLUDED.score, preview_json = EXCLUDED.preview_json, updated_at = now()
            """,
            (campaign_id, row["lead_id"], row["audit_id"], int(row["final_score"]), Jsonb(preview)),
        )
        created += 1
    execute("UPDATE campaigns SET status = 'preview_ready', updated_at = now() WHERE id = %s", (campaign_id,))
    return {"campaign_id": campaign_id, "preview_count": created, "threshold": threshold, "live_send": False}


def get_campaign(campaign_id: str) -> dict[str, Any] | None:
    campaign = fetch_one("SELECT * FROM campaigns WHERE id = %s", (campaign_id,))
    if not campaign:
        return None
    leads = fetch_all("SELECT status, score, preview_json FROM campaign_leads WHERE campaign_id = %s ORDER BY score DESC", (campaign_id,))
    payload = dict(campaign)
    payload["leads"] = [dict(row) for row in leads]
    return payload
