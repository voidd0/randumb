from __future__ import annotations

from typing import Any
import uuid

from psycopg.types.json import Jsonb

from .db import execute
from .lead_scoring import score_lead
from .scouts import create_campaign, prepare_campaign


def run_synthetic_lead_simulation(count: int = 100, country: str = "EE", niche: str = "dentists", product_key: str = "contact_form_repair") -> dict[str, Any]:
    count = max(1, min(count, 250))
    token = uuid.uuid4().hex[:10]
    sim = execute(
        "INSERT INTO revenue_simulation_runs(status, lead_count, result_json) VALUES ('running', %s, %s) RETURNING *",
        (count, Jsonb({"token": token, "country": country, "niche": niche, "product_key": product_key})),
    )
    accepted = 0
    scanner_jobs = 0
    audits = 0
    for i in range(count):
        domain = f"sim-{token}-{i}.example.test"
        business = execute(
            """
            INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
            VALUES (%s, %s, 'Synthetic City', 'en', %s, 'p7_simulation', %s, %s, %s, 'scouted')
            RETURNING id
            """,
            (f"Simulated Business {i}", country, niche, f"https://{domain}", domain, f"owner@{domain}"),
        )
        lead = execute(
            """
            INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
            VALUES (%s, %s, 'p7_simulation', 'scouted', 80, 'en', %s, 'Synthetic City', %s)
            RETURNING id
            """,
            (business["id"], f"owner@{domain}", country, niche),
        )
        job = execute(
            "INSERT INTO scanner_jobs(url, business_name, status, dry_run, result_json) VALUES (%s, %s, 'queued', true, %s) RETURNING id",
            (f"https://{domain}", f"Simulated Business {i}", Jsonb({"simulation_id": str(sim["id"])})),
        )
        audit = execute(
            """
            INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
            VALUES (%s, %s, %s, %s, 'completed', 74, 'Contact path may be weak on mobile.', %s, now())
            RETURNING id
            """,
            (business["id"], lead["id"], domain, f"https://{domain}", f"sim-{token}-{i}"),
        )
        execute(
            """
            INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
            VALUES (%s, 'contact_path', 'high', 'Contact path may be weak', 'The public mobile page may not present a clear enquiry path.', 'Review the mobile CTA and contact path.')
            """,
            (audit["id"],),
        )
        score_lead(str(lead["id"]), str(audit["id"]))
        execute("UPDATE leads SET score = 88 WHERE id = %s", (lead["id"],))
        execute("UPDATE lead_scores SET final_score = 88 WHERE lead_id = %s AND audit_id = %s", (lead["id"], audit["id"]))
        accepted += 1
        scanner_jobs += 1
        audits += 1
    campaign = create_campaign({"name": f"P7 synthetic {token}", "country": country, "language": "en", "niche": niche, "offer_key": product_key})
    preview = prepare_campaign(str(campaign["id"]), threshold=70, limit=min(50, count))
    done = execute(
        """
        UPDATE revenue_simulation_runs
        SET status = 'completed', accepted_count = %s, scanner_jobs_count = %s, audits_count = %s,
            campaign_id = %s, result_json = %s
        WHERE id = %s
        RETURNING *
        """,
        (accepted, scanner_jobs, audits, campaign["id"], Jsonb({"token": token, "campaign_preview": preview}), sim["id"]),
    )
    return dict(done)
