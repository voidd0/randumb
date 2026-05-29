from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import fetch_all, fetch_one


RAW_EMAIL_REGEX = r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"


def _count(query: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(query, params)
    return int(row["count"] or 0) if row else 0


def _report_dir() -> Path:
    preferred = Path("/opt/voiddo-rescue/reports")
    if preferred.exists():
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    fallback = Path("/app/storage/reports")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def mail_send_compliance_snapshot(window_hours: int = 24) -> dict[str, Any]:
    """Verify outgoing mail cannot bypass unsubscribe, logging, and safety records.

    This is intentionally a read-only audit. It does not send mail and does not
    expose raw recipients in its result or report.
    """
    hours = max(1, min(int(window_hours or 24), 168))
    outreach_sent = _count("SELECT count(*) AS count FROM outreach_messages WHERE status = 'sent'")
    warmup_sent = _count("SELECT count(*) AS count FROM warmup_schedule WHERE status = 'sent'")
    customer_sent = _count("SELECT count(*) AS count FROM mailer_send_ledger WHERE status = 'sent'")
    diagnostic_sent = _count("SELECT count(*) AS count FROM email_events WHERE event_type = 'deliverability_diagnostic_sent'")

    checks = {
        "outreach_sent_without_event": _count(
            """
            SELECT count(*) AS count
            FROM outreach_messages om
            WHERE om.status = 'sent'
              AND NOT EXISTS (
                SELECT 1 FROM email_events ee
                WHERE ee.outreach_message_id = om.id
                  AND ee.event_type = 'outreach_sent'
              )
            """
        ),
        "outreach_sent_missing_signed_unsubscribe": _count(
            """
            SELECT count(*) AS count
            FROM outreach_messages
            WHERE status = 'sent'
              AND body NOT LIKE '%%/unsubscribe/u_%%'
            """
        ),
        "outreach_sent_event_missing_one_click_headers": _count(
            """
            SELECT count(*) AS count
            FROM email_events
            WHERE event_type = 'outreach_sent'
              AND (
                COALESCE(payload_json->>'unsubscribe_one_click_ready', 'false') != 'true'
                OR COALESCE(payload_json->>'list_unsubscribe_header', 'false') != 'true'
              )
            """
        ),
        "warmup_sent_without_message_id": _count(
            """
            SELECT count(*) AS count
            FROM warmup_schedule
            WHERE status = 'sent'
              AND COALESCE(result_json->>'message_id', '') = ''
            """
        ),
        "warmup_sent_without_event": _count(
            """
            SELECT count(*) AS count
            FROM warmup_schedule ws
            WHERE ws.status = 'sent'
              AND NOT EXISTS (
                SELECT 1 FROM email_events ee
                WHERE ee.event_type = 'warmup_sent'
                  AND ee.message_id = ws.result_json->>'message_id'
              )
            """
        ),
        "customer_mail_sent_without_ledger": _count(
            """
            SELECT count(*) AS count
            FROM mailer_action_queue maq
            WHERE maq.status = 'sent'
              AND NOT EXISTS (
                SELECT 1 FROM mailer_send_ledger msl
                WHERE msl.action_id = maq.id
                  AND msl.status = 'sent'
              )
            """
        ),
        "customer_mail_ledger_sent_without_provider_message_id": _count(
            """
            SELECT count(*) AS count
            FROM mailer_send_ledger
            WHERE status = 'sent'
              AND COALESCE(result_json->>'provider_message_id', '') = ''
            """
        ),
        "recent_outgoing_event_payload_raw_email": _count(
            """
            SELECT count(*) AS count
            FROM email_events
            WHERE event_type = ANY(%s)
              AND created_at >= now() - (%s || ' hours')::interval
              AND (
                COALESCE(payload_json->>'raw_recipient_included', 'false') = 'true'
                OR COALESCE(payload_json->>'raw_recipient_addresses_included', 'false') = 'true'
                OR EXISTS (
                  SELECT 1
                  FROM jsonb_each_text(payload_json) AS payload(key, value)
                  WHERE payload.key ~* '(recipient|email|to)'
                    AND payload.key !~* '(hash|domain|message|sender|mailbox|provider)'
                    AND payload.value ~* %s
                )
              )
            """,
            (["outreach_sent", "warmup_sent", "deliverability_diagnostic_sent"], hours, RAW_EMAIL_REGEX),
        ),
        "recent_customer_ledger_payload_raw_email": _count(
            """
            SELECT count(*) AS count
            FROM mailer_send_ledger
            WHERE status = 'sent'
              AND created_at >= now() - (%s || ' hours')::interval
              AND (
                COALESCE(result_json->>'raw_recipient_included', 'false') = 'true'
                OR COALESCE(gate_result_json->>'raw_recipient_included', 'false') = 'true'
                OR EXISTS (
                  SELECT 1
                  FROM jsonb_each_text(result_json) AS payload(key, value)
                  WHERE payload.key ~* '(recipient|email|to)'
                    AND payload.key !~* '(hash|domain|message|sender|mailbox|provider)'
                    AND payload.value ~* %s
                )
                OR EXISTS (
                  SELECT 1
                  FROM jsonb_each_text(gate_result_json) AS payload(key, value)
                  WHERE payload.key ~* '(recipient|email|to)'
                    AND payload.key !~* '(hash|domain|message|sender|mailbox|provider)'
                    AND payload.value ~* %s
                )
              )
            """,
            (hours, RAW_EMAIL_REGEX, RAW_EMAIL_REGEX),
        ),
    }
    blocker_codes = [code for code, count in checks.items() if int(count or 0) > 0]
    decision = "PASS" if not blocker_codes else "FAIL_BLOCK_SEND"
    result = {
        "status": "PASS_MAIL_SEND_COMPLIANCE" if decision == "PASS" else "FAIL_MAIL_SEND_COMPLIANCE",
        "decision": decision,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": hours,
        "outgoing_totals": {
            "outreach_sent": outreach_sent,
            "warmup_sent": warmup_sent,
            "customer_mail_sent": customer_sent,
            "deliverability_diagnostic_sent": diagnostic_sent,
        },
        "checks": checks,
        "blocker_count": len(blocker_codes),
        "blockers": blocker_codes,
        "unsubscribe_policy": {
            "required_for": ["cold_or_sales_outreach"],
            "not_required_for": ["warmup_neutral", "deliverability_diagnostic", "transactional_customer_mail"],
            "one_click_required": True,
            "list_unsubscribe_headers_required": True,
        },
        "registration_policy": {
            "outreach": "outreach_messages + email_events.outreach_sent",
            "warmup": "warmup_schedule + email_events.warmup_sent",
            "deliverability_diagnostic": "email_events.deliverability_diagnostic_sent + mail_signals",
            "customer_mail": "mailer_action_queue + mailer_send_ledger",
        },
        "raw_recipient_addresses_included": False,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
    }
    return result


def write_mail_send_compliance_report(result: dict[str, Any] | None = None) -> str:
    result = result or mail_send_compliance_snapshot()
    path = _report_dir() / "mail_send_compliance_report.md"
    lines = [
        "# Vøiddo Rescue Mail Send Compliance",
        "",
        f"- generated_at: `{result['generated_at']}`",
        f"- decision: `{result['decision']}`",
        f"- status: `{result['status']}`",
        f"- blocker_count: `{result['blocker_count']}`",
        f"- raw_recipient_addresses_included: `{str(result['raw_recipient_addresses_included']).lower()}`",
        "",
        "## Outgoing Totals",
    ]
    for key, value in result["outgoing_totals"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Checks"])
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Policies", ""])
    lines.append("```json")
    lines.append(json.dumps({"unsubscribe_policy": result["unsubscribe_policy"], "registration_policy": result["registration_policy"]}, indent=2, ensure_ascii=False))
    lines.append("```")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def run_mail_send_compliance_agent(window_hours: int = 24, write_report: bool = True) -> dict[str, Any]:
    result = mail_send_compliance_snapshot(window_hours)
    if write_report:
        result["report_path"] = write_mail_send_compliance_report(result)
    return result
