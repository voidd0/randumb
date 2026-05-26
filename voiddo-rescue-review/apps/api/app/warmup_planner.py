from __future__ import annotations

from collections import defaultdict
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import email_provider, latest_mail_qa_decision, mail_signal_summary, recipient_hash, run_mail_qa


def _adjacent_same(providers: list[str]) -> int:
    return sum(1 for index in range(1, len(providers)) if providers[index] == providers[index - 1])


def _interleave_by_provider(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[email_provider(row["recipient_email"])].append(row)
    ordered: list[dict[str, Any]] = []
    last_provider = ""
    while any(groups.values()):
        candidates = sorted(
            [(provider, items) for provider, items in groups.items() if items],
            key=lambda item: (item[0] == last_provider, -len(item[1]), item[0]),
        )
        provider, items = candidates[0]
        ordered.append(items.pop(0))
        last_provider = provider
    return ordered


def plan_provider_spaced_warmup(limit: int = 50, apply: bool = False) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, recipient_email, sender_mailbox, day_number, scheduled_for
        FROM warmup_schedule
        WHERE status = 'scheduled' AND scheduled_for > now()
        ORDER BY scheduled_for
        LIMIT %s
        """,
        (limit,),
    )
    providers = [email_provider(row["recipient_email"]) for row in rows]
    current_adjacent = _adjacent_same(providers)
    times = [row["scheduled_for"] for row in rows]
    proposed_rows = _interleave_by_provider([dict(row) for row in rows])
    proposed_providers = [email_provider(row["recipient_email"]) for row in proposed_rows]
    proposed_adjacent = _adjacent_same(proposed_providers)
    issues: list[dict[str, Any]] = []
    if not rows:
        issues.append({"code": "no_future_scheduled_warmup", "severity": "medium"})
    if proposed_adjacent:
        issues.append({"code": "provider_spacing_not_fully_solved", "severity": "medium", "count": proposed_adjacent})
    proposed = []
    for index, row in enumerate(proposed_rows):
        proposed.append(
            {
                "schedule_id": str(row["id"]),
                "recipient_hash": recipient_hash(row["recipient_email"]),
                "provider": email_provider(row["recipient_email"]),
                "sender_mailbox": row["sender_mailbox"],
                "old_scheduled_for": str(row["scheduled_for"]),
                "new_scheduled_for": str(times[index]) if index < len(times) else str(row["scheduled_for"]),
            }
        )
    can_apply = bool(apply and rows and proposed_adjacent <= current_adjacent)
    if can_apply:
        for index, row in enumerate(proposed_rows):
            execute(
                """
                UPDATE warmup_schedule
                SET scheduled_for = %s,
                    result_json = jsonb_set(result_json, '{p11_provider_spacing}', %s::jsonb, true),
                    updated_at = now()
                WHERE id = %s
                """,
                (times[index], Jsonb({"repair": "provider_spacing", "recipient_hash": recipient_hash(row["recipient_email"])}), row["id"]),
            )
    status = "applied" if can_apply else ("planned" if rows else "empty")
    row = execute(
        """
        INSERT INTO warmup_schedule_repairs(
          status, applied, inspected_count, current_adjacent_same_provider,
          proposed_adjacent_same_provider, issues_json, proposed_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            status,
            can_apply,
            len(rows),
            current_adjacent,
            proposed_adjacent,
            Jsonb(issues),
            Jsonb({"entries": proposed, "policy": "no_send_provider_spacing_repair"}),
        ),
    )
    return dict(row)


def apply_provider_spacing_when_safe(limit: int = 50) -> dict[str, Any]:
    signals = mail_signal_summary(24)
    issues: list[dict[str, Any]] = []
    if signals["bounce_or_dsn_count"] or signals["rate_limit_count"] or signals["spam_signal_count"]:
        issues.append({"code": "recent_mail_signals", "severity": "high", "signals": signals})
    mail_qa = latest_mail_qa_decision()
    if mail_qa != "PASS" and not issues:
        mail_qa = run_mail_qa(allow_deliverability_send=False)["decision"]
    if mail_qa != "PASS":
        issues.append({"code": "mail_qa_not_pass", "severity": "high", "decision": mail_qa})
    due = fetch_one("SELECT count(*) AS count FROM warmup_schedule WHERE status = 'scheduled' AND scheduled_for <= now()")
    due_count = int(due["count"]) if due else 0
    if due_count:
        issues.append({"code": "due_warmup_rows_present", "severity": "high", "count": due_count})
    if issues:
        row = execute(
            """
            INSERT INTO warmup_schedule_repairs(
              status, applied, inspected_count, current_adjacent_same_provider,
              proposed_adjacent_same_provider, issues_json, proposed_json
            )
            VALUES ('blocked_safety_gate', false, 0, 0, 0, %s, %s)
            RETURNING *
            """,
            (Jsonb(issues), Jsonb({"policy": "no_send_provider_spacing_application", "signals": signals, "mail_qa_decision": mail_qa, "due_now": due_count})),
        )
        return dict(row)
    plan = plan_provider_spaced_warmup(limit=limit, apply=False)
    if plan["inspected_count"] <= 0 or plan["proposed_adjacent_same_provider"] > plan["current_adjacent_same_provider"]:
        execute("UPDATE warmup_schedule_repairs SET status = 'blocked_no_safe_improvement' WHERE id = %s", (plan["id"],))
        plan["status"] = "blocked_no_safe_improvement"
        return plan
    entries = plan["proposed_json"].get("entries", [])
    for entry in entries:
        execute(
            """
            UPDATE warmup_schedule
            SET scheduled_for = %s::timestamptz,
                result_json = jsonb_set(result_json, '{p12_spacing_repair}', %s::jsonb, true),
                updated_at = now()
            WHERE id = %s AND status = 'scheduled'
            """,
            (entry["new_scheduled_for"], Jsonb({"repair_id": str(plan["id"]), "old_scheduled_for": entry["old_scheduled_for"], "recipient_hash": entry["recipient_hash"]}), entry["schedule_id"]),
        )
    updated = execute(
        """
        UPDATE warmup_schedule_repairs
        SET status = 'applied_safe_gate', applied = true,
            proposed_json = jsonb_set(proposed_json, '{application}', %s::jsonb, true)
        WHERE id = %s
        RETURNING *
        """,
        (Jsonb({"mail_qa_decision": mail_qa, "signals": signals, "sends_started": False, "rollback_ready": True}), plan["id"]),
    )
    return dict(updated)


def rollback_latest_spacing_repair() -> dict[str, Any]:
    repair = fetch_one(
        """
        SELECT *
        FROM warmup_schedule_repairs
        WHERE applied = true AND status = 'applied_safe_gate'
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    if not repair:
        row = execute(
            """
            INSERT INTO warmup_schedule_rollbacks(status, restored_count, skipped_count, rollback_json)
            VALUES ('nothing_to_rollback', 0, 0, %s)
            RETURNING *
            """,
            (Jsonb({"reason": "no_applied_spacing_repair"}),),
        )
        return dict(row)
    restored = 0
    skipped = 0
    entries = repair["proposed_json"].get("entries", [])
    for entry in entries:
        result = execute(
            """
            UPDATE warmup_schedule
            SET scheduled_for = %s::timestamptz,
                result_json = result_json - 'p12_spacing_repair',
                updated_at = now()
            WHERE id = %s AND status = 'scheduled'
            RETURNING id
            """,
            (entry["old_scheduled_for"], entry["schedule_id"]),
        )
        if result:
            restored += 1
        else:
            skipped += 1
    execute("UPDATE warmup_schedule_repairs SET status = 'rolled_back', applied = false WHERE id = %s", (repair["id"],))
    row = execute(
        """
        INSERT INTO warmup_schedule_rollbacks(repair_id, status, restored_count, skipped_count, rollback_json)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
        """,
        (repair["id"], "rolled_back", restored, skipped, Jsonb({"entries": len(entries), "sends_started": False})),
    )
    return dict(row)
