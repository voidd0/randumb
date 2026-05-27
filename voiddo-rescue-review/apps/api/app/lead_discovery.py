from __future__ import annotations

import csv
import io
import json
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from .db import fetch_all
from .scouts import create_scout_source, run_scout_source_readiness, website_url_for


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
]

FIRST_TIER_TARGETS: list[dict[str, Any]] = [
    {"country": country, "city": city, "language": "en", "niche": niche, "priority": 100 - index}
    for index, (country, city, niche) in enumerate(FIRST_TIER_MARKETS)
]

SECONDARY_TEST_TARGETS: list[dict[str, Any]] = [
    {"country": "IL", "city": "Tel Aviv", "language": "he", "niche": "dentists", "priority": 45},
    {"country": "EE", "city": "Tallinn", "language": "en", "niche": "dentists", "priority": 40},
]


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
    source = create_scout_source(
        {
            "name": f"overpass-{country.upper()}-{city}-{niche}",
            "source_type": "business_directory_import_scout",
            "country": country.upper(),
            "language": language,
            "niche": niche,
            "status": "preflight_ready",
            "config_json": {"csv": csv_text, "source": "overpass_osm_public_poi"},
        }
    )
    readiness = run_scout_source_readiness(str(source["id"]))
    return {
        "status": "source_created",
        "source_id": str(source["id"]),
        "source_name": source["name"],
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
        "created_sources": len([item for item in created if item.get("status") == "source_created"]),
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
            }
            for item in created
        ],
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
