from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

import app.self_development as dev_module
from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.self_development import run_self_development_cycle


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def cleanup(token: str) -> None:
    execute("DELETE FROM self_operating_cycles WHERE scope = 'self_development_executor' AND result_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM self_build_queue WHERE title LIKE %s OR acceptance_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM self_fix_tasks WHERE title LIKE %s OR evidence_json::text LIKE %s", (f"%{token}%", f"%{token}%"))


def test_self_development_dedupes_and_closes_resolved_agent_failures(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        execute(
            "INSERT INTO self_build_queue(module, priority, title, acceptance_json) VALUES ('pytest_self_dev', 'P2', %s, %s)",
            (f"Build duplicate {token}", Jsonb([token])),
        )
        execute(
            "INSERT INTO self_build_queue(module, priority, title, acceptance_json) VALUES ('pytest_self_dev', 'P2', %s, %s)",
            (f"Build duplicate {token}", Jsonb([token])),
        )
        execute(
            "INSERT INTO self_fix_tasks(type, priority, title, evidence_json) VALUES ('self_audit_finding', 'P1', %s, %s)",
            (f"1 agent failures in last 24h. {token}", Jsonb({"token": token})),
        )
        execute(
            "INSERT INTO self_fix_tasks(type, priority, title, evidence_json) VALUES ('self_audit_finding', 'P1', %s, %s)",
            (f"1 agent failures in last 24h. {token}", Jsonb({"token": token})),
        )
        monkeypatch.setattr(dev_module, "_count_unrecovered_agent_failures", lambda: 0)

        result = run_self_development_cycle(limit=1, execute_safe_auto=False)

        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert result["dedupe"]["build_duplicates_closed"] >= 1
        fix_statuses = fetch_one(
            """
            SELECT
              count(*) FILTER (WHERE status = 'resolved_current_state') AS resolved,
              count(*) FILTER (WHERE status = 'superseded_duplicate') AS dupes
            FROM self_fix_tasks
            WHERE title LIKE %s
            """,
            (f"%{token}%",),
        )
        assert int(fix_statuses["resolved"] or 0) >= 1
        assert int(fix_statuses["dupes"] or 0) >= 1
    finally:
        cleanup(token)


def test_self_development_executes_safe_lead_supply_item_without_send(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        item = execute(
            "INSERT INTO self_build_queue(module, priority, title, acceptance_json) VALUES ('lead_supply', 'P0', %s, %s) RETURNING id",
            (f"Close revenue autonomy gap: approved preview stockpile below target {token}", Jsonb([token])),
        )
        monkeypatch.setattr(dev_module, "_safe_to_execute", lambda: (True, []))
        monkeypatch.setattr(
            dev_module,
            "lead_supply_buildout",
            lambda **_kwargs: {
                "status": "qa_safe_buildout",
                "send_mail": False,
                "live_outreach_allowed": False,
                "token": token,
            },
        )

        result = run_self_development_cycle(limit=1, execute_safe_auto=True)

        assert result["execution"]["executed"] == 1
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        row = fetch_one("SELECT status, acceptance_json FROM self_build_queue WHERE id = %s", (item["id"],))
        assert row["status"] == "executed_safe_auto"
        assert row["acceptance_json"]["self_development_execution"]["live_outreach_allowed"] is False
    finally:
        cleanup(token)


def test_self_development_closes_resolved_campaign_readiness_items(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        build = execute(
            "INSERT INTO self_build_queue(module, priority, title, acceptance_json) VALUES ('campaign_readiness', 'P1', %s, %s) RETURNING id",
            (f"Prevent recurring campaign economics blocked {token}", Jsonb([token])),
        )
        fix = execute(
            "INSERT INTO self_fix_tasks(type, priority, title, evidence_json) VALUES ('closed_loop_finding', 'P1', %s, %s) RETURNING id",
            (f"Resolve scout quality not pass {token}", Jsonb({"token": token})),
        )
        monkeypatch.setattr(
            dev_module,
            "_campaign_launch_evidence",
            lambda: {
                "resolved": True,
                "reason": "current_canary_launch_gates_pass",
                "activation_decision": "READY_FOR_OPERATOR_ENV_ACTIVATION",
                "canary_quality_decision": "PASS_CANARY_BATCH_QUALITY",
                "send_mail": False,
                "live_outreach_allowed": False,
            },
        )

        result = run_self_development_cycle(limit=1, execute_safe_auto=False)

        assert result["resolved"]["campaign_readiness_build_items_closed"] >= 1
        assert result["resolved"]["campaign_readiness_fix_tasks_closed"] >= 1
        build_row = fetch_one("SELECT status, acceptance_json FROM self_build_queue WHERE id = %s", (build["id"],))
        fix_row = fetch_one("SELECT status, evidence_json FROM self_fix_tasks WHERE id = %s", (fix["id"],))
        assert build_row["status"] == "resolved_current_state"
        assert fix_row["status"] == "resolved_current_state"
        assert build_row["acceptance_json"]["self_development_resolution"]["live_outreach_allowed"] is False
        assert fix_row["evidence_json"]["self_development_resolution"]["send_mail"] is False
    finally:
        cleanup(token)


def test_self_development_closes_agent_failure_build_items_when_recovered(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        build = execute(
            "INSERT INTO self_build_queue(module, priority, title, acceptance_json) VALUES ('agent_runs', 'P1', %s, %s) RETURNING id",
            (f"Prevent recurring unrecovered agent failure {token}", Jsonb([token])),
        )
        monkeypatch.setattr(dev_module, "_count_unrecovered_agent_failures", lambda: 0)
        result = run_self_development_cycle(limit=1, execute_safe_auto=False)
        assert result["resolved"]["agent_failure_build_items_closed"] >= 1
        build_row = fetch_one("SELECT status, acceptance_json FROM self_build_queue WHERE id = %s", (build["id"],))
        assert build_row["status"] == "resolved_current_state"
        assert build_row["acceptance_json"]["self_development_resolution"]["send_mail"] is False
    finally:
        cleanup(token)


def test_self_development_endpoint_and_agent_are_admin_gated(monkeypatch):
    token = uuid.uuid4().hex[:8]
    monkeypatch.setattr(
        dev_module,
        "run_self_development_cycle",
        lambda *args, **kwargs: {
            "status": f"qa-{token}",
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        },
    )
    assert client.post("/admin/self/development/run", json={"limit": 1}).status_code == 401
    authed = client.post("/admin/self/development/run", json={"limit": 1, "execute_safe_auto": False}, headers=admin_headers())
    assert authed.status_code == 200
    assert authed.json()["cycle"]["live_outreach_allowed"] is False

    agent = run_agent("self_development_executor_agent", {"limit": 1, "execute_safe_auto": False})
    assert agent["status"] == "completed"
    assert agent["result_json"]["live_outreach_allowed"] is False
