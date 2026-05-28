from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db import connect_dict
from app.main import app
from app.p0 import (
    create_scanner_job,
    handle_paddle_event,
    import_lead_batch,
    latest_production_visual_qa_decision,
    parse_owner_command,
    persist_inbound_message,
    prepare_warmup,
    record_visual_qa,
    run_mail_qa,
)


client = TestClient(app)


def test_scanner_job_lifecycle_and_audit_api_db_writes():
    token = uuid.uuid4().hex[:10]
    slug = f"p0-example-{token}"
    job = create_scanner_job("https://example.com", "P0 Test", dry_run=False)
    with connect_dict() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audits(domain, url, status, score, summary, public_slug, checked_at)
                VALUES ('example.com', 'https://example.com', 'completed', 80, 'P0 test audit', %s, now())
                RETURNING id
                """,
                (slug,),
            )
            audit_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, recommendation, evidence_json)
                VALUES (%s, 'contact_path', 'high', 'Contact path needs verification', 'Public check text.', 'Fix recommendation.', %s)
                """,
                (audit_id, Jsonb({"test": True})),
            )
            cur.execute(
                """
                INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport)
                VALUES (%s, 'desktop', '/app/storage/screenshots/test/desktop.png', 'https://api.rescue.voiddo.com/media/screenshots/test/desktop.png', '1440x1000')
                """,
                (audit_id,),
            )
            cur.execute("UPDATE scanner_jobs SET status = 'completed', audit_id = %s, completed_at = now() WHERE id = %s", (audit_id, job["id"]))
        conn.commit()
    job_response = client.get(f"/scanner/jobs/{job['id']}")
    assert job_response.status_code == 200
    assert job_response.json()["job"]["status"] == "completed"
    audit_response = client.get(f"/audits/{slug}")
    assert audit_response.status_code == 200
    audit = audit_response.json()["audit"]
    assert audit["issues"][0]["issue_type"] == "contact_path"
    assert audit["screenshots"][0]["type"] == "desktop"


def test_paddle_transaction_paid_creates_payment_and_fix_request():
    token = uuid.uuid4().hex
    result = handle_paddle_event(
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
        provisioning_paused=True,
    )
    assert "payment_recorded" in result["actions"]
    assert "fix_request_created" in result["actions"]


def test_paddle_subscription_creates_subscription_record():
    token = uuid.uuid4().hex
    result = handle_paddle_event(
        {
            "event_type": "subscription.activated",
            "data": {
                "id": f"sub_{token}",
                "customer_id": f"ctm_{token}",
                "customer": {"email": f"subscriber-{token}@voiddorescue.local"},
                "status": "active",
                "custom_data": {"product_key": "monitor_monthly"},
            },
        },
        provisioning_paused=True,
    )
    assert "subscription_recorded" in result["actions"]


def test_inbox_persistence_idempotency_and_unsubscribe_suppression():
    token = uuid.uuid4().hex
    message = {
        "mailbox": "audit",
        "uid": token,
        "message_id": f"<{token}@example.test>",
        "sender": f"lead-{token}@example.test",
        "subject": "remove me",
        "body": "Please unsubscribe me",
    }
    first = persist_inbound_message(message)
    second = persist_inbound_message(message)
    assert first["stored"] is True
    assert first["classification"] == "unsubscribe"
    assert second["duplicate"] is True


def test_owner_command_safe_auto_and_high_risk_blocked():
    owner = os.environ["OWNER_COMMAND_EMAIL"]
    safe = parse_owner_command(owner, "STATUS", "", owner, "dkim=pass")
    risky = parse_owner_command(owner, "RUN SHELL", "ls -la", owner, "dkim=pass")
    assert safe["risk_level"] == "SAFE_AUTO"
    assert safe["status"] == "executed"
    assert risky["risk_level"] == "HIGH_RISK"
    assert risky["status"] == "review_required"


def test_visual_qa_detects_unresolved_template_vars():
    result = record_visual_qa("email_visual_agent", "inline:test", "<html>{{business_name}}</html>")
    assert result["decision"] == "FAIL_BLOCK_LAUNCH"
    assert "unresolved_template_vars" in result["issues_json"]


def test_production_visual_decision_ignores_inline_test_artifacts():
    token = uuid.uuid4().hex[:8]
    prod = record_visual_qa("app_visual_agent", f"/admin-test-{token}", "<html><body>Ready</body></html>")
    inline = record_visual_qa("email_visual_agent", "inline:test", "<html>{{business_name}}</html>")
    assert prod["decision"] == "PASS"
    assert inline["decision"] == "FAIL_BLOCK_LAUNCH"
    assert latest_production_visual_qa_decision() == "PASS"


def test_mail_qa_blocks_missing_dkim(monkeypatch):
    import app.p0 as p0

    def fake_dig(record_type: str, name: str) -> str:
        if name.startswith("dkim."):
            return ""
        if name.startswith("_dmarc."):
            return "v=DMARC1; p=none"
        return "ok"

    monkeypatch.setattr(p0, "_dig", fake_dig)
    monkeypatch.setattr(p0, "approved_test_inbox_emails", lambda settings=None: [])
    result = run_mail_qa()
    assert result["decision"] == "FAIL_BLOCK_LAUNCH"
    assert "missing_dkim" in result["issues_json"]


def test_warmup_cannot_start_without_recipient_pool(monkeypatch):
    import app.p0 as p0

    monkeypatch.setattr(p0, "approved_warmup_recipient_emails", lambda settings=None: [])
    result = prepare_warmup(recipient_pool_count=0, day_number=1)
    assert result["status"] == "blocked_no_recipient_pool"


def test_lead_batch_import_is_dry_run_and_excludes_niches():
    csv_text = "email,website_url,niche,score\none@example.com,https://one.example,dentists,80\nbad@example.com,https://bad.example,crypto,99\n"
    result = import_lead_batch("p0-test", csv_text, country="EE", niche="dentists")
    assert result["status"] == "dry_run_imported"
    assert result["accepted_rows"] == 1
    assert result["rejected_rows"] == 1


def test_outreach_cannot_send_when_launch_flag_false():
    response = client.post("/outreach/send", json={"lead_id": "test"})
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
