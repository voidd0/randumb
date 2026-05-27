from __future__ import annotations

import uuid
from typing import Any

from psycopg.types.json import Jsonb

from .campaign_preview_quality import campaign_preview_quality_pack
from .db import execute, fetch_one
from .customer_journey import customer_journey_snapshot
from .lead_scoring import score_lead
from .p0 import handle_paddle_event, json_safe
from .scouts import create_campaign, prepare_campaign


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def cleanup_buyer_journey_scenario(token: str) -> dict[str, Any]:
    deleted: dict[str, int] = {}
    statements = [
        ("outbound_mailer_decisions", "DELETE FROM outbound_mailer_decisions WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",)),
        ("public_language_gate_runs", "DELETE FROM public_language_gate_runs WHERE scope = 'campaign_preview_quality' AND created_at >= now() - interval '2 hours'", ()),
        ("mailer_send_ledger", "DELETE FROM mailer_send_ledger WHERE result_json::text LIKE %s OR gate_result_json::text LIKE %s", (f"%{token}%", f"%{token}%")),
        ("recipient_resolver_audit", "DELETE FROM recipient_resolver_audit WHERE customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%")),
        ("mailer_action_queue", "DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s OR payload_json->>'customer_id' IN (SELECT id::text FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%", f"%{token}%")),
        ("campaign_readiness_snapshots", "DELETE FROM campaign_readiness_snapshots WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",)),
        ("campaign_leads", "DELETE FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s) OR preview_json::text LIKE %s", (f"%{token}%", f"%{token}%")),
        ("campaigns", "DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",)),
        ("customer_journey_snapshots", "DELETE FROM customer_journey_snapshots WHERE customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%")),
        ("customer_access_tokens", "DELETE FROM customer_access_tokens WHERE customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%")),
        ("monitoring_runs", "DELETE FROM monitoring_runs WHERE monitoring_target_id IN (SELECT mt.id FROM monitoring_targets mt JOIN customers c ON c.id = mt.customer_id WHERE c.email LIKE %s OR c.paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%")),
        ("monitoring_targets", "DELETE FROM monitoring_targets WHERE customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%")),
        ("codex_tasks", "DELETE FROM codex_tasks WHERE input_json::text LIKE %s", (f"%{token}%",)),
        ("onboarding_tasks", "DELETE FROM onboarding_tasks WHERE payload_json::text LIKE %s OR customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%", f"%{token}%")),
        ("fix_requests", "DELETE FROM fix_requests WHERE evidence_json::text LIKE %s OR customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%", f"%{token}%")),
        ("payments", "DELETE FROM payments WHERE paddle_transaction_id LIKE %s OR customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%", f"%{token}%")),
        ("subscriptions", "DELETE FROM subscriptions WHERE paddle_subscription_id LIKE %s OR customer_id IN (SELECT id FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s)", (f"%{token}%", f"%{token}%", f"%{token}%")),
        ("customers", "DELETE FROM customers WHERE email LIKE %s OR paddle_customer_id LIKE %s", (f"%{token}%", f"%{token}%")),
        ("audit_strength_scores", "DELETE FROM audit_strength_scores WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",)),
        ("screenshots", "DELETE FROM screenshots WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",)),
        ("audit_issues", "DELETE FROM audit_issues WHERE audit_id IN (SELECT id FROM audits WHERE public_slug LIKE %s)", (f"%{token}%",)),
        ("lead_scores", "DELETE FROM lead_scores WHERE lead_id IN (SELECT id FROM leads WHERE email LIKE %s)", (f"%{token}%",)),
        ("audits", "DELETE FROM audits WHERE public_slug LIKE %s OR domain LIKE %s", (f"%{token}%", f"%{token}%")),
        ("leads", "DELETE FROM leads WHERE email LIKE %s", (f"%{token}%",)),
        ("businesses", "DELETE FROM businesses WHERE domain LIKE %s OR email LIKE %s", (f"%{token}%", f"%{token}%")),
        ("system_events", "DELETE FROM system_events WHERE payload_json::text LIKE %s AND type LIKE 'buyer_journey%%'", (f"%{token}%",)),
    ]
    for name, sql, params in statements:
        row = execute(sql + " RETURNING 1", params)
        deleted[name] = 1 if row else 0
    return {"token": token, "deleted_markers": deleted, "send_mail": False, "live_outreach_allowed": False}


def run_buyer_journey_scenario(cleanup: bool = True) -> dict[str, Any]:
    token = f"p62-{uuid.uuid4().hex[:10]}"
    domain = f"{token}.example.test"
    business = execute(
        """
        INSERT INTO businesses(name, country, city, language, niche, source, website_url, domain, email, status)
        VALUES (%s, 'QA', 'Scenario City', 'en', 'dentists', 'buyer_journey_scenario', %s, %s, %s, 'scouted')
        RETURNING id
        """,
        (f"Scenario Clinic {token}", f"https://{domain}", domain, f"owner-{token}@{domain}"),
    )
    lead = execute(
        """
        INSERT INTO leads(business_id, email, source, status, score, language, country, city, niche)
        VALUES (%s, %s, 'buyer_journey_scenario', 'scouted', 91, 'en', 'QA', 'Scenario City', 'dentists')
        RETURNING id
        """,
        (business["id"], f"owner-{token}@{domain}"),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 67, 'Contact path and mobile CTA may be weak.', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], domain, f"https://{domain}", token),
    )
    for issue_type in ["contact_path", "mobile_cta", "metadata"]:
        execute(
            """
            INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation)
            VALUES (%s, %s, 'high', 'Public enquiry path may be weak', 'Visible from a public browser session.', 'Review the visible public enquiry path.')
            """,
            (audit["id"], issue_type),
        )
    execute(
        "INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport) VALUES (%s, 'desktop', %s, %s, 'desktop')",
        (audit["id"], f"/app/storage/screenshots/{token}.png", f"/media/screenshots/{token}.png"),
    )
    score_lead(str(lead["id"]), str(audit["id"]))
    execute("UPDATE leads SET score = 91 WHERE id = %s", (lead["id"],))
    execute("UPDATE lead_scores SET final_score = 91 WHERE lead_id = %s AND audit_id = %s", (lead["id"], audit["id"]))
    campaign = create_campaign({"name": f"buyer-journey-{token}", "country": "QA", "language": "en", "niche": "dentists", "offer_key": "contact_form_repair"})
    preview = prepare_campaign(str(campaign["id"]), 70, 5)
    quality = campaign_preview_quality_pack(str(campaign["id"]), 5)
    payment = handle_paddle_event(
        {
            "event_type": "transaction.paid",
            "data": {
                "id": f"txn_{token}",
                "customer_id": f"ctm_{token}",
                "customer": {"email": f"buyer-{token}@voiddorescue.local"},
                "custom_data": {"product_key": "contact_form_repair"},
                "details": {"totals": {"total": "9900", "currency_code": "USD"}},
            },
        },
        provisioning_paused=False,
    )
    customer = fetch_one("SELECT id FROM customers WHERE paddle_customer_id = %s", (f"ctm_{token}",))
    journey = customer_journey_snapshot(customer_id=str(customer["id"])) if customer else {"result_json": {}}
    result = {
        "token": token,
        "business_created": bool(business),
        "lead_created": bool(lead),
        "audit_created": bool(audit),
        "campaign_preview_count": int(preview.get("preview_count") or 0),
        "preview_quality_status": quality["status"],
        "preview_quality_ready_count": quality["ready_count"],
        "paddle_actions": payment["actions"],
        "customer_created": bool(customer),
        "dashboard_ready": bool((journey.get("result_json") or {}).get("dashboard_ready")),
        "fix_request_count": _count("SELECT count(*) FROM fix_requests WHERE customer_id = %s", (customer["id"],)) if customer else 0,
        "codex_task_count": _count("SELECT count(*) FROM codex_tasks WHERE input_json::text LIKE %s", (f"%{token}%",)),
        "mailer_actions_queued": _count("SELECT count(*) FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{token}%",)),
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
    event = execute(
        """
        INSERT INTO system_events(type, severity, message, payload_json)
        VALUES ('buyer_journey.scenario', 'info', 'No-send buyer journey scenario completed', %s)
        RETURNING id
        """,
        (Jsonb(json_safe({**result, "token": token})),),
    )
    result["system_event_id"] = str(event["id"]) if event else None
    if cleanup:
        result["cleanup"] = cleanup_buyer_journey_scenario(token)
    return json_safe(result)


def buyer_journey_readiness_scoreboard() -> dict[str, Any]:
    return {
        "checkout_paid_events": _count("SELECT count(*) FROM payments WHERE status = 'paid'"),
        "customer_count": _count("SELECT count(*) FROM customers"),
        "fix_request_count": _count("SELECT count(*) FROM fix_requests"),
        "codex_task_count": _count("SELECT count(*) FROM codex_tasks WHERE type = 'customer_fix_request'"),
        "campaign_preview_count": _count("SELECT count(*) FROM campaign_leads WHERE status = 'preview'"),
        "live_outreach_sent_count": _count("SELECT count(*) FROM outreach_messages WHERE status = 'sent'"),
        "warmup_sent_count": _count("SELECT count(*) FROM email_events WHERE event_type = 'warmup_sent'"),
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
