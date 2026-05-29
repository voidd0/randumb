from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .campaign_preflight import campaign_preflight_batch
from .canary_batch_quality import canary_batch_quality
from .canary_operator_packet import build_canary_operator_packet
from .clean_window_recheck import post_window_recheck_scheduler
from .launch_activation import launch_activation_readiness
from .p0 import json_safe


DEFAULT_REPORT_PATH = "/app/storage/reports/post_window_recheck_runner_report.md"
SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "sends_started": False,
}


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _write_report(path: str | Path, result: dict[str, Any]) -> None:
    payload = json_safe(result)
    bundle = payload.get("readiness_bundle") or {}
    lines = [
        "# Vøiddo Rescue Post-Window Recheck Runner",
        "",
        f"- status: {payload.get('status')}",
        f"- transition_decision: {payload.get('transition_decision')}",
        f"- recheck_due: {payload.get('recheck_due')}",
        f"- next_safe_at: {payload.get('next_safe_at')}",
        f"- live_outreach_allowed: {payload.get('live_outreach_allowed')}",
        f"- sends_started: {payload.get('sends_started')}",
        f"- created_at: {payload.get('created_at')}",
        "",
        "## Safety",
        "",
        "- This runner performs readiness evidence only.",
        "- It does not enable live outreach.",
        "- It does not force warmup sends.",
        "- It does not send diagnostics, customer mail, or outreach.",
        "",
        "## No-Send Readiness Bundle",
        "",
        f"- status: {bundle.get('status', 'not_run')}",
        f"- activation_decision: {bundle.get('activation_decision')}",
        f"- campaign_preflight_status: {bundle.get('campaign_preflight_status')}",
        f"- campaign_preflight_passed: {bundle.get('campaign_preflight_passed_count')}",
        f"- canary_quality_decision: {bundle.get('canary_quality_decision')}",
        f"- operator_packet_decision: {bundle.get('operator_packet_decision')}",
        f"- bundle_blockers: {', '.join(bundle.get('blockers') or []) if bundle.get('blockers') else 'none'}",
        "",
        "## Result JSON",
        "",
        "```json",
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        "```",
        "",
    ]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines))


def _readiness_bundle(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 20))
    preflight = campaign_preflight_batch(safe_limit)
    quality = canary_batch_quality(safe_limit, store=True)
    activation = launch_activation_readiness(safe_limit)
    packet = build_canary_operator_packet(safe_limit, store=True, run_checkout_simulation=False)
    blockers: list[str] = []
    if preflight.get("status") != "completed" or int(preflight.get("failed_count") or 0) > 0:
        blockers.append("campaign_preflight_not_clean")
    if int(preflight.get("passed_count") or 0) <= 0:
        blockers.append("campaign_preflight_pass_missing")
    if quality.get("decision") != "PASS_CANARY_BATCH_QUALITY":
        blockers.append("canary_quality_not_pass")
    if activation.get("decision") != "READY_FOR_OPERATOR_ENV_ACTIVATION":
        blockers.append("activation_not_ready")
    if packet.get("decision") != "READY_FOR_REDACTED_CANARY_OPERATOR_REVIEW":
        blockers.append("operator_packet_not_ready")
    return json_safe(
        {
            "status": "ready" if not blockers else "blocked",
            "limit": safe_limit,
            "blockers": sorted(set(blockers)),
            "campaign_preflight_status": preflight.get("status"),
            "campaign_preflight_campaign_count": int(preflight.get("campaign_count") or 0),
            "campaign_preflight_passed_count": int(preflight.get("passed_count") or 0),
            "campaign_preflight_failed_count": int(preflight.get("failed_count") or 0),
            "canary_quality_decision": quality.get("decision"),
            "canary_quality_candidate_count": int(quality.get("candidate_count") or 0),
            "activation_decision": activation.get("decision"),
            "activation_blockers": activation.get("blockers") or [],
            "operator_packet_decision": packet.get("decision"),
            "operator_packet_blockers": packet.get("blockers") or [],
            "next_action": "operator_activation_packet_ready_no_env_change" if not blockers else "repair_no_send_readiness_blockers",
            **SAFE_FLAGS,
        }
    )


def run_post_window_recheck_runner(
    window_hours: int = 24,
    run_recovery_if_due: bool | None = None,
    run_readiness_bundle_if_due: bool | None = None,
    readiness_limit: int = 20,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    recovery = _bool_env("POST_WINDOW_RECHECK_RUN_RECOVERY_IF_DUE", True) if run_recovery_if_due is None else run_recovery_if_due
    bundle_enabled = _bool_env("POST_WINDOW_RECHECK_RUN_READINESS_BUNDLE_IF_DUE", True) if run_readiness_bundle_if_due is None else run_readiness_bundle_if_due
    result = dict(post_window_recheck_scheduler(window_hours=window_hours, run_recovery_if_due=recovery))
    bundle = None
    if bundle_enabled and bool(result.get("recheck_due")):
        bundle = _readiness_bundle(readiness_limit)
    result.update(SAFE_FLAGS)
    result["readiness_bundle"] = bundle or {**SAFE_FLAGS, "status": "not_run", "reason": "not_due_or_disabled"}
    result["runner_policy"] = {
        "mode": "readiness_evidence_only",
        "force_warmup": False,
        "force_outreach": False,
        "send_mail": False,
        "smtp_called": False,
        "readiness_bundle_enabled": bundle_enabled,
    }
    target = report_path or os.environ.get("POST_WINDOW_RECHECK_REPORT_PATH", DEFAULT_REPORT_PATH)
    _write_report(target, result)
    result["report_path"] = str(target)
    return json_safe(result)


def main() -> None:
    window_hours = int(os.environ.get("POST_WINDOW_RECHECK_WINDOW_HOURS", "24"))
    result = run_post_window_recheck_runner(window_hours=window_hours)
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
