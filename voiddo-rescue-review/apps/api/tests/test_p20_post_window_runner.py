from __future__ import annotations

import json
from pathlib import Path

from app.post_window_recheck_runner import run_post_window_recheck_runner


def test_post_window_runner_not_due_writes_no_send_report(monkeypatch, tmp_path):
    import app.post_window_recheck_runner as runner

    monkeypatch.setattr(
        runner,
        "post_window_recheck_scheduler",
        lambda window_hours=24, run_recovery_if_due=True: {
            "id": "run-not-due",
            "status": "not_due",
            "recheck_due": False,
            "next_safe_at": "2026-05-27T11:19:56+00:00",
            "transition_decision": "WAIT_UNTIL_NEXT_SAFE_AT",
            "live_outreach_allowed": False,
            "sends_started": False,
            "created_at": "2026-05-26T20:40:00+00:00",
        },
    )
    report = tmp_path / "runner.md"
    result = run_post_window_recheck_runner(report_path=report)
    assert result["status"] == "not_due"
    assert result["sends_started"] is False
    assert result["live_outreach_allowed"] is False
    assert result["runner_policy"]["send_mail"] is False
    text = report.read_text()
    assert "readiness evidence only" in text
    assert "WAIT_UNTIL_NEXT_SAFE_AT" in text


def test_post_window_runner_due_ready_still_only_updates_evidence(monkeypatch, tmp_path):
    import app.post_window_recheck_runner as runner

    monkeypatch.setattr(
        runner,
        "post_window_recheck_scheduler",
        lambda window_hours=24, run_recovery_if_due=True: {
            "id": "run-due",
            "status": "recheck_executed",
            "recheck_due": True,
            "next_safe_at": None,
            "transition_decision": "WARMUP_READY_PENDING_NATURAL_TIMER",
            "live_outreach_allowed": False,
            "sends_started": False,
            "created_at": "2026-05-27T12:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        runner,
        "_readiness_bundle",
        lambda limit=20: {
            "status": "ready",
            "blockers": [],
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "sends_started": False,
        },
    )
    result = run_post_window_recheck_runner(report_path=tmp_path / "runner.md")
    assert result["transition_decision"] == "WARMUP_READY_PENDING_NATURAL_TIMER"
    assert result["runner_policy"]["force_warmup"] is False
    assert result["runner_policy"]["force_outreach"] is False
    assert result["readiness_bundle"]["status"] == "ready"
    assert result["readiness_bundle"]["send_mail"] is False


def test_post_window_runner_honors_recovery_env(monkeypatch, tmp_path):
    import app.post_window_recheck_runner as runner

    calls = {}

    def fake_scheduler(window_hours=24, run_recovery_if_due=True):
        calls["window_hours"] = window_hours
        calls["run_recovery_if_due"] = run_recovery_if_due
        return {
            "id": "run-env",
            "status": "not_due",
            "recheck_due": False,
            "next_safe_at": "2026-05-27T11:19:56+00:00",
            "transition_decision": "WAIT_UNTIL_NEXT_SAFE_AT",
            "live_outreach_allowed": False,
            "sends_started": False,
        }

    monkeypatch.setattr(runner, "post_window_recheck_scheduler", fake_scheduler)
    monkeypatch.setenv("POST_WINDOW_RECHECK_RUN_RECOVERY_IF_DUE", "false")
    run_post_window_recheck_runner(window_hours=12, report_path=tmp_path / "runner.md")
    assert calls == {"window_hours": 12, "run_recovery_if_due": False}


def test_post_window_runner_skips_bundle_when_not_due(monkeypatch, tmp_path):
    import app.post_window_recheck_runner as runner

    calls = {"bundle": 0}
    monkeypatch.setattr(
        runner,
        "post_window_recheck_scheduler",
        lambda window_hours=24, run_recovery_if_due=True: {
            "id": "run-not-due",
            "status": "not_due",
            "recheck_due": False,
            "next_safe_at": "2026-05-27T11:19:56+00:00",
            "transition_decision": "WAIT_UNTIL_NEXT_SAFE_AT",
            "live_outreach_allowed": False,
            "sends_started": False,
        },
    )

    def fake_bundle(limit=20):
        calls["bundle"] += 1
        return {"status": "ready", "send_mail": False}

    monkeypatch.setattr(runner, "_readiness_bundle", fake_bundle)
    result = run_post_window_recheck_runner(report_path=tmp_path / "runner.md")
    assert calls["bundle"] == 0
    assert result["readiness_bundle"]["status"] == "not_run"


def test_post_window_runner_readiness_bundle_can_be_disabled(monkeypatch, tmp_path):
    import app.post_window_recheck_runner as runner

    calls = {"bundle": 0}
    monkeypatch.setattr(
        runner,
        "post_window_recheck_scheduler",
        lambda window_hours=24, run_recovery_if_due=True: {
            "id": "run-due",
            "status": "recheck_executed",
            "recheck_due": True,
            "next_safe_at": None,
            "transition_decision": "WARMUP_READY_PENDING_NATURAL_TIMER",
            "live_outreach_allowed": False,
            "sends_started": False,
        },
    )
    monkeypatch.setattr(runner, "_readiness_bundle", lambda limit=20: calls.__setitem__("bundle", calls["bundle"] + 1) or {"status": "ready"})
    result = run_post_window_recheck_runner(run_readiness_bundle_if_due=False, report_path=tmp_path / "runner.md")
    assert calls["bundle"] == 0
    assert result["readiness_bundle"]["reason"] == "not_due_or_disabled"
    assert result["runner_policy"]["readiness_bundle_enabled"] is False


def test_post_window_readiness_bundle_summarizes_no_send(monkeypatch):
    import app.post_window_recheck_runner as runner

    monkeypatch.setattr(
        runner,
        "campaign_preflight_batch",
        lambda limit=20: {"status": "completed", "campaign_count": 2, "passed_count": 2, "failed_count": 0},
    )
    monkeypatch.setattr(
        runner,
        "canary_batch_quality",
        lambda limit=20, store=True: {"decision": "PASS_CANARY_BATCH_QUALITY", "candidate_count": 20},
    )
    monkeypatch.setattr(
        runner,
        "launch_activation_readiness",
        lambda limit=20: {"decision": "READY_FOR_OPERATOR_ENV_ACTIVATION", "blockers": []},
    )
    monkeypatch.setattr(
        runner,
        "build_canary_operator_packet",
        lambda limit=20, store=True, run_checkout_simulation=False: {
            "decision": "READY_FOR_REDACTED_CANARY_OPERATOR_REVIEW",
            "blockers": [],
        },
    )
    bundle = runner._readiness_bundle(20)
    assert bundle["status"] == "ready"
    assert bundle["next_action"] == "operator_activation_packet_ready_no_env_change"
    assert bundle["send_mail"] is False
    assert bundle["smtp_called"] is False
    assert bundle["live_outreach_allowed"] is False


def test_post_window_runner_source_is_no_send():
    source = Path(__file__).resolve().parents[1] / "app" / "post_window_recheck_runner.py"
    text = source.read_text()
    assert "post_window_recheck_scheduler" in text
    assert "run_warmup_calendar_due" not in text
    assert "FIRST_LIVE_SEND_FLAG" not in text
    assert "send_outreach" not in text.lower()
    assert '"send_mail": False' in text


def test_post_window_report_json_is_parseable(monkeypatch, tmp_path):
    import app.post_window_recheck_runner as runner

    monkeypatch.setattr(
        runner,
        "post_window_recheck_scheduler",
        lambda window_hours=24, run_recovery_if_due=True: {
            "id": "run-json",
            "status": "not_due",
            "recheck_due": False,
            "next_safe_at": "2026-05-27T11:19:56+00:00",
            "transition_decision": "WAIT_UNTIL_NEXT_SAFE_AT",
            "live_outreach_allowed": False,
            "sends_started": False,
        },
    )
    report = tmp_path / "runner.md"
    run_post_window_recheck_runner(report_path=report)
    block = report.read_text().split("```json", 1)[1].split("```", 1)[0]
    parsed = json.loads(block)
    assert parsed["live_outreach_allowed"] is False
    assert parsed["sends_started"] is False
