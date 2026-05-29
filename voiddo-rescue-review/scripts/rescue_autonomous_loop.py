#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from http.client import RemoteDisconnected
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_ENV = Path("/opt/voiddo-rescue/.env")
DEFAULT_LOCK = Path("/tmp/voiddo-rescue-autonomous-loop.lock")

CORE_AGENTS: tuple[tuple[str, dict], ...] = (
    ("mail_throttle_agent", {}),
    ("mail_qa_agent", {}),
    ("mailer_status_agent", {}),
    ("mail_signal_learning_agent", {}),
    ("studio_mail_monitor_health_agent", {"max_age_minutes": 15}),
    ("studio_mail_monitor_agent", {"limit": 20}),
    ("clean_window_recheck_agent", {}),
    ("post_window_recheck_agent", {}),
    ("warmup_block_recovery_snapshot_agent", {"limit": 50}),
    ("warmup_post_send_observer_agent", {"limit": 10}),
    ("scanner_stale_recovery_agent", {"limit": 10, "older_than_minutes": 15, "dry_run": False}),
    ("scanner_completion_watch_agent", {"limit": 100, "min_new_completed": 1, "dry_run": False}),
    ("lead_quality_diagnostics_agent", {"limit": 500}),
    ("scout_source_feedback_agent", {"limit": 500, "dry_run": False}),
    ("quality_aware_regional_target_plan_agent", {"limit_targets": 5}),
    ("post_scan_campaign_cycle_agent", {"limit": 120, "dry_run": False}),
    ("outreach_preview_queue_agent", {"limit": 100}),
    ("outreach_preview_dedupe_agent", {"limit": 500, "apply": True}),
    ("campaign_geo_hygiene_agent", {"limit": 500, "apply": True}),
    ("campaign_preflight_orphan_hygiene_agent", {"limit": 100, "apply": True}),
    ("campaign_preflight_agent", {"limit": 20}),
    ("scout_campaign_quality_summary_agent", {}),
    ("scout_campaign_quality_regression_guard_agent", {}),
    ("scout_source_readiness_regression_guard_agent", {}),
    ("launch_readiness_scoreboard_agent", {"limit": 25}),
    ("reporting_agent", {}),
    ("autonomous_mailer_executor_agent", {"limit": 10}),
    ("mailer_digest_trend_guard_agent", {}),
    ("mailer_policy_score_agent", {}),
)

FULL_EXTRA_AGENTS: tuple[tuple[str, dict], ...] = (
    (
        "lead_supply_buildout_agent",
        {
            "target_preview_count": 110,
            "canary_count": 20,
            "limit": 120,
            "max_cycles": 1,
            "max_seconds": 75,
            "enrichment_limit": 2,
            "apply": True,
        },
    ),
    ("post_scan_campaign_cycle_agent", {"limit": 120, "dry_run": False}),
    ("canary_batch_quality_agent", {"limit": 20}),
    ("canary_operator_packet_agent", {"limit": 20, "run_checkout_simulation": False}),
    ("canary_send_window_plan_agent", {"limit": 20}),
    ("inbox_integrity_gate_agent", {"window_hours": 24}),
    ("revenue_autonomy_gap_agent", {"target_mrr_cents": 500_000, "approved_preview_target": 110, "apply": True}),
    ("quality_plugin_agent", {}),
    ("visual_qa_agent", {}),
    ("self_audit_agent", {}),
    ("self_closed_loop_agent", {}),
    ("self_fix_agent", {}),
    ("self_learning_agent", {}),
    ("self_building_agent", {}),
    ("self_development_executor_agent", {"limit": 3, "execute_safe_auto": True}),
)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _result_json(row: dict) -> dict:
    value = row.get("result_json") or {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def build_summary(result: dict) -> dict:
    loop = result.get("loop", {}) if isinstance(result, dict) else {}
    runs = loop.get("runs", []) if isinstance(loop, dict) else []
    completed = sum(1 for row in runs if row.get("status") == "completed")
    failed = sum(1 for row in runs if row.get("status") == "failed")
    warmup_sent = 0
    send_mail_flags = 0
    live_flags = 0
    failed_agents: list[str] = []
    for row in runs:
        if row.get("status") == "failed":
            failed_agents.append(str(row.get("agent", "unknown")))
        payload = _result_json(row)
        if payload.get("send_mail") is True:
            send_mail_flags += 1
        if payload.get("live_outreach_allowed") is True:
            live_flags += 1
        if row.get("agent") == "warmup_agent":
            warmup_sent += int(payload.get("sent", 0) or 0)
    live_outreach = bool(loop.get("live_outreach")) if isinstance(loop, dict) else False
    return {
        "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
        "agents": int(loop.get("agents", len(runs)) or len(runs)) if isinstance(loop, dict) else 0,
        "completed": completed,
        "failed": failed,
        "failed_agents": failed_agents[:10],
        "warmup_sent": warmup_sent,
        "send_mail_flags": send_mail_flags,
        "live_outreach": live_outreach,
        "live_outreach_flags": live_flags,
        "live_outreach_allowed": False,
    }


def assert_safe(summary: dict) -> None:
    if not summary.get("ok"):
        raise RuntimeError("daily_loop_api_not_ok")
    if summary.get("live_outreach") is True or int(summary.get("live_outreach_flags", 0)) > 0:
        raise RuntimeError("daily_loop_reported_live_outreach_permission")
    if int(summary.get("failed", 0)) > 0:
        raise RuntimeError("daily_loop_agent_failures")


def run_loop(api_base: str, token: str, timeout: int, attempts: int = 2) -> dict:
    request = Request(
        f"{api_base.rstrip('/')}/admin/daily-loop/run",
        data=b"{}",
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
        method="POST",
    )
    last_error: Exception | None = None
    for _attempt in range(max(1, attempts)):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (ConnectionResetError, TimeoutError, URLError, RemoteDisconnected) as exc:
            last_error = exc
    raise last_error or RuntimeError("daily_loop_request_failed")


def run_agent(api_base: str, token: str, agent: str, payload: dict, timeout: int, attempts: int = 2) -> dict:
    last_error: Exception | None = None
    for _attempt in range(max(1, attempts)):
        try:
            request = Request(
                f"{api_base.rstrip('/')}/admin/agents/{agent}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Admin-Token": token},
                method="POST",
            )
            with urlopen(request, timeout=max(15, timeout)) as response:
                result = json.loads(response.read().decode("utf-8"))
            return result.get("run", {}) if isinstance(result, dict) else {}
        except (ConnectionResetError, TimeoutError, URLError, RemoteDisconnected, json.JSONDecodeError) as exc:
            last_error = exc
    return {
        "agent": agent,
        "status": "failed",
        "error": type(last_error).__name__ if last_error else "agent_request_failed",
        "result_json": {"send_mail": False, "live_outreach_allowed": False},
    }


def run_core_loop(api_base: str, token: str, timeout: int) -> dict:
    per_agent_timeout = max(20, min(timeout, 180))
    runs = [run_agent(api_base, token, agent, payload, per_agent_timeout) for agent, payload in CORE_AGENTS]
    return {"ok": True, "loop": {"agents": len(runs), "runs": runs, "live_outreach": False, "mode": "core"}}


def run_bounded_full_loop(api_base: str, token: str, timeout: int) -> dict:
    per_agent_timeout = max(20, min(timeout, 180))
    agents = (*CORE_AGENTS, *FULL_EXTRA_AGENTS)
    runs = [run_agent(api_base, token, agent, payload, per_agent_timeout) for agent, payload in agents]
    return {"ok": True, "loop": {"agents": len(runs), "runs": runs, "live_outreach": False, "mode": "full_bounded"}}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Vøiddo Rescue no-send autonomous operating loop.")
    parser.add_argument("--api-base", default="http://127.0.0.1:18082")
    parser.add_argument("--env", default=str(DEFAULT_ENV))
    parser.add_argument("--lock", default=str(DEFAULT_LOCK))
    parser.add_argument("--mode", choices=["core", "full"], default="full")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--allow-agent-failures", action="store_true")
    args = parser.parse_args()

    env = load_env(Path(args.env))
    token = os.environ.get("ADMIN_AUTH_TOKEN") or env.get("ADMIN_AUTH_TOKEN")
    if not token:
        raise SystemExit("ADMIN_AUTH_TOKEN missing")

    lock_path = Path(args.lock)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_handle = lock_path.open("w")
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "status": "skipped",
                        "reason": "already_running",
                        "live_outreach_allowed": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.mode == "core":
            result = run_core_loop(args.api_base, token, max(30, args.timeout))
        else:
            result = run_bounded_full_loop(args.api_base, token, max(30, args.timeout))
        summary = build_summary(result)
        summary["mode"] = args.mode
        if args.allow_agent_failures and int(summary.get("failed", 0)) > 0:
            summary["agent_failures_allowed"] = True
        else:
            assert_safe(summary)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (RuntimeError, URLError, TimeoutError, RemoteDisconnected) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": type(exc).__name__,
                    "reason": str(exc),
                    "live_outreach_allowed": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
