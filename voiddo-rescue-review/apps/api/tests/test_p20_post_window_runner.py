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
    result = run_post_window_recheck_runner(report_path=tmp_path / "runner.md")
    assert result["transition_decision"] == "WARMUP_READY_PENDING_NATURAL_TIMER"
    assert result["runner_policy"]["force_warmup"] is False
    assert result["runner_policy"]["force_outreach"] is False


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
