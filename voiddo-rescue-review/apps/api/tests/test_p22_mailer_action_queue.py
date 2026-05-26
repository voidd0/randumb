from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.db import execute
from app.mailer_action_queue import enqueue_mailer_action, mailer_action_queue_summary, process_mailer_action_queue
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(marker: str) -> None:
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s OR recipient_hash = %s", (f"%{marker}%", marker))


def test_cold_outreach_action_remains_blocked():
    marker = "p22-cold"
    try:
        enqueue_mailer_action({"action_type": "cold_outreach", "recipient_email": "cold@example.test", "marker": marker})
        result = process_mailer_action_queue(5)
        action = next(item for item in result["actions"] if item["action_type"] == "cold_outreach")
        assert action["status"] == "blocked"
        assert "high_risk_action_requires_review" in action["gate_result_json"]["blockers"]
        assert result["send_mail"] is False
    finally:
        _cleanup(marker)


def test_owner_report_prepared_but_not_sent_when_mail_signals_block():
    marker = "p22-owner"
    try:
        action = enqueue_mailer_action({"action_type": "owner_report", "marker": marker})
        assert action["status"] == "queued"
        result = process_mailer_action_queue(5)
        processed = [item for item in result["actions"] if item["action_type"] == "owner_report"]
        assert processed
        assert processed[-1]["status"] == "prepared"
        assert processed[-1]["gate_result_json"]["send_mail"] is False
    finally:
        _cleanup(marker)


def test_warmup_action_blocked_by_recent_signals_or_natural_timer_gate():
    marker = "p22-warmup"
    try:
        enqueue_mailer_action({"action_type": "warmup_slot", "marker": marker})
        result = process_mailer_action_queue(5)
        action = next(item for item in result["actions"] if item["action_type"] == "warmup_slot")
        assert action["status"] == "blocked"
        assert "natural_warmup_timer_only" in action["gate_result_json"]["blockers"]
    finally:
        _cleanup(marker)


def test_action_queue_summary_omits_raw_addresses():
    marker = "p22-raw-address"
    raw = "private-p22@example.test"
    try:
        enqueue_mailer_action({"action_type": "safe_reply_draft", "recipient_email": raw, "marker": marker})
        summary = mailer_action_queue_summary()
        text = str(summary)
        assert raw not in text
        assert summary["raw_recipient_addresses_included"] is False
    finally:
        _cleanup(marker)


def test_action_queue_endpoints_require_auth():
    assert client.get("/admin/mailer/action-queue").status_code == 401
    assert client.post("/admin/mailer/action-queue/process", json={"limit": 1}).status_code == 401
    assert client.get("/admin/mailer/action-queue", headers=admin_headers()).status_code == 200
