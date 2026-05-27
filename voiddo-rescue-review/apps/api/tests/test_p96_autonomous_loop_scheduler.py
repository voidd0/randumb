from __future__ import annotations

import importlib.util
from pathlib import Path


def _script_path() -> Path:
    here = Path(__file__).resolve()
    for root in [here.parent, *here.parents]:
        candidate = root / "scripts" / "rescue_autonomous_loop.py"
        if candidate.exists():
            return candidate
    raise AssertionError("rescue_autonomous_loop.py not found")


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
