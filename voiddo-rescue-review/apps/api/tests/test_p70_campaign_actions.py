from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.campaign_actions import campaign_actions_summary, run_campaign_action
from app.db import execute, fetch_one
from app.main import app
from app.scouts import create_campaign


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute(
        """
        DELETE FROM campaign_action_runs
        WHERE result_json::text LIKE %s
           OR campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)
        """,
        (f"%{token}%", f"%{token}%"),
    )
    execute("DELETE FROM campaign_leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%",))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"%{token}%",))


def _campaign(token: str) -> str:
    campaign = create_campaign(
        {
            "name": f"p70-campaign-{token}",
            "country": "QA",
            "language": "en",
            "niche": "dentists",
            "offer_key": "contact_form_repair",
            "dry_run": True,
        }
    )
    return str(campaign["id"])


def test_campaign_actions_endpoints_require_admin_auth():
    assert client.get("/admin/campaign-actions").status_code == 401
    assert client.post("/admin/campaign-actions/run", json={"action": "refresh_previews"}).status_code == 401
    assert client.get("/admin/campaign-actions", headers=admin_headers()).status_code == 200


def test_unknown_campaign_action_blocks_without_send_or_shell():
    token = uuid.uuid4().hex[:8]
    try:
        result = run_campaign_action(f"run_shell_{token}")
        assert result["status"] == "blocked"
        assert result["reason"] == "unknown_or_unsafe_campaign_action"
        assert result["send_mail"] is False
        assert result["smtp_called"] is False
        assert result["live_outreach_allowed"] is False
        assert result["raw_recipient_addresses_included"] is False
        assert result["secrets_included"] is False
    finally:
        _cleanup(token)


def test_campaign_actions_are_preview_only_and_persisted():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        safety = run_campaign_action("safety_lock", campaign_id=campaign_id, dry_run=True)
        assert safety["status"] == "dry_run"
        assert safety["send_mail"] is False
        assert fetch_one("SELECT status FROM campaigns WHERE id = %s", (campaign_id,))["status"] == "draft"

        real_safety = run_campaign_action("safety_lock", campaign_id=campaign_id, dry_run=False)
        assert real_safety["status"] == "completed"
        assert real_safety["new_status"] == "safety_locked"
        assert real_safety["send_mail"] is False
        assert fetch_one("SELECT status, dry_run FROM campaigns WHERE id = %s", (campaign_id,))["status"] == "safety_locked"

        quality = run_campaign_action("run_quality", campaign_id=campaign_id, limit=5)
        assert quality["status"] == "completed"
        assert quality["send_mail"] is False
        assert quality["smtp_called"] is False

        summary = campaign_actions_summary(10)
        assert summary["send_mail"] is False
        assert summary["live_outreach_allowed"] is False
        assert any(item["action"] == "safety_lock" for item in summary["latest_runs"])
    finally:
        _cleanup(token)


def test_campaign_owner_preview_report_dry_run_does_not_send_or_expose_recipients():
    response = client.post(
        "/admin/campaign-actions/run",
        json={"action": "owner_preview_report", "dry_run": True, "limit": 5},
        headers=admin_headers(),
    )
    assert response.status_code == 200
    payload = response.json()["action"]
    assert payload["status"] == "dry_run"
    assert payload["report_path"] == "dry_run"
    assert payload["send_mail"] is False
    assert payload["smtp_called"] is False
    assert payload["raw_recipient_addresses_included"] is False


def test_refresh_previews_action_is_no_send_even_when_executed():
    response = client.post(
        "/admin/campaign-actions/run",
        json={"action": "refresh_previews", "dry_run": True, "limit": 5},
        headers=admin_headers(),
    )
    assert response.status_code == 200
    payload = response.json()["action"]
    assert payload["status"] == "dry_run"
    assert payload["send_mail"] is False
    assert payload["smtp_called"] is False
    assert payload["live_outreach_allowed"] is False
