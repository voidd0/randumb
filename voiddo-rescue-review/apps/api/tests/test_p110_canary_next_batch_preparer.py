from __future__ import annotations

import app.canary_next_batch_preparer as preparer_module
from app.autonomous_agents import run_agent
from app.canary_next_batch_preparer import prepare_next_canary_batch_if_ready


def test_next_batch_preparer_noops_until_canary_complete(monkeypatch):
    monkeypatch.setattr(
        preparer_module,
        "canary_scale_plan",
        lambda canary_limit=20, next_batch_limit=40, store=True: {
            "decision": "CONTINUE_CURRENT_CANARY",
            "sent_count": 10,
            "queued_count": 10,
            "blockers": [],
        },
    )
    called = {"stage": False}
    monkeypatch.setattr(preparer_module, "stage_live_outreach_batch", lambda *args, **kwargs: called.update(stage=True))
    result = prepare_next_canary_batch_if_ready(20, 40)
    assert result["decision"] == "NOOP_CANARY_NOT_COMPLETE"
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False
    assert called["stage"] is False


def test_next_batch_preparer_runs_dry_run_only_when_ready(monkeypatch):
    monkeypatch.setattr(
        preparer_module,
        "canary_scale_plan",
        lambda canary_limit=20, next_batch_limit=40, store=True: {
            "decision": "READY_FOR_NEXT_BATCH_DRY_RUN",
            "recommended_next_batch_limit": 40,
            "sent_count": 20,
            "queued_count": 0,
            "blockers": [],
        },
    )
    monkeypatch.setattr(
        preparer_module,
        "stage_live_outreach_batch",
        lambda limit, dry_run=True, requested_by="": {
            "result": {"decision": "BLOCKED", "blockers": ["dry_run_no_messages_staged"], "requested_by": requested_by},
            "send_mail": False,
            "live_outreach_allowed": False,
            "dry_run": dry_run,
            "limit": limit,
        },
    )
    result = prepare_next_canary_batch_if_ready(20, 40)
    assert result["decision"] == "NEXT_BATCH_DRY_RUN_PREPARED"
    assert result["stage"]["dry_run"] is True
    assert result["stage"]["limit"] == 40
    assert result["send_mail"] is False
    assert result["live_outreach_allowed"] is False


def test_next_batch_preparer_agent_is_no_send(monkeypatch):
    import app.autonomous_agents as agents_module

    monkeypatch.setattr(
        agents_module,
        "prepare_next_canary_batch_if_ready",
        lambda canary_limit=20, next_batch_limit=40: {
            "decision": "NOOP_CANARY_NOT_COMPLETE",
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    result = run_agent("canary_next_batch_preparer_agent", {"canary_limit": 20, "next_batch_limit": 40})
    assert result["status"] == "completed"
    assert result["result_json"]["send_mail"] is False
    assert result["result_json"]["live_outreach_allowed"] is False
