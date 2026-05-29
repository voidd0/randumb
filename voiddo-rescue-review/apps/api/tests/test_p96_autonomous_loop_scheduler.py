from __future__ import annotations

from http.client import RemoteDisconnected
import importlib.util
from pathlib import Path

import pytest


def _script_path() -> Path:
    here = Path(__file__).resolve()
    for root in [here.parent, *here.parents]:
        candidate = root / "scripts" / "rescue_autonomous_loop.py"
        if candidate.exists():
            return candidate
    pytest.skip("host rescue_autonomous_loop.py is outside the API image build context", allow_module_level=True)


SCRIPT_PATH = _script_path()
spec = importlib.util.spec_from_file_location("rescue_autonomous_loop", SCRIPT_PATH)
assert spec and spec.loader
loop_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loop_script)


def test_autonomous_loop_summary_stays_no_send_and_no_live_outreach():
    result = {
        "ok": True,
        "loop": {
            "agents": 3,
            "live_outreach": False,
            "runs": [
                {"agent": "reporting_agent", "status": "completed", "result_json": {"send_mail": False, "live_outreach_allowed": False}},
                {"agent": "warmup_agent", "status": "completed", "result_json": {"sent": 0, "send_mail": False, "live_outreach_allowed": False}},
                {"agent": "launch_readiness_scoreboard_agent", "status": "completed", "result_json": {"score": 90}},
            ],
        },
    }
    summary = loop_script.build_summary(result)
    loop_script.assert_safe(summary)
    assert summary["agents"] == 3
    assert summary["completed"] == 3
    assert summary["failed"] == 0
    assert summary["warmup_sent"] == 0
    assert summary["live_outreach_allowed"] is False


def test_autonomous_loop_blocks_live_outreach_signal():
    result = {
        "ok": True,
        "loop": {
            "agents": 1,
            "live_outreach": False,
            "runs": [
                {"agent": "bad_agent", "status": "completed", "result_json": {"live_outreach_allowed": True}},
            ],
        },
    }
    summary = loop_script.build_summary(result)
    try:
        loop_script.assert_safe(summary)
    except RuntimeError as exc:
        assert str(exc) == "daily_loop_reported_live_outreach_permission"
    else:
        raise AssertionError("live outreach permission must fail the scheduler safety gate")


def test_autonomous_loop_allows_live_canary_scoreboard_signal_only():
    result = {
        "ok": True,
        "loop": {
            "agents": 1,
            "live_outreach": False,
            "runs": [
                {
                    "agent": "launch_readiness_scoreboard_agent",
                    "status": "completed",
                    "result_json": {"state": "LIVE_OUTREACH_READY", "send_mail": False, "live_outreach_allowed": True},
                },
            ],
        },
    }
    summary = loop_script.build_summary(result)
    loop_script.assert_safe(summary)
    assert summary["allowed_live_canary_flags"] == 1
    assert summary["live_outreach_flags"] == 0


def test_autonomous_loop_blocks_agent_failures_by_default():
    result = {
        "ok": True,
        "loop": {
            "agents": 1,
            "live_outreach": False,
            "runs": [
                {"agent": "scanner_agent", "status": "failed", "result_json": {}, "error": "boom"},
            ],
        },
    }
    summary = loop_script.build_summary(result)
    try:
        loop_script.assert_safe(summary)
    except RuntimeError as exc:
        assert str(exc) == "daily_loop_agent_failures"
    else:
        raise AssertionError("agent failures must fail the scheduler safety gate")


def test_autonomous_loop_allow_failures_still_blocks_live_permission():
    result = {
        "ok": True,
        "loop": {
            "agents": 2,
            "live_outreach": False,
            "runs": [
                {"agent": "heavy_agent", "status": "failed", "result_json": {"send_mail": False, "live_outreach_allowed": False}},
                {"agent": "bad_agent", "status": "completed", "result_json": {"live_outreach_allowed": True}},
            ],
        },
    }
    summary = loop_script.build_summary(result)
    with pytest.raises(RuntimeError, match="daily_loop_reported_live_outreach_permission"):
        loop_script.assert_safe(summary, allow_agent_failures=True)
    safe_result = {
        "ok": True,
        "loop": {
            "agents": 1,
            "live_outreach": False,
            "runs": [
                {"agent": "heavy_agent", "status": "failed", "result_json": {"send_mail": False, "live_outreach_allowed": False}},
            ],
        },
    }
    loop_script.assert_safe(loop_script.build_summary(safe_result), allow_agent_failures=True)


def test_core_loop_runs_bounded_agent_sequence(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_run_agent(api_base, token, agent, payload, timeout):
        calls.append((agent, payload))
        return {"agent": agent, "status": "completed", "result_json": {"send_mail": False, "live_outreach_allowed": False}}

    monkeypatch.setattr(loop_script, "run_agent", fake_run_agent)
    result = loop_script.run_core_loop("http://api.local", "token", 60)
    summary = loop_script.build_summary(result)
    loop_script.assert_safe(summary)
    assert result["loop"]["mode"] == "core"
    assert len(calls) == len(loop_script.CORE_AGENTS)
    assert calls[0][0] == "mail_throttle_agent"
    assert "inbox_control_signal_hygiene_agent" in [agent for agent, _payload in calls]
    assert "outreach_post_send_observer_agent" in [agent for agent, _payload in calls]
    assert "canary_bounce_recovery_agent" in [agent for agent, _payload in calls]
    assert "outreach_transport_block_hygiene_agent" in [agent for agent, _payload in calls]
    assert "canary_clean_window_forecast_agent" in [agent for agent, _payload in calls]
    assert "canary_resume_plan_agent" in [agent for agent, _payload in calls]
    assert "canary_next_batch_preparer_agent" in [agent for agent, _payload in calls]
    assert "canary_scale_plan_agent" in [agent for agent, _payload in calls]
    assert "lead_supply_buildout_agent" not in [agent for agent, _payload in calls]
    assert [agent for agent, _payload in calls].index("outreach_post_send_observer_agent") < [agent for agent, _payload in calls].index("canary_bounce_recovery_agent")
    assert [agent for agent, _payload in calls].index("canary_bounce_recovery_agent") < [agent for agent, _payload in calls].index("canary_scale_plan_agent")
    assert [agent for agent, _payload in calls].index("canary_clean_window_forecast_agent") < [agent for agent, _payload in calls].index("canary_resume_plan_agent")
    assert [agent for agent, _payload in calls].index("canary_resume_plan_agent") < [agent for agent, _payload in calls].index("canary_next_batch_preparer_agent")
    assert [agent for agent, _payload in calls].index("lead_quality_diagnostics_agent") < [agent for agent, _payload in calls].index("quality_aware_regional_target_plan_agent")
    assert [agent for agent, _payload in calls].index("scout_source_feedback_agent") < [agent for agent, _payload in calls].index("quality_aware_regional_target_plan_agent")
    assert [agent for agent, _payload in calls].index("quality_aware_regional_target_plan_agent") < [agent for agent, _payload in calls].index("post_scan_campaign_cycle_agent")
    assert [agent for agent, _payload in calls].index("post_scan_campaign_cycle_agent") < [agent for agent, _payload in calls].index("outreach_preview_queue_agent")
    assert [agent for agent, _payload in calls].index("outreach_preview_queue_agent") < [agent for agent, _payload in calls].index("campaign_preflight_agent")
    assert [agent for agent, _payload in calls].index("outreach_preview_dedupe_agent") < [agent for agent, _payload in calls].index("campaign_preflight_agent")
    assert [agent for agent, _payload in calls].index("campaign_geo_hygiene_agent") < [agent for agent, _payload in calls].index("campaign_preflight_agent")
    assert [agent for agent, _payload in calls].index("campaign_preflight_orphan_hygiene_agent") < [agent for agent, _payload in calls].index("campaign_preflight_agent")
    assert calls[-1][0] == "mailer_policy_score_agent"


def test_run_agent_retries_transient_connection_reset(monkeypatch):
    calls = {"count": 0}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"run":{"agent":"mail_qa_agent","status":"completed","result_json":{"send_mail":false,"live_outreach_allowed":false}}}'

    def flaky_urlopen(_request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ConnectionResetError("transient")
        return Response()

    monkeypatch.setattr(loop_script, "urlopen", flaky_urlopen)
    result = loop_script.run_agent("http://api.local", "token", "mail_qa_agent", {}, 30)
    assert calls["count"] == 2
    assert result["status"] == "completed"
    assert result["result_json"]["send_mail"] is False


def test_run_agent_uses_in_process_request_not_curl_argv(monkeypatch):
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"run":{"agent":"mail_qa_agent","status":"completed","result_json":{"send_mail":false,"live_outreach_allowed":false}}}'

    def fake_urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["token_header"] = request.headers.get("X-admin-token")
        observed["body"] = request.data
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(loop_script, "urlopen", fake_urlopen)
    result = loop_script.run_agent("http://api.local", "secret-token", "mail_qa_agent", {"limit": 1}, 30)
    assert result["status"] == "completed"
    assert observed["url"] == "http://api.local/admin/agents/mail_qa_agent"
    assert observed["token_header"] == "secret-token"
    assert b'"limit": 1' in observed["body"]
    assert not hasattr(loop_script, "subprocess")


def test_live_canary_control_blocks_without_activation_env(monkeypatch):
    script_path = SCRIPT_PATH.with_name("rescue_live_canary_control.py")
    spec = importlib.util.spec_from_file_location("rescue_live_canary_control", script_path)
    assert spec and spec.loader
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)

    class Args:
        confirm = "START LIVE OUTREACH"
        confirm_send_window = ""
        send_window = False
        apply = False
        limit = 20

    result = control.activate(Args(), {"ALLOW_LIVE_OUTREACH_ACTIVATION": "false"}, "token")
    assert result["status"] == "blocked"
    assert result["blockers"] == ["allow_live_outreach_activation_env_false"]


def test_live_canary_control_does_not_stage_duplicate_when_queue_exists(monkeypatch):
    script_path = SCRIPT_PATH.with_name("rescue_live_canary_control.py")
    spec = importlib.util.spec_from_file_location("rescue_live_canary_control", script_path)
    assert spec and spec.loader
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    calls: list[str] = []

    class Args:
        confirm = "START LIVE OUTREACH"
        confirm_send_window = ""
        send_window = False
        apply = True
        limit = 20

    monkeypatch.setattr(control, "preflight", lambda _token, _limit: {"activation": {"decision": "READY_FOR_OPERATOR_ENV_ACTIVATION", "blockers": []}, "packet": {"status": "ready", "blockers": []}, "plan": {"decision": "READY_NO_SEND_CANARY_WINDOW_PLAN", "blockers": []}})
    monkeypatch.setattr(control, "write_env_updates", lambda _updates: "/tmp/backup.env")
    monkeypatch.setattr(control, "restart_services", lambda _services: None)
    monkeypatch.setattr(control, "live_queue_status", lambda _token, _limit: {"history": {"queued_message_count": 3}})

    def fake_api(path, _token, payload=None, method="POST", timeout=180):
        calls.append(path)
        if path == "/admin/launch-activation/apply":
            return {"activation": {"activation": {"decision": "READY_RECORDED_NO_ENV_CHANGE"}}}
        if path == "/admin/outreach/live-queue/stage":
            raise AssertionError("must not stage when queued messages already exist")
        return {}

    monkeypatch.setattr(control, "api_request", fake_api)
    result = control.activate(Args(), {"ALLOW_LIVE_OUTREACH_ACTIVATION": "true"}, "token")
    assert result["status"] == "applied"
    assert result["staged_decision"] == "SKIPPED_EXISTING_QUEUED_CANARY"
    assert result["existing_queued_message_count"] == 3
    assert "/admin/outreach/live-queue/stage" not in calls
    assert "/admin/launch-activation/apply" in calls


def test_run_loop_retries_remote_disconnected(monkeypatch):
    calls = {"count": 0}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true,"loop":{"agents":0,"runs":[],"live_outreach":false}}'

    def flaky_urlopen(_request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RemoteDisconnected("closed")
        return Response()

    monkeypatch.setattr(loop_script, "urlopen", flaky_urlopen)
    result = loop_script.run_loop("http://api.local", "token", 30)
    assert calls["count"] == 2
    assert result["ok"] is True
    assert result["loop"]["live_outreach"] is False


def test_run_agent_returns_no_send_failure_after_retry_exhaustion(monkeypatch):
    monkeypatch.setattr(loop_script, "urlopen", lambda _request, timeout: (_ for _ in ()).throw(ConnectionResetError("down")))
    result = loop_script.run_agent("http://api.local", "token", "mail_qa_agent", {}, 30, attempts=2)
    assert result["status"] == "failed"
    assert result["error"] == "ConnectionResetError"
    assert result["result_json"]["send_mail"] is False
