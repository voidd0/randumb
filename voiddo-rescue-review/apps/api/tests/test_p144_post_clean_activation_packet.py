from __future__ import annotations

from app.autonomous_agents import run_agent
from app.post_clean_activation_packet import build_post_clean_activation_packet


def test_post_clean_activation_packet_waits_without_send(monkeypatch):
    import app.post_clean_activation_packet as packet

    monkeypatch.setattr(
        packet,
        "canary_clean_window_forecast",
        lambda window_hours=24, store=True: {
            "status": "waiting_clean_window",
            "eligible_after": "2026-05-30T10:31:39+00:00",
            "seconds_remaining": 3600,
            "send_mail": False,
        },
    )
    result = build_post_clean_activation_packet(20, store=False)
    assert result["decision"] == "WAIT_CLEAN_WINDOW"
    assert result["status"] == "not_due"
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False


def test_post_clean_activation_packet_builds_ready_packet_without_send(monkeypatch):
    import app.post_clean_activation_packet as packet

    monkeypatch.setattr(packet, "canary_clean_window_forecast", lambda window_hours=24, store=True: {"status": "clean", "seconds_remaining": 0})
    monkeypatch.setattr(packet, "campaign_preflight_batch", lambda limit=20: {"status": "completed", "campaign_count": 3, "passed_count": 3, "failed_count": 0})
    monkeypatch.setattr(packet, "canary_batch_quality", lambda limit=20, store=True: {"decision": "PASS_CANARY_BATCH_QUALITY", "candidate_count": 20})
    monkeypatch.setattr(packet, "launch_activation_readiness", lambda limit=20: {"decision": "READY_FOR_OPERATOR_ENV_ACTIVATION", "blockers": []})
    monkeypatch.setattr(packet, "build_canary_operator_packet", lambda limit=20, store=True, run_checkout_simulation=False: {"decision": "READY_FOR_REDACTED_CANARY_OPERATOR_REVIEW", "blockers": []})
    monkeypatch.setattr(packet, "live_outreach_queue_candidates", lambda limit=20: {"candidate_count": 20})
    result = build_post_clean_activation_packet(20, store=False)
    assert result["decision"] == "READY_NO_SEND_ACTIVATION_PACKET"
    assert result["status"] == "ready"
    assert result["blockers"] == []
    assert result["campaign_preflight_passed_count"] == 3
    assert result["live_queue_candidate_count"] == 20
    assert result["send_mail"] is False
    assert result["smtp_called"] is False
    assert result["live_outreach_allowed"] is False


def test_post_clean_activation_packet_blocks_incomplete_packet(monkeypatch):
    import app.post_clean_activation_packet as packet

    monkeypatch.setattr(packet, "canary_clean_window_forecast", lambda window_hours=24, store=True: {"status": "clean", "seconds_remaining": 0})
    monkeypatch.setattr(packet, "campaign_preflight_batch", lambda limit=20: {"status": "completed", "campaign_count": 1, "passed_count": 0, "failed_count": 1})
    monkeypatch.setattr(packet, "canary_batch_quality", lambda limit=20, store=True: {"decision": "FAIL_CANARY_BATCH_QUALITY", "candidate_count": 12})
    monkeypatch.setattr(packet, "launch_activation_readiness", lambda limit=20: {"decision": "BLOCKED", "blockers": ["x"]})
    monkeypatch.setattr(packet, "build_canary_operator_packet", lambda limit=20, store=True, run_checkout_simulation=False: {"decision": "BLOCKED_CANARY_OPERATOR_PACKET", "blockers": ["y"]})
    monkeypatch.setattr(packet, "live_outreach_queue_candidates", lambda limit=20: {"candidate_count": 0})
    result = build_post_clean_activation_packet(20, store=False)
    assert result["decision"] == "BLOCKED_NO_SEND_ACTIVATION_PACKET"
    assert "campaign_preflight_not_clean" in result["blockers"]
    assert "live_queue_candidate_count_below_limit" in result["blockers"]
    assert result["send_mail"] is False


def test_post_clean_activation_packet_agent_is_no_send(monkeypatch):
    import app.autonomous_agents as agents

    monkeypatch.setattr(
        agents,
        "build_post_clean_activation_packet",
        lambda limit=20, store=True: {
            "decision": "WAIT_CLEAN_WINDOW",
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
        },
    )
    monkeypatch.setattr(
        agents,
        "_record_agent",
        lambda agent, func: {"agent": agent, "status": "completed", "result_json": func()},
    )
    result = run_agent("post_clean_activation_packet_agent", {"limit": 20})
    assert result["status"] == "completed"
    assert result["result_json"]["send_mail"] is False
    assert result["result_json"]["live_outreach_allowed"] is False
