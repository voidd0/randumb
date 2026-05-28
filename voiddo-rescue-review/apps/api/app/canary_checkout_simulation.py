from __future__ import annotations

import uuid
from typing import Any

from psycopg.types.json import Jsonb

from .canary_batch_quality import canary_batch_quality
from .customer_journey import customer_journey_snapshot
from .db import execute, fetch_one
from .p0 import handle_paddle_event, json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"] or 0) if row else 0


def _cleanup_canary_checkout_simulation(token: str) -> None:
    execute("DELETE FROM recipient_resolver_audit WHERE customer_id IN (SELECT id FROM customers WHERE paddle_customer_id = %s)", (f"ctm_canary_{token}",))
    execute("DELETE FROM mailer_action_queue WHERE payload_json::text LIKE %s OR payload_json->>'customer_id' IN (SELECT id::text FROM customers WHERE paddle_customer_id = %s)", (f"%{token}%", f"ctm_canary_{token}"))
    execute("DELETE FROM customer_journey_snapshots WHERE customer_id IN (SELECT id FROM customers WHERE paddle_customer_id = %s)", (f"ctm_canary_{token}",))
    execute("DELETE FROM customer_access_tokens WHERE customer_id IN (SELECT id FROM customers WHERE paddle_customer_id = %s)", (f"ctm_canary_{token}",))
    execute("DELETE FROM monitoring_targets WHERE customer_id IN (SELECT id FROM customers WHERE paddle_customer_id = %s)", (f"ctm_canary_{token}",))
    execute("DELETE FROM onboarding_tasks WHERE payload_json::text LIKE %s OR customer_id IN (SELECT id FROM customers WHERE paddle_customer_id = %s)", (f"%{token}%", f"ctm_canary_{token}"))
    execute("DELETE FROM fix_requests WHERE evidence_json::text LIKE %s OR customer_id IN (SELECT id FROM customers WHERE paddle_customer_id = %s)", (f"%{token}%", f"ctm_canary_{token}"))
    execute("DELETE FROM payments WHERE paddle_transaction_id = %s", (f"txn_canary_{token}",))
    execute("DELETE FROM customers WHERE paddle_customer_id = %s", (f"ctm_canary_{token}",))


def run_canary_checkout_simulation(cleanup_after: bool = True) -> dict[str, Any]:
    token = uuid.uuid4().hex[:10]
    quality = canary_batch_quality(1, store=False)
    items = quality.get("items") or []
    if not items:
        result = {"status": "blocked", "decision": "NO_CANARY_CANDIDATE", "blockers": ["no_canary_candidate"], **SAFE_FLAGS}
        execute(
            "INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at) VALUES ('canary_checkout_simulation_agent', 'blocked', %s, now(), now())",
            (Jsonb(result),),
        )
        return json_safe(result)

    item = items[0]
    audit_slug = item.get("audit_slug") or ""
    product_key = item.get("offer_key") or "contact_form_repair"
    _cleanup_canary_checkout_simulation(token)
    payment = handle_paddle_event(
        {
            "event_type": "transaction.paid",
            "data": {
                "id": f"txn_canary_{token}",
                "customer_id": f"ctm_canary_{token}",
                "customer": {"email": f"canary-buyer-{token}@voiddorescue.local"},
                "custom_data": {"product_key": product_key, "audit_slug": audit_slug, "source": "canary_checkout_simulation"},
                "details": {"totals": {"total": "9900", "currency_code": "USD"}},
            },
        },
        provisioning_paused=False,
    )
    customer = fetch_one("SELECT id, business_id FROM customers WHERE paddle_customer_id = %s", (f"ctm_canary_{token}",))
    customer_id = str(customer["id"]) if customer else ""
    journey = customer_journey_snapshot(customer_id=customer_id) if customer_id else {"result_json": {}}
    fix_count = _count("SELECT count(*) FROM fix_requests WHERE customer_id = %s", (customer_id,)) if customer_id else 0
    payment_count = _count("SELECT count(*) FROM payments WHERE paddle_transaction_id = %s", (f"txn_canary_{token}",))
    mailer_actions = _count("SELECT count(*) FROM mailer_action_queue WHERE payload_json::text LIKE %s", (f"%{token}%",))
    result = json_safe(
        {
            "status": "completed",
            "decision": "PASS_CANARY_CHECKOUT_SIMULATION" if customer and payment_count == 1 and fix_count >= 1 else "FAIL_CANARY_CHECKOUT_SIMULATION",
            "blockers": [] if customer and payment_count == 1 and fix_count >= 1 else ["checkout_simulation_state_incomplete"],
            "token_hash": token[:6],
            "source_audit_slug": audit_slug,
            "source_domain": item.get("domain"),
            "product_key": product_key,
            "paddle_actions": payment.get("actions", []),
            "customer_created": bool(customer),
            "audit_context_linked": bool(customer and customer.get("business_id")),
            "payment_count": payment_count,
            "fix_request_count": fix_count,
            "dashboard_ready": bool((journey.get("result_json") or {}).get("dashboard_ready")),
            "mailer_actions_queued": mailer_actions,
            "qa_artifacts_cleaned": bool(cleanup_after),
            **SAFE_FLAGS,
        }
    )
    if cleanup_after:
        _cleanup_canary_checkout_simulation(token)
    execute(
        "INSERT INTO agent_runs(agent, status, result_json, started_at, completed_at) VALUES ('canary_checkout_simulation_agent', %s, %s, now(), now())",
        ("completed" if result["decision"].startswith("PASS") else "blocked", Jsonb(result)),
    )
    return result
