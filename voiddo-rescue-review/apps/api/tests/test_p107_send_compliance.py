from __future__ import annotations

import app.p0 as p0


class LiveSettings:
    outreach_dry_run = False
    outreach_paused = False
    first_live_send_flag = True


def test_transport_gate_requires_huanshu_and_secondary_visual_plugins(monkeypatch):
    monkeypatch.setattr(p0, "get_settings", lambda: LiveSettings())
    monkeypatch.setattr(p0, "effective_pause_state", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(p0, "latest_decision", lambda _table: "PASS")
    monkeypatch.setattr(
        p0,
        "live_outreach_quota_status",
        lambda _email="": {
            "allowed": True,
            "daily_sent": 0,
            "daily_limit": 20,
            "hourly_domain_sent": 0,
            "hourly_domain_limit": 5,
            "blockers": [],
            "raw_recipient_addresses_included": False,
        },
    )
    monkeypatch.setattr(
        p0,
        "visual_design_send_gate_status",
        lambda: {
            "allowed": False,
            "blockers": ["huanshu_not_pass", "quality_plugins_missing"],
            "visual_qa_decision": "PASS",
            "huanshu_status": "FAIL",
            "required_tools": ["huanshu", "axe-core-playwright", "pa11y", "lighthouse-ci", "pixelmatch"],
            "tool_status": {"huanshu": "FAIL"},
            "missing_tools": ["axe-core-playwright", "pa11y", "lighthouse-ci", "pixelmatch"],
            "failing_tools": ["huanshu"],
        },
    )
    result = p0.transport_gate_status(
        {
            "email": "lead@example.com",
            "body": "Public check.\nUnsubscribe: https://go.rescue.voiddo.com/unsubscribe/u_00000000-0000-0000-0000-000000000000.token",
            "html_body": "<!doctype html><html><body>ok</body></html>",
        }
    )
    assert result["allowed"] is False
    assert result["reason"] == "huanshu_not_pass,quality_plugins_missing"
    assert result["checks"]["visual_design_gate"]["huanshu_status"] == "FAIL"


def test_transport_gate_requires_signed_unsubscribe_before_any_send(monkeypatch):
    monkeypatch.setattr(p0, "get_settings", lambda: LiveSettings())
    monkeypatch.setattr(p0, "effective_pause_state", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(p0, "latest_decision", lambda _table: "PASS")
    monkeypatch.setattr(
        p0,
        "live_outreach_quota_status",
        lambda _email="": {
            "allowed": True,
            "daily_sent": 0,
            "daily_limit": 20,
            "hourly_domain_sent": 0,
            "hourly_domain_limit": 5,
            "blockers": [],
            "raw_recipient_addresses_included": False,
        },
    )
    monkeypatch.setattr(
        p0,
        "visual_design_send_gate_status",
        lambda: {
            "allowed": True,
            "blockers": [],
            "visual_qa_decision": "PASS",
            "huanshu_status": "PASS",
            "required_tools": ["huanshu", "axe-core-playwright", "pa11y", "lighthouse-ci", "pixelmatch"],
            "tool_status": {
                "huanshu": "PASS",
                "axe-core-playwright": "PASS",
                "pa11y": "PASS",
                "lighthouse-ci": "PASS_WITH_WARNINGS",
                "pixelmatch": "PASS",
            },
            "missing_tools": [],
            "failing_tools": [],
        },
    )
    result = p0.transport_gate_status(
        {
            "email": "lead@example.com",
            "body": "Public check without opt-out link.",
            "html_body": "<!doctype html><html><body>ok</body></html>",
        }
    )
    assert result["allowed"] is False
    assert result["reason"] == "missing_unsubscribe"
    assert result["checks"]["unsubscribe_one_click_ready"] is False
