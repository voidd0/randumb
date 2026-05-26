from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.campaign_control import campaign_readiness_snapshot
from app.db import execute, fetch_one
from app.mailer_control import evaluate_outbound_message
from app.main import app
from app.reply_actions import plan_reply_action
from app.scout_quality import score_scout_provenance
from app.scouts import create_campaign, create_scout_run, create_scout_source, prepare_campaign, process_scout_run


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _campaign_with_audit(token: str) -> str:
    business = execute(
        "INSERT INTO businesses(name, domain, source, niche, country, status) VALUES (%s, %s, 'p9_test', 'dentists', 'P9', 'scouted') RETURNING id",
        (f"P9 {token}", f"p9-{token}.example.test"),
    )
    lead = execute(
        "INSERT INTO leads(business_id, email, source, status, score, niche, country, language) VALUES (%s, %s, 'p9_test', 'scouted', 90, 'dentists', 'P9', 'en') RETURNING id",
        (business["id"], f"owner@p9-{token}.example.test"),
    )
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 85, 'Contact path issue', %s, now())
        RETURNING id
        """,
        (business["id"], lead["id"], f"p9-{token}.example.test", f"https://p9-{token}.example.test", f"p9-{token}"),
    )
    for _ in range(3):
        execute("INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text) VALUES (%s, 'contact', 'high', 'Issue', 'Issue text')", (audit["id"],))
    execute("INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport) VALUES (%s, 'desktop', '/tmp/p9.png', '/media/p9.png', 'desktop')", (audit["id"],))
    campaign = create_campaign({"name": f"p9-{token}", "country": "P9", "language": "en", "niche": "dentists", "offer_key": "contact_form_repair"})
    prepare_campaign(str(campaign["id"]), 70, 20)
    return str(campaign["id"])


def test_campaign_readiness_records_blockers_and_counts():
    campaign_id = _campaign_with_audit(uuid.uuid4().hex[:8])
    snapshot = campaign_readiness_snapshot(campaign_id)
    assert snapshot["lead_count"] >= 1
    assert snapshot["qualified_count"] >= 1
    assert snapshot["min_audit_strength"] >= 70
    assert snapshot["status"] in {"blocked", "ready_for_preview_only"}


def test_outbound_message_decision_blocks_and_hashes_recipient():
    decision = evaluate_outbound_message({"email": "lead-p9@example.test", "template_key": "first_audit_notice"})
    assert decision["status"] == "blocked"
    assert decision["action"] == "do_not_send"
    assert decision["recipient_hash"] != "lead-p9@example.test"
    assert "outreach_dry_run_enabled" in decision["reason"] or "recent_" in decision["reason"]


def test_outbound_message_decision_rejects_suppressed_recipient():
    email = f"suppressed-{uuid.uuid4().hex[:6]}@example.test"
    execute("INSERT INTO suppression_list(email, reason, source) VALUES (%s, 'pytest', 'p9')", (email,))
    decision = evaluate_outbound_message({"email": email, "template_key": "first_audit_notice"})
    assert "recipient_suppressed" in decision["reason"]


def test_reply_action_plan_blocks_legal_and_allows_price_draft():
    price = plan_reply_action("Price", "How much does it cost?", "audit@voiddorescue.com")
    legal = plan_reply_action("Legal", "My lawyer will contact you", "support@voiddorescue.com")
    assert price["safe_action"] == "prepare_safe_reply_draft"
    assert legal["human_review_required"] is True
    assert legal["safe_action"] == "stop_thread_create_review_item"


def test_reply_action_plan_unsubscribe_suppression_action():
    plan = plan_reply_action("Stop", "Please unsubscribe me", "audit@voiddorescue.com")
    assert plan["classification"] == "unsubscribe"
    assert plan["safe_action"].startswith("suppress_sender")


def test_scout_provenance_scores_source_quality():
    token = uuid.uuid4().hex[:8]
    csv_text = (
        "business_name,website_url,email,country,niche,source_url,confidence\n"
        f"One,https://prov-{token}.example.test,a@prov-{token}.example.test,P9,dentists,https://directory.example.test/one,90\n"
    )
    source = create_scout_source({"name": f"prov-{token}", "source_type": "manual_csv_scout", "country": "P9", "niche": "dentists", "config_json": {"csv": csv_text}})
    run = create_scout_run(str(source["id"]))
    process_scout_run(str(run["id"]))
    score = score_scout_provenance(str(run["id"]))
    assert score["status"] == "pass"
    assert score["score"] >= 75


def test_p9_admin_endpoints_require_auth_and_work():
    campaign_id = _campaign_with_audit(uuid.uuid4().hex[:8])
    assert client.post(f"/admin/campaigns/{campaign_id}/readiness").status_code == 401
    assert client.post(f"/admin/campaigns/{campaign_id}/readiness", headers=admin_headers()).status_code == 200
    assert client.post("/admin/mailer/outbound-decision", json={"email": "lead@example.test"}, headers=admin_headers()).status_code == 200
    assert client.post("/admin/replies/action-plan", json={"subject": "Price", "body": "cost?"}, headers=admin_headers()).status_code == 200


def test_p9_tables_exist():
    for table in ["campaign_readiness_snapshots", "outbound_mailer_decisions", "reply_action_plans", "scout_provenance_scores"]:
        row = fetch_one("SELECT to_regclass(%s) AS name", (table,))
        assert row["name"] == table
