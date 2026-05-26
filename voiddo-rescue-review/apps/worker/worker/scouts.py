from __future__ import annotations

import csv
import io
import re
from typing import Any
from urllib.parse import urlparse

from psycopg.types.json import Jsonb

from .db import connect

EXCLUDED_NICHES = {"government", "banks", "bank", "hospitals", "hospital", "gambling", "adult", "crypto", "political"}


def normalize_domain(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    domain = parsed.netloc or parsed.path.split("/")[0]
    return domain.removeprefix("www.").strip("/")


def website_url_for(value: str) -> str:
    return value if value.startswith(("http://", "https://")) else f"https://{normalize_domain(value)}"


def claim_scout_run() -> dict[str, Any] | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH picked AS (
                  SELECT id FROM scout_runs WHERE status = 'queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE scout_runs SET status = 'running', started_at = now()
                FROM picked WHERE scout_runs.id = picked.id
                RETURNING scout_runs.*
                """
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def process_one_scout_run() -> dict[str, Any]:
    run = claim_scout_run()
    if not run:
        return {"processed": False}
    with connect() as conn:
        with conn.cursor() as cur:
            source = cur.execute("SELECT * FROM scout_sources WHERE id = %s", (run["source_id"],)).fetchone()
            if not source:
                cur.execute("UPDATE scout_runs SET status = 'failed', error = 'source_missing', completed_at = now() WHERE id = %s", (run["id"],))
                conn.commit()
                return {"processed": True, "failed": True, "reason": "source_missing"}
            config = source["config_json"] or {}
            if source["source_type"] in {"manual_csv_scout", "business_directory_import_scout", "search_result_import_scout"}:
                rows = [dict(item) for item in csv.DictReader(io.StringIO(config.get("csv", "")))]
            else:
                rows = [{"website_url": item, "business_name": normalize_domain(item)} for item in re.split(r"[\s,;]+", config.get("domains", "")) if item.strip()]
            accepted = 0
            rejected = 0
            for item in rows:
                website = item.get("website_url") or item.get("domain") or item.get("url") or ""
                domain = normalize_domain(website)
                niche = (item.get("niche") or run["niche"] or source["niche"] or "").lower()
                if not domain or niche in EXCLUDED_NICHES:
                    rejected += 1
                    continue
                if cur.execute("SELECT 1 FROM businesses WHERE lower(domain) = lower(%s)", (domain,)).fetchone():
                    rejected += 1
                    continue
                business = cur.execute(
                    """
                    INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
                    VALUES (%s, %s, %s, %s, %s, 'scout_worker', %s, %s, %s, 'scouted')
                    RETURNING id
                    """,
                    (
                        item.get("business_name") or domain,
                        item.get("country") or run["country"],
                        item.get("city") or run["city"],
                        item.get("language") or run["language"] or "en",
                        niche,
                        website_url_for(website),
                        domain,
                        item.get("email") or None,
                    ),
                ).fetchone()
                lead = cur.execute(
                    """
                    INSERT INTO leads(business_id, email, source, status, language, country, city, niche)
                    VALUES (%s, %s, 'scout_worker', 'scouted', %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (business["id"], item.get("email") or None, item.get("language") or run["language"] or "en", item.get("country") or run["country"], item.get("city") or run["city"], niche),
                ).fetchone()
                cur.execute(
                    "INSERT INTO scanner_jobs(url, business_name, status, result_json) VALUES (%s, %s, 'queued', %s)",
                    (website_url_for(website), item.get("business_name") or domain, Jsonb({"lead_id": str(lead["id"]), "source": "scout_worker"})),
                )
                accepted += 1
            cur.execute(
                """
                UPDATE scout_runs SET status = 'completed', found_count = %s, accepted_count = %s,
                    rejected_count = %s, result_json = %s, completed_at = now()
                WHERE id = %s
                """,
                (len(rows), accepted, rejected, Jsonb({"accepted": accepted, "rejected": rejected}), run["id"]),
            )
        conn.commit()
    return {"processed": True, "run_id": str(run["id"]), "accepted": accepted, "rejected": rejected}
