from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.db import execute, fetch_one
from app.main import app
from app.mailer_readiness import mailbox_health_score, run_clean_window_transition, sender_rotation_ready
from app.p0 import handle_paddle_event
from app.reply_actions import plan_reply_action
from app.scouts import create_campaign


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_clean_window_transition_blocks_without_sending_on_recent_signals(monkeypatch):
    import app.mailer_readiness as readiness

    monkeypatch.setattr(
        readiness,
        "mail_signal_summary",
        lambda hours=24: {"window_hours": hours, "items": [], "bounce_or_dsn_count": 1, "rate_limit_count": 0, "spam_signal_count": 0},
    )
    transition = run_clean_window_transition(24)
    assert transition["status"] == "blocked_recent_signals"
    assert transition["sends_started"] is False
    assert transition["warmup_transition"] == "not_ready"


def test_clean_window_transition_reruns_mail_qa_without_deliverability_send(monkeypatch):
    import app.mailer_readiness as readiness

    calls: list[bool] = []
    monkeypatch.setattr(
        readiness,
        "mail_signal_summary",
        lambda hours=24: {"window_hours": hours, "items": [], "bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0},
    )

    def fake_run_mail_qa(allow_deliverability_send: bool = True):
        calls.append(allow_deliverability_send)
        return {"decision": "PASS", "checks_json": {"deliverability_diagnostics": {"sent": 0}}}

    monkeypatch.setattr(readiness, "run_mail_qa", fake_run_mail_qa)
    campaign = create_campaign({"name": f"p10-empty-{uuid.uuid4().hex[:8]}", "country": "P10", "language": "en", "niche": "dentists"})
    transition = run_clean_window_transition(24)
    assert calls == [False]
    assert transition["status"] in {"ready_for_scheduler", "blocked_mail_qa"}
    assert transition["sends_started"] is False
    assert transition["result_json"]["policy"] == "no_send_transition"
    assert campaign["id"]


def test_mailbox_health_score_records_blocked_state(monkeypatch):
    import app.mailer_readiness as readiness

    monkeypatch.setattr(readiness, "latest_mail_qa_decision", lambda: "PASS")
    monkeypatch.setattr(readiness, "recent_mail_signal_count", lambda types, hours=24: 1)
    monkeypatch.setattr(readiness, "smtp_credentials_for_sender", lambda settings, mailbox: ("user", "pw", mailbox))
    health = mailbox_health_score("audit@voiddorescue.com")
    assert health["status"] == "blocked"
    assert health["recent_signal_count"] == 1


def test_sender_rotation_readiness_records_result(monkeypatch):
    import app.mailer_readiness as readiness

    monkeypatch.setattr(readiness, "mailbox_health_score", lambda mailbox: {"mailbox": mailbox, "status": "ready", "score": 90})
    result = sender_rotation_ready()
    assert result["ready_sender_count"] >= 1
    assert result["total_sender_count"] >= result["ready_sender_count"]
    assert result["status"] in {"ready", "blocked"}


def test_interested_reply_to_mock_checkout_creates_onboarding_and_fix_request():
    token = uuid.uuid4().hex
    plan = plan_reply_action("Re: audit", "Yes, interested, fix it", "audit@voiddorescue.com")
    assert plan["classification"] == "interested"
    assert plan["safe_action"] == "store_and_wait"
    result = handle_paddle_event(
        {
            "event_type": "transaction.paid",
            "data": {
                "id": f"txn_p10_{token}",
                "customer_id": f"ctm_p10_{token}",
                "customer": {"email": f"p10-{token}@voiddorescue.local"},
                "custom_data": {"product_key": "contact_form_repair"},
                "details": {"totals": {"total": "9900", "currency_code": "USD"}},
            },
        },
        provisioning_paused=False,
    )
    assert "fix_request_created" in result["actions"]
    assert "onboarding_task_created" in result["actions"]
    fix = fetch_one("SELECT count(*) AS count FROM fix_requests WHERE evidence_json->>'paddle_transaction_id' = %s", (f"txn_p10_{token}",))
    onboard = fetch_one("SELECT count(*) AS count FROM onboarding_tasks WHERE payload_json->>'paddle_transaction_id' = %s", (f"txn_p10_{token}",))
    assert int(fix["count"]) == 1
    assert int(onboard["count"]) == 1


def test_p10_admin_endpoints_require_auth_and_work():
    assert client.post("/admin/mailer/clean-window-transition", json={}).status_code == 401
    assert client.post("/admin/mailer/clean-window-transition", json={}, headers=admin_headers()).status_code == 200
    assert client.post("/admin/mailer/mailbox-health", json={"mailbox": "audit@voiddorescue.com"}, headers=admin_headers()).status_code == 200
    assert client.post("/admin/mailer/sender-rotation", headers=admin_headers()).status_code == 200


def test_p10_tables_exist():
    for table in ["mail_clean_window_transitions", "mailbox_health_scores", "sender_rotation_readiness"]:
        row = fetch_one("SELECT to_regclass(%s) AS name", (table,))
        assert row["name"] == table
