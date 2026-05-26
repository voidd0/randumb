from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all, fetch_one
from .p0 import json_safe


def _customer_lookup(customer_id: str | None = None, email: str | None = None, paddle_customer_id: str | None = None) -> dict[str, Any]:
    row = None
    if customer_id:
        row = fetch_one("SELECT * FROM customers WHERE id = %s", (customer_id,))
    elif paddle_customer_id:
        row = fetch_one("SELECT * FROM customers WHERE paddle_customer_id = %s", (paddle_customer_id,))
    elif email:
        row = fetch_one("SELECT * FROM customers WHERE lower(email) = lower(%s)", (email,))
    if not row:
        raise ValueError("customer_not_found")
    return dict(row)


def ensure_fix_codex_task(fix_request_id: str) -> dict[str, Any]:
    fix = fetch_one("SELECT * FROM fix_requests WHERE id = %s", (fix_request_id,))
    if not fix:
        raise ValueError("fix_request_not_found")
    if fix["codex_task_id"]:
        task = fetch_one("SELECT * FROM codex_tasks WHERE id = %s", (fix["codex_task_id"],))
        if task:
            return dict(task)
    task = execute(
        """
        INSERT INTO codex_tasks(type, priority, status, title, description, input_json)
        VALUES ('customer_fix_request', %s, 'open', %s, %s, %s)
        RETURNING *
        """,
        (
            fix["priority"],
            fix["title"],
            fix["description"] or "Customer paid fix request awaiting studio review.",
            Jsonb(
                {
                    "fix_request_id": str(fix["id"]),
                    "customer_id": str(fix["customer_id"]) if fix["customer_id"] else None,
                    "audit_id": str(fix["audit_id"]) if fix["audit_id"] else None,
                    "issue_id": str(fix["issue_id"]) if fix["issue_id"] else None,
                    "product_key": fix["product_key"],
                    "evidence": fix["evidence_json"],
                    "safety": "no customer website changes without review gate",
                }
            ),
        ),
    )
    execute("UPDATE fix_requests SET codex_task_id = %s, updated_at = now() WHERE id = %s", (task["id"], fix_request_id))
    return dict(task)


def customer_journey_snapshot(customer_id: str | None = None, email: str | None = None, paddle_customer_id: str | None = None) -> dict[str, Any]:
    customer = _customer_lookup(customer_id, email, paddle_customer_id)
    payments = [dict(row) for row in fetch_all("SELECT product_key, status, amount, currency, created_at FROM payments WHERE customer_id = %s ORDER BY created_at DESC", (customer["id"],))]
    subscriptions = [dict(row) for row in fetch_all("SELECT product_key, status, current_period_start, current_period_end, created_at FROM subscriptions WHERE customer_id = %s ORDER BY created_at DESC", (customer["id"],))]
    fix_requests = [dict(row) for row in fetch_all("SELECT * FROM fix_requests WHERE customer_id = %s ORDER BY created_at DESC", (customer["id"],))]
    enriched_fix_requests = []
    for fix in fix_requests:
        task = ensure_fix_codex_task(str(fix["id"]))
        enriched_fix_requests.append(
            {
                "id": str(fix["id"]),
                "product_key": fix["product_key"],
                "status": fix["status"],
                "priority": fix["priority"],
                "title": fix["title"],
                "codex_task_id": str(task["id"]),
                "codex_task_status": task["status"],
            }
        )
    onboarding = [dict(row) for row in fetch_all("SELECT product_key, status, task_type, title, created_at FROM onboarding_tasks WHERE customer_id = %s ORDER BY created_at DESC", (customer["id"],))]
    monitoring = [dict(row) for row in fetch_all("SELECT domain, site_url, status, last_checked_at, created_at FROM monitoring_targets WHERE customer_id = %s ORDER BY created_at DESC", (customer["id"],))]
    purchased = {"payments": payments, "subscriptions": subscriptions}
    status = "active_with_fix_queue" if enriched_fix_requests else ("active_with_onboarding" if onboarding else "active")
    result = json_safe(
        {
            "customer": {"id": str(customer["id"]), "email": customer["email"], "status": customer["status"]},
            "purchased": purchased,
            "fix_requests": enriched_fix_requests,
            "onboarding": onboarding,
            "monitoring": monitoring,
            "dashboard_ready": True,
        }
    )
    row = execute(
        """
        INSERT INTO customer_journey_snapshots(
          customer_id, status, purchased_products_json, fix_requests_json,
          onboarding_json, monitoring_json, result_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            customer["id"],
            status,
            Jsonb(json_safe(purchased)),
            Jsonb(json_safe(enriched_fix_requests)),
            Jsonb(json_safe(onboarding)),
            Jsonb(json_safe(monitoring)),
            Jsonb(result),
        ),
    )
    payload = dict(row)
    payload["result_json"] = result
    return payload
