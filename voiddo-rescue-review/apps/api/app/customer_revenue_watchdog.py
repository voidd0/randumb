from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .customer_journey import customer_journey_snapshot
from .db import execute, fetch_all
from .monitoring import ensure_monitoring_target
from .p0 import json_safe
from .revenue_loop import prepare_customer_lifecycle


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _customer_candidates(limit: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT c.id AS customer_id, c.business_id,
               count(DISTINCT p.id) AS payment_count,
               count(DISTINCT s.id) AS subscription_count,
               count(DISTINCT f.id) AS fix_request_count,
               count(DISTINCT o.id) AS onboarding_count,
               count(DISTINCT mt.id) AS monitoring_target_count,
               bool_or(f.codex_task_id IS NULL) FILTER (WHERE f.id IS NOT NULL) AS has_fix_without_task,
               b.website_url
        FROM customers c
        LEFT JOIN payments p ON p.customer_id = c.id
        LEFT JOIN subscriptions s ON s.customer_id = c.id
        LEFT JOIN fix_requests f ON f.customer_id = c.id
        LEFT JOIN onboarding_tasks o ON o.customer_id = c.id
        LEFT JOIN monitoring_targets mt ON mt.customer_id = c.id
        LEFT JOIN businesses b ON b.id = c.business_id
        WHERE EXISTS (SELECT 1 FROM payments p2 WHERE p2.customer_id = c.id AND p2.status = 'paid')
           OR EXISTS (SELECT 1 FROM subscriptions s2 WHERE s2.customer_id = c.id AND s2.status NOT IN ('canceled', 'cancelled'))
        GROUP BY c.id, c.business_id, b.website_url, c.created_at
        ORDER BY c.created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 25), 100)),),
    )
    return [dict(row) for row in rows]


def run_paid_customer_watchdog(limit: int = 25, repair: bool = True) -> dict[str, Any]:
    candidates = _customer_candidates(limit)
    repaired = 0
    blockers: list[str] = []
    customers: list[dict[str, Any]] = []
    lifecycle = prepare_customer_lifecycle(limit, dry_run=not repair)
    for row in candidates:
        customer_id = str(row["customer_id"])
        before_missing = []
        if int(row["onboarding_count"] or 0) <= 0:
            before_missing.append("onboarding")
        if int(row["fix_request_count"] or 0) > 0 and bool(row["has_fix_without_task"]):
            before_missing.append("fix_codex_task")
        if row.get("website_url") and int(row["monitoring_target_count"] or 0) <= 0:
            before_missing.append("monitoring_target")
        journey = customer_journey_snapshot(customer_id=customer_id)
        monitoring_created = False
        if repair and row.get("website_url"):
            ensure_monitoring_target(customer_id, str(row["website_url"]))
            monitoring_created = True
        if before_missing or monitoring_created:
            repaired += 1
        refreshed = customer_journey_snapshot(customer_id=customer_id)
        dashboard_ready = bool((refreshed.get("result_json") or {}).get("dashboard_ready"))
        if not dashboard_ready:
            blockers.append("customer_dashboard_not_ready")
        customers.append(
            {
                "customer_id": customer_id,
                "payment_count": int(row["payment_count"] or 0),
                "subscription_count": int(row["subscription_count"] or 0),
                "fix_request_count": int(row["fix_request_count"] or 0),
                "missing_before": before_missing,
                "dashboard_ready": dashboard_ready,
                "journey_snapshot_id": str(refreshed.get("id", "")),
                "email_included": False,
            }
        )
    decision = "CUSTOMER_REVENUE_LOOP_READY" if not blockers else "BLOCKED"
    result = json_safe(
        {
            "status": "ready" if not blockers else "blocked",
            "decision": decision,
            "checked_customer_count": len(candidates),
            "repaired_customer_count": repaired,
            "blockers": sorted(set(blockers)),
            "customers": customers,
            "lifecycle": lifecycle,
            **SAFE_FLAGS,
        }
    )
    run = execute(
        """
        INSERT INTO paid_customer_watchdog_runs(
          status, decision, checked_customer_count, repaired_customer_count,
          blocker_count, result_json, send_mail, smtp_called,
          live_outreach_allowed, raw_recipient_addresses_included, secrets_included
        )
        VALUES (%s, %s, %s, %s, %s, %s, false, false, false, false, false)
        RETURNING id, status, decision, checked_customer_count, repaired_customer_count,
                  blocker_count, created_at
        """,
        (result["status"], decision, len(candidates), repaired, len(set(blockers)), Jsonb(result)),
    )
    return json_safe({"run": dict(run), "result": result, **SAFE_FLAGS})


def latest_paid_customer_watchdog_runs(limit: int = 10) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, status, decision, checked_customer_count, repaired_customer_count,
               blocker_count, send_mail, smtp_called, live_outreach_allowed,
               raw_recipient_addresses_included, secrets_included, created_at
        FROM paid_customer_watchdog_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 50)),),
    )
    return json_safe({"count": len(rows), "runs": [dict(row) for row in rows], **SAFE_FLAGS})
