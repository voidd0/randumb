from __future__ import annotations

from collections import defaultdict
from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all
from .p0 import email_provider, recipient_hash


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
