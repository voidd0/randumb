from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.campaign_remediation import campaign_remediation_plan, execute_campaign_remediation, latest_campaign_remediation_executions, latest_campaign_remediation_plans
from app.db import execute, fetch_one
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM campaign_remediation_plans WHERE plan_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_remediation_executions WHERE result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE agent = 'campaign_remediation_agent' AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM codex_tasks WHERE input_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM campaign_preflight_runs WHERE result_json::text LIKE %s OR campaign_id IN (SELECT id FROM campaigns WHERE name LIKE %s)", (f"%{token}%", f"p82-{token}%"))
    execute("DELETE FROM campaigns WHERE name LIKE %s", (f"p82-{token}%",))


def _failed_preflight(token: str) -> str:
    campaign = execute(
        """
        INSERT INTO campaigns(name, status, country, language, niche, offer_key, dry_run)
        VALUES (%s, 'preview_ready', 'QA', 'en', 'dentists', 'contact_form_repair', true)
        RETURNING id
        """,
        (f"p82-{token}",),
    )
    execute(
        """
        INSERT INTO campaign_preflight_runs(
          campaign_id, status, decision, checked_count, ready_count, blocker_count, result_json,
          send_mail, smtp_called, live_outreach_allowed,
          raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, 'completed', 'FAIL_BLOCK_LAUNCH', 3, 0, 2, %s, false, false, false, false, false)
        """,
        (
            campaign["id"],
            Jsonb(
                {
                    "token": token,
                    "blockers": ["preview_quality_not_pass", "mailer_policy_not_ready"],
                    "quality_blockers_by_code": {"audit_strength_below_70": 3},
                    "send_mail": False,
                    "live_outreach_allowed": False,
                }
            ),
        ),
    )
    return str(campaign["id"])


def test_campaign_remediation_creates_safe_tasks_without_send():
    token = uuid.uuid4().hex[:8]
    try:
        campaign_id = _failed_preflight(token)
        result = campaign_remediation_plan(25, create_tasks=True)
        plan = next(item for item in result["plans"] if item["campaign_id"] == campaign_id)
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert plan["blockers"] == ["preview_quality_not_pass", "mailer_policy_not_ready", "audit_strength_below_70"]
        assert {item["action"] for item in plan["actions"]} >= {"refresh_campaign_preview_quality", "repair_mailer_policy_blockers", "improve_audit_evidence"}
        assert plan["tasks"]
        assert not any("@example" in str(item) for item in result["plans"])
        task_count = fetch_one("SELECT count(*) AS count FROM codex_tasks WHERE input_json::text LIKE %s", (f"%{token}%",))["count"]
        assert task_count >= 3
    finally:
        _cleanup(token)


def test_campaign_remediation_dedupes_open_tasks():
    token = uuid.uuid4().hex[:8]
    try:
        _failed_preflight(token)
        first = campaign_remediation_plan(25, create_tasks=True)
        second = campaign_remediation_plan(25, create_tasks=True)
        assert first["created_task_count"] >= 1
        assert second["created_task_count"] == 0
        assert second["task_count"] >= 1
    finally:
        _cleanup(token)


def test_campaign_remediation_endpoints_and_agent_are_admin_gated():
    token = uuid.uuid4().hex[:8]
    try:
        _failed_preflight(token)
        assert client.get("/admin/campaign-remediation/plans").status_code == 401
        assert client.post("/admin/campaign-remediation/plan", json={"limit": 25}).status_code == 401
        response = client.post("/admin/campaign-remediation/plan", json={"limit": 25, "create_tasks": False}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["remediation"]["send_mail"] is False
        history = client.get("/admin/campaign-remediation/plans", headers=admin_headers())
        assert history.status_code == 200
        assert latest_campaign_remediation_plans(5)["send_mail"] is False
        agent = run_agent("campaign_remediation_agent", {"limit": 25, "create_tasks": False})
        assert agent["status"] == "completed"
        assert agent["result_json"]["live_outreach_allowed"] is False
    finally:
        _cleanup(token)


def test_campaign_remediation_executor_runs_only_safe_actions(monkeypatch):
    import app.campaign_remediation as remediation

    token = uuid.uuid4().hex[:8]
    calls: list[str] = []
    try:
        campaign_id = _failed_preflight(token)
        campaign_remediation_plan(25, create_tasks=False)

        monkeypatch.setattr(remediation, "run_campaign_action", lambda action, campaign_id=None, limit=100, dry_run=False: calls.append(action) or {"status": "completed", "send_mail": False, "live_outreach_allowed": False})
        monkeypatch.setattr(remediation, "campaign_preview_quality_pack", lambda campaign_id, limit=20: calls.append("quality") or {"status": "PASS_PREVIEW_QUALITY", "send_mail": False, "live_outreach_allowed": False})
        monkeypatch.setattr(remediation, "mailer_policy_score", lambda: calls.append("policy") or {"decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "send_mail": False, "live_outreach_allowed": False})
        monkeypatch.setattr(remediation, "campaign_preflight", lambda campaign_id, limit=20: {"decision": "FAIL_BLOCK_LAUNCH", "status": "completed", "blockers": ["mailer_policy_not_ready"], "send_mail": False})

        result = execute_campaign_remediation(25, rerun_preflight=True)
        execution = next(item for item in result["executions"] if item["campaign_id"] == campaign_id)
        assert result["send_mail"] is False
        assert result["timed_out"] is False
        assert result["max_seconds"] == 30
        assert execution["executed_count"] == 2
        assert execution["skipped_count"] == 1
        executed_actions = {item["action"] for item in execution["actions"] if item["status"] == "executed"}
        assert executed_actions == {"refresh_campaign_preview_quality", "repair_mailer_policy_blockers"}
        assert "quality" in calls
        assert "policy" in calls
        skipped = [item for item in execution["actions"] if item["status"].startswith("skipped")]
        assert skipped[0]["risk"] == "MEDIUM_RISK"
        assert latest_campaign_remediation_executions(5)["send_mail"] is False
    finally:
        _cleanup(token)
