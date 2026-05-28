from __future__ import annotations

import csv
import io
import json
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from .db import fetch_all
from .scouts import create_scout_source, run_scout_source_readiness, website_url_for

TEST_COUNTRY_PATTERN = r"^(P7|P8|P9|P10|P11|P12|P59|P60|P61|P62|P63|P68|P72|P73|P74)"

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

NICHE_TAGS: dict[str, list[tuple[str, str]]] = {
    "dentists": [("amenity", "dentist"), ("healthcare", "dentist")],
    "clinics": [("amenity", "clinic"), ("healthcare", "clinic")],
    "beauty salons": [("shop", "beauty"), ("shop", "hairdresser")],
    "law firms": [("office", "lawyer")],
    "local tourism": [("tourism", "hotel"), ("tourism", "guest_house"), ("tourism", "attraction")],
    "private courses": [("amenity", "language_school"), ("amenity", "music_school")],
    "contractors": [("craft", "builder"), ("office", "construction_company")],
}

CITY_AREAS: dict[tuple[str, str], str] = {
    ("EE", "tallinn"): "Tallinn",
    ("EE", "tartu"): "Tartu",
    ("IL", "tel aviv"): "Tel Aviv-Yafo",
    ("IL", "jerusalem"): "Jerusalem",
    ("AU", "gold coast"): "City of Gold Coast",
    ("AU", "sunshine coast"): "Sunshine Coast Regional",
    ("NZ", "tauranga"): "Tauranga City",
    ("NZ", "hamilton"): "Hamilton City",
    ("CA", "st johns"): "St. John's",
}

COUNTRY_AREA_CODES = {
    "US": "US",
    "UK": "GB",
    "AU": "AU",
    "NZ": "NZ",
    "CA": "CA",
    "IE": "IE",
    "IL": "IL",
    "EE": "EE",
}

FIRST_TIER_MARKETS: list[tuple[str, str, str]] = [
    ("US", "Boise", "dentists"),
    ("US", "Spokane", "contractors"),
    ("US", "Knoxville", "dentists"),
    ("US", "Chattanooga", "beauty salons"),
    ("US", "Greenville", "law firms"),
    ("US", "Asheville", "local tourism"),
    ("US", "Fort Myers", "clinics"),
    ("US", "Sarasota", "beauty salons"),
    ("US", "Des Moines", "contractors"),
    ("US", "Madison", "dentists"),
    ("US", "Tulsa", "law firms"),
    ("US", "Reno", "clinics"),
    ("UK", "Bristol", "dentists"),
    ("UK", "Leeds", "contractors"),
    ("UK", "York", "local tourism"),
    ("UK", "Bath", "beauty salons"),
    ("UK", "Norwich", "law firms"),
    ("UK", "Exeter", "dentists"),
    ("UK", "Brighton", "beauty salons"),
    ("UK", "Cardiff", "clinics"),
    ("UK", "Cheltenham", "law firms"),
    ("UK", "Reading", "contractors"),
    ("AU", "Gold Coast", "dentists"),
    ("AU", "Sunshine Coast", "contractors"),
    ("AU", "Newcastle", "clinics"),
    ("AU", "Geelong", "beauty salons"),
    ("AU", "Wollongong", "dentists"),
    ("AU", "Hobart", "local tourism"),
    ("AU", "Cairns", "local tourism"),
    ("AU", "Toowoomba", "contractors"),
    ("AU", "Ballarat", "law firms"),
    ("NZ", "Tauranga", "dentists"),
    ("NZ", "Hamilton", "contractors"),
    ("NZ", "Dunedin", "clinics"),
    ("NZ", "Queenstown", "local tourism"),
    ("NZ", "Napier", "beauty salons"),
    ("NZ", "Nelson", "local tourism"),
    ("NZ", "Rotorua", "local tourism"),
    ("NZ", "Palmerston North", "law firms"),
    ("CA", "Kelowna", "dentists"),
    ("CA", "Victoria", "beauty salons"),
    ("CA", "Halifax", "law firms"),
    ("CA", "London", "clinics"),
    ("CA", "Kingston", "contractors"),
    ("CA", "Guelph", "dentists"),
    ("CA", "Barrie", "beauty salons"),
    ("CA", "Saskatoon", "contractors"),
    ("CA", "Moncton", "local tourism"),
    ("CA", "St Johns", "clinics"),
    ("IE", "Cork", "dentists"),
    ("IE", "Galway", "local tourism"),
    ("IE", "Limerick", "contractors"),
    ("IE", "Waterford", "beauty salons"),
    ("IE", "Kilkenny", "local tourism"),
    ("IE", "Sligo", "clinics"),
    ("IE", "Drogheda", "law firms"),
    ("IE", "Wexford", "dentists"),
    ("US", "Bend", "dentists"),
    ("US", "Eugene", "beauty salons"),
    ("US", "Ann Arbor", "dentists"),
    ("US", "Fayetteville", "contractors"),
    ("US", "Lexington", "law firms"),
    ("US", "Charleston", "local tourism"),
    ("US", "Savannah", "local tourism"),
    ("US", "Wilmington", "dentists"),
    ("US", "Lancaster", "beauty salons"),
    ("US", "Fort Collins", "contractors"),
    ("US", "Santa Fe", "law firms"),
    ("US", "Boulder", "beauty salons"),
    ("UK", "Oxford", "dentists"),
    ("UK", "Cambridge", "law firms"),
    ("UK", "Canterbury", "local tourism"),
    ("UK", "Winchester", "dentists"),
    ("UK", "Harrogate", "beauty salons"),
    ("UK", "Lincoln", "contractors"),
    ("UK", "Plymouth", "dentists"),
    ("UK", "Chester", "local tourism"),
    ("UK", "Gloucester", "law firms"),
    ("UK", "Portsmouth", "beauty salons"),
    ("AU", "Bendigo", "dentists"),
    ("AU", "Maitland", "contractors"),
    ("AU", "Launceston", "beauty salons"),
    ("AU", "Albury", "dentists"),
    ("AU", "Mackay", "contractors"),
    ("AU", "Bundaberg", "clinics"),
    ("AU", "Wagga Wagga", "law firms"),
    ("AU", "Port Macquarie", "local tourism"),
    ("NZ", "Invercargill", "dentists"),
    ("NZ", "Whangarei", "beauty salons"),
    ("NZ", "New Plymouth", "contractors"),
    ("NZ", "Hastings", "law firms"),
    ("NZ", "Blenheim", "local tourism"),
    ("NZ", "Timaru", "dentists"),
    ("CA", "Nanaimo", "dentists"),
    ("CA", "Peterborough", "law firms"),
    ("CA", "Kamloops", "beauty salons"),
    ("CA", "Red Deer", "contractors"),
    ("CA", "Sherbrooke", "dentists"),
    ("CA", "Fredericton", "law firms"),
    ("CA", "Charlottetown", "local tourism"),
    ("CA", "Belleville", "beauty salons"),
    ("IE", "Killarney", "local tourism"),
    ("IE", "Tralee", "dentists"),
    ("IE", "Ennis", "beauty salons"),
    ("IE", "Athlone", "contractors"),
    ("IE", "Mullingar", "law firms"),
    ("IE", "Bray", "dentists"),
]

FIRST_TIER_TARGETS: list[dict[str, Any]] = [
    {"country": country, "city": city, "language": "en", "niche": niche, "priority": 100 - index}
    for index, (country, city, niche) in enumerate(FIRST_TIER_MARKETS)
]

SECONDARY_TEST_TARGETS: list[dict[str, Any]] = [
    {"country": "IL", "city": "Tel Aviv", "language": "he", "niche": "dentists", "priority": 45},
    {"country": "EE", "city": "Tallinn", "language": "en", "niche": "dentists", "priority": 40},
]

STOCKPILE_EXPANSION_MARKETS: list[tuple[str, str, str]] = [
    ("IE", "Dingle", "local tourism"),
    ("IE", "Westport", "local tourism"),
    ("IE", "Kenmare", "local tourism"),
    ("IE", "Clifden", "local tourism"),
    ("IE", "Doolin", "local tourism"),
    ("IE", "Lahinch", "local tourism"),
    ("IE", "Naas", "dentists"),
    ("IE", "Carlow", "dentists"),
    ("IE", "Letterkenny", "dentists"),
    ("US", "Athens", "dentists"),
    ("US", "Flagstaff", "dentists"),
    ("US", "Salem", "dentists"),
    ("US", "Missoula", "dentists"),
    ("US", "Gainesville", "law firms"),
    ("US", "Columbia", "law firms"),
    ("US", "Roanoke", "law firms"),
    ("UK", "Durham", "dentists"),
    ("UK", "Worcester", "dentists"),
    ("UK", "Shrewsbury", "dentists"),
    ("UK", "Salisbury", "dentists"),
    ("UK", "St Albans", "law firms"),
    ("CA", "Waterloo", "dentists"),
    ("CA", "Lethbridge", "dentists"),
    ("CA", "Medicine Hat", "dentists"),
]

STOCKPILE_EXPANSION_TARGETS: list[dict[str, Any]] = [
    {"country": country, "city": city, "language": "en", "niche": niche, "priority": 120 - index}
    for index, (country, city, niche) in enumerate(STOCKPILE_EXPANSION_MARKETS)
]

NICHE_EXPANSION_PRIORITY = {
    "dentists": 18,
    "law firms": 16,
    "clinics": 14,
    "contractors": 12,
    "private courses/schools": 10,
    "beauty salons": 9,
    "local tourism": 7,
}


def lead_discovery_target_plan(include_secondary: bool = False) -> dict[str, Any]:
    targets = [*FIRST_TIER_TARGETS, *(SECONDARY_TEST_TARGETS if include_secondary else [])]
    return {
        "status": "ready",
        "primary_tier": "US_UK_AU_NZ_CA_IE",
        "default_target": FIRST_TIER_TARGETS[0],
        "target_count": len(targets),
        "targets": sorted(targets, key=lambda row: int(row["priority"]), reverse=True),
        "depth_strategy": "regional_and_secondary_cities_first",
        "first_tier_market_count": len(FIRST_TIER_TARGETS),
        "secondary_targets_included": include_secondary,
        "israel_is_secondary_local_only": True,
        "estonia_is_secondary_test_only": True,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def _overpass_query(country: str, city: str, niche: str, limit: int) -> str:
    country_code = COUNTRY_AREA_CODES.get(country.upper(), country.upper())
    area_name = CITY_AREAS.get((country.upper(), city.strip().lower()), city.strip())
    tags = NICHE_TAGS.get(niche, [])
    if not area_name or not tags:
        raise ValueError("unsupported_overpass_source")
    selectors = []
    for key, value in tags:
        selectors.append(f'node["{key}"="{value}"](area.searchArea);')
        selectors.append(f'way["{key}"="{value}"](area.searchArea);')
        selectors.append(f'relation["{key}"="{value}"](area.searchArea);')
    body = "\n  ".join(selectors)
    return f"""
[out:json][timeout:25];
area["ISO3166-1"="{country_code}"][admin_level=2]->.countryArea;
(
  area["name"="{area_name}"](area.countryArea);
  area["name"="{area_name}"];
)->.searchArea;
(
  {body}
);
out center tags {max(1, min(int(limit or 50), 100))};
""".strip()


def _fetch_overpass(query: str) -> dict[str, Any]:
    body = f"data={quote(query)}".encode("utf-8")
    last_error: Exception | None = None
    for url in OVERPASS_URLS:
        request = Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "VoiddoRescue/1.0 public-safe-lead-discovery"})
        try:
            with urlopen(request, timeout=35) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"overpass_unavailable:{type(last_error).__name__ if last_error else 'unknown'}")


def _element_to_row(element: dict[str, Any], country: str, city: str, language: str, niche: str) -> dict[str, str] | None:
    tags = element.get("tags") or {}
    name = tags.get("name") or tags.get("operator") or ""
    website = tags.get("website") or tags.get("contact:website") or tags.get("url") or ""
    email = tags.get("email") or tags.get("contact:email") or ""
    phone = tags.get("phone") or tags.get("contact:phone") or ""
    if not website:
        return None
    source_url = f"https://www.openstreetmap.org/{element.get('type', 'node')}/{element.get('id')}"
    confidence = 88 if email else 76
    return {
        "business_name": name or website,
        "website_url": website_url_for(website),
        "email": email.lower(),
        "phone": phone,
        "country": country.upper(),
        "city": city,
        "language": language,
        "niche": niche,
        "source_url": source_url,
        "confidence": str(confidence),
    }


def _rows_to_csv(rows: list[dict[str, str]]) -> str:
    output = io.StringIO()
    fieldnames = ["business_name", "website_url", "email", "phone", "country", "city", "language", "niche", "source_url", "confidence"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return output.getvalue()


def overpass_lead_discovery(
    country: str = "US",
    city: str = "Boise",
    niche: str = "dentists",
    language: str = "en",
    limit: int = 50,
    dry_run: bool = True,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 50), 100))
    query = _overpass_query(country, city, niche, safe_limit)
    if dry_run:
        return {
            "status": "dry_run",
            "source_type": "overpass_osm_public_poi",
            "country": country.upper(),
            "city": city,
            "niche": niche,
            "language": language,
            "limit": safe_limit,
            "query_preview": query[:500],
            "created_source": False,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    payload = _fetch_overpass(query)
    rows = []
    seen_sites: set[str] = set()
    for element in payload.get("elements") or []:
        row = _element_to_row(element, country, city, language, niche)
        if not row:
            continue
        site_key = row["website_url"].lower().rstrip("/")
        if site_key in seen_sites:
            continue
        seen_sites.add(site_key)
        rows.append(row)
        if len(rows) >= safe_limit:
            break
    csv_text = _rows_to_csv(rows)
    source_status = "preflight_ready" if rows else "no_rows_public_source"
    source = create_scout_source(
        {
            "name": f"overpass-{country.upper()}-{city}-{niche}",
            "source_type": "business_directory_import_scout",
            "country": country.upper(),
            "language": language,
            "niche": niche,
            "status": source_status,
            "config_json": {
                "csv": csv_text,
                "source": "overpass_osm_public_poi",
                "discovery_result": "rows_found" if rows else "no_public_rows_found",
            },
        }
    )
    readiness = run_scout_source_readiness(str(source["id"]))
    return {
        "status": "source_created" if rows else "empty_source_recorded",
        "source_id": str(source["id"]),
        "source_name": source["name"],
        "source_status": source_status,
        "country": country.upper(),
        "city": city,
        "niche": niche,
        "language": language,
        "found_count": len(rows),
        "with_email_count": len([row for row in rows if row.get("email")]),
        "with_website_count": len([row for row in rows if row.get("website_url")]),
        "readiness": {
            "status": readiness["status"],
            "score": readiness["score"],
            "allowed_for_scout_run": readiness["allowed_for_scout_run"],
            "issue_count": len(readiness.get("issues") or []),
        },
        "created_scout_runs": 0,
        "created_scanner_jobs": 0,
        "empty_target_recorded": not bool(rows),
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def regional_lead_discovery_cycle(limit_targets: int = 2, per_target_limit: int = 30, dry_run: bool = True) -> dict[str, Any]:
    safe_target_limit = max(1, min(int(limit_targets or 2), 8))
    safe_per_target_limit = max(1, min(int(per_target_limit or 30), 50))
    existing_rows = fetch_all("SELECT name FROM scout_sources WHERE name LIKE %s", ("overpass-%",))
    existing = {str(row["name"]) for row in existing_rows}
    targets = []
    for target in lead_discovery_target_plan(False)["targets"]:
        source_name = f"overpass-{target['country'].upper()}-{target['city']}-{target['niche']}"
        if source_name in existing:
            continue
        targets.append({**target, "source_name": source_name})
        if len(targets) >= safe_target_limit:
            break

    if dry_run:
        return {
            "status": "dry_run",
            "selected_count": len(targets),
            "targets": targets,
            "created_sources": 0,
            "found_count": 0,
            "with_email_count": 0,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }

    created = []
    errors = []
    for target in targets:
        try:
            result = overpass_lead_discovery(
                target["country"],
                target["city"],
                target["niche"],
                target["language"],
                safe_per_target_limit,
                dry_run=False,
            )
            created.append(result)
        except Exception as exc:
            errors.append({"country": target["country"], "city": target["city"], "niche": target["niche"], "error": type(exc).__name__})
    return {
        "status": "completed" if created or not errors else "failed",
        "selected_count": len(targets),
        "created_sources": len([item for item in created if item.get("source_id")]),
        "non_empty_sources": len([item for item in created if item.get("status") == "source_created"]),
        "empty_sources": len([item for item in created if item.get("status") == "empty_source_recorded"]),
        "found_count": sum(int(item.get("found_count", 0)) for item in created),
        "with_email_count": sum(int(item.get("with_email_count", 0)) for item in created),
        "errors": errors,
        "targets": [{"country": item["country"], "city": item["city"], "niche": item["niche"], "language": item["language"]} for item in targets],
        "results": [
            {
                "source_id": item.get("source_id"),
                "country": item.get("country"),
                "city": item.get("city"),
                "niche": item.get("niche"),
                "found_count": item.get("found_count", 0),
                "with_email_count": item.get("with_email_count", 0),
                "readiness": item.get("readiness", {}),
                "source_status": item.get("source_status"),
            }
            for item in created
        ],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def performance_guided_target_plan(limit_targets: int = 5) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit_targets or 5), 20))
    latest_performance = fetch_all(
        """
        WITH latest AS (
          SELECT DISTINCT ON (source_id)
            source_id, status, qualified_count, qualified_rate, average_final_score,
            email_coverage, issue_signal_rate, recommendation, created_at
          FROM scout_source_performance_scores
          WHERE source_id IS NOT NULL
          ORDER BY source_id, created_at DESC
        )
        SELECT ss.name, ss.country, ss.niche, ss.language, latest.*
        FROM latest
        JOIN scout_sources ss ON ss.id = latest.source_id
        WHERE latest.recommendation IN ('PROMOTE_SOURCE_FOR_MORE_SCOUTING', 'KEEP_TESTING_WITH_SMALL_BATCHES')
          AND latest.qualified_count > 0
          AND upper(COALESCE(ss.country, '')) !~ %s
        ORDER BY
          CASE latest.recommendation WHEN 'PROMOTE_SOURCE_FOR_MORE_SCOUTING' THEN 0 ELSE 1 END,
          CASE WHEN latest.email_coverage > 0 THEN 0 ELSE 1 END,
          latest.email_coverage DESC,
          latest.qualified_rate DESC,
          latest.average_final_score DESC,
          latest.created_at DESC
        LIMIT 25
        """,
        (TEST_COUNTRY_PATTERN,),
    )
    existing_source_names = {str(row["name"]) for row in fetch_all("SELECT name FROM scout_sources WHERE name LIKE %s", ("overpass-%",))}
    selected: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for perf in latest_performance:
        country = str(perf.get("country") or "").upper()
        niche = str(perf.get("niche") or "")
        language = str(perf.get("language") or "en")
        for target in lead_discovery_target_plan(False)["targets"]:
            if target["country"].upper() != country or target["niche"] != niche:
                continue
            source_name = f"overpass-{target['country'].upper()}-{target['city']}-{target['niche']}"
            if source_name in existing_source_names or source_name in seen_names:
                continue
            selected.append(
                {
                    **target,
                    "language": target.get("language") or language,
                    "source_name": source_name,
                    "guidance": {
                        "source_id": str(perf["source_id"]),
                        "source_name": perf["name"],
                        "recommendation": perf["recommendation"],
                        "qualified_count": int(perf["qualified_count"] or 0),
                        "qualified_rate": float(perf["qualified_rate"] or 0),
                        "average_final_score": float(perf["average_final_score"] or 0),
                        "email_coverage": float(perf["email_coverage"] or 0),
                        "issue_signal_rate": float(perf["issue_signal_rate"] or 0),
                    },
                }
            )
            seen_names.add(source_name)
            if len(selected) >= safe_limit:
                break
        if len(selected) >= safe_limit:
            break
    return {
        "status": "ready" if selected else "no_guided_targets",
        "selected_count": len(selected),
        "targets": selected,
        "guidance_sources_checked": len(latest_performance),
        "strategy": "promote_country_niche_pairs_with_real_qualified_scan_yield_and_email_coverage_first",
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def performance_guided_regional_discovery_cycle(limit_targets: int = 3, per_target_limit: int = 30, dry_run: bool = True) -> dict[str, Any]:
    safe_target_limit = max(1, min(int(limit_targets or 3), 8))
    safe_per_target_limit = max(1, min(int(per_target_limit or 30), 50))
    plan = performance_guided_target_plan(safe_target_limit)
    targets = plan["targets"]
    if dry_run or not targets:
        return {
            "status": "dry_run" if dry_run else "no_guided_targets",
            "selected_count": len(targets),
            "targets": targets,
            "created_sources": 0,
            "found_count": 0,
            "with_email_count": 0,
            "plan": plan,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }

    created = []
    errors = []
    for target in targets:
        try:
            result = overpass_lead_discovery(
                target["country"],
                target["city"],
                target["niche"],
                target.get("language") or "en",
                safe_per_target_limit,
                dry_run=False,
            )
            created.append(result)
        except Exception as exc:
            errors.append({"country": target["country"], "city": target["city"], "niche": target["niche"], "error": type(exc).__name__})
    return {
        "status": "completed" if created or not errors else "failed",
        "selected_count": len(targets),
        "created_sources": len([item for item in created if item.get("source_id")]),
        "non_empty_sources": len([item for item in created if item.get("status") == "source_created"]),
        "empty_sources": len([item for item in created if item.get("status") == "empty_source_recorded"]),
        "found_count": sum(int(item.get("found_count", 0)) for item in created),
        "with_email_count": sum(int(item.get("with_email_count", 0)) for item in created),
        "errors": errors,
        "targets": [{"country": item["country"], "city": item["city"], "niche": item["niche"], "language": item["language"], "guidance": item.get("guidance", {})} for item in targets],
        "results": [
            {
                "source_id": item.get("source_id"),
                "country": item.get("country"),
                "city": item.get("city"),
                "niche": item.get("niche"),
                "found_count": item.get("found_count", 0),
                "with_email_count": item.get("with_email_count", 0),
                "readiness": item.get("readiness", {}),
                "source_status": item.get("source_status"),
            }
            for item in created
        ],
        "plan": {key: value for key, value in plan.items() if key != "targets"},
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def stockpile_expansion_target_plan(limit_targets: int = 5) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit_targets or 5), 12))
    existing_source_names = {str(row["name"]) for row in fetch_all("SELECT name FROM scout_sources WHERE name LIKE %s", ("overpass-%",))}
    proven_segments = fetch_all(
        """
        WITH latest_reviews AS (
          SELECT DISTINCT ON (campaign_lead_id) campaign_lead_id, action
          FROM campaign_preview_reviews
          ORDER BY campaign_lead_id, created_at DESC
        )
        SELECT c.country, c.niche, count(*) AS approved_count, avg(cl.score) AS average_score
        FROM campaign_leads cl
        JOIN campaigns c ON c.id = cl.campaign_id
        JOIN latest_reviews lr ON lr.campaign_lead_id = cl.id AND lr.action = 'approved'
        WHERE cl.status = 'preview'
          AND c.status IN ('draft', 'preview_ready')
          AND upper(COALESCE(c.country, '')) !~ %s
        GROUP BY c.country, c.niche
        """,
        (TEST_COUNTRY_PATTERN,),
    )
    performance_rows = fetch_all(
        """
        WITH latest AS (
          SELECT DISTINCT ON (source_id)
            source_id, recommendation, qualified_rate, average_final_score,
            email_coverage, issue_signal_rate, created_at
          FROM scout_source_performance_scores
          WHERE source_id IS NOT NULL
          ORDER BY source_id, created_at DESC
        )
        SELECT
          ss.country,
          ss.niche,
          count(*) AS source_count,
          avg(latest.qualified_rate) AS qualified_rate,
          avg(latest.average_final_score) AS average_final_score,
          avg(latest.email_coverage) AS email_coverage,
          avg(latest.issue_signal_rate) AS issue_signal_rate,
          count(*) FILTER (WHERE latest.recommendation = 'PROMOTE_SOURCE_FOR_MORE_SCOUTING') AS promote_count,
          count(*) FILTER (WHERE latest.recommendation = 'PAUSE_SOURCE_UNTIL_REVIEW') AS pause_count
        FROM latest
        JOIN scout_sources ss ON ss.id = latest.source_id
        WHERE upper(COALESCE(ss.country, '')) !~ %s
        GROUP BY ss.country, ss.niche
        """,
        (TEST_COUNTRY_PATTERN,),
    )
    segment_scores = {
        (str(row["country"] or "").upper(), str(row["niche"] or "")): {
            "approved_count": int(row["approved_count"] or 0),
            "average_score": float(row["average_score"] or 0),
        }
        for row in proven_segments
    }
    performance = {
        (str(row["country"] or "").upper(), str(row["niche"] or "")): {
            "source_count": int(row["source_count"] or 0),
            "qualified_rate": float(row["qualified_rate"] or 0),
            "average_final_score": float(row["average_final_score"] or 0),
            "email_coverage": float(row["email_coverage"] or 0),
            "issue_signal_rate": float(row["issue_signal_rate"] or 0),
            "promote_count": int(row["promote_count"] or 0),
            "pause_count": int(row["pause_count"] or 0),
        }
        for row in performance_rows
    }
    candidates: list[dict[str, Any]] = []
    for target in STOCKPILE_EXPANSION_TARGETS:
        key = (target["country"].upper(), target["niche"])
        source_name = f"overpass-{target['country'].upper()}-{target['city']}-{target['niche']}"
        if source_name in existing_source_names:
            continue
        segment = segment_scores.get(key)
        if not segment:
            continue
        perf = performance.get(
            key,
            {
                "source_count": 0,
                "qualified_rate": 0.0,
                "average_final_score": 0.0,
                "email_coverage": 0.0,
                "issue_signal_rate": 0.0,
                "promote_count": 0,
                "pause_count": 0,
            },
        )
        if perf["source_count"] >= 3 and perf["pause_count"] > perf["promote_count"] and perf["qualified_rate"] < 0.08:
            continue
        expansion_score = round(
            (segment["approved_count"] * 8)
            + (segment["average_score"] * 0.35)
            + (perf["qualified_rate"] * 90)
            + (perf["email_coverage"] * 35)
            + (perf["issue_signal_rate"] * 25)
            + NICHE_EXPANSION_PRIORITY.get(target["niche"], 5)
            + (target.get("priority", 0) * 0.05)
            - (perf["pause_count"] * 1.5),
            2,
        )
        candidates.append(
            {
                **target,
                "source_name": source_name,
                "expansion_score": expansion_score,
                "guidance": {
                    "strategy": "expand_segments_with_existing_approved_preview_yield",
                    "approved_count": segment["approved_count"],
                    "average_score": segment["average_score"],
                    "source_performance": perf,
                },
            }
        )
    candidates.sort(
        key=lambda item: (
            item["expansion_score"],
            item["guidance"]["source_performance"]["email_coverage"],
            item["guidance"]["source_performance"]["qualified_rate"],
            NICHE_EXPANSION_PRIORITY.get(item["niche"], 0),
            item.get("priority", 0),
        ),
        reverse=True,
    )
    selected = candidates[:safe_limit]
    return {
        "status": "ready" if selected else "no_stockpile_expansion_targets",
        "selected_count": len(selected),
        "targets": selected,
        "proven_segment_count": len(segment_scores),
        "performance_segment_count": len(performance),
        "strategy": "quality_aware_stockpile_expansion_ranked_by_approved_preview_yield_email_coverage_and_issue_signal",
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def stockpile_expansion_discovery_cycle(limit_targets: int = 3, per_target_limit: int = 35, dry_run: bool = True) -> dict[str, Any]:
    safe_target_limit = max(1, min(int(limit_targets or 3), 8))
    safe_per_target_limit = max(1, min(int(per_target_limit or 35), 50))
    plan = stockpile_expansion_target_plan(safe_target_limit)
    targets = plan["targets"]
    if dry_run or not targets:
        return {
            "status": "dry_run" if dry_run else "no_stockpile_expansion_targets",
            "selected_count": len(targets),
            "targets": targets,
            "created_sources": 0,
            "found_count": 0,
            "with_email_count": 0,
            "plan": plan,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    created = []
    errors = []
    for target in targets:
        try:
            created.append(
                overpass_lead_discovery(
                    target["country"],
                    target["city"],
                    target["niche"],
                    target.get("language") or "en",
                    safe_per_target_limit,
                    dry_run=False,
                )
            )
        except Exception as exc:
            errors.append({"country": target["country"], "city": target["city"], "niche": target["niche"], "error": type(exc).__name__})
    return {
        "status": "completed" if created or not errors else "failed",
        "selected_count": len(targets),
        "created_sources": len([item for item in created if item.get("source_id")]),
        "non_empty_sources": len([item for item in created if item.get("status") == "source_created"]),
        "empty_sources": len([item for item in created if item.get("status") == "empty_source_recorded"]),
        "found_count": sum(int(item.get("found_count", 0)) for item in created),
        "with_email_count": sum(int(item.get("with_email_count", 0)) for item in created),
        "errors": errors,
        "targets": [{"country": item["country"], "city": item["city"], "niche": item["niche"], "language": item["language"], "guidance": item.get("guidance", {})} for item in targets],
        "results": [
            {
                "source_id": item.get("source_id"),
                "country": item.get("country"),
                "city": item.get("city"),
                "niche": item.get("niche"),
                "found_count": item.get("found_count", 0),
                "with_email_count": item.get("with_email_count", 0),
                "readiness": item.get("readiness", {}),
                "source_status": item.get("source_status"),
            }
            for item in created
        ],
        "plan": {key: value for key, value in plan.items() if key != "targets"},
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
