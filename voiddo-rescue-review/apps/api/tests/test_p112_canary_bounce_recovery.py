from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.autonomous_agents import run_agent
from app.canary_bounce_recovery import _extract_dsn_details, backfill_bounce_dsn_details, canary_bounce_recovery
from app.db import execute
from app.main import app
from app.p0 import execute_owner_command, runtime_control_enabled, set_runtime_control


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_canary_bounce_recovery_blocks_and_redacts_raw_addresses():
    token = uuid.uuid4().hex[:10]
    previous_pause = runtime_control_enabled("pause_outreach")
    try:
        execute(
            """
            INSERT INTO mail_signals(signal_type, severity, source, mailbox, recipient_hash, provider, message_id, raw_summary)
            VALUES ('bounce', 'warning', 'p112', 'audit', %s, 'gmail', %s, %s)
            """,
            (f"hash-{token}", f"msg-{token}", f"Delivery failed for lead-{token}@example.test: domain not found"),
        )
        result = canary_bounce_recovery(24, apply_pause=True, store=True)
        assert result["decision"] == "KEEP_PAUSED_RECOVER_BOUNCES"
        assert "recent_bounce_or_dsn" in result["blockers"]
        assert result["pause_outreach_applied"] is True
        assert result["send_mail"] is False
        assert result["raw_recipient_addresses_included"] is False
        assert runtime_control_enabled("pause_outreach") is True
        assert f"lead-{token}@example.test" not in str(result)
        assert "@" not in str(result)
    finally:
        execute("DELETE FROM mail_signals WHERE raw_summary LIKE %s", (f"%{token}%",))
        execute("DELETE FROM agent_runs WHERE agent = 'canary_bounce_recovery_agent' AND result_json::text LIKE %s", (f"%{token}%",))
        execute("DELETE FROM system_events WHERE type = 'outreach.canary_bounce_recovery' AND payload_json::text LIKE %s", (f"%{token}%",))
        set_runtime_control("pause_outreach", previous_pause, "p112_test_cleanup", "restore")


def test_canary_bounce_recovery_endpoint_requires_admin():
    assert client.get("/admin/outreach/bounce-recovery").status_code == 401
    response = client.get("/admin/outreach/bounce-recovery", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["history"]["send_mail"] is False


def test_canary_bounce_recovery_agent_is_no_send(monkeypatch):
    import app.autonomous_agents as agents_module

    monkeypatch.setattr(
        agents_module,
        "canary_bounce_recovery",
        lambda window_hours=24, apply_pause=True, store=True: {
            "decision": "KEEP_PAUSED_RECOVER_BOUNCES",
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    result = run_agent("canary_bounce_recovery_agent", {"window_hours": 24})
    assert result["status"] == "completed"
    assert result["result_json"]["send_mail"] is False
    assert result["result_json"]["live_outreach_allowed"] is False


def test_owner_command_show_canary_bounce_recovery_is_safe_auto(monkeypatch):
    import app.canary_bounce_recovery as recovery_module

    monkeypatch.setattr(
        recovery_module,
        "canary_bounce_recovery",
        lambda window_hours=24, apply_pause=True, store=True: {
            "decision": "KEEP_PAUSED_RECOVER_BOUNCES",
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    monkeypatch.setattr(
        recovery_module,
        "latest_canary_bounce_recovery_runs",
        lambda limit=5: {"count": 0, "runs": [], "send_mail": False, "live_outreach_allowed": False},
    )
    result = execute_owner_command({"command": "SHOW CANARY BOUNCE RECOVERY", "risk_level": "SAFE_AUTO", "args_json": {}})
    assert result["ok"] is True
    assert result["action"] == "canary_bounce_recovery_status"
    assert result["recovery"]["send_mail"] is False
    assert result["recovery"]["live_outreach_allowed"] is False


def test_dsn_detail_extractor_redacts_and_classifies_domain_failure():
    raw = b"""Subject: Undelivered Mail Returned to Sender
Content-Type: multipart/report; boundary=\"x\"

--x
Content-Type: text/plain

Delivery failed.
--x
Content-Type: message/delivery-status

Final-Recipient: rfc822; lead@example.test
Action: failed
Status: 5.4.4
Diagnostic-Code: X-Postfix; Host or domain name not found
--x
Content-Type: message/rfc822

Message-ID: <original-message@voiddorescue.com>
To: lead@example.test
Subject: Possible issue

Body
--x--
"""
    result = _extract_dsn_details(raw)
    assert result["ok"] is True
    assert result["reason"] == "domain_not_found"
    assert result["recipient_hash"]
    assert result["original_message_id_present"] is True
    assert result["bounced_recipient"] == "lead@example.test"


def test_bounce_dsn_backfill_uses_hashes_and_no_send(monkeypatch):
    import app.canary_bounce_recovery as recovery_module

    token = uuid.uuid4().hex[:10]
    raw = f"""Subject: Undelivered Mail Returned to Sender
Final-Recipient: rfc822; lead-{token}@example.test
Diagnostic-Code: X-Postfix; Host or domain name not found
Message-ID: <orig-{token}@voiddorescue.com>
""".encode()

    monkeypatch.setattr(
        recovery_module,
        "fetch_all",
        lambda *args, **kwargs: [{"mailbox": "audit", "uid": f"uid-{token}", "message_id": f"dsn-{token}", "created_at": "now"}],
    )
    monkeypatch.setattr(recovery_module, "fetch_one", lambda *args, **kwargs: {"id": "outreach-id"})
    monkeypatch.setattr(recovery_module, "_fetch_raw_email", lambda mailbox, uid: raw)
    calls = []
    monkeypatch.setattr(recovery_module, "execute", lambda *args, **kwargs: calls.append((args, kwargs)) or {"id": "run-id"})

    result = backfill_bounce_dsn_details(24, 10, apply=True)
    assert result["processed"] == 1
    assert result["enriched"] == 1
    assert result["linked_outreach_count"] == 1
    assert result["send_mail"] is False
    assert result["raw_recipient_addresses_included"] is False
    assert f"lead-{token}@example.test" not in str(result)
    assert "@" not in str(result)
    assert calls
