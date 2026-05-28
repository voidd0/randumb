from __future__ import annotations

from typing import Any

from .billing import checkout_config_status
from .campaign_control import campaign_readiness_snapshot
from .customer_journey import customer_journey_snapshot, ensure_fix_codex_task
from .config import get_settings
from .db import fetch_all, fetch_one
from .mailer_action_queue import enqueue_mailer_action, mailer_action_queue_summary
from .monitoring import ensure_monitoring_target
from .p0 import json_safe, latest_mail_qa_decision, launch_readiness_state, mail_signal_summary
from .scouts import prepare_campaign_gated, queue_ready_scout_source_runs, ready_scout_source_queue_candidates


def _count(sql: str, params: tuple = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"]) if row else 0


def _status_counts(table: str, column: str = "status") -> dict[str, int]:
    rows = fetch_all(f"SELECT {column} AS status, count(*) AS count FROM {table} GROUP BY {column} ORDER BY {column}")
    return {str(row["status"] or "unknown"): int(row["count"]) for row in rows}


def _qa_customer_predicate(alias: str = "c") -> str:
    return (
        f"(lower({alias}.email) LIKE '%%@voiddorescue.local' "
        f"OR lower({alias}.email) LIKE '%%@example.test' "
        f"OR {alias}.paddle_customer_id LIKE 'ctm_p%%' "
        f"OR {alias}.paddle_customer_id LIKE 'ctm_onboard_%%')"
    )


def _real_customer_predicate(alias: str = "c") -> str:
    return f"NOT {_qa_customer_predicate(alias)}"


def _amount(sql: str, params: tuple = ()) -> float:
    row = fetch_one(sql, params)
    return float(row["amount"] or 0) if row else 0.0


def _latest_campaign_readiness(limit: int = 5) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT DISTINCT ON (campaign_id)
               campaign_id, status, lead_count, qualified_count, min_audit_strength,
               economics_decision, mail_safety_decision, visual_safety_decision, blockers_json, created_at
        FROM campaign_readiness_snapshots
        ORDER BY campaign_id, created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [
        {
            "campaign_id": str(row["campaign_id"]),
            "status": row["status"],
            "lead_count": int(row["lead_count"] or 0),
            "qualified_count": int(row["qualified_count"] or 0),
            "min_audit_strength": int(row["min_audit_strength"] or 0),
            "economics_decision": row["economics_decision"],
            "mail_safety_decision": row["mail_safety_decision"],
            "visual_safety_decision": row["visual_safety_decision"],
            "blocker_count": len(row["blockers_json"] or []),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _customer_lifecycle_candidates(limit: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        f"""
        SELECT c.id, c.business_id,
               {_qa_customer_predicate('c')} AS is_qa_customer,
               count(DISTINCT p.id) AS payment_count,
               count(DISTINCT s.id) AS subscription_count,
               count(DISTINCT f.id) AS fix_request_count,
               count(DISTINCT o.id) AS onboarding_count,
               count(DISTINCT mt.id) AS monitoring_target_count
        FROM customers c
        LEFT JOIN payments p ON p.customer_id = c.id
        LEFT JOIN subscriptions s ON s.customer_id = c.id
        LEFT JOIN fix_requests f ON f.customer_id = c.id
        LEFT JOIN onboarding_tasks o ON o.customer_id = c.id
        LEFT JOIN monitoring_targets mt ON mt.customer_id = c.id
        WHERE EXISTS (SELECT 1 FROM payments p2 WHERE p2.customer_id = c.id)
           OR EXISTS (SELECT 1 FROM subscriptions s2 WHERE s2.customer_id = c.id)
           OR EXISTS (SELECT 1 FROM fix_requests f2 WHERE f2.customer_id = c.id)
        GROUP BY c.id, c.business_id, c.email, c.paddle_customer_id, c.created_at
        ORDER BY c.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [
        {
            "customer_id": str(row["id"]),
            "business_id": str(row["business_id"]) if row["business_id"] else None,
            "customer_is_qa": bool(row["is_qa_customer"]),
            "payment_count": int(row["payment_count"] or 0),
            "subscription_count": int(row["subscription_count"] or 0),
            "fix_request_count": int(row["fix_request_count"] or 0),
            "onboarding_count": int(row["onboarding_count"] or 0),
            "monitoring_target_count": int(row["monitoring_target_count"] or 0),
        }
        for row in rows
    ]


def _queue_customer_lifecycle_action(action_type: str, customer_id: str, template_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    safe_payload = {
        "action_type": action_type,
        "risk_level": "SAFE_AUTO",
        "mailbox": "support@voiddorescue.com",
        "template_key": template_key,
        "customer_id": customer_id,
        **payload,
        "source": "revenue_loop",
    }
    return enqueue_mailer_action(safe_payload)


def prepare_customer_lifecycle(limit: int = 25, dry_run: bool = True) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    candidates = _customer_lifecycle_candidates(safe_limit)
    prepared: list[dict[str, Any]] = []
    if dry_run:
        return {
            "status": "preview_only",
            "candidate_count": len(candidates),
            "customers": candidates,
            "journey_snapshots_created": 0,
            "codex_tasks_created_or_confirmed": 0,
            "monitoring_targets_created_or_confirmed": 0,
            "mailer_actions_queued_or_confirmed": 0,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }

    journey_count = 0
    task_count = 0
    monitoring_count = 0
    action_count = 0
    for customer in candidates:
        customer_id = customer["customer_id"]
        journey = customer_journey_snapshot(customer_id=customer_id)
        journey_count += 1
        business = fetch_one("SELECT website_url FROM businesses WHERE id = %s", (customer.get("business_id"),)) if customer.get("business_id") else None
        if business and business.get("website_url"):
            ensure_monitoring_target(customer_id, str(business["website_url"]))
            monitoring_count += 1
        payments = fetch_all("SELECT paddle_transaction_id, product_key FROM payments WHERE customer_id = %s ORDER BY created_at DESC", (customer_id,))
        subscriptions = fetch_all("SELECT paddle_subscription_id, product_key FROM subscriptions WHERE customer_id = %s ORDER BY created_at DESC", (customer_id,))
        fixes = fetch_all("SELECT id, product_key FROM fix_requests WHERE customer_id = %s ORDER BY created_at DESC", (customer_id,))
        for payment in payments:
            action = _queue_customer_lifecycle_action(
                "customer_onboarding",
                customer_id,
                "payment_onboarding",
                {
                    "source_event": "revenue_loop.payment",
                    "paddle_transaction_id": payment["paddle_transaction_id"],
                    "product_key": payment["product_key"],
                    "mode": "lifecycle_recovery",
                    "customer_is_qa": customer["customer_is_qa"],
                },
            )
            action_count += 1
        for subscription in subscriptions:
            action = _queue_customer_lifecycle_action(
                "customer_onboarding",
                customer_id,
                "payment_onboarding",
                {
                    "source_event": "revenue_loop.subscription",
                    "paddle_subscription_id": subscription["paddle_subscription_id"],
                    "product_key": subscription["product_key"],
                    "mode": "subscription_lifecycle",
                    "customer_is_qa": customer["customer_is_qa"],
                },
            )
            action_count += 1
        for fix in fixes:
            task = ensure_fix_codex_task(str(fix["id"]))
            task_count += 1
            action = _queue_customer_lifecycle_action(
                "fix_request_created",
                customer_id,
                "fix_request_created",
                {
                    "source_event": "revenue_loop.fix_request",
                    "fix_request_id": str(fix["id"]),
                    "product_key": fix["product_key"],
                    "customer_is_qa": customer["customer_is_qa"],
                },
            )
            action_count += 1
        prepared.append(
            {
                "customer_id": customer_id,
                "journey_snapshot_id": str(journey["id"]),
                "fix_request_count": customer["fix_request_count"],
                "dashboard_ready": True,
                "customer_email_included": False,
            }
        )
    return {
        "status": "prepared",
        "candidate_count": len(candidates),
        "customers": prepared,
        "journey_snapshots_created": journey_count,
        "codex_tasks_created_or_confirmed": task_count,
        "monitoring_targets_created_or_confirmed": monitoring_count,
        "mailer_actions_queued_or_confirmed": action_count,
        "send_mail": False,
        "smtp_called": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }


def _prepare_campaigns(limit: int, dry_run: bool) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id
        FROM campaigns
        WHERE status IN ('draft', 'preview_ready')
        ORDER BY updated_at DESC, created_at DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 10), 50)),),
    )
    if dry_run:
        return {"status": "preview_only", "campaign_count": len(rows), "prepared_count": 0, "readiness_count": 0, "campaigns": []}
    prepared = []
    readiness = []
    for row in rows:
        campaign_id = str(row["id"])
        prepared.append(prepare_campaign_gated(campaign_id, 70, 20))
        readiness.append(campaign_readiness_snapshot(campaign_id))
    return {
        "status": "prepared",
        "campaign_count": len(rows),
        "prepared_count": len(prepared),
        "readiness_count": len(readiness),
        "campaigns": [{"campaign_id": item["campaign_id"], "preview_count": item.get("preview_count", 0), "status": item.get("status", "unknown")} for item in prepared],
    }


def revenue_loop_snapshot(limit: int = 25) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    settings = get_settings()
    source_queue = ready_scout_source_queue_candidates(safe_limit)
    return json_safe(
        {
            "status": "snapshot",
            "launch_readiness_state": launch_readiness_state(),
            "checkout": checkout_config_status(settings),
            "mail": {
                "latest_mail_qa_decision": latest_mail_qa_decision(),
                "signals": mail_signal_summary(24),
                "queue": mailer_action_queue_summary(),
            },
            "scouts": {
                "source_queue_candidates": source_queue["candidate_count"],
                "source_queue_top_score": max([int(item["readiness"]["score"]) for item in source_queue["candidates"]] or [0]),
                "source_queue_send_mail": False,
                "scout_runs": _status_counts("scout_runs"),
                "scout_leads": _status_counts("scout_leads"),
            },
            "scanner": {
                "jobs": _status_counts("scanner_jobs"),
                "audits": _status_counts("audits"),
                "audit_count": _count("SELECT count(*) FROM audits"),
                "issue_count": _count("SELECT count(*) FROM audit_issues"),
                "screenshot_count": _count("SELECT count(*) FROM screenshots"),
            },
            "campaigns": {
                "campaigns": _status_counts("campaigns"),
                "campaign_leads": _status_counts("campaign_leads"),
                "latest_readiness": _latest_campaign_readiness(5),
            },
            "customers": {
                "customer_count": _count("SELECT count(*) FROM customers"),
                "real_customer_count": _count(f"SELECT count(*) FROM customers c WHERE {_real_customer_predicate('c')}"),
                "qa_customer_count": _count(f"SELECT count(*) FROM customers c WHERE {_qa_customer_predicate('c')}"),
                "payment_count": _count("SELECT count(*) FROM payments"),
                "real_payment_count": _count(f"SELECT count(*) FROM payments p JOIN customers c ON c.id = p.customer_id WHERE {_real_customer_predicate('c')}"),
                "qa_payment_count": _count(f"SELECT count(*) FROM payments p JOIN customers c ON c.id = p.customer_id WHERE {_qa_customer_predicate('c')}"),
                "real_paid_revenue_usd": _amount(f"SELECT COALESCE(sum(p.amount), 0) AS amount FROM payments p JOIN customers c ON c.id = p.customer_id WHERE p.status = 'paid' AND p.currency = 'USD' AND {_real_customer_predicate('c')}"),
                "qa_paid_revenue_usd": _amount(f"SELECT COALESCE(sum(p.amount), 0) AS amount FROM payments p JOIN customers c ON c.id = p.customer_id WHERE p.status = 'paid' AND p.currency = 'USD' AND {_qa_customer_predicate('c')}"),
                "subscription_count": _count("SELECT count(*) FROM subscriptions"),
                "fix_request_count": _count("SELECT count(*) FROM fix_requests"),
                "open_fix_request_count": _count("SELECT count(*) FROM fix_requests WHERE status IN ('new', 'open', 'queued')"),
                "onboarding_task_count": _count("SELECT count(*) FROM onboarding_tasks"),
                "monitoring_target_count": _count("SELECT count(*) FROM monitoring_targets"),
                "journey_snapshot_count": _count("SELECT count(*) FROM customer_journey_snapshots"),
                "lifecycle_candidate_count": len(_customer_lifecycle_candidates(safe_limit)),
            },
            "safety": {
                "send_mail": False,
                "smtp_called": False,
                "live_outreach_allowed": False,
                "raw_recipient_addresses_included": False,
                "secrets_included": False,
                "cold_outreach_enabled": False,
            },
        }
    )


def prepare_revenue_loop(
    limit: int = 25,
    dry_run: bool = True,
    activate_sources: bool = False,
    source_id: str | None = None,
    allow_bulk_source_activation: bool = False,
    prepare_campaigns: bool = True,
    prepare_customers: bool = True,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 25), 100))
    blockers: list[str] = []
    source_queue = {"status": "skipped", "queued_count": 0, "created_scanner_jobs": 0}
    if activate_sources and not source_id and not allow_bulk_source_activation:
        blockers.append("source_activation_requires_explicit_source_id")
    else:
        source_queue = queue_ready_scout_source_runs(safe_limit, dry_run=(dry_run or not activate_sources), source_id=source_id)

    campaigns = _prepare_campaigns(min(safe_limit, 20), dry_run=dry_run or not prepare_campaigns) if prepare_campaigns else {"status": "skipped"}
    customers = prepare_customer_lifecycle(safe_limit, dry_run=dry_run or not prepare_customers) if prepare_customers else {"status": "skipped"}
    snapshot = revenue_loop_snapshot(safe_limit)
    status = "blocked" if blockers else ("preview_only" if dry_run else "prepared")
    return json_safe(
        {
            "status": status,
            "dry_run": dry_run,
            "blockers": blockers,
            "source_queue": source_queue,
            "campaigns": campaigns,
            "customers": customers,
            "snapshot": snapshot,
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )
