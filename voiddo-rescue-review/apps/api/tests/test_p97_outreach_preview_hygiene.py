from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb

from app.db import execute, fetch_one
from app.p0 import prepare_outreach_preview, queue_outreach_preview, suppress_unsubscribe_token


def _cleanup(token: str) -> None:
    execute("DELETE FROM outreach_messages WHERE body LIKE %s OR subject LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM outreach_preview_batches WHERE preview_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM suppression_list WHERE email LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaign_preview_reviews WHERE campaign_lead_id IN (SELECT id FROM campaign_leads WHERE preview_json::text LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaign_leads WHERE preview_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))
    execute("DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",))
    execute("DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%"))


def _preview_candidate(token: str, approved: bool = True, source: str = "qa97_fixture") -> tuple[str, str]:
    domain = f"qa97-{token}.clinic"
    email = f"owner-{token}@{domain}"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, 'US', 'Control City', 'en', 'dentists', %s, %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"QA97 Clinic {token}", source, f"https://{domain}", domain, email),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, %s, 'scouted', 91, 'en', 'US', 'Control City', 'dentists')
        RETURNING id
        """,
        (business["id"], email, source),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 68, 'Contact path may be unclear from a public browser session.', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", f"qa97-{token}"),
    )
    execute(
        """
        INSERT INTO lead_scores(lead_id, audit_id, technical_score, sales_score, urgency_score, value_score, deliverability_score, final_score, reasoning_json)
        VALUES (%s, %s, 99, 99, 99, 99, 99, 99, '{}')
        """,
        (lead["id"], audit["id"]),
    )
    campaign = execute(
        """
        INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
        VALUES (%s, 'preview_ready', 'US', 'en', 'dentists', 'contact_form_repair', true)
        RETURNING id
        """,
        (f"QA97 Campaign {token}",),
    )
    campaign_lead = execute(
        """
        INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json)
        VALUES (%s, %s, %s, 'preview', 99, %s)
        RETURNING id
        """,
        (campaign["id"], lead["id"], audit["id"], Jsonb({"token": token})),
    )
    execute(
        """
        INSERT INTO campaign_preview_reviews(campaign_lead_id, action, reason, actor)
        VALUES (%s, %s, 'QA97 preview gate', 'campaign_preview_self_review_agent')
        """,
        (campaign_lead["id"], "approved" if approved else "held"),
    )
    return str(campaign_lead["id"]), email


def test_outreach_preview_uses_only_approved_campaign_rows_without_raw_email():
    approved_token = uuid.uuid4().hex[:8]
    held_token = uuid.uuid4().hex[:8]
    try:
        _preview_candidate(approved_token, approved=True)
        _, held_email = _preview_candidate(held_token, approved=False)
        result = prepare_outreach_preview(10)
        text = str(result)
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert result["raw_recipient_addresses_included"] is False
        assert f"qa97-{approved_token}.clinic" in text
        assert held_email not in text
        assert f"qa97-{held_token}.clinic" not in text
        assert "owner-" not in text
        assert all(item["source"] == "approved_campaign_preview" for item in result["preview_json"])
        assert all("email" not in item for item in result["preview_json"])
        item = next(row for row in result["preview_json"] if row["domain"] == f"qa97-{approved_token}.clinic")
        assert "/unsubscribe/preview" not in item["unsubscribe_url"]
        token = item["unsubscribe_url"].rsplit("/", 1)[-1]
        suppressed = suppress_unsubscribe_token(token)
        assert suppressed["suppressed"] is True
        assert suppressed["raw_recipient_addresses_included"] is False
        assert fetch_one("SELECT 1 FROM suppression_list WHERE domain = %s", (f"qa97-{approved_token}.clinic",))
    finally:
        _cleanup(approved_token)
        _cleanup(held_token)


def test_queue_outreach_preview_remains_dry_run_and_suppresses_raw_recipients():
    token = uuid.uuid4().hex[:8]
    preview_batch_id = ""
    try:
        _preview_candidate(token, approved=True)
        result = queue_outreach_preview(5)
        preview_batch_id = result["preview_batch_id"]
        assert result["created"] >= 1
        assert result["dry_run_only"] is True
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
        assert result["raw_recipient_addresses_included"] is False
    finally:
        if preview_batch_id:
            execute("DELETE FROM outreach_preview_batches WHERE id = %s", (preview_batch_id,))
        _cleanup(token)
