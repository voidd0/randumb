from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.db import execute
from app.mailer_autonomy_ledger import mailer_autonomy_ledger
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_mailer_ledger_reports_no_live_outreach_unlock():
    ledger = mailer_autonomy_ledger()
    assert ledger["gates"]["live_outreach_allowed"] is False
    assert ledger["gates"]["send_mail_from_ledger"] is False
    assert ledger["runtime"]["live_outreach_sent_count"] == 0


def test_mailer_ledger_has_required_sections():
    ledger = mailer_autonomy_ledger()
    for key in ["owner_commands", "inbound", "outbound", "signals", "throttle", "suppression", "warmup", "gates"]:
        assert key in ledger
    assert isinstance(ledger["owner_commands"]["latest"], list)
    assert isinstance(ledger["outbound"]["messages_by_status"], list)


def test_mailer_ledger_omits_raw_addresses_and_mail_bodies():
    marker = "ledger-raw-should-not-appear@example.test"
    execute(
        """
        INSERT INTO owner_commands(sender, body, command, risk_level, status)
        VALUES (%s, %s, 'STATUS', 'SAFE_AUTO', 'executed')
        """,
        (marker, f"STATUS from {marker}"),
    )
    ledger = mailer_autonomy_ledger()
    text = str(ledger)
    assert marker not in text
    assert "raw_recipient_addresses_included" in text
    assert ledger["privacy"]["raw_owner_address_included"] is False


def test_admin_mailer_ledger_requires_auth():
    assert client.get("/admin/mailer/autonomy-ledger").status_code == 401
    response = client.get("/admin/mailer/autonomy-ledger", headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["ledger"]["policy"] == "autonomous_mailer_all_io_gated_no_raw_addresses"


def test_mailer_ledger_blocks_warmup_with_recent_signals():
    ledger = mailer_autonomy_ledger()
    if ledger["signals"]["bounce_or_dsn_count"] > 0 or ledger["signals"]["rate_limit_count"] > 0:
        assert "recent_bounce_or_dsn" in ledger["gates"]["blockers"] or "recent_rate_limit" in ledger["gates"]["blockers"]
    assert ledger["warmup"]["live_outreach_sent_count"] == 0
