from __future__ import annotations

import csv
from io import StringIO
from urllib.parse import urlparse


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    return (parsed.netloc or parsed.path).removeprefix("www.").split("/")[0]


def domain_list_to_csv(text: str, country: str = "", niche: str = "", language: str = "en") -> str:
    rows = ["business_name,website_url,email,country,city,language,niche,source_url"]
    seen: set[str] = set()
    for raw in text.replace(",", "\n").splitlines():
        domain = normalize_domain(raw)
        if not domain or domain in seen:
            continue
        seen.add(domain)
        rows.append(f"{domain},https://{domain},,{country},,{language},{niche},domain_list")
    return "\n".join(rows)


def directory_rows_to_csv(text: str, country: str = "", niche: str = "", language: str = "en") -> str:
    reader = csv.DictReader(StringIO(text))
    rows = ["business_name,website_url,email,country,city,language,niche,source_url"]
    for row in reader:
        website = row.get("website_url") or row.get("website") or row.get("url") or ""
        domain = normalize_domain(website)
        if not domain:
            continue
        name = (row.get("business_name") or row.get("name") or domain).replace(",", " ")
        email = (row.get("email") or "").strip().lower()
        city = (row.get("city") or "").replace(",", " ")
        source = (row.get("source_url") or row.get("source") or "directory_import").replace(",", "%2C")
        rows.append(f"{name},https://{domain},{email},{country},{city},{language},{niche},{source}")
    return "\n".join(rows)
