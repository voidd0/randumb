from __future__ import annotations

import csv
import io
import re
from typing import Any
from urllib.parse import urlparse

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .lead_scoring import score_lead
from .mailer_control_room import latest_mailer_self_audit_matrix_history
from .scout_quality import lead_scout_quality_gate, run_scout_quality_gate

EXCLUDED_NICHES = {"government", "banks", "bank", "hospitals", "hospital", "gambling", "adult", "crypto", "political"}
SUPPORTED_SCOUT_TYPES = {
    "manual_csv_scout",
    "sitemap/domain_list_scout",
    "business_directory_import_scout",
    "search_result_import_scout",
    "wordpress_footprint_scout",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


def _source_row_domain(row: dict[str, Any]) -> str:
    website = row.get("website_url") or row.get("url") or row.get("domain") or row.get("site") or ""
    return normalize_domain(str(website))


def _source_row_confidence(row: dict[str, Any]) -> float:
    try:
        raw = float(row.get("confidence") or 70)
    except (TypeError, ValueError):
        raw = 0
    return raw / 100 if raw > 1 else raw


def run_scout_source_readiness(source_id: str) -> dict[str, Any]:
    source = fetch_one("SELECT * FROM scout_sources WHERE id = %s", (source_id,))
    if not source:
        raise ValueError("scout_source_not_found")
    rows = _rows_from_source(dict(source))
    row_count = len(rows)
    domains = [_source_row_domain(row) for row in rows]
    parseable = [domain for domain in domains if domain]
    source_urls = [row.get("source_url") for row in rows if row.get("source_url")]
    seen: set[str] = set()
    duplicate_domains: set[str] = set()
    for domain in parseable:
        if domain in seen:
            duplicate_domains.add(domain)
        seen.add(domain)
    suppressed = 0
    invalid_email = 0
    excluded = 0
    confidence_values: list[float] = []
    for row in rows:
        niche = str(row.get("niche") or source["niche"] or "").strip().lower()
        if niche in EXCLUDED_NICHES:
            excluded += 1
        email = str(row.get("email") or "").strip().lower()
        if email and not EMAIL_RE.match(email):
            invalid_email += 1
        if email and fetch_one("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (email,)):
            suppressed += 1
        confidence_values.append(_source_row_confidence(row))
    domain_coverage = round(len(parseable) / row_count, 4) if row_count else 0
    source_url_coverage = round(len(source_urls) / row_count, 4) if row_count else 0
    confidence_average = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0
    issues: list[dict[str, Any]] = []
    if row_count == 0:
        issues.append({"code": "empty_source_rows", "severity": "high"})
    if domain_coverage < 0.9:
        issues.append({"code": "weak_domain_coverage", "severity": "high", "coverage": domain_coverage})
    if source_url_coverage < 0.8:
        issues.append({"code": "weak_source_url_coverage", "severity": "medium", "coverage": source_url_coverage})
    if confidence_average < 0.65:
        issues.append({"code": "low_average_confidence", "severity": "medium", "confidence": confidence_average})
    if duplicate_domains:
        issues.append({"code": "duplicate_domains_in_source", "severity": "medium", "count": len(duplicate_domains)})
    if excluded:
        issues.append({"code": "excluded_niche_rows", "severity": "high", "count": excluded})
    if suppressed:
        issues.append({"code": "suppressed_emails_in_source", "severity": "high", "count": suppressed})
    if invalid_email:
        issues.append({"code": "invalid_emails_in_source", "severity": "medium", "count": invalid_email})
    score = (
        int(domain_coverage * 30)
        + int(source_url_coverage * 25)
        + int(confidence_average * 20)
        + (10 if not duplicate_domains else max(0, 10 - len(duplicate_domains) * 2))
        + (10 if not excluded else 0)
        + (5 if not suppressed and not invalid_email else 0)
    )
    has_high = any(issue["severity"] == "high" for issue in issues)
    status = "PASS_SOURCE_READY" if score >= 75 and not has_high else "REVIEW_SOURCE_BEFORE_RUN"
    row = execute(
        """
        INSERT INTO scout_source_readiness_checks(
          source_id, status, score, row_count, parseable_count, domain_coverage,
          source_url_coverage, confidence_average, duplicate_domain_count,
          excluded_niche_count, suppressed_email_count, invalid_email_count, issues_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            source_id,
            status,
            score,
            row_count,
            len(parseable),
            domain_coverage,
            source_url_coverage,
            confidence_average,
            len(duplicate_domains),
            excluded,
            suppressed,
            invalid_email,
            Jsonb(issues),
        ),
    )
    payload = dict(row)
    payload["allowed_for_scout_run"] = status == "PASS_SOURCE_READY"
    payload["issues"] = issues
    payload["send_mail"] = False
    payload["smtp_called"] = False
    payload["live_outreach_allowed"] = False
    payload["raw_recipient_addresses_included"] = False
    payload["secrets_included"] = False
    return payload


def latest_scout_source_readiness(source_id: str) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT *
        FROM scout_source_readiness_checks
        WHERE source_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (source_id,),
    )
    if not row:
        return {
            "status": "missing",
            "score": 0,
            "allowed_for_scout_run": False,
            "issues": [{"code": "missing_source_readiness_check", "severity": "high"}],
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    payload = dict(row)
    payload["allowed_for_scout_run"] = payload["status"] == "PASS_SOURCE_READY"
    payload["issues"] = payload.get("issues_json") or []
    return payload


def scout_source_readiness_summary() -> dict[str, Any]:
    latest = fetch_all(
        """
        SELECT DISTINCT ON (source_id) source_id, status, score, row_count, parseable_count,
               duplicate_domain_count, excluded_niche_count, suppressed_email_count,
               invalid_email_count, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM scout_source_readiness_checks
        ORDER BY source_id, created_at DESC
        """
    )
    blockers = [
        row
        for row in latest
        if row["status"] != "PASS_SOURCE_READY"
        or any(bool(row.get(flag)) for flag in ["send_mail", "smtp_called", "live_outreach_allowed", "raw_recipient_addresses_included", "secrets_included"])
    ]
    return {
        "status": "PASS_NO_SEND" if not blockers and latest else "REVIEW_REQUIRED_NO_SEND",
        "sources_checked": len(latest),
        "sources_ready": len([row for row in latest if row["status"] == "PASS_SOURCE_READY"]),
        "sources_blocked": len(blockers),
        "latest": [dict(row) for row in latest[:20]],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def scout_campaign_expansion_gate() -> dict[str, Any]:
    matrix = latest_mailer_self_audit_matrix_history()
    blockers: list[str] = []
    if matrix["count"] < 1:
        blockers.append("missing_mailer_self_audit_matrix")
    if int(matrix.get("latest_coverage_score") or 0) < 100:
        blockers.append("self_audit_coverage_below_100")
    if int(matrix.get("latest_fail_count") or 0) > 0:
        blockers.append("self_audit_matrix_failures")
    if matrix.get("latest_send_mail") or matrix.get("latest_live_outreach_allowed"):
        blockers.append("self_audit_send_state_not_safe")
    return {
        "allowed": not blockers,
        "blockers": blockers,
        "matrix_count": matrix["count"],
        "latest_coverage_score": matrix.get("latest_coverage_score", 0),
        "latest_fail_count": matrix.get("latest_fail_count", 0),
        "send_mail": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


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


def process_scout_run_gated(run_id: str) -> dict[str, Any]:
    gate = scout_campaign_expansion_gate()
    if not gate["allowed"]:
        execute(
            "UPDATE scout_runs SET status = 'blocked', error = %s, result_json = %s, completed_at = now() WHERE id = %s",
            ("self_audit_gate_blocked", Jsonb({"gate": gate}), run_id),
        )
        return {"processed": False, "status": "blocked", "reason": "self_audit_gate_blocked", "gate": gate, "send_mail": False, "live_outreach_allowed": False}
    result = process_scout_run(run_id)
    quality_gate = run_scout_quality_gate(run_id)
    if not quality_gate["allowed_for_campaign_preview"]:
        execute(
            """
            UPDATE scout_runs
            SET status = 'review_required',
                result_json = COALESCE(result_json, '{}'::jsonb) || %s::jsonb
            WHERE id = %s
            """,
            (Jsonb({"quality_gate": quality_gate}), run_id),
        )
        result["status"] = "review_required"
    else:
        result["status"] = "completed"
    result["quality_gate"] = quality_gate
    result["gate"] = gate
    result["send_mail"] = False
    result["live_outreach_allowed"] = False
    return result


def process_queued_scout_runs(limit: int = 5) -> dict[str, Any]:
    gate = scout_campaign_expansion_gate()
    if not gate["allowed"]:
        return {"processed": 0, "status": "blocked", "reason": "self_audit_gate_blocked", "gate": gate, "send_mail": False, "live_outreach_allowed": False}
    rows = fetch_all(
        """
        SELECT id
        FROM scout_runs
        WHERE status = 'queued'
        ORDER BY created_at
        LIMIT %s
        """,
        (max(1, min(int(limit or 5), 25)),),
    )
    results = [process_scout_run_gated(str(row["id"])) for row in rows]
    return {"processed": len(results), "status": "ok" if results else "idle", "results": results, "gate": gate, "send_mail": False, "live_outreach_allowed": False}


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
               l.source AS lead_source,
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
    quality_excluded = 0
    for row in rows:
        quality_gate = lead_scout_quality_gate(str(row["lead_id"]))
        if not quality_gate["allowed_for_campaign_preview"]:
            quality_excluded += 1
            continue
        preview = {
            "business_name": row["business_name"],
            "domain": row["domain"],
            "audit_slug": row["public_slug"],
            "offer_key": campaign["offer_key"],
            "dry_run": True,
            "scout_quality_decision": quality_gate["decision"],
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
    return {"campaign_id": campaign_id, "preview_count": created, "threshold": threshold, "quality_excluded": quality_excluded, "live_send": False}


def prepare_campaign_gated(campaign_id: str, threshold: int = 70, limit: int = 20) -> dict[str, Any]:
    gate = scout_campaign_expansion_gate()
    if not gate["allowed"]:
        return {"campaign_id": campaign_id, "preview_count": 0, "threshold": threshold, "status": "blocked", "reason": "self_audit_gate_blocked", "gate": gate, "live_send": False, "send_mail": False, "live_outreach_allowed": False}
    result = prepare_campaign(campaign_id, threshold, limit)
    result["status"] = "preview_ready"
    result["gate"] = gate
    result["send_mail"] = False
    result["live_outreach_allowed"] = False
    return result


def get_campaign(campaign_id: str) -> dict[str, Any] | None:
    campaign = fetch_one("SELECT * FROM campaigns WHERE id = %s", (campaign_id,))
    if not campaign:
        return None
    leads = fetch_all("SELECT status, score, preview_json FROM campaign_leads WHERE campaign_id = %s ORDER BY score DESC", (campaign_id,))
    payload = dict(campaign)
    payload["leads"] = [dict(row) for row in leads]
    return payload
