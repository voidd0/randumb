from __future__ import annotations

import csv
import io
import json
import re
from typing import Any
from urllib.parse import urlparse

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .lead_scoring import score_lead
from .mailer_control_room import latest_mailer_self_audit_matrix_history
from .scout_quality import lead_scout_quality_gate, run_scout_quality_gate
from .source_adapters import directory_rows_to_csv, domain_list_to_csv

EXCLUDED_NICHES = {"government", "banks", "bank", "hospitals", "hospital", "gambling", "adult", "crypto", "political"}
EXCLUDED_LARGE_BRAND_TOKENS = {
    "bestwestern",
    "casino",
    "choicehotels",
    "cityof",
    "communityhealth",
    "county",
    "department",
    "dept",
    "enterprise",
    "facebook",
    "gov",
    "gov.uk",
    "healthsystem",
    "hilton",
    "holidayinn",
    "hopkinsmedicine",
    "hospital",
    "hyatt",
    "ihg",
    "instagram",
    "linkedin",
    "lq.com",
    "marriott",
    "medicalcenter",
    "medicalcentre",
    "motel6",
    "mydentist",
    "nhs",
    "nhs.uk",
    "radissonhotels",
    "renown",
    "ryancompanies",
    "schooldistrict",
    "super8",
    "twitter",
    "university",
    "wales.nhs.uk",
    "wyndham",
    "wyndhamhotels",
    "x.com",
    "laserclinics",
}
SUPPORTED_SCOUT_TYPES = {
    "manual_csv_scout",
    "sitemap/domain_list_scout",
    "business_directory_import_scout",
    "search_result_import_scout",
    "wordpress_footprint_scout",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


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


def _public_source_summary(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(source["id"]),
        "name": source.get("name"),
        "source_type": source.get("source_type"),
        "country": source.get("country"),
        "language": source.get("language"),
        "niche": source.get("niche"),
        "status": source.get("status"),
        "created_at": source["created_at"].isoformat() if source.get("created_at") else None,
        "updated_at": source["updated_at"].isoformat() if source.get("updated_at") else None,
        "config_redacted": True,
    }


def prepare_scout_source_from_adapter(adapter_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    country = payload.get("country", "")
    niche = payload.get("niche", "")
    language = payload.get("language", "en")
    if adapter_type == "domain_list":
        csv_text = domain_list_to_csv(payload.get("text", ""), country, niche, language)
        source_type = "manual_csv_scout"
    elif adapter_type == "directory":
        csv_text = directory_rows_to_csv(payload.get("csv", ""), country, niche, language)
        source_type = "business_directory_import_scout"
    else:
        raise ValueError("unsupported_source_adapter")
    source = create_scout_source(
        {
            "name": payload.get("name") or f"{adapter_type}-{country or 'global'}-{niche or 'general'}",
            "source_type": source_type,
            "country": country,
            "language": language,
            "niche": niche,
            "status": "preflight_ready",
            "config_json": {"csv": csv_text},
        }
    )
    readiness = run_scout_source_readiness(str(source["id"]))
    return {
        "adapter_type": adapter_type,
        "source": _public_source_summary(source),
        "readiness": readiness,
        "created_scout_runs": 0,
        "created_scanner_jobs": 0,
        "processed_now": False,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


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
    payload = _json_safe(dict(row))
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


def _is_excluded_large_brand(business_name: str, domain: str, website: str = "") -> bool:
    combined = re.sub(r"[^a-z0-9.]+", "", f"{business_name} {domain} {website}".lower())
    if any(token in combined for token in EXCLUDED_LARGE_BRAND_TOKENS):
        return True
    normalized_domain = normalize_domain(domain or website)
    return normalized_domain in {"facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com"} or normalized_domain.endswith(".business.site")


def is_excluded_sensitive_target(business_name: str, domain: str, website: str = "", niche: str = "") -> bool:
    normalized_niche = (niche or "").strip().lower()
    if normalized_niche in EXCLUDED_NICHES:
        return True
    return _is_excluded_large_brand(business_name, domain, website)


def _is_sensitive_health_or_public_target(business_name: str, domain: str, website: str = "") -> bool:
    combined = re.sub(r"[^a-z0-9.]+", "", f"{business_name} {domain} {website}".lower())
    return any(
        token in combined
        for token in [
            "communityhealth",
            "healthsystem",
            "hopkinsmedicine",
            "hospital",
            "medicalcenter",
            "medicalcentre",
            "nhs",
            "renown",
        ]
    )


def _is_social_or_platform_profile(domain: str, website: str = "") -> bool:
    normalized = normalize_domain(domain or website)
    return normalized in {"facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com"} or normalized.endswith(".business.site")


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
    excluded_large_brand = 0
    confidence_values: list[float] = []
    for row in rows:
        niche = str(row.get("niche") or source["niche"] or "").strip().lower()
        domain = _source_row_domain(row)
        business_name = str(row.get("business_name") or row.get("name") or "")
        if niche in EXCLUDED_NICHES:
            excluded += 1
        if _is_excluded_large_brand(business_name, domain, str(row.get("website_url") or row.get("url") or row.get("domain") or "")):
            excluded_large_brand += 1
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
    if excluded_large_brand:
        severity = "high" if row_count and excluded_large_brand / row_count > 0.2 else "medium"
        issues.append({"code": "excluded_large_brand_rows", "severity": severity, "count": excluded_large_brand})
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
    payload = _json_safe(dict(row))
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
    payload = _json_safe(dict(row))
    payload["allowed_for_scout_run"] = payload["status"] == "PASS_SOURCE_READY"
    payload["issues"] = payload.get("issues_json") or []
    return payload


def scout_source_readiness_gate(source_id: str) -> dict[str, Any]:
    latest = latest_scout_source_readiness(source_id)
    if latest["status"] == "missing":
        latest = run_scout_source_readiness(source_id)
    blockers = []
    if latest["status"] != "PASS_SOURCE_READY":
        blockers.append({"code": "source_readiness_not_pass", "severity": "high", "status": latest["status"], "score": int(latest.get("score") or 0)})
    if any(bool(latest.get(flag)) for flag in ["send_mail", "smtp_called", "live_outreach_allowed", "raw_recipient_addresses_included", "secrets_included"]):
        blockers.append({"code": "source_readiness_flags_not_safe", "severity": "high"})
    return {
        "allowed": not blockers,
        "blockers": blockers,
        "readiness": latest,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


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
    guard = latest_scout_source_readiness_regression_guard_summary()
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
        "latest": [_json_safe(dict(row)) for row in latest[:20]],
        "regression_guard": guard,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def latest_scout_source_readiness_regression_guard_summary() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT id, status, result_json, error, started_at, completed_at, created_at
        FROM agent_runs
        WHERE agent = 'scout_source_readiness_regression_guard_agent'
        ORDER BY completed_at DESC NULLS LAST, started_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """
    )
    if not row:
        return {
            "decision": "MISSING_NO_SEND",
            "regressions": ["missing_source_readiness_regression_guard_run"],
            "regression_count": 1,
            "review_task_created": False,
            "agent_status": "missing",
            "latest_run_id": None,
            "latest_run_completed_at": None,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
            "raw_history_rows_included": False,
        }
    result = dict(row["result_json"]) if isinstance(row.get("result_json"), dict) else {}
    regressions = result.get("regressions") if isinstance(result.get("regressions"), list) else []
    return {
        "decision": result.get("decision", "MISSING_NO_SEND"),
        "regressions": regressions,
        "regression_count": len(regressions),
        "rows_checked": result.get("rows_checked"),
        "latest_score": result.get("latest_score"),
        "baseline_score": result.get("baseline_score"),
        "review_task_created": bool(result.get("review_task_created", False)),
        "agent_status": row["status"],
        "latest_run_id": str(row["id"]),
        "latest_run_completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
        "send_mail": bool(result.get("send_mail", False)),
        "smtp_called": bool(result.get("smtp_called", False)),
        "live_outreach_allowed": bool(result.get("live_outreach_allowed", False)),
        "raw_recipient_addresses_included": bool(result.get("raw_recipient_addresses_included", False)),
        "secrets_included": bool(result.get("secrets_included", False)),
        "raw_history_rows_included": bool(result.get("raw_history_rows_included", False)),
    }


def cleanup_scout_source_readiness_checks(keep: int = 120) -> dict[str, Any]:
    capped = max(10, min(int(keep or 120), 500))
    before = fetch_one("SELECT count(*) AS count FROM scout_source_readiness_checks")
    deleted = execute(
        """
        WITH retained AS (
          SELECT id FROM scout_source_readiness_checks ORDER BY created_at DESC, id DESC LIMIT %s
        ),
        removed AS (
          DELETE FROM scout_source_readiness_checks
          WHERE id NOT IN (SELECT id FROM retained)
          RETURNING id
        )
        SELECT count(*) AS deleted_count FROM removed
        """,
        (capped,),
    )
    after = fetch_one("SELECT count(*) AS count FROM scout_source_readiness_checks")
    return {
        "keep": capped,
        "before_count": int(before["count"]) if before else 0,
        "deleted_count": int((deleted or {}).get("deleted_count", 0) or 0),
        "after_count": int(after["count"]) if after else 0,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def scout_source_readiness_regression_guard(limit: int = 12) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, source_id, status, score, row_count, duplicate_domain_count,
               excluded_niche_count, suppressed_email_count, invalid_email_count,
               send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM scout_source_readiness_checks
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (max(2, min(int(limit or 12), 50)),),
    )
    latest = dict(rows[0]) if rows else None
    prior = [dict(row) for row in rows[1:]]
    regressions: list[str] = []
    latest_score = int((latest or {}).get("score") or 0)
    baseline_scores = [
        int(row.get("score") or 0)
        for row in prior
        if row.get("status") == "PASS_SOURCE_READY"
        and not any(bool(row.get(flag)) for flag in ["send_mail", "smtp_called", "live_outreach_allowed", "raw_recipient_addresses_included", "secrets_included"])
    ]
    baseline_score = max(baseline_scores) if baseline_scores else None
    if not latest:
        decision = "MISSING_NO_SEND"
    else:
        if latest["status"] != "PASS_SOURCE_READY":
            regressions.append("latest_source_readiness_not_pass")
        if any(bool(latest.get(flag)) for flag in ["send_mail", "smtp_called", "live_outreach_allowed", "raw_recipient_addresses_included", "secrets_included"]):
            regressions.append("latest_source_readiness_flags_not_safe")
        if baseline_score is not None and latest_score <= baseline_score - 10:
            regressions.append("source_readiness_score_dropped")
        decision = "PASS_NO_SEND" if not regressions else "FAIL_REVIEW_REQUIRED_NO_SEND"
    event_id = None
    task_id = None
    if latest and regressions:
        event = execute(
            """
            INSERT INTO system_events(type, severity, message, payload_json)
            VALUES ('scout.source_readiness_regression', 'warning', 'Scout source readiness regression requires review', %s)
            RETURNING id
            """,
            (
                Jsonb(
                    {
                        "decision": decision,
                        "regressions": regressions,
                        "latest_check_id": str(latest["id"]),
                        "latest_source_id": str(latest["source_id"]),
                        "latest_score": latest_score,
                        "baseline_score": baseline_score,
                        "send_mail": False,
                    }
                ),
            ),
        )
        event_id = str(event["id"]) if event else None
        task = execute(
            """
            INSERT INTO codex_tasks(type, priority, status, title, description, input_json)
            VALUES ('scanner_failed_case', 'medium', 'open', 'Review scout source readiness regression',
                    'Scout source readiness regression guard detected weaker source intake evidence.', %s)
            RETURNING id
            """,
            (
                Jsonb(
                    {
                        "source": "scout_source_readiness_regression_guard",
                        "regressions": regressions,
                        "latest_scout_source_readiness_check_id": str(latest["id"]),
                        "constraints": ["no_live_outreach", "no_secret_exposure", "source_quality_review_only"],
                    }
                ),
            ),
        )
        task_id = str(task["id"]) if task else None
    return {
        "decision": decision,
        "regressions": regressions,
        "rows_checked": len(rows),
        "latest_score": latest_score if latest else None,
        "baseline_score": baseline_score,
        "system_event_id": event_id,
        "codex_task_id": task_id,
        "review_task_created": bool(task_id),
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
        "raw_history_rows_included": False,
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
        elif _is_sensitive_health_or_public_target(business_name, domain, website):
            rejection_reason = "excluded_sensitive_target"
        elif _is_social_or_platform_profile(domain, website):
            rejection_reason = "excluded_sensitive_target"
        elif _is_excluded_large_brand(business_name, domain, website):
            rejection_reason = "excluded_large_enterprise"
        elif is_excluded_sensitive_target(business_name, domain, website, niche):
            rejection_reason = "excluded_sensitive_target"
        elif fetch_one(
            """
            SELECT 1
            FROM scout_leads
            WHERE lower(COALESCE(domain, '')) = lower(%s)
              AND lower(COALESCE(email, '')) = lower(%s)
            """,
            (domain, email or ""),
        ):
            rejection_reason = "duplicate_scout_lead"
        elif fetch_one("SELECT 1 FROM businesses WHERE lower(domain) = lower(%s)", (domain,)):
            rejection_reason = "duplicate_domain"
        elif email and fetch_one("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (email,)):
            rejection_reason = "suppressed_email"
        status = "accepted" if not rejection_reason else "rejected"
        if status == "accepted":
            accepted += 1
        else:
            rejected += 1
        if rejection_reason == "duplicate_scout_lead":
            continue
        scout_lead = execute(
            """
            INSERT INTO scout_leads(scout_run_id, business_name, domain, website_url, email, phone, country, city,
                                    language, niche, source_url, confidence, status, rejection_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
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
        if not scout_lead:
            rejected += 1
            if status == "accepted":
                accepted -= 1
            continue
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
    result = {
        "found": len(rows),
        "accepted": accepted,
        "rejected": rejected,
        "scanner_jobs": scanner_jobs,
        "previews": previews[:20],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
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
    run = fetch_one("SELECT source_id FROM scout_runs WHERE id = %s", (run_id,))
    if not run:
        raise ValueError("scout_run_not_found")
    source_gate = scout_source_readiness_gate(str(run["source_id"]))
    if not source_gate["allowed"]:
        execute(
            "UPDATE scout_runs SET status = 'review_required', error = %s, result_json = %s, completed_at = now() WHERE id = %s",
            ("source_readiness_review_required", Jsonb({"gate": gate, "source_readiness_gate": source_gate}), run_id),
        )
        return {
            "processed": False,
            "status": "review_required",
            "reason": "source_readiness_review_required",
            "gate": gate,
            "source_readiness_gate": source_gate,
            "send_mail": False,
            "live_outreach_allowed": False,
        }
    try:
        result = process_scout_run(run_id)
    except Exception as exc:
        execute(
            """
            UPDATE scout_runs
            SET status = 'failed',
                error = %s,
                result_json = COALESCE(result_json, '{}'::jsonb) || %s::jsonb,
                completed_at = now()
            WHERE id = %s
            """,
            (
                type(exc).__name__,
                Jsonb(
                    {
                        "error": type(exc).__name__,
                        "send_mail": False,
                        "live_outreach_allowed": False,
                    }
                ),
                run_id,
            ),
        )
        return {
            "processed": False,
            "status": "failed",
            "error": type(exc).__name__,
            "send_mail": False,
            "live_outreach_allowed": False,
        }
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


def ready_scout_source_queue_candidates(limit: int = 20, source_id: str | None = None) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 100))
    source_filter = "AND s.id = %s" if source_id else ""
    params: tuple[Any, ...] = (source_id, safe_limit) if source_id else (safe_limit,)
    rows = fetch_all(
        f"""
        WITH latest AS (
          SELECT DISTINCT ON (source_id) *
          FROM scout_source_readiness_checks
          ORDER BY source_id, created_at DESC, id DESC
        )
        SELECT s.*, latest.id AS readiness_id, latest.status AS readiness_status,
               latest.score AS readiness_score, latest.row_count AS readiness_row_count,
               latest.parseable_count AS readiness_parseable_count,
               latest.created_at AS readiness_created_at
        FROM scout_sources s
        JOIN latest ON latest.source_id = s.id
        WHERE latest.status = 'PASS_SOURCE_READY'
          AND s.status IN ('active', 'preflight_ready')
          {source_filter}
          AND NOT EXISTS (
            SELECT 1 FROM scout_runs sr
            WHERE sr.source_id = s.id
              AND sr.status IN ('queued', 'running', 'completed', 'review_required')
          )
        ORDER BY latest.created_at DESC, s.created_at DESC
        LIMIT %s
        """,
        params,
    )
    candidates = []
    for row in rows:
        source = _public_source_summary(dict(row))
        candidates.append(
            {
                "source": source,
                "readiness": {
                    "id": str(row["readiness_id"]),
                    "status": row["readiness_status"],
                    "score": int(row["readiness_score"] or 0),
                    "row_count": int(row["readiness_row_count"] or 0),
                    "parseable_count": int(row["readiness_parseable_count"] or 0),
                    "created_at": row["readiness_created_at"].isoformat() if row.get("readiness_created_at") else None,
                },
            }
        )
    return {
        "candidate_count": len(candidates),
        "candidates": candidates,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def queue_ready_scout_source_runs(limit: int = 10, dry_run: bool = True, source_id: str | None = None) -> dict[str, Any]:
    candidates = ready_scout_source_queue_candidates(limit, source_id)
    gate = scout_campaign_expansion_gate()
    queued: list[dict[str, Any]] = []
    duplicates_skipped = 0
    if dry_run or not gate["allowed"]:
        return {
            "status": "preview_only" if dry_run else "blocked",
            "reason": "" if dry_run else "self_audit_gate_blocked",
            "dry_run": dry_run,
            "candidate_count": candidates["candidate_count"],
            "candidates": candidates["candidates"],
            "queued_count": 0,
            "queued": queued,
            "duplicates_skipped": duplicates_skipped,
            "gate": gate,
            "created_scanner_jobs": 0,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    for item in candidates["candidates"]:
        source = item["source"]
        run = execute(
            """
            INSERT INTO scout_runs(source_id, status, country, niche, language)
            SELECT %s, 'queued', %s, %s, %s
            WHERE NOT EXISTS (
              SELECT 1 FROM scout_runs
              WHERE source_id = %s
                AND status IN ('queued', 'running', 'completed', 'review_required')
            )
            RETURNING *
            """,
            (source["id"], source.get("country"), source.get("niche"), source.get("language"), source["id"]),
        )
        if run:
            queued.append({"id": str(run["id"]), "source_id": source["id"], "status": run["status"]})
        else:
            duplicates_skipped += 1
    return {
        "status": "queued" if queued else "idle",
        "reason": "",
        "dry_run": False,
        "candidate_count": candidates["candidate_count"],
        "queued_count": len(queued),
        "queued": queued,
        "duplicates_skipped": duplicates_skipped,
        "gate": gate,
        "created_scanner_jobs": 0,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


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
          AND COALESCE(l.status, '') NOT IN ('excluded_sensitive_target', 'suppressed', 'unsubscribed')
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(s.email) = lower(l.email))
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(COALESCE(s.domain, '')) = lower(COALESCE(b.domain, '')))
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
