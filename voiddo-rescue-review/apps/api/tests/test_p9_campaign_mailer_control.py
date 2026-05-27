from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.campaign_control import campaign_readiness_snapshot
from app.db import execute, fetch_one
from app.mailer_control import evaluate_outbound_message
from app.main import app
from app.reply_actions import plan_reply_action
from app.scout_quality import cleanup_scout_campaign_quality_history, latest_scout_campaign_quality_history, run_scout_quality_gate, score_scout_provenance, scout_campaign_quality_regression_guard, scout_campaign_quality_summary
from app.scouts import cleanup_scout_source_readiness_checks, create_campaign, create_scout_run, create_scout_source, latest_scout_source_readiness, prepare_campaign, process_scout_run, run_scout_source_readiness, scout_source_readiness_regression_guard, scout_source_readiness_summary


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


def test_campaign_readiness_blocks_stale_scout_lead_without_quality_pass():
    token = uuid.uuid4().hex[:8]
    csv_text = (
        "business_name,website_url,email,country,niche\n"
        f"Weak,https://p9-weak-{token}.example.test,weak@p9-weak-{token}.example.test,P9Q,dentists\n"
    )
    source = create_scout_source({"name": f"p9-weak-quality-{token}", "source_type": "manual_csv_scout", "country": "P9Q", "language": "en", "niche": "dentists", "config_json": {"csv": csv_text}})
    run = create_scout_run(str(source["id"]))
    processed = process_scout_run(str(run["id"]))
    assert run_scout_quality_gate(str(run["id"]))["allowed_for_campaign_preview"] is False
    lead_id = processed["previews"][0]["lead_id"]
    business = fetch_one("SELECT business_id FROM leads WHERE id = %s", (lead_id,))
    audit = execute(
        """
        INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
        VALUES (%s, %s, %s, %s, 'completed', 85, 'Contact path issue', %s, now())
        RETURNING id
        """,
        (business["business_id"], lead_id, f"p9-weak-{token}.example.test", f"https://p9-weak-{token}.example.test", f"p9-weak-{token}"),
    )
    for _ in range(3):
        execute("INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text) VALUES (%s, 'contact', 'high', 'Issue', 'Issue text')", (audit["id"],))
    execute("INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport) VALUES (%s, 'desktop', '/tmp/p9-weak.png', '/media/p9-weak.png', 'desktop')", (audit["id"],))
    campaign = create_campaign({"name": f"p9-weak-quality-{token}", "country": "P9Q", "language": "en", "niche": "dentists", "offer_key": "contact_form_repair"})
    execute(
        """
        INSERT INTO campaign_leads(campaign_id, lead_id, audit_id, status, score, preview_json)
        VALUES (%s, %s, %s, 'preview', 88, %s)
        """,
        (campaign["id"], lead_id, audit["id"], Jsonb({"dry_run": True, "legacy_stale_preview": True})),
    )
    snapshot = campaign_readiness_snapshot(str(campaign["id"]))
    assert snapshot["status"] == "blocked"
    assert snapshot["summary_json"]["scout_quality"]["failed_count"] == 1
    assert snapshot["summary_json"]["scout_source_readiness"]["failed_count"] == 1
    assert any(blocker["code"] == "scout_quality_not_pass" for blocker in snapshot["blockers_json"])
    assert any(blocker["code"] == "scout_source_readiness_not_pass" for blocker in snapshot["blockers_json"])


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


def test_scout_source_readiness_scores_source_before_run():
    token = uuid.uuid4().hex[:8]
    csv_text = (
        "business_name,website_url,email,country,niche,source_url,confidence\n"
        f"Ready,https://ready-{token}.example.test,owner@ready-{token}.example.test,P9,dentists,https://directory.example.test/ready,95\n"
    )
    source = create_scout_source({"name": f"ready-source-{token}", "source_type": "manual_csv_scout", "country": "P9", "niche": "dentists", "config_json": {"csv": csv_text}})
    readiness = run_scout_source_readiness(str(source["id"]))
    latest = latest_scout_source_readiness(str(source["id"]))
    assert readiness["status"] == "PASS_SOURCE_READY"
    assert readiness["allowed_for_scout_run"] is True
    assert readiness["send_mail"] is False
    assert latest["status"] == "PASS_SOURCE_READY"


def test_scout_source_readiness_blocks_weak_or_sensitive_source_without_sending():
    token = uuid.uuid4().hex[:8]
    email = f"suppressed-source-{token}@example.test"
    execute("INSERT INTO suppression_list(email, reason, source) VALUES (%s, 'pytest', 'p9')", (email,))
    csv_text = (
        "business_name,website_url,email,country,niche,confidence\n"
        f"Bad,,{email},P9,crypto,30\n"
    )
    source = create_scout_source({"name": f"blocked-source-{token}", "source_type": "manual_csv_scout", "country": "P9", "niche": "dentists", "config_json": {"csv": csv_text}})
    readiness = run_scout_source_readiness(str(source["id"]))
    issue_codes = {issue["code"] for issue in readiness["issues"]}
    assert readiness["status"] == "REVIEW_SOURCE_BEFORE_RUN"
    assert readiness["allowed_for_scout_run"] is False
    assert "weak_domain_coverage" in issue_codes
    assert "excluded_niche_rows" in issue_codes
    assert "suppressed_emails_in_source" in issue_codes
    assert readiness["send_mail"] is False
    assert readiness["live_outreach_allowed"] is False


def test_scout_source_readiness_summary_and_agent_are_no_send():
    summary = scout_source_readiness_summary()
    assert summary["send_mail"] is False
    assert summary["smtp_called"] is False
    assert summary["live_outreach_allowed"] is False
    agent = run_agent("scout_source_readiness_summary_agent")
    assert agent["status"] == "completed"
    assert agent["result_json"]["send_mail"] is False


def test_scout_source_readiness_retention_and_regression_are_no_send():
    token = uuid.uuid4().hex[:8]
    source = create_scout_source({"name": f"p77-source-{token}", "source_type": "manual_csv_scout", "country": "P9", "niche": "dentists", "config_json": {"csv": ""}})
    try:
        execute(
            """
            INSERT INTO scout_source_readiness_checks(source_id, status, score, row_count, parseable_count, issues_json, created_at)
            VALUES (%s, 'PASS_SOURCE_READY', 95, 10, 10, '[]'::jsonb, now() - interval '2 minutes')
            """,
            (source["id"],),
        )
        execute(
            """
            INSERT INTO scout_source_readiness_checks(source_id, status, score, row_count, parseable_count, issues_json, created_at)
            VALUES (%s, 'REVIEW_SOURCE_BEFORE_RUN', 40, 1, 0, %s, now())
            """,
            (source["id"], Jsonb([{"code": "weak_domain_coverage", "severity": "high"}])),
        )
        guard = scout_source_readiness_regression_guard(5)
        assert guard["decision"] == "FAIL_REVIEW_REQUIRED_NO_SEND"
        assert "latest_source_readiness_not_pass" in guard["regressions"]
        assert guard["send_mail"] is False
        assert guard["review_task_created"] is True
        retention = cleanup_scout_source_readiness_checks(120)
        assert retention["send_mail"] is False
        retention_agent = run_agent("scout_source_readiness_retention_agent")
        regression_agent = run_agent("scout_source_readiness_regression_guard_agent")
        assert retention_agent["status"] == "completed"
        assert regression_agent["status"] == "completed"
        assert regression_agent["result_json"]["send_mail"] is False
    finally:
        execute("DELETE FROM scout_source_readiness_checks WHERE source_id = %s", (source["id"],))
        execute("DELETE FROM scout_sources WHERE id = %s", (source["id"],))


def test_p9_admin_endpoints_require_auth_and_work():
    campaign_id = _campaign_with_audit(uuid.uuid4().hex[:8])
    assert client.post(f"/admin/campaigns/{campaign_id}/readiness").status_code == 401
    assert client.post(f"/admin/campaigns/{campaign_id}/readiness", headers=admin_headers()).status_code == 200
    assert client.get("/admin/scouts/campaign-quality-summary").status_code == 401
    assert client.get("/admin/scouts/campaign-quality-summary", headers=admin_headers()).status_code == 200
    assert client.get("/admin/scouts/campaign-quality-history").status_code == 401
    assert client.get("/admin/scouts/campaign-quality-history", headers=admin_headers()).status_code == 200
    assert client.get("/admin/scouts/source-readiness-summary").status_code == 401
    assert client.get("/admin/scouts/source-readiness-summary", headers=admin_headers()).status_code == 200
    assert client.post("/admin/scouts/source-readiness-retention", headers=admin_headers()).status_code == 200
    assert client.post("/admin/scouts/source-readiness-regression-guard", headers=admin_headers()).status_code == 200
    assert client.post("/admin/scouts/campaign-quality-regression-guard", headers=admin_headers()).status_code == 200
    assert client.post("/admin/mailer/outbound-decision", json={"email": "lead@example.test"}, headers=admin_headers()).status_code == 200
    assert client.post("/admin/replies/action-plan", json={"subject": "Price", "body": "cost?"}, headers=admin_headers()).status_code == 200


def test_scout_campaign_quality_summary_and_agent_are_no_send():
    summary = scout_campaign_quality_summary()
    assert summary["send_mail"] is False
    assert summary["smtp_called"] is False
    assert summary["live_outreach_allowed"] is False
    assert summary["raw_recipient_addresses_included"] is False
    assert "campaign_quality" in summary
    agent = run_agent("scout_campaign_quality_summary_agent")
    assert agent["status"] == "completed"
    assert agent["result_json"]["send_mail"] is False
    history = latest_scout_campaign_quality_history()
    assert history["count"] >= 1
    assert history["latest"]["send_mail"] is False
    assert history["latest"]["raw_recipient_addresses_included"] is False


def test_scout_campaign_quality_retention_and_regression_are_no_send():
    execute("DELETE FROM scout_campaign_quality_history")
    execute(
        """
        INSERT INTO scout_campaign_quality_history(status, blocker_count, scout_runs_json, latest_self_check_json, latest_provenance_json, campaign_quality_json, created_at)
        VALUES ('PASS_NO_SEND', 0, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, %s, now() - interval '2 minutes')
        """,
        (Jsonb({"latest_failed_count": 0}),),
    )
    execute(
        """
        INSERT INTO scout_campaign_quality_history(status, blocker_count, scout_runs_json, latest_self_check_json, latest_provenance_json, campaign_quality_json, created_at)
        VALUES ('PASS_NO_SEND', 0, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, %s, now() - interval '1 minute')
        """,
        (Jsonb({"latest_failed_count": 0}),),
    )
    execute(
        """
        INSERT INTO scout_campaign_quality_history(status, blocker_count, scout_runs_json, latest_self_check_json, latest_provenance_json, campaign_quality_json, created_at)
        VALUES ('REVIEW_REQUIRED_NO_SEND', 1, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, %s, now())
        """,
        (Jsonb({"latest_failed_count": 1}),),
    )
    guard = scout_campaign_quality_regression_guard(5)
    assert guard["decision"] == "FAIL_REVIEW_REQUIRED_NO_SEND"
    assert guard["send_mail"] is False
    assert guard["review_task_created"] is True
    retention = cleanup_scout_campaign_quality_history(120)
    assert retention["send_mail"] is False
    retention_agent = run_agent("scout_campaign_quality_retention_agent")
    regression_agent = run_agent("scout_campaign_quality_regression_guard_agent")
    assert retention_agent["status"] == "completed"
    assert regression_agent["status"] == "completed"
    assert regression_agent["result_json"]["send_mail"] is False


def test_p9_tables_exist():
    for table in ["campaign_readiness_snapshots", "outbound_mailer_decisions", "reply_action_plans", "scout_provenance_scores", "scout_source_readiness_checks"]:
        row = fetch_one("SELECT to_regclass(%s) AS name", (table,))
        assert row["name"] == table
