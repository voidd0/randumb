from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb

from app.campaign_preflight_status import latest_campaign_preflight_status
from app.db import execute
from app.mailer_action_queue import enqueue_mailer_action, process_mailer_action_queue
from app.mailer_control import evaluate_outbound_message
import app.mailer_control as mailer_control


def _campaign(token: str) -> str:
    row = execute(
        """
        INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
        VALUES (%s, 'preview_ready', 'QA', 'en', 'dentists', 'contact_form_repair', true)
        RETURNING id
        """,
        (f"p81-{token}",),
    )
    return str(row["id"])


def _cleanup(token: str) -> None:
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM outbound_mailer_decisions WHERE checks_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_preflight_runs WHERE result_json::text LIKE %s OR campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%", f"p81-{token}%"))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"p81-{token}%",))


def _insert_preflight(campaign_id: str, token: str, decision: str = "PASS_NO_SEND_PREFLIGHT") -> None:
    execute(
        """
        INSERT INTO campaign_preflight_runs(
          campaign_id, status, decision, checked_count, ready_count, blocker_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, 'completed', %s, 1, 1, 0, %s, false, false, false, false, false)
        """,
        (
            campaign_id,
            decision,
            Jsonb({"token": token, "decision": decision, "send_mail": False, "live_outreach_allowed": False}),
        ),
    )


def _patch_outbound_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(mailer_control, "transport_gate_status", lambda payload=None: {"allowed": True, "reason": "all_gates_passed"})
    monkeypatch.setattr(mailer_control, "throttle_decision", lambda *args, **kwargs: {"allowed": True, "reason": "ok"})
    monkeypatch.setattr(
        mailer_control,
        "render_email_template",
        lambda *args, **kwargs: {"subject": "Audit note", "text": "Public check details. Unsubscribe: https://go.rescue.voiddo.com/u", "template_key": "first_audit_notice"},
    )
    monkeypatch.setattr(mailer_control, "qa_email_template", lambda rendered: {"passed": True, "issues": [], "score": 100})


def test_outbound_message_requires_fresh_campaign_preflight(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        _patch_outbound_dependencies(monkeypatch)
        missing = evaluate_outbound_message({"email": f"lead-{token}@example.test", "campaign_id": campaign_id})
        assert missing["status"] == "blocked"
        assert "campaign_preflight_missing" in missing["reason"]

        _insert_preflight(campaign_id, token)
        passed = evaluate_outbound_message({"email": f"lead-{token}@example.test", "campaign_id": campaign_id})
        assert passed["status"] == "ready"
        assert passed["action"] == "send_allowed_by_gates"
        assert passed["checks_json"]["campaign_preflight"]["decision"] == "PASS_NO_SEND_PREFLIGHT"
    finally:
        _cleanup(token)


def test_send_outreach_queue_keeps_preflight_as_hard_gate():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        action = enqueue_mailer_action({"action_type": "send_outreach", "campaign_id": campaign_id, "recipient_email": f"lead-{token}@example.test", "marker": token})
        result = process_mailer_action_queue(100)
        processed = next(item for item in result["actions"] if item["id"] == action["id"])
        assert processed["status"] == "blocked"
        assert "campaign_preflight_missing" in processed["gate_result_json"]["blockers"]
        assert processed["gate_result_json"]["send_mail"] is False

        _insert_preflight(campaign_id, token)
        action2 = enqueue_mailer_action({"action_type": "send_outreach", "campaign_id": campaign_id, "recipient_email": f"lead2-{token}@example.test", "marker": f"{token}-pass"})
        result2 = process_mailer_action_queue(100)
        processed2 = next(item for item in result2["actions"] if item["id"] == action2["id"])
        assert "campaign_preflight_missing" not in processed2["gate_result_json"]["blockers"]
        assert processed2["gate_result_json"]["campaign_preflight"]["allowed"] is True
        assert processed2["status"] == "blocked"
        assert "high_risk_action_requires_review" in processed2["gate_result_json"]["blockers"]
        assert result2["send_mail"] is False
    finally:
        _cleanup(token)


def test_latest_campaign_preflight_status_blocks_failed_or_stale_evidence():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        assert latest_campaign_preflight_status(campaign_id)["reason"] == "campaign_preflight_missing"
        _insert_preflight(campaign_id, token, "FAIL_BLOCK_LAUNCH")
        failed = latest_campaign_preflight_status(campaign_id)
        assert failed["allowed"] is False
        assert failed["reason"] == "campaign_preflight_not_pass"
    finally:
        _cleanup(token)
