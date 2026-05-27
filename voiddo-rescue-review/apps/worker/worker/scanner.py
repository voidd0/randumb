from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
import hashlib
import json
import time

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


@dataclass
class SafeIssue:
    issue_type: str
    severity: str
    title: str
    public_text: str
    recommendation: str
    evidence_json: dict = field(default_factory=dict)


def _slug(url: str) -> str:
    parsed = urlparse(url)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{parsed.netloc.lower().replace('www.', '').replace('.', '-')}-{digest}"


def _issue_score(issues: list[SafeIssue]) -> int:
    weights = {"critical": 45, "high": 30, "medium": 15, "low": 5}
    return max(0, 100 - sum(weights.get(issue.severity, 5) for issue in issues))


def _mailto_addresses(links: list[str]) -> list[str]:
    addresses: list[str] = []
    seen: set[str] = set()
    for href in links:
        if not href.startswith("mailto:"):
            continue
        address = unquote(href.split(":", 1)[1].split("?", 1)[0]).strip().lower()
        if "@" not in address or address in seen:
            continue
        seen.add(address)
        addresses.append(address)
    return addresses[:5]


def safe_public_scan(url: str, storage_root: str, timeout_ms: int = 15000) -> dict:
    """Run public, non-invasive homepage checks only."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("scanner accepts only http/https URLs")

    slug = _slug(url)
    out_dir = Path(storage_root) / "audits" / slug
    shot_dir = Path(storage_root) / "screenshots" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    shot_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    issues: list[SafeIssue] = []
    screenshots = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            status = response.status if response else 0
            page.wait_for_timeout(800)
            desktop_path = shot_dir / "desktop.png"
            page.screenshot(path=str(desktop_path), full_page=True)
            screenshots.append({"type": "desktop", "file_path": str(desktop_path), "viewport": "1440x1100"})

            mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
            mobile.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            mobile.wait_for_timeout(800)
            mobile_path = shot_dir / "mobile.png"
            mobile.screenshot(path=str(mobile_path), full_page=True)
            screenshots.append({"type": "mobile", "file_path": str(mobile_path), "viewport": "390x844"})

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            title = (soup.title.string or "").strip() if soup.title else ""
            meta = soup.find("meta", attrs={"name": "description"})
            meta_description = (meta.get("content") or "").strip() if meta else ""
            h1 = [node.get_text(" ", strip=True) for node in soup.find_all("h1")]
            links = [a.get("href") for a in soup.find_all("a") if a.get("href")]
            mailto = [href for href in links if href.startswith("mailto:")]
            mailto_emails = _mailto_addresses(links)
            tel = [href for href in links if href.startswith("tel:")]
            whatsapp = [href for href in links if "wa.me/" in href or "whatsapp" in href.lower()]
            booking = [href for href in links if any(word in href.lower() for word in ["book", "calendly", "appointment"])]
            forms = soup.find_all("form")

            if status >= 500 or status == 0:
                issues.append(SafeIssue("availability", "critical", "Homepage may be unavailable", "The homepage did not return a usable public browser response.", "Check hosting, DNS, and server health.", {"status": status}))
            if parsed.scheme != "https":
                issues.append(SafeIssue("https", "critical", "Site is not loaded over HTTPS", "The public URL uses HTTP rather than HTTPS.", "Redirect all public pages to HTTPS.", {}))
            if not title:
                issues.append(SafeIssue("metadata", "medium", "Missing page title", "The homepage does not expose a clear browser title.", "Add a specific page title for search and browser tabs.", {}))
            if not meta_description:
                issues.append(SafeIssue("metadata", "medium", "Missing meta description", "The homepage may not control its search snippet.", "Add a concise meta description for the main service and location.", {}))
            if not h1:
                issues.append(SafeIssue("content", "medium", "Missing visible H1", "The public check could not find a main page heading.", "Add one clear H1 that states the service and location.", {}))
            if not forms and not (mailto or tel or whatsapp or booking):
                issues.append(SafeIssue("contact_path", "high", "No obvious enquiry path found", "The homepage does not expose a form, email, phone, WhatsApp, or booking link in public HTML.", "Add a prominent contact path above the fold and in the footer.", {}))

            robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
            sitemap_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/sitemap.xml")

            result = {
                "domain": parsed.netloc.lower(),
                "url": url,
                "status": "completed",
                "http_status": status,
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "title": title,
                "meta_description": meta_description,
                "h1": h1[:3],
                "counts": {
                    "links": len(links),
                    "forms": len(forms),
                    "mailto": len(mailto),
                    "tel": len(tel),
                    "whatsapp": len(whatsapp),
                    "booking": len(booking),
                },
                "contact_evidence": {
                    "mailto_emails": mailto_emails,
                    "has_phone_link": bool(tel),
                    "has_whatsapp_link": bool(whatsapp),
                    "has_booking_link": bool(booking),
                    "has_form": bool(forms),
                },
                "public_slug": slug,
                "score": _issue_score(issues),
                "issues": [issue.__dict__ for issue in issues],
                "screenshots": screenshots,
                "robots_url": robots_url,
                "sitemap_url": sitemap_url,
                "safe_scan": True,
            }
            (out_dir / "audit.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
            return result
        finally:
            browser.close()
