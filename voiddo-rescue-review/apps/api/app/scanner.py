from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from .models import Issue, ScanResult


def slug_for_url(url: str) -> str:
    parsed = urlparse(url)
    base = parsed.netloc or parsed.path
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    clean = base.lower().replace("www.", "").replace(".", "-").replace(":", "-")
    return f"{clean}-{digest}"


def score_issues(issues: list[Issue]) -> int:
    penalty = 0
    weights = {"critical": 45, "high": 30, "medium": 15, "low": 5}
    for issue in issues:
        penalty += weights.get(issue.severity, 5)
    return max(0, min(100, 100 - penalty))


def deterministic_safe_scan(url: str, business_name: str | None = None) -> ScanResult:
    """Non-invasive placeholder scanner for API tests and dry-run demos.

    The worker contains the Playwright implementation; this function gives the API a
    deterministic dry-run path without touching external websites.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    issues = [
        Issue(
            issue_type="contact_signal",
            severity="high",
            title="Contact path needs verification",
            public_text="The public check could not confirm a reliable enquiry path in this dry run.",
            recommendation="Verify contact form, phone, email, WhatsApp, or booking CTA from the homepage.",
            evidence_json={"mode": "dry_run", "url": url},
        ),
        Issue(
            issue_type="metadata",
            severity="medium",
            title="Search snippet may be incomplete",
            public_text="The public check should verify title and meta description before outreach.",
            recommendation="Add a clear title and meta description tied to the business service and location.",
            evidence_json={"mode": "dry_run"},
        ),
    ]
    score = score_issues(issues)
    return ScanResult(
        domain=domain,
        url=url,
        score=score,
        status="dry_run",
        summary=f"Dry-run public website check for {business_name or domain}.",
        public_slug=slug_for_url(url),
        issues=issues,
    )
