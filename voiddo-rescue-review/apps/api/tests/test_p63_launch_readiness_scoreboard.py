from __future__ import annotations

import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.launch_readiness_scoreboard as scoreboard_module
from app.autonomous_agents import run_agent
from app.launch_readiness_scoreboard import launch_readiness_scoreboard
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def patch_send_compliance(monkeypatch, decision: str = "PASS", blockers: list[str] | None = None) -> None:
    monkeypatch.setattr(
        scoreboard_module,
        "run_mail_send_compliance_agent",
        lambda write_report=False: {
            "decision": decision,
            "status": "PASS_MAIL_SEND_COMPLIANCE" if decision == "PASS" else "FAIL_MAIL_SEND_COMPLIANCE",
            "blocker_count": len(blockers or []),
            "blockers": blockers or [],
            "outgoing_totals": {"outreach_sent": 0, "warmup_sent": 0, "customer_mail_sent": 0, "deliverability_diagnostic_sent": 0},
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )


def test_launch_readiness_scoreboard_endpoint_requires_auth_and_is_no_send():
    assert client.get("/admin/launch-readiness-scoreboard").status_code == 401
    response = client.get("/admin/launch-readiness-scoreboard", headers=admin_headers())
    assert response.status_code == 200
    payload = response.json()["scoreboard"]
    assert payload["send_mail"] is False
    assert payload["smtp_called"] is False
    assert payload["live_outreach_allowed"] is (payload["state"] == "LIVE_OUTREACH_READY")
    assert payload["raw_recipient_addresses_included"] is False
    assert payload["secrets_included"] is False


def test_launch_readiness_scoreboard_includes_required_evidence_and_reports_runtime_flags():
    result = launch_readiness_scoreboard(5)
    evidence = result["evidence"]
    for key in ["checkout", "mail", "visual", "warmup", "warmup_maturity", "campaigns", "source_operator", "revenue_loop", "buyer_journey", "transport_gate", "mail_send_compliance"]:
        assert key in evidence
    assert isinstance(evidence["settings"]["outreach_paused"], bool)
    assert isinstance(evidence["settings"]["first_live_send_flag"], bool)
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is (result["state"] == "LIVE_OUTREACH_READY")


def test_launch_readiness_scoreboard_can_reach_preview_state_but_not_live_without_flags(monkeypatch):
    settings = SimpleNamespace(
        global_kill_switch=False,
        scanning_paused=True,
        outreach_dry_run=True,
        outreach_paused=True,
        auto_replies_paused=True,
        first_live_send_flag=False,
        paddle_provisioning_paused=True,
    )
    monkeypatch.setattr(scoreboard_module, "get_settings", lambda: settings)
    patch_send_compliance(monkeypatch)
    monkeypatch.setattr(scoreboard_module, "checkout_config_status", lambda _: {"ready": True, "missing_price_keys": []})
    monkeypatch.setattr(scoreboard_module, "latest_decision", lambda table: "PASS")
    monkeypatch.setattr(
        scoreboard_module,
        "mail_signal_summary",
        lambda hours=24: {"window_hours": hours, "items": [], "bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0},
    )
    monkeypatch.setattr(
        scoreboard_module,
        "warmup_calendar_health",
        lambda: {"scheduled_total": 10, "sent_today": 0, "due_now": 0, "blocked_today": 0},
    )
    monkeypatch.setattr(
        scoreboard_module,
        "warmup_domain_maturity_status",
        lambda settings=None: {"allowed": True, "warmup_sent_count": 5, "legacy_warmup_event_count": 0, "maturity_source": "warmup_schedule_sent", "blockers": []},
    )
    monkeypatch.setattr(
        scoreboard_module,
        "latest_quality_summary",
        lambda: {
            "all_pass": True,
            "blockers": [],
            "runs": [
                {"tool": "huanshu", "status": "PASS"},
                {"tool": "axe-core-playwright", "status": "PASS"},
                {"tool": "pa11y", "status": "PASS"},
                {"tool": "lighthouse-ci", "status": "PASS"},
            ],
        },
    )
    monkeypatch.setattr(
        scoreboard_module,
        "mailer_policy_score",
        lambda: {"score": 97, "decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "blockers": []},
    )
    monkeypatch.setattr(scoreboard_module, "latest_mailer_policy_score_history", lambda limit=3: {"latest_decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"})
    monkeypatch.setattr(scoreboard_module, "latest_preview_transport_gate_status", lambda: {"allowed": False, "reason": "outreach_dry_run_enabled", "checks": {"has_unsubscribe": True, "unsubscribe_one_click_ready": True, "html_body_ready": True}, "source": "latest_preview_outreach_message"})
    monkeypatch.setattr(
        scoreboard_module,
        "revenue_loop_snapshot",
        lambda limit=25: {"launch_readiness_state": "CHECKOUT_READY_NOT_WARMED", "scanner": {"audit_count": 1}, "customers": {"customer_count": 1, "payment_count": 1, "fix_request_count": 1}},
    )
    monkeypatch.setattr(
        scoreboard_module,
        "source_campaign_operator_snapshot",
        lambda limit=25: {"candidate_count": 1, "queued_or_running_runs": [], "scanner_jobs": {"completed": 1}},
    )
    monkeypatch.setattr(
        scoreboard_module,
        "campaign_control_room_snapshot",
        lambda limit=25, threshold=70: {"candidate_count": 1, "ready_candidate_count": 1, "segment_count": 1},
    )
    monkeypatch.setattr(
        scoreboard_module,
        "buyer_journey_readiness_scoreboard",
        lambda: {"campaign_preview_count": 1, "live_outreach_sent_count": 0, "warmup_sent_count": 0},
    )
    monkeypatch.setattr(scoreboard_module, "_count", lambda sql, params=(): 0)

    result = launch_readiness_scoreboard(5)
    assert result["blocker_count"] == 0
    assert result["state"] in {"WARMUP_SCHEDULED_NO_OUTREACH", "PREVIEW_PIPELINE_READY_NO_OUTREACH"}
    assert result["state"] != "LIVE_OUTREACH_READY"
    assert result["live_outreach_allowed"] is False
    assert result["send_mail"] is False
    assert result["evidence"]["transport_gate"]["source"] == "latest_preview_outreach_message"
    assert result["evidence"]["transport_gate"]["checks"]["unsubscribe_one_click_ready"] is True


def test_launch_readiness_scoreboard_can_reach_live_state_when_all_live_flags_and_transport_pass(monkeypatch):
    settings = SimpleNamespace(
        global_kill_switch=False,
        scanning_paused=False,
        outreach_dry_run=False,
        outreach_paused=False,
        auto_replies_paused=True,
        first_live_send_flag=True,
        paddle_provisioning_paused=False,
    )
    monkeypatch.setattr(scoreboard_module, "get_settings", lambda: settings)
    patch_send_compliance(monkeypatch)
    monkeypatch.setattr(scoreboard_module, "checkout_config_status", lambda _: {"ready": True, "missing_price_keys": []})
    monkeypatch.setattr(scoreboard_module, "latest_decision", lambda table: "PASS")
    monkeypatch.setattr(
        scoreboard_module,
        "mail_signal_summary",
        lambda hours=24: {"window_hours": hours, "items": [], "bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0},
    )
    monkeypatch.setattr(scoreboard_module, "warmup_calendar_health", lambda: {"scheduled_total": 10, "sent_today": 5, "due_now": 0, "blocked_today": 0})
    monkeypatch.setattr(scoreboard_module, "warmup_domain_maturity_status", lambda settings=None: {"allowed": True, "warmup_sent_count": 5, "legacy_warmup_event_count": 0, "maturity_source": "warmup_schedule_sent", "blockers": []})
    monkeypatch.setattr(
        scoreboard_module,
        "latest_quality_summary",
        lambda: {
            "all_pass": True,
            "blockers": [],
            "runs": [
                {"tool": "huanshu", "status": "PASS"},
                {"tool": "axe-core-playwright", "status": "PASS"},
                {"tool": "pa11y", "status": "PASS"},
                {"tool": "lighthouse-ci", "status": "PASS"},
            ],
        },
    )
    monkeypatch.setattr(scoreboard_module, "mailer_policy_score", lambda: {"score": 100, "decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "blockers": []})
    monkeypatch.setattr(scoreboard_module, "latest_mailer_policy_score_history", lambda limit=3: {"latest_decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"})
    monkeypatch.setattr(scoreboard_module, "latest_preview_transport_gate_status", lambda: {"allowed": True, "reason": "allowed", "checks": {"has_unsubscribe": True, "unsubscribe_one_click_ready": True, "html_body_ready": True}, "source": "latest_preview_outreach_message"})
    monkeypatch.setattr(scoreboard_module, "revenue_loop_snapshot", lambda limit=25: {"launch_readiness_state": "PREVIEW_PIPELINE_READY_NO_OUTREACH", "scanner": {"audit_count": 1}, "customers": {"customer_count": 1, "payment_count": 1, "fix_request_count": 1}})
    monkeypatch.setattr(scoreboard_module, "source_campaign_operator_snapshot", lambda limit=25: {"candidate_count": 1, "queued_or_running_runs": [], "scanner_jobs": {"completed": 1}})
    monkeypatch.setattr(scoreboard_module, "campaign_control_room_snapshot", lambda limit=25, threshold=70: {"candidate_count": 1, "ready_candidate_count": 1, "segment_count": 1})
    monkeypatch.setattr(scoreboard_module, "buyer_journey_readiness_scoreboard", lambda: {"campaign_preview_count": 1, "live_outreach_sent_count": 0, "warmup_sent_count": 5})
    monkeypatch.setattr(scoreboard_module, "_count", lambda sql, params=(): 0)

    result = launch_readiness_scoreboard(5)
    assert result["blocker_count"] == 0
    assert result["state"] == "LIVE_OUTREACH_READY"
    assert result["live_outreach_allowed"] is True


def test_launch_readiness_scoreboard_blocks_mail_send_compliance_failure(monkeypatch):
    settings = SimpleNamespace(
        global_kill_switch=False,
        scanning_paused=False,
        outreach_dry_run=False,
        outreach_paused=False,
        auto_replies_paused=True,
        first_live_send_flag=True,
        paddle_provisioning_paused=False,
    )
    monkeypatch.setattr(scoreboard_module, "get_settings", lambda: settings)
    patch_send_compliance(monkeypatch, "FAIL_BLOCK_SEND", ["outreach_sent_missing_signed_unsubscribe"])
    monkeypatch.setattr(scoreboard_module, "checkout_config_status", lambda _: {"ready": True, "missing_price_keys": []})
    monkeypatch.setattr(scoreboard_module, "latest_decision", lambda table: "PASS")
    monkeypatch.setattr(scoreboard_module, "mail_signal_summary", lambda hours=24: {"window_hours": hours, "items": [], "bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0})
    monkeypatch.setattr(scoreboard_module, "warmup_calendar_health", lambda: {"scheduled_total": 10, "sent_today": 5, "due_now": 0, "blocked_today": 0})
    monkeypatch.setattr(scoreboard_module, "warmup_domain_maturity_status", lambda settings=None: {"allowed": True, "warmup_sent_count": 5, "legacy_warmup_event_count": 0, "maturity_source": "warmup_schedule_sent", "blockers": []})
    monkeypatch.setattr(scoreboard_module, "latest_quality_summary", lambda: {"all_pass": True, "blockers": [], "runs": [{"tool": "huanshu", "status": "PASS"}, {"tool": "axe-core-playwright", "status": "PASS"}, {"tool": "pa11y", "status": "PASS"}, {"tool": "lighthouse-ci", "status": "PASS"}]})
    monkeypatch.setattr(scoreboard_module, "mailer_policy_score", lambda: {"score": 100, "decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "blockers": []})
    monkeypatch.setattr(scoreboard_module, "latest_mailer_policy_score_history", lambda limit=3: {"latest_decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"})
    monkeypatch.setattr(scoreboard_module, "latest_preview_transport_gate_status", lambda: {"allowed": True, "reason": "allowed", "checks": {"has_unsubscribe": True, "unsubscribe_one_click_ready": True, "html_body_ready": True}, "source": "latest_preview_outreach_message"})
    monkeypatch.setattr(scoreboard_module, "revenue_loop_snapshot", lambda limit=25: {"launch_readiness_state": "PREVIEW_PIPELINE_READY_NO_OUTREACH", "scanner": {"audit_count": 1}, "customers": {"customer_count": 1, "payment_count": 1, "fix_request_count": 1}})
    monkeypatch.setattr(scoreboard_module, "source_campaign_operator_snapshot", lambda limit=25: {"candidate_count": 1, "queued_or_running_runs": [], "scanner_jobs": {"completed": 1}})
    monkeypatch.setattr(scoreboard_module, "campaign_control_room_snapshot", lambda limit=25, threshold=70: {"candidate_count": 1, "ready_candidate_count": 1, "segment_count": 1})
    monkeypatch.setattr(scoreboard_module, "buyer_journey_readiness_scoreboard", lambda: {"campaign_preview_count": 1, "live_outreach_sent_count": 0, "warmup_sent_count": 5})
    monkeypatch.setattr(scoreboard_module, "_count", lambda sql, params=(): 0)

    result = launch_readiness_scoreboard(5)
    assert result["state"] != "LIVE_OUTREACH_READY"
    assert result["live_outreach_allowed"] is False
    assert "mail_send_compliance_not_pass" in {item["code"] for item in result["blockers"]}


def test_launch_readiness_scoreboard_blocks_recent_mail_auth_signal(monkeypatch):
    settings = SimpleNamespace(
        global_kill_switch=False,
        scanning_paused=True,
        outreach_dry_run=True,
        outreach_paused=True,
        auto_replies_paused=True,
        first_live_send_flag=False,
        paddle_provisioning_paused=True,
    )
    monkeypatch.setattr(scoreboard_module, "get_settings", lambda: settings)
    patch_send_compliance(monkeypatch)
    monkeypatch.setattr(scoreboard_module, "checkout_config_status", lambda _: {"ready": True, "missing_price_keys": []})
    monkeypatch.setattr(scoreboard_module, "latest_decision", lambda table: "PASS")
    monkeypatch.setattr(
        scoreboard_module,
        "mail_signal_summary",
        lambda hours=24: {
            "window_hours": hours,
            "items": [{"signal_type": "dmarc_failure", "severity": "warning", "count": 1}],
            "bounce_or_dsn_count": 0,
            "rate_limit_count": 0,
            "spam_signal_count": 0,
            "mail_auth_failure_count": 1,
        },
    )
    monkeypatch.setattr(scoreboard_module, "warmup_calendar_health", lambda: {"scheduled_total": 10, "sent_today": 0, "due_now": 0, "blocked_today": 0})
    monkeypatch.setattr(scoreboard_module, "warmup_domain_maturity_status", lambda settings=None: {"allowed": True, "warmup_sent_count": 5, "legacy_warmup_event_count": 0, "maturity_source": "warmup_schedule_sent", "blockers": []})
    monkeypatch.setattr(scoreboard_module, "latest_quality_summary", lambda: {"all_pass": True, "blockers": [], "runs": [{"tool": "huanshu", "status": "PASS"}, {"tool": "axe-core-playwright", "status": "PASS"}, {"tool": "pa11y", "status": "PASS"}, {"tool": "lighthouse-ci", "status": "PASS"}]})
    monkeypatch.setattr(scoreboard_module, "mailer_policy_score", lambda: {"score": 100, "decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "blockers": []})
    monkeypatch.setattr(scoreboard_module, "latest_mailer_policy_score_history", lambda limit=3: {"latest_decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"})
    monkeypatch.setattr(scoreboard_module, "latest_preview_transport_gate_status", lambda: {"allowed": False, "reason": "outreach_dry_run_enabled", "checks": {"has_unsubscribe": True, "unsubscribe_one_click_ready": True, "html_body_ready": True}, "source": "latest_preview_outreach_message"})
    monkeypatch.setattr(scoreboard_module, "revenue_loop_snapshot", lambda limit=25: {"launch_readiness_state": "CHECKOUT_READY_NOT_WARMED", "scanner": {"audit_count": 1}, "customers": {"customer_count": 1, "payment_count": 1, "fix_request_count": 1}})
    monkeypatch.setattr(scoreboard_module, "source_campaign_operator_snapshot", lambda limit=25: {"candidate_count": 1, "queued_or_running_runs": [], "scanner_jobs": {"completed": 1}})
    monkeypatch.setattr(scoreboard_module, "campaign_control_room_snapshot", lambda limit=25, threshold=70: {"candidate_count": 1, "ready_candidate_count": 1, "segment_count": 1})
    monkeypatch.setattr(scoreboard_module, "buyer_journey_readiness_scoreboard", lambda: {"campaign_preview_count": 1, "live_outreach_sent_count": 0, "warmup_sent_count": 5})
    monkeypatch.setattr(scoreboard_module, "_count", lambda sql, params=(): 0)

    result = launch_readiness_scoreboard(5)
    assert result["state"] != "LIVE_OUTREACH_READY"
    assert "recent_mail_auth_failure_signal" in {item["code"] for item in result["blockers"]}


def test_launch_readiness_scoreboard_blocks_inconsistent_live_flags(monkeypatch):
    settings = SimpleNamespace(
        global_kill_switch=False,
        scanning_paused=False,
        outreach_dry_run=False,
        outreach_paused=True,
        auto_replies_paused=True,
        first_live_send_flag=False,
        paddle_provisioning_paused=False,
    )
    monkeypatch.setattr(scoreboard_module, "get_settings", lambda: settings)
    patch_send_compliance(monkeypatch)
    monkeypatch.setattr(scoreboard_module, "checkout_config_status", lambda _: {"ready": True, "missing_price_keys": []})
    monkeypatch.setattr(scoreboard_module, "latest_decision", lambda table: "PASS")
    monkeypatch.setattr(scoreboard_module, "mail_signal_summary", lambda hours=24: {"window_hours": hours, "items": [], "bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0})
    monkeypatch.setattr(scoreboard_module, "warmup_calendar_health", lambda: {"scheduled_total": 10, "sent_today": 5, "due_now": 0, "blocked_today": 0})
    monkeypatch.setattr(scoreboard_module, "warmup_domain_maturity_status", lambda settings=None: {"allowed": True, "warmup_sent_count": 5, "legacy_warmup_event_count": 0, "maturity_source": "warmup_schedule_sent", "blockers": []})
    monkeypatch.setattr(scoreboard_module, "latest_quality_summary", lambda: {"all_pass": True, "blockers": [], "runs": [{"tool": "huanshu", "status": "PASS"}, {"tool": "axe-core-playwright", "status": "PASS"}, {"tool": "pa11y", "status": "PASS"}, {"tool": "lighthouse-ci", "status": "PASS"}]})
    monkeypatch.setattr(scoreboard_module, "mailer_policy_score", lambda: {"score": 100, "decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "blockers": []})
    monkeypatch.setattr(scoreboard_module, "latest_mailer_policy_score_history", lambda limit=3: {"latest_decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"})
    monkeypatch.setattr(scoreboard_module, "latest_preview_transport_gate_status", lambda: {"allowed": False, "reason": "live_outreach_not_approved", "checks": {}})
    monkeypatch.setattr(scoreboard_module, "revenue_loop_snapshot", lambda limit=25: {"launch_readiness_state": "PREVIEW_PIPELINE_READY_NO_OUTREACH", "scanner": {"audit_count": 1}, "customers": {"customer_count": 1, "payment_count": 1, "fix_request_count": 1}})
    monkeypatch.setattr(scoreboard_module, "source_campaign_operator_snapshot", lambda limit=25: {"candidate_count": 1, "queued_or_running_runs": [], "scanner_jobs": {"completed": 1}})
    monkeypatch.setattr(scoreboard_module, "campaign_control_room_snapshot", lambda limit=25, threshold=70: {"candidate_count": 1, "ready_candidate_count": 1, "segment_count": 1})
    monkeypatch.setattr(scoreboard_module, "buyer_journey_readiness_scoreboard", lambda: {"campaign_preview_count": 1, "live_outreach_sent_count": 0, "warmup_sent_count": 5})
    monkeypatch.setattr(scoreboard_module, "_count", lambda sql, params=(): 0)

    result = launch_readiness_scoreboard(5)
    assert result["state"] != "LIVE_OUTREACH_READY"
    assert "live_outreach_flags_inconsistent" in {item["code"] for item in result["blockers"]}
    assert result["live_outreach_allowed"] is False


def test_launch_readiness_scoreboard_blocks_unverified_warmup_maturity(monkeypatch):
    settings = SimpleNamespace(
        global_kill_switch=False,
        scanning_paused=True,
        outreach_dry_run=True,
        outreach_paused=True,
        auto_replies_paused=True,
        first_live_send_flag=False,
        paddle_provisioning_paused=True,
    )
    monkeypatch.setattr(scoreboard_module, "get_settings", lambda: settings)
    patch_send_compliance(monkeypatch)
    monkeypatch.setattr(scoreboard_module, "checkout_config_status", lambda _: {"ready": True, "missing_price_keys": []})
    monkeypatch.setattr(scoreboard_module, "latest_decision", lambda table: "PASS")
    monkeypatch.setattr(scoreboard_module, "mail_signal_summary", lambda hours=24: {"window_hours": hours, "items": [], "bounce_or_dsn_count": 0, "rate_limit_count": 0, "spam_signal_count": 0})
    monkeypatch.setattr(scoreboard_module, "warmup_calendar_health", lambda: {"scheduled_total": 10, "sent_today": 0, "due_now": 0, "blocked_today": 0})
    monkeypatch.setattr(
        scoreboard_module,
        "warmup_domain_maturity_status",
        lambda settings=None: {
            "allowed": False,
            "warmup_sent_count": 0,
            "legacy_warmup_event_count": 5,
            "maturity_source": "warmup_schedule_sent",
            "blockers": ["warmup_clean_send_count_below_threshold"],
        },
    )
    monkeypatch.setattr(
        scoreboard_module,
        "latest_quality_summary",
        lambda: {
            "all_pass": True,
            "blockers": [],
            "runs": [
                {"tool": "huanshu", "status": "PASS"},
                {"tool": "axe-core-playwright", "status": "PASS"},
                {"tool": "pa11y", "status": "PASS"},
                {"tool": "lighthouse-ci", "status": "PASS"},
            ],
        },
    )
    monkeypatch.setattr(scoreboard_module, "mailer_policy_score", lambda: {"score": 100, "decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW", "blockers": []})
    monkeypatch.setattr(scoreboard_module, "latest_mailer_policy_score_history", lambda limit=3: {"latest_decision": "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW"})
    monkeypatch.setattr(scoreboard_module, "latest_preview_transport_gate_status", lambda: {"allowed": False, "reason": "outreach_dry_run_enabled", "checks": {"has_unsubscribe": True, "unsubscribe_one_click_ready": True, "html_body_ready": True}})
    monkeypatch.setattr(scoreboard_module, "revenue_loop_snapshot", lambda limit=25: {"launch_readiness_state": "CHECKOUT_READY_NOT_WARMED", "scanner": {"audit_count": 1}, "customers": {"customer_count": 1, "payment_count": 1, "fix_request_count": 1}})
    monkeypatch.setattr(scoreboard_module, "source_campaign_operator_snapshot", lambda limit=25: {"candidate_count": 1, "queued_or_running_runs": [], "scanner_jobs": {"completed": 1}})
    monkeypatch.setattr(scoreboard_module, "campaign_control_room_snapshot", lambda limit=25, threshold=70: {"candidate_count": 1, "ready_candidate_count": 1, "segment_count": 1})
    monkeypatch.setattr(scoreboard_module, "buyer_journey_readiness_scoreboard", lambda: {"campaign_preview_count": 1, "live_outreach_sent_count": 0, "warmup_sent_count": 5})
    monkeypatch.setattr(scoreboard_module, "_count", lambda sql, params=(): 0)

    result = launch_readiness_scoreboard(5)
    assert result["state"] == "WARMUP_SCHEDULED_NO_OUTREACH"
    assert "warmup_maturity_not_verified" in {item["code"] for item in result["blockers"]}
    assert result["evidence"]["warmup_maturity"]["legacy_warmup_event_count"] == 5
    assert result["live_outreach_allowed"] is False


def test_launch_readiness_scoreboard_agent_runs_no_send():
    run = run_agent("launch_readiness_scoreboard_agent", {"limit": 5})
    assert run["status"] == "completed"
    assert run["result_json"]["send_mail"] is False
    assert run["result_json"]["smtp_called"] is False
    assert run["result_json"]["live_outreach_allowed"] is (run["result_json"]["state"] == "LIVE_OUTREACH_READY")
