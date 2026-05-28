from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import urljoin
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import httpx
from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .lead_scoring import score_lead
from .p0 import json_safe
from .scouts import is_excluded_sensitive_target, normalize_domain


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}
ROLE_LOCALS = {
    "info",
    "contact",
    "hello",
    "office",
    "admin",
    "enquiries",
    "enquiry",
    "reception",
    "support",
    "booking",
    "bookings",
    "appointments",
    "webmaster",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_FIND_RE = re.compile(r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")
MAILTO_RE = re.compile(r"(?i)mailto:([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})")
PUBLIC_CONTACT_PATHS = (
    "/contact",
    "/contact/",
    "/contact-us",
    "/contact-us/",
    "/about",
    "/about/",
    "/about-us",
    "/about-us/",
)
MAX_PUBLIC_CONTACT_BYTES = 350_000
PUBLIC_CONTACT_HEADERS = {
    "User-Agent": "VoiddoRescue/1.0 public-contact-enrichment",
    "Accept": "text/html,application/xhtml+xml",
}


def _hash(value: str) -> str:
    return hashlib.sha256((value or "").strip().lower().encode("utf-8")).hexdigest()[:12]


def _base_url(domain: str, website_url: str | None = None) -> str:
    raw = (website_url or "").strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip("/")
    normalized = normalize_domain(raw or domain)
    return f"https://{normalized}".rstrip("/")


def _contact_urls(domain: str, website_url: str | None = None, max_pages: int = 4) -> list[str]:
    base = _base_url(domain, website_url)
    urls: list[str] = [base]
    for path in PUBLIC_CONTACT_PATHS:
        urls.append(urljoin(base + "/", path.lstrip("/")))
    seen: set[str] = set()
    safe_urls: list[str] = []
    normalized_domain = normalize_domain(domain)
    for url in urls:
        candidate_domain = normalize_domain(url)
        if not candidate_domain or candidate_domain != normalized_domain:
            continue
        if any(marker in url.lower() for marker in ("/admin", "/login", "/wp-admin", "/user", "/account", "/checkout")):
            continue
        if url in seen:
            continue
        seen.add(url)
        safe_urls.append(url)
        if len(safe_urls) >= max(1, min(max_pages, 8)):
            break
    return safe_urls


def fetch_public_contact_page(url: str) -> tuple[int, str, str]:
    with httpx.Client(timeout=12.0, follow_redirects=True, headers=PUBLIC_CONTACT_HEADERS) as client:
        response = client.get(url)
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type and response.status_code < 400:
        return response.status_code, "", str(response.url)
    return response.status_code, response.text[:MAX_PUBLIC_CONTACT_BYTES], str(response.url)


def _extract_emails_from_html(html: str) -> set[str]:
    if not html:
        return set()
    scrubbed = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    emails = {match.group(1).strip().lower() for match in MAILTO_RE.finditer(scrubbed)}
    emails.update(match.group(0).strip().lower() for match in EMAIL_FIND_RE.finditer(scrubbed))
    return {email for email in emails if EMAIL_RE.match(email)}


def _select_public_contact_email(domain: str, emails: set[str]) -> tuple[str | None, dict[str, Any]]:
    normalized_domain = normalize_domain(domain)
    choices: list[dict[str, Any]] = []
    for value in emails:
        local, email_domain = value.split("@", 1)
        if normalize_domain(email_domain) != normalized_domain:
            continue
        if fetch_one("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (value,)):
            continue
        role_bonus = 100 if local in ROLE_LOCALS else 0
        shorter_bonus = max(0, 30 - len(local))
        choices.append({"email": value, "local": local, "rank": role_bonus + shorter_bonus})
    choices.sort(key=lambda row: row["rank"], reverse=True)
    selected = next((row for row in choices if row["local"] in ROLE_LOCALS), None) or (choices[0] if choices else None)
    return (selected["email"] if selected else None), {
        "same_domain_email_count": len(choices),
        "selected_role": bool(selected and selected["local"] in ROLE_LOCALS),
        "selected_hash": _hash(selected["email"]) if selected else None,
    }


def contact_enrichment_candidates(limit: int = 25) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    recent_runs = fetch_all(
        """
        SELECT result_json
        FROM contact_enrichment_runs
        WHERE provider = 'public_contact_page'
          AND created_at > now() - interval '24 hours'
        ORDER BY created_at DESC
        LIMIT 25
        """
    )
    cooldown_hashes: set[str] = set()
    for run in recent_runs:
        for item in (run.get("result_json") or {}).get("results", []) or []:
            if item.get("status") in {"no_safe_public_contact_email", "time_budget_exhausted"} and item.get("domain_hash"):
                cooldown_hashes.add(str(item["domain_hash"]))
    fetch_limit = min(500, max(safe_limit, safe_limit + len(cooldown_hashes) * 2))
    rows = fetch_all(
        """
        SELECT l.id AS lead_id, b.id AS business_id, b.name AS business_name, b.domain,
               b.website_url, l.country, l.city, l.language, l.niche,
               a.id AS audit_id, a.public_slug, COALESCE(ls.final_score, l.score, 0) AS final_score
        FROM leads l
        JOIN businesses b ON b.id = l.business_id
        JOIN LATERAL (
          SELECT *
          FROM audits a
          WHERE a.lead_id = l.id
            AND a.status = 'completed'
          ORDER BY a.checked_at DESC NULLS LAST, a.created_at DESC
          LIMIT 1
        ) a ON true
        LEFT JOIN LATERAL (
          SELECT final_score
          FROM lead_scores
          WHERE lead_id = l.id
          ORDER BY created_at DESC
          LIMIT 1
        ) ls ON true
        WHERE l.source = 'scout_agent'
          AND COALESCE(l.status, '') NOT IN ('excluded_sensitive_target', 'suppressed', 'unsubscribed')
          AND COALESCE(b.status, '') NOT IN ('excluded_sensitive_target', 'suppressed', 'unsubscribed')
          AND (l.email IS NULL OR l.email = '')
          AND COALESCE(b.domain, '') <> ''
          AND NOT EXISTS (SELECT 1 FROM suppression_list s WHERE lower(COALESCE(s.domain, '')) = lower(COALESCE(b.domain, '')))
        ORDER BY COALESCE(ls.final_score, l.score, 0) DESC, a.checked_at DESC NULLS LAST
        LIMIT %s
        """,
        (fetch_limit,),
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        domain = normalize_domain(str(payload.get("domain") or payload.get("website_url") or ""))
        if not domain:
            continue
        if is_excluded_sensitive_target(
            str(payload.get("business_name") or ""),
            domain,
            str(payload.get("website_url") or ""),
            str(payload.get("niche") or ""),
        ):
            continue
        domain_hash = _hash(domain)
        if domain_hash in cooldown_hashes:
            continue
        candidates.append(
            {
                "lead_id": str(payload["lead_id"]),
                "business_id": str(payload["business_id"]),
                "audit_id": str(payload["audit_id"]),
                "public_slug": payload.get("public_slug"),
                "domain": domain,
                "domain_hash": domain_hash,
                "country": payload.get("country"),
                "language": payload.get("language"),
                "niche": payload.get("niche"),
                "final_score": int(payload.get("final_score") or 0),
            }
        )
        if len(candidates) >= safe_limit:
            break
    return json_safe(
        {
            "status": "ready" if candidates else "idle",
            "candidate_count": len(candidates),
            "cooldown_domain_count": len(cooldown_hashes),
            "candidates": candidates,
            **SAFE_FLAGS,
        }
    )


def hunter_domain_search(domain: str, api_key: str, limit: int = 10) -> dict[str, Any]:
    params = urlencode({"domain": domain, "api_key": api_key, "limit": max(1, min(int(limit or 10), 20))})
    request = Request(
        f"https://api.hunter.io/v2/domain-search?{params}",
        headers={"User-Agent": "VoiddoRescue/1.0 contact-enrichment"},
    )
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def _candidate_email(domain: str, hunter_payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    emails = ((hunter_payload.get("data") or {}).get("emails") or []) if isinstance(hunter_payload, dict) else []
    normalized_domain = normalize_domain(domain)
    choices: list[dict[str, Any]] = []
    for item in emails:
        value = str(item.get("value") or "").strip().lower()
        if not EMAIL_RE.match(value):
            continue
        local, email_domain = value.split("@", 1)
        if normalize_domain(email_domain) != normalized_domain:
            continue
        if fetch_one("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (value,)):
            continue
        confidence = int(item.get("confidence") or 0)
        role_bonus = 100 if local in ROLE_LOCALS else 0
        choices.append({"email": value, "local": local, "confidence": confidence, "rank": role_bonus + confidence})
    choices.sort(key=lambda row: row["rank"], reverse=True)
    role_choice = next((row for row in choices if row["local"] in ROLE_LOCALS), None)
    selected = role_choice or (choices[0] if choices and choices[0]["confidence"] >= 90 else None)
    return (selected["email"] if selected else None), {
        "email_count": len(choices),
        "selected_role": bool(selected and selected["local"] in ROLE_LOCALS),
        "selected_hash": _hash(selected["email"]) if selected else None,
        "selected_confidence": selected["confidence"] if selected else None,
    }


def run_hunter_contact_enrichment(limit: int = 10, dry_run: bool = True) -> dict[str, Any]:
    settings = get_settings()
    safe_limit = max(1, min(int(limit or 10), 25))
    candidates = contact_enrichment_candidates(safe_limit)["candidates"]
    if not settings.hunter_api_key:
        status = "blocked_missing_hunter_api_key"
        row = execute(
            """
            INSERT INTO contact_enrichment_runs(provider, status, scanned_count, enriched_count, skipped_count, result_json)
            VALUES ('hunter', %s, 0, 0, %s, %s)
            RETURNING id
            """,
            (status, len(candidates), Jsonb({"reason": status, **SAFE_FLAGS})),
        )
        return json_safe({"status": status, "run_id": str(row["id"]), "candidate_count": len(candidates), "enriched_count": 0, **SAFE_FLAGS})
    recent_rate_limit = fetch_one(
        """
        SELECT id, created_at
        FROM contact_enrichment_runs
        WHERE provider = 'hunter'
          AND status = 'provider_rate_limited'
          AND created_at > now() - interval '24 hours'
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    if recent_rate_limit and settings.hunter_api_key != "test-key":
        row = execute(
            """
            INSERT INTO contact_enrichment_runs(provider, status, scanned_count, enriched_count, skipped_count, result_json)
            VALUES ('hunter', 'blocked_provider_cooldown', 0, 0, %s, %s)
            RETURNING id
            """,
            (
                len(candidates),
                Jsonb(
                    {
                        "reason": "recent_hunter_rate_limit",
                        "recent_rate_limit_run_id": str(recent_rate_limit["id"]),
                        "candidate_count": len(candidates),
                        **SAFE_FLAGS,
                    }
                ),
            ),
        )
        return json_safe(
            {
                "status": "blocked_provider_cooldown",
                "run_id": str(row["id"]),
                "candidate_count": len(candidates),
                "scanned_count": 0,
                "enriched_count": 0,
                "skipped_count": len(candidates),
                "cooldown_hours": 24,
                **SAFE_FLAGS,
            }
        )

    scanned = 0
    enriched = 0
    skipped = 0
    results: list[dict[str, Any]] = []
    for item in candidates:
        scanned += 1
        domain = item["domain"]
        try:
            payload = hunter_domain_search(domain, settings.hunter_api_key, 10)
            selected, evidence = _candidate_email(domain, payload)
        except Exception as exc:
            skipped += 1
            if isinstance(exc, HTTPError) and exc.code == 429:
                results.append({"domain_hash": item["domain_hash"], "status": "provider_rate_limited", "http_status": 429})
                break
            results.append(
                {
                    "domain_hash": item["domain_hash"],
                    "status": "provider_error",
                    "error": type(exc).__name__,
                    "http_status": exc.code if isinstance(exc, HTTPError) else None,
                }
            )
            continue
        if not selected:
            skipped += 1
            results.append({"domain_hash": item["domain_hash"], "status": "no_safe_role_email", **evidence})
            continue
        if not dry_run:
            execute("UPDATE leads SET email = COALESCE(email, %s), updated_at = now() WHERE id = %s", (selected, item["lead_id"]))
            execute("UPDATE businesses SET email = COALESCE(email, %s), updated_at = now() WHERE id = %s", (selected, item["business_id"]))
            score_lead(item["lead_id"], item["audit_id"])
        enriched += 1
        results.append({"domain_hash": item["domain_hash"], "status": "would_enrich" if dry_run else "enriched", **evidence})

    rate_limited = any(item.get("status") == "provider_rate_limited" for item in results)
    status = "dry_run" if dry_run else ("provider_rate_limited" if rate_limited else ("enriched" if enriched else "no_safe_enrichment"))
    row = execute(
        """
        INSERT INTO contact_enrichment_runs(provider, status, scanned_count, enriched_count, skipped_count, result_json)
        VALUES ('hunter', %s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            status,
            scanned,
            enriched,
            skipped,
            Jsonb({"results": results, "dry_run": dry_run, **SAFE_FLAGS}),
        ),
    )
    return json_safe(
        {
            "status": status,
            "run_id": str(row["id"]),
            "created_at": row["created_at"],
            "candidate_count": len(candidates),
            "scanned_count": scanned,
            "enriched_count": enriched,
            "skipped_count": skipped,
            "results": results,
            "dry_run": dry_run,
            **SAFE_FLAGS,
        }
    )


def run_public_contact_page_enrichment(
    limit: int = 10,
    dry_run: bool = True,
    max_pages_per_domain: int = 4,
    max_seconds: int = 45,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 10), 100))
    safe_max_pages = max(1, min(int(max_pages_per_domain or 4), 8))
    safe_max_seconds = max(5, min(int(max_seconds or 45), 180))
    candidates = contact_enrichment_candidates(safe_limit)["candidates"]
    scanned = 0
    enriched = 0
    skipped = 0
    results: list[dict[str, Any]] = []
    started = time.monotonic()
    time_budget_exhausted = False
    for item in candidates:
        if time.monotonic() - started >= safe_max_seconds:
            time_budget_exhausted = True
            break
        scanned += 1
        domain = item["domain"]
        urls = _contact_urls(domain, None, safe_max_pages)
        found_emails: set[str] = set()
        page_results: list[dict[str, Any]] = []
        for url in urls:
            if time.monotonic() - started >= safe_max_seconds:
                time_budget_exhausted = True
                page_results.append({"path_hash": _hash(url), "status": "time_budget_exhausted"})
                break
            try:
                status_code, html, final_url = fetch_public_contact_page(url)
            except Exception as exc:
                page_results.append({"path_hash": _hash(url), "status": "fetch_error", "error": type(exc).__name__})
                continue
            page_emails = _extract_emails_from_html(html)
            found_emails.update(page_emails)
            page_results.append(
                {
                    "path_hash": _hash(url),
                    "final_path_hash": _hash(final_url),
                    "status_code": status_code,
                    "email_count": len(page_emails),
                }
            )
            if page_emails:
                break
        if time_budget_exhausted and not found_emails:
            skipped += 1
            results.append(
                {
                    "domain_hash": item["domain_hash"],
                    "status": "time_budget_exhausted",
                    "pages_checked": len(page_results),
                    "pages": page_results,
                }
            )
            break
        selected, evidence = _select_public_contact_email(domain, found_emails)
        if not selected:
            skipped += 1
            results.append(
                {
                    "domain_hash": item["domain_hash"],
                    "status": "no_safe_public_contact_email",
                    "pages_checked": len(page_results),
                    "pages": page_results,
                    **evidence,
                }
            )
            continue
        if not dry_run:
            execute("UPDATE leads SET email = COALESCE(email, %s), updated_at = now() WHERE id = %s", (selected, item["lead_id"]))
            execute("UPDATE businesses SET email = COALESCE(email, %s), updated_at = now() WHERE id = %s", (selected, item["business_id"]))
            score_lead(item["lead_id"], item["audit_id"])
        enriched += 1
        results.append(
            {
                "domain_hash": item["domain_hash"],
                "status": "would_enrich" if dry_run else "enriched",
                "pages_checked": len(page_results),
                "pages": page_results,
                **evidence,
            }
        )

    status = "dry_run" if dry_run else ("partial_time_budget_exhausted" if time_budget_exhausted else ("enriched" if enriched else "no_safe_enrichment"))
    row = execute(
        """
        INSERT INTO contact_enrichment_runs(provider, status, scanned_count, enriched_count, skipped_count, result_json)
        VALUES ('public_contact_page', %s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            status,
            scanned,
            enriched,
            skipped,
            Jsonb(
                {
                    "results": results,
                    "dry_run": dry_run,
                    "max_pages_per_domain": safe_max_pages,
                    "max_seconds": safe_max_seconds,
                    "time_budget_exhausted": time_budget_exhausted,
                    **SAFE_FLAGS,
                }
            ),
        ),
    )
    return json_safe(
        {
            "status": status,
            "run_id": str(row["id"]),
            "created_at": row["created_at"],
            "candidate_count": len(candidates),
            "scanned_count": scanned,
            "enriched_count": enriched,
            "skipped_count": skipped,
            "results": results,
            "dry_run": dry_run,
            "max_pages_per_domain": safe_max_pages,
            "max_seconds": safe_max_seconds,
            "time_budget_exhausted": time_budget_exhausted,
            **SAFE_FLAGS,
        }
    )
