from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.campaign_remediation_feedback import campaign_remediation_feedback, latest_campaign_remediation_feedback
from app.db import execute, fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM campaign_remediation_feedback_runs WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent = 'campaign_remediation_feedback_agent' AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM self_learning_events WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM self_fix_tasks WHERE evidence_json::text LIKE %s OR title LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM self_build_queue WHERE acceptance_json::text LIKE %s OR title LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM campaign_remediation_executions WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"p83-{token}%",))


def _campaign(token: str) -> str:
    row = execute(
        """
        INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
        VALUES (%s, 'preview_ready', 'QA', 'en', 'dentists', 'contact_form_repair', true)
        RETURNING id
        """,
        (f"p83-{token}",),
    )
    return str(row["id"])


def _execution(token: str, campaign_id: str) -> None:
    execute(
        """
        INSERT INTO campaign_remediation_executions(
          campaign_id, status, executed_count, skipped_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, 'executed', 1, 1, %s, false, false, false, false, false)
        """,
        (
            campaign_id,
            Jsonb(
                {
                    "token": token,
                    "preflight": {"blockers": ["audit_strength_below_70", "mailer_policy_not_ready"]},
                    "actions": [{"action": "improve_audit_evidence", "status": "skipped_review_required"}],
                    "send_mail": False,
                    "live_outreach_allowed": False,
                }
            ),
        ),
    )


def test_campaign_remediation_feedback_records_learning_and_build_items():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        _execution(token, campaign_id)
        _execution(token, campaign_id)
        result = campaign_remediation_feedback(25, repeated_threshold=2)
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert result["blocker_counts"]["audit_strength_below_70"] >= 2
        assert result["learning_count"] >= 2
        assert result["self_build_count"] >= 1
        learning_count = fetch_one("SELECT count(*) AS count FROM self_learning_events WHERE payload_json::text LIKE %s", (f"%{token}%",))["count"]
        assert learning_count >= 1
    finally:
        _cleanup(token)


def test_campaign_remediation_feedback_dedupes_recent_learning():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        _execution(token, campaign_id)
        _execution(token, campaign_id)
        first = campaign_remediation_feedback(25, repeated_threshold=2)
        second = campaign_remediation_feedback(25, repeated_threshold=2)
        assert any(item["status"] == "created" for item in first["learning"])
        assert all(item["status"] in {"existing", "created"} for item in second["learning"])
        assert latest_campaign_remediation_feedback(5)["send_mail"] is False
    finally:
        _cleanup(token)


def test_campaign_remediation_feedback_endpoints_and_agent_are_admin_gated():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _campaign(token)
        _execution(token, campaign_id)
        _execution(token, campaign_id)
        assert client.get("/admin/campaign-remediation/feedback").status_code == 401
        assert client.post("/admin/campaign-remediation/feedback", json={"limit": 25}).status_code == 401
        response = client.post("/admin/campaign-remediation/feedback", json={"limit": 25, "repeated_threshold": 2}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["feedback"]["send_mail"] is False
        history = client.get("/admin/campaign-remediation/feedback", headers=admin_headers())
        assert history.status_code == 200
        agent = run_agent("campaign_remediation_feedback_agent", {"limit": 25, "repeated_threshold": 2})
        assert agent["status"] == "completed"
        assert agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)
