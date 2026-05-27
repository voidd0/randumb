from __future__ import annotations

from typing import Any

from .billing import checkout_config_status
from .buyer_journey_scenarios import buyer_journey_readiness_scoreboard
from .campaign_control_room import campaign_control_room_snapshot
from .config import get_settings
from .db import fetch_one
from .mailer_control_room import latest_mailer_policy_score_history, mailer_policy_score
from .p0 import json_safe, latest_decision, mail_signal_summary, transport_gate_status, warmup_calendar_health, warmup_domain_maturity_status
from .quality_plugins import latest_quality_summary
from .revenue_loop import revenue_loop_snapshot
from .source_campaign_operator import source_campaign_operator_snapshot


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def _add_blocker(blockers: list[dict[str, Any]], code: str, severity: str = "high", detail: Any = None) -> None:
    item: dict[str, Any] = {"code": code, "severity": severity}
    if detail is not None:
        item["detail"] = detail
    blockers.append(item)


def _visual_quality_evidence() -> dict[str, Any]:
    summary = latest_quality_summary()
    runs = summary.get("runs") or []
    huanshu_runs = [row for row in runs if row.get("tool") == "huanshu"]
    additional_tools = sorted({row.get("tool") for row in runs if row.get("tool") != "huanshu" and row.get("tool")})
    return {
        "visual_qa_decision": latest_decision("visual_qa_runs"),
        "huanshu_latest_status": huanshu_runs[-1].get("status") if huanshu_runs else "MISSING",
        "huanshu_run_count": len(huanshu_runs),
        "additional_tool_count": len(additional_tools),
        "additional_tools": additional_tools,
        "quality_plugins_all_pass": bool(summary.get("all_pass")),
        "quality_plugin_blocker_count": len(summary.get("blockers") or []),
    }


def _state(score: int, blockers: list[dict[str, Any]], evidence: dict[str, Any]) -> str:
    settings = evidence["settings"]
    if blockers:
        if any(row.get("code") == "warmup_maturity_not_verified" for row in blockers) and evidence["checkout"]["ready"]:
            return "WARMUP_SCHEDULED_NO_OUTREACH"
        if evidence["checkout"]["ready"] and evidence["mail"]["mail_qa_decision"] == "PASS":
            return "CHECKOUT_READY_NOT_WARMED"
        return "NOT_LAUNCH_READY"
    if not evidence["warmup_maturity"].get("allowed") and int(evidence["warmup"].get("scheduled_total", 0) or 0) > 0:
        return "WARMUP_SCHEDULED_NO_OUTREACH"
    if int(evidence["campaigns"].get("ready_candidate_count", 0) or 0) > 0:
        return "PREVIEW_PIPELINE_READY_NO_OUTREACH"
    if (
        score >= 95
        and not settings["outreach_dry_run"]
        and not settings["outreach_paused"]
        and settings["first_live_send_flag"]
        and evidence["transport_gate"].get("allowed") is True
    ):
        return "LIVE_OUTREACH_READY"
    return "CHECKOUT_READY_NOT_WARMED" if evidence["checkout"]["ready"] else "NOT_LAUNCH_READY"


def launch_readiness_scoreboard(limit: int = 25) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    settings = get_settings()
    checkout = checkout_config_status(settings)
    revenue = revenue_loop_snapshot(safe_limit)
    source_operator = source_campaign_operator_snapshot(min(safe_limit, 25))
    campaigns = campaign_control_room_snapshot(safe_limit, 70)
    buyer_journey = buyer_journey_readiness_scoreboard()
    warmup = warmup_calendar_health()
    warmup_maturity = warmup_domain_maturity_status(settings)
    signals = mail_signal_summary(24)
    visual = _visual_quality_evidence()
    policy_score = mailer_policy_score()
    policy_history = latest_mailer_policy_score_history(3)
    transport = transport_gate_status(
        {
            "email": "redacted@example.test",
            "body": "Public non-invasive website check.\nUnsubscribe: https://go.rescue.voiddo.com/unsubscribe/test",
        }
    )
    settings_evidence = {
        "global_kill_switch": settings.global_kill_switch,
        "scanning_paused": settings.scanning_paused,
        "outreach_dry_run": settings.outreach_dry_run,
        "outreach_paused": settings.outreach_paused,
        "auto_replies_paused": settings.auto_replies_paused,
        "first_live_send_flag": settings.first_live_send_flag,
        "paddle_provisioning_paused": settings.paddle_provisioning_paused,
    }
    mail = {
        "mail_qa_decision": latest_decision("mail_qa_runs"),
        "signals": {
            "bounce_or_dsn_count": int(signals.get("bounce_or_dsn_count", 0) or 0),
            "rate_limit_count": int(signals.get("rate_limit_count", 0) or 0),
            "spam_signal_count": int(signals.get("spam_signal_count", 0) or 0),
            "window_hours": signals.get("window_hours", 24),
        },
        "policy_score": policy_score,
        "policy_history_latest_decision": policy_history.get("latest_decision"),
    }

    blockers: list[dict[str, Any]] = []
    score = 100
    if settings.global_kill_switch:
        _add_blocker(blockers, "global_kill_switch_enabled", "critical")
        score -= 50
    if not checkout["ready"]:
        _add_blocker(blockers, "checkout_not_ready", "high", {"missing_price_keys": checkout.get("missing_price_keys", [])})
        score -= 20
    if mail["mail_qa_decision"] != "PASS":
        _add_blocker(blockers, "mail_qa_not_pass", "critical", mail["mail_qa_decision"])
        score -= 25
    if mail["signals"]["bounce_or_dsn_count"] > 0:
        _add_blocker(blockers, "recent_bounce_or_dsn", "high", mail["signals"]["bounce_or_dsn_count"])
        score -= 20
    if mail["signals"]["rate_limit_count"] > 0:
        _add_blocker(blockers, "recent_rate_limit", "high", mail["signals"]["rate_limit_count"])
        score -= 15
    if mail["signals"]["spam_signal_count"] > 0:
        _add_blocker(blockers, "recent_spam_signal", "critical", mail["signals"]["spam_signal_count"])
        score -= 25
    if visual["visual_qa_decision"] != "PASS":
        _add_blocker(blockers, "visual_qa_not_pass", "high", visual["visual_qa_decision"])
        score -= 20
    if visual["huanshu_latest_status"] != "PASS":
        _add_blocker(blockers, "huanshu_not_pass", "high", visual["huanshu_latest_status"])
        score -= 20
    if visual["additional_tool_count"] < 3 or not visual["quality_plugins_all_pass"]:
        _add_blocker(blockers, "secondary_design_plugins_not_pass", "medium", visual)
        score -= 10
    if int(warmup.get("scheduled_total", 0) or 0) <= 0:
        _add_blocker(blockers, "warmup_schedule_missing", "medium")
        score -= 5
    if not warmup_maturity.get("allowed"):
        _add_blocker(blockers, "warmup_maturity_not_verified", "medium", warmup_maturity.get("blockers", []))
        score -= 10
    if int(buyer_journey.get("campaign_preview_count", 0) or 0) <= 0:
        _add_blocker(blockers, "buyer_journey_campaign_preview_missing", "medium")
        score -= 5
    if int(campaigns.get("ready_candidate_count", 0) or 0) <= 0:
        _add_blocker(blockers, "campaign_preview_pipeline_empty", "medium")
        score -= 5
    if policy_score.get("decision") != "NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW":
        _add_blocker(blockers, "mailer_policy_score_not_ready", "high", policy_score.get("decision"))
        score -= 15
    if transport.get("allowed"):
        _add_blocker(blockers, "transport_gate_unexpectedly_allows_live_send", "critical")
        score -= 50
    if not settings.outreach_paused or not settings.outreach_dry_run or settings.first_live_send_flag:
        _add_blocker(blockers, "live_outreach_flags_not_blocked", "critical", settings_evidence)
        score -= 50

    score = max(0, min(100, score))
    evidence = {
        "settings": settings_evidence,
        "checkout": checkout,
        "mail": mail,
        "visual": visual,
        "warmup": warmup,
        "warmup_maturity": warmup_maturity,
        "campaigns": {
            "candidate_count": campaigns.get("candidate_count", 0),
            "ready_candidate_count": campaigns.get("ready_candidate_count", 0),
            "segment_count": campaigns.get("segment_count", 0),
        },
        "source_operator": {
            "candidate_count": source_operator.get("candidate_count", 0),
            "queued_or_running_count": len(source_operator.get("queued_or_running_runs") or []),
            "scanner_jobs": source_operator.get("scanner_jobs", {}),
        },
        "revenue_loop": {
            "launch_readiness_state": revenue.get("launch_readiness_state"),
            "audit_count": revenue.get("scanner", {}).get("audit_count", 0),
            "customer_count": revenue.get("customers", {}).get("customer_count", 0),
            "real_customer_count": revenue.get("customers", {}).get("real_customer_count", 0),
            "qa_customer_count": revenue.get("customers", {}).get("qa_customer_count", 0),
            "payment_count": revenue.get("customers", {}).get("payment_count", 0),
            "real_payment_count": revenue.get("customers", {}).get("real_payment_count", 0),
            "qa_payment_count": revenue.get("customers", {}).get("qa_payment_count", 0),
            "real_paid_revenue_usd": revenue.get("customers", {}).get("real_paid_revenue_usd", 0),
            "fix_request_count": revenue.get("customers", {}).get("fix_request_count", 0),
        },
        "buyer_journey": buyer_journey,
        "transport_gate": transport,
        "counts": {
            "live_outreach_sent": _count("SELECT count(*) FROM outreach_messages WHERE status = 'sent'"),
            "warmup_sent": _count("SELECT count(*) FROM warmup_schedule WHERE status = 'sent'"),
            "legacy_warmup_event_count": _count("SELECT count(*) FROM email_events WHERE event_type = 'warmup_sent'"),
            "mailer_action_queue": _count("SELECT count(*) FROM mailer_action_queue"),
            "mailer_send_ledger": _count("SELECT count(*) FROM mailer_send_ledger"),
        },
    }
    state = _state(score, blockers, evidence)
    if state == "LIVE_OUTREACH_READY" and blockers:
        state = "NOT_LAUNCH_READY"

    return json_safe(
        {
            "state": state,
            "score": score,
            "blockers": blockers,
            "blocker_count": len(blockers),
            "evidence": evidence,
            "next_action": "clear_blockers_and_continue_no_send_daily_loop" if blockers else "continue_preview_pipeline_and_wait_for_explicit_launch_approval",
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": state == "LIVE_OUTREACH_READY",
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
