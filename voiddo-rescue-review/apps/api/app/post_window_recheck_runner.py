from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .clean_window_recheck import post_window_recheck_scheduler
from .p0 import json_safe


DEFAULT_REPORT_PATH = "/app/storage/reports/post_window_recheck_runner_report.md"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _write_report(path: str | Path, result: dict[str, Any]) -> None:
    payload = json_safe(result)
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


def run_post_window_recheck_runner(
    window_hours: int = 24,
    run_recovery_if_due: bool | None = None,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    recovery = _bool_env("POST_WINDOW_RECHECK_RUN_RECOVERY_IF_DUE", True) if run_recovery_if_due is None else run_recovery_if_due
    result = dict(post_window_recheck_scheduler(window_hours=window_hours, run_recovery_if_due=recovery))
    result["live_outreach_allowed"] = False
    result["sends_started"] = False
    result["runner_policy"] = {
        "mode": "readiness_evidence_only",
        "force_warmup": False,
        "force_outreach": False,
        "send_mail": False,
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
