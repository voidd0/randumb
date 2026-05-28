from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app.autonomous_agents as agents_module
from app.autonomous_agents import run_agent, run_daily_loop
from app.autonomous_mailer import decide_inbound_mail, decide_outbound_mail, run_autonomous_mailer_cycle
from app.db import fetch_one
from app.economics import calculate_unit_economics, run_economics_audit
from app.main import app
from app.quality_plugins import normalize_quality_tool, quality_plugin_manifest, record_quality_plugin_run
from app.self_operating import queue_self_build, record_learning, run_self_audit, self_operating_summary


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_economics_engine_calculates_margin_and_records_snapshots():
    one = calculate_unit_economics("contact_form_repair")
    assert one["gross_margin_percent"] >= 70
    result = run_economics_audit()
    assert result["products"] >= 6
    assert result["status"] == "pass"


def test_self_audit_records_findings_and_creates_prevention_state():
    result = run_self_audit("pytest_p6")
    assert "audit" in result
    assert isinstance(result["findings"], list)
    summary = self_operating_summary()
    assert int(summary["counts"]["self_audit_runs"]) >= 1


def test_self_learning_and_build_queue_are_persistent():
    learning = record_learning("pytest_signal", "pytest", "Do not repeat this issue.", "Add regression test.", "info")
    build = queue_self_build("pytest_module", "Build safer regression harness", "P3", ["test passes"])
    assert learning["signal_type"] == "pytest_signal"
    assert build["module"] == "pytest_module"


def test_autonomous_mailer_blocks_outbound_by_default():
    decision = decide_outbound_mail({"email": "lead@example.test", "body": "hello"})
    assert decision["status"] == "blocked"
    assert decision["action"] == "do_not_send"


def test_autonomous_mailer_routes_inbound_safely():
    price = decide_inbound_mail("Price?", "Can you send the price?", "audit@voiddorescue.com")
    legal = decide_inbound_mail("Legal", "legal threat", "support@voiddorescue.com")
    assert price["status"] in {"blocked", "ready"}
    assert legal["status"] == "review_required"


def test_autonomous_mailer_cycle_sends_zero():
    result = run_autonomous_mailer_cycle()
    assert result["sent"] == 0
    assert result["outbound"]["status"] == "blocked"


def test_quality_plugin_manifest_has_huanshu_plus_four_plugins():
    manifest = quality_plugin_manifest()
    assert manifest["canonical"] == "huanshu"
    assert len(manifest["additional_plugins"]) >= 4
    run = record_quality_plugin_run("axe-core-playwright", "/", "PASS", 100, [], None)
    assert run["tool"] == "axe-core-playwright"
    assert run["artifact_path"] == ""
    assert normalize_quality_tool("huanshu-local-adapter") == "huanshu"
    huanshu_run = record_quality_plugin_run("huashu-design", "/r/demo", "PASS", 100, [])
    assert huanshu_run["tool"] == "huanshu"


def test_visual_qa_agent_requires_real_huanshu_and_secondary_plugin_evidence(monkeypatch):
    def fake_quality_summary():
        return {
            "all_pass": True,
            "blockers": [],
            "runs": [
                {"tool": "huanshu", "status": "PASS"},
                {"tool": "axe-core-playwright", "status": "PASS"},
                {"tool": "pa11y", "status": "PASS"},
                {"tool": "lighthouse-ci", "status": "PASS_WITH_WARNINGS"},
                {"tool": "pixelmatch", "status": "PASS"},
            ],
        }

    def fake_fetch_one(sql: str, *args):
        if "FROM visual_qa_runs" in sql:
            return {"decision": "PASS", "huanshu_status": "PASS", "target_url": "/admin", "score": 100}
        if "FROM quality_plugin_runs" in sql:
            return {"status": "PASS", "target": "/admin", "score": 100}
        return None

    monkeypatch.setattr(agents_module, "latest_quality_summary", fake_quality_summary)
    monkeypatch.setattr(agents_module, "fetch_one", fake_fetch_one)
    result = agents_module.visual_qa_evidence_snapshot()
    assert result["status"] == "PASS_VISUAL_QA_EVIDENCE"
    assert result["canonical"] == "huanshu"
    assert result["missing_tools"] == []
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False


def test_visual_qa_agent_blocks_missing_huanshu_evidence(monkeypatch):
    monkeypatch.setattr(
        agents_module,
        "latest_quality_summary",
        lambda: {
            "all_pass": True,
            "blockers": [],
            "runs": [
                {"tool": "axe-core-playwright", "status": "PASS"},
                {"tool": "pa11y", "status": "PASS"},
                {"tool": "lighthouse-ci", "status": "PASS"},
                {"tool": "pixelmatch", "status": "PASS"},
            ],
        },
    )
    monkeypatch.setattr(agents_module, "fetch_one", lambda *args, **kwargs: None)
    result = agents_module.visual_qa_evidence_snapshot()
    assert result["decision"] == "FAIL_BLOCK_LAUNCH"
    assert "missing_huanshu" in result["blockers"]
    assert result["latest_huanshu_status"] == "MISSING"


def test_new_agents_record_self_operating_results():
    for agent in ["economics_agent", "autonomous_mailer_agent", "self_audit_agent", "quality_plugin_agent"]:
        result = run_agent(agent)
        assert result["status"] == "completed"
    latest = fetch_one("SELECT count(*) AS count FROM agent_runs WHERE agent IN ('economics_agent', 'autonomous_mailer_agent', 'self_audit_agent', 'quality_plugin_agent')")
    assert int(latest["count"]) >= 4


def test_daily_loop_includes_self_operating_agents_and_no_live_outreach():
    result = run_daily_loop()
    assert result["live_outreach"] is False
    assert result["agents"] >= 9


def test_admin_self_operating_endpoints_require_auth_and_work():
    assert client.get("/admin/self/summary").status_code == 401
    assert client.get("/admin/self/summary", headers=admin_headers()).status_code == 200
    assert client.post("/admin/mailer/autonomous-cycle", headers=admin_headers()).status_code == 200
    assert client.get("/admin/quality/plugins", headers=admin_headers()).status_code == 200
